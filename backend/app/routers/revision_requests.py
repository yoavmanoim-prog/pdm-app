import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from app.authz import APPROVE_RELEASE, require_privilege
from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.document import Document
from app.models.commit import Commit, CommitFile
from app.models.revision import Revision
from app.models.revision_request import RevisionRequest
from app.models.audit import AuditEvent
from app.protocol.engine import run_publish_checks
from app.protocol.rules import first_revision, next_revision
from app.models.repository import Repository
from app.settings_config import effective_settings

router = APIRouter(prefix="/repos", tags=["revision-requests"])


def _require_remote():
    if settings.VAULT_MODE != "remote":
        raise HTTPException(status_code=403, detail="This endpoint is only available on the remote vault")


def _next_revision_code(document_id: uuid.UUID, db: Session) -> str:
    """Next revision code for a document, in the repo's scheme (letters or
    numbers): first release if none, else the next value in sequence."""
    doc = db.get(Document, document_id)
    repo = db.get(Repository, doc.repository_id) if doc else None
    scheme = effective_settings(repo)["revision_scheme"]

    latest = (
        db.query(Revision)
        .filter(Revision.document_id == document_id)
        .order_by(desc(Revision.published_at))
        .first()
    )
    if not latest:
        return first_revision(scheme)
    nxt = next_revision(scheme, latest.revision_code)
    if nxt is None:
        raise HTTPException(status_code=400, detail="Document has reached the last revision code")
    return nxt


class ReleaseRequestCreate(BaseModel):
    requested_by: str
    change_note: str | None = None


class ReleaseRequestDeny(BaseModel):
    # who reviewed — now taken from the authenticated user; kept optional so older
    # callers that still send it don't break.
    reviewed_by: str | None = None


class ReleaseRequestApprove(BaseModel):
    reviewed_by: str | None = None


@router.post("/{repo_id}/documents/{doc_id}/release-request", status_code=201)
def create_release_request(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID,
    body: ReleaseRequestCreate,
    db: Session = Depends(get_db),
):
    _require_remote()

    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # must have at least one commit on main
    has_commit = (
        db.query(CommitFile)
        .join(Commit)
        .filter(CommitFile.document_id == doc_id, Commit.branch_id.is_(None))
        .first()
    )
    if not has_commit:
        raise HTTPException(status_code=400, detail="Document has no committed drawing yet")

    # block duplicate pending requests
    existing = db.query(RevisionRequest).filter(
        RevisionRequest.document_id == doc_id,
        RevisionRequest.status == "pending",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A release request is already pending for this document")

    proposed_code = _next_revision_code(doc_id, db).upper()

    req = RevisionRequest(
        repository_id=repo_id,
        document_id=doc_id,
        proposed_revision_code=proposed_code,
        requested_by=body.requested_by,
        change_note=body.change_note,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "id": str(req.id),
        "document_id": str(doc_id),
        "part_number": doc.part_number,
        "title": doc.title,
        "proposed_revision_code": proposed_code,
        "requested_by": req.requested_by,
        "change_note": req.change_note,
        "status": req.status,
        "created_at": req.created_at.isoformat(),
    }


@router.get("/{repo_id}/release-requests")
def list_release_requests(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_remote()

    requests = (
        db.query(RevisionRequest)
        .filter(RevisionRequest.repository_id == repo_id)
        .order_by(RevisionRequest.created_at.desc())
        .all()
    )

    # bulk-fetch documents to avoid N+1
    doc_ids = {r.document_id for r in requests}
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()}

    result = []
    for r in requests:
        doc = docs.get(r.document_id)
        result.append({
            "id": str(r.id),
            "document_id": str(r.document_id),
            "part_number": doc.part_number if doc else None,
            "title": doc.title if doc else None,
            "doc_type": doc.doc_type if doc else None,
            "proposed_revision_code": r.proposed_revision_code,
            "requested_by": r.requested_by,
            "change_note": r.change_note,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        })
    return result


@router.post("/{repo_id}/release-requests/{req_id}/approve")
def approve_release_request(
    repo_id: uuid.UUID,
    req_id: uuid.UUID,
    body: ReleaseRequestApprove,
    db: Session = Depends(get_db),
    current: User = Depends(require_privilege(APPROVE_RELEASE)),
):
    _require_remote()
    reviewer = current.full_name or current.email   # sign-off is the logged-in user

    req = db.get(RevisionRequest, req_id)
    if not req or req.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Release request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request is already {req.status}")

    doc = db.get(Document, req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # get the latest commit on main for this document
    latest_cf = (
        db.query(CommitFile)
        .join(Commit)
        .filter(CommitFile.document_id == req.document_id, Commit.branch_id.is_(None))
        .order_by(desc(Commit.timestamp))
        .first()
    )
    if not latest_cf:
        raise HTTPException(status_code=400, detail="No committed drawing found")

    # run protocol checks
    result = run_publish_checks(doc, req.proposed_revision_code, req.change_note, db)
    if not result["passed"]:
        db.add(AuditEvent(
            repository_id=repo_id,
            actor=reviewer,
            action="publish_blocked",
            entity_type="document",
            entity_id=str(doc.id),
            details={"revision_code": req.proposed_revision_code, "violations": result["violations"]},
            is_breach=True,
        ))
        db.commit()
        raise HTTPException(status_code=422, detail={
            "message": "Protocol check failed — revision not published",
            "violations": result["violations"],
        })

    # mark previous released revision as obsolete
    prev = db.query(Revision).filter(
        Revision.document_id == req.document_id,
        Revision.status == "released",
    ).first()
    if prev:
        prev.status = "obsolete"

    revision = Revision(
        document_id=req.document_id,
        commit_id=latest_cf.commit_id,
        revision_code=req.proposed_revision_code,
        status="released",
        published_by=reviewer,
        published_at=datetime.utcnow(),
        change_note=req.change_note,
        passed_protocol=True,
        violations=[],
    )
    db.add(revision)

    req.status = "approved"
    req.reviewed_by = reviewer
    req.reviewed_at = datetime.utcnow()

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=reviewer,
        action="publish",
        entity_type="document",
        entity_id=str(doc.id),
        details={
            "revision_code": req.proposed_revision_code,
            "commit_hash": latest_cf.commit.short_hash,
            "change_note": req.change_note,
            "via_release_request": str(req_id),
        },
        is_breach=False,
    ))

    db.commit()
    db.refresh(revision)

    return {
        "revision_id": str(revision.id),
        "document_id": str(doc.id),
        "part_number": doc.part_number,
        "revision_code": revision.revision_code,
        "status": revision.status,
        "published_at": revision.published_at.isoformat(),
    }


@router.post("/{repo_id}/release-requests/{req_id}/deny")
def deny_release_request(
    repo_id: uuid.UUID,
    req_id: uuid.UUID,
    body: ReleaseRequestDeny,
    db: Session = Depends(get_db),
    current: User = Depends(require_privilege(APPROVE_RELEASE)),
):
    _require_remote()
    reviewer = current.full_name or current.email

    req = db.get(RevisionRequest, req_id)
    if not req or req.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Release request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request is already {req.status}")

    req.status = "denied"
    req.reviewed_by = reviewer
    req.reviewed_at = datetime.utcnow()

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=reviewer,
        action="release_denied",
        entity_type="document",
        entity_id=str(req.document_id),
        details={"proposed_revision_code": req.proposed_revision_code, "request_id": str(req_id)},
        is_breach=False,
    ))
    db.commit()

    return {"id": str(req.id), "status": "denied", "reviewed_by": req.reviewed_by}
