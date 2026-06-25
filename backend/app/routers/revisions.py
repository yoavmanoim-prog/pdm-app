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
from app.models.commit import Commit
from app.models.revision import Revision
from app.models.audit import AuditEvent
from app.protocol.engine import run_publish_checks

router = APIRouter(prefix="/repos", tags=["revisions"])


class PublishRequest(BaseModel):
    document_id: uuid.UUID
    commit_hash: str       # short hash of the commit being released
    revision_code: str     # "A", "B", "C" …
    # who published — now the authenticated user; optional for back-compat callers
    published_by: str | None = None
    change_note: str | None = None


# ── Step 30 — publish revision (remote vault only) ────────────────────────────

@router.post("/{repo_id}/revisions/publish")
def publish_revision(
    repo_id: uuid.UUID,
    body: PublishRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_privilege(APPROVE_RELEASE)),
):
    if settings.VAULT_MODE != "remote":
        raise HTTPException(status_code=403, detail="Revisions can only be published on the remote vault")
    publisher = current.full_name or current.email

    doc = db.get(Document, body.document_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")

    commit = db.query(Commit).filter(
        Commit.repository_id == repo_id,
        Commit.short_hash == body.commit_hash,
    ).first()
    if not commit:
        raise HTTPException(status_code=404, detail=f"Commit '{body.commit_hash}' not found")

    # run all protocol rules
    result = run_publish_checks(doc, body.revision_code, body.change_note, db)

    if not result["passed"]:
        db.add(AuditEvent(
            repository_id=repo_id,
            actor=publisher,
            action="publish_blocked",
            entity_type="document",
            entity_id=str(body.document_id),
            details={"revision_code": body.revision_code, "violations": result["violations"]},
            is_breach=True,
        ))
        db.commit()
        raise HTTPException(status_code=422, detail={
            "message": "Protocol check failed — revision not published",
            "violations": result["violations"],
        })

    # mark previous released revision as obsolete
    prev = db.query(Revision).filter(
        Revision.document_id == body.document_id,
        Revision.status == "released",
    ).first()
    if prev:
        prev.status = "obsolete"

    revision = Revision(
        document_id=body.document_id,
        commit_id=commit.id,
        revision_code=body.revision_code.upper(),
        status="released",
        published_by=publisher,
        published_at=datetime.utcnow(),
        change_note=body.change_note,
        passed_protocol=True,
        violations=[],
    )
    db.add(revision)

    db.add(AuditEvent(
        repository_id=repo_id,
        actor=publisher,
        action="publish",
        entity_type="document",
        entity_id=str(body.document_id),
        details={
            "revision_code": body.revision_code.upper(),
            "commit_hash": body.commit_hash,
            "change_note": body.change_note,
        },
        is_breach=False,
    ))

    db.commit()
    db.refresh(revision)

    return {
        "revision_id": str(revision.id),
        "document_id": str(body.document_id),
        "revision_code": revision.revision_code,
        "status": revision.status,
        "published_at": revision.published_at.isoformat(),
    }


# ── List and get revisions ─────────────────────────────────────────────────────

@router.get("/{repo_id}/revisions/")
def list_revisions(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    result = []
    for doc in docs:
        revs = db.query(Revision).filter(
            Revision.document_id == doc.id
        ).order_by(desc(Revision.published_at)).all()
        for r in revs:
            result.append({
                "document_id": str(doc.id),
                "part_number": doc.part_number,
                "revision_code": r.revision_code,
                "status": r.status,
                "published_by": r.published_by,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "change_note": r.change_note,
            })
    return result


@router.get("/{repo_id}/revisions/{rev_code}")
def get_revision(repo_id: uuid.UUID, rev_code: str, db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    for doc in docs:
        rev = db.query(Revision).filter(
            Revision.document_id == doc.id,
            Revision.revision_code == rev_code.upper(),
        ).first()
        if rev:
            return {
                "document_id": str(doc.id),
                "part_number": doc.part_number,
                "revision_code": rev.revision_code,
                "status": rev.status,
                "published_by": rev.published_by,
                "published_at": rev.published_at.isoformat() if rev.published_at else None,
                "change_note": rev.change_note,
            }
    raise HTTPException(status_code=404, detail=f"Revision {rev_code.upper()} not found")
