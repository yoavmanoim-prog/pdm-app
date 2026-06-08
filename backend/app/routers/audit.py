import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models.document import Document
from app.models.commit import Commit, CommitFile
from app.models.revision import Revision
from app.models.audit import AuditEvent
from app.models.bom import BOMEntry

router = APIRouter(prefix="/repos", tags=["audit"])


# ── Step 31 — audit log endpoints ─────────────────────────────────────────────

@router.get("/{repo_id}/audit")
def get_audit_log(
    repo_id: uuid.UUID,
    actor: str | None = Query(None),
    action: str | None = Query(None),
    document_id: uuid.UUID | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AuditEvent).filter(AuditEvent.repository_id == repo_id)

    if actor:
        query = query.filter(AuditEvent.actor == actor)
    if action:
        query = query.filter(AuditEvent.action == action)
    if document_id:
        query = query.filter(AuditEvent.entity_id == str(document_id))
    if since:
        query = query.filter(AuditEvent.timestamp >= since)
    if until:
        query = query.filter(AuditEvent.timestamp <= until)

    events = query.order_by(desc(AuditEvent.timestamp)).limit(limit).all()

    return [
        {
            "id": str(e.id),
            "timestamp": e.timestamp.isoformat(),
            "actor": e.actor,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "details": e.details,
            "is_breach": e.is_breach,
        }
        for e in events
    ]


@router.get("/{repo_id}/audit/breaches")
def get_protocol_breaches(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns only audit events that were protocol violations."""
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.repository_id == repo_id, AuditEvent.is_breach.is_(True))
        .order_by(desc(AuditEvent.timestamp))
        .all()
    )
    return [
        {
            "id": str(e.id),
            "timestamp": e.timestamp.isoformat(),
            "actor": e.actor,
            "action": e.action,
            "entity_id": e.entity_id,
            "details": e.details,
        }
        for e in events
    ]


# ── Step 32 — revision history for a document ─────────────────────────────────

@router.get("/{repo_id}/documents/{doc_id}/history")
def get_document_history(repo_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Complete revision history for one document — every revision ever published,
    the commit it points to, who published it, and the change note.
    """
    doc = db.get(Document, doc_id)
    if not doc or doc.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Document not found")

    revisions = (
        db.query(Revision)
        .filter(Revision.document_id == doc_id)
        .order_by(Revision.published_at)
        .all()
    )

    history = []
    for rev in revisions:
        commit = db.get(Commit, rev.commit_id)
        commit_files = (
            db.query(CommitFile)
            .filter(CommitFile.commit_id == rev.commit_id, CommitFile.document_id == doc_id)
            .first()
        )
        history.append({
            "revision_code": rev.revision_code,
            "status": rev.status,
            "published_by": rev.published_by,
            "published_at": rev.published_at.isoformat() if rev.published_at else None,
            "change_note": rev.change_note,
            "commit_hash": commit.short_hash if commit else None,
            "commit_message": commit.message if commit else None,
            "s3_key_pdf": commit_files.s3_key_pdf if commit_files else None,
            "passed_protocol": rev.passed_protocol,
        })

    return {
        "document_id": str(doc_id),
        "part_number": doc.part_number,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "revisions": history,
    }


# ── Step 33 — product tree audit ──────────────────────────────────────────────

@router.get("/{repo_id}/audit/tree")
def get_tree_audit(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Audit summary for every document in the repository:
    last committed, by whom, current revision, and open branches affecting it.
    """
    docs = db.query(Document).filter(Document.repository_id == repo_id).all()
    result = []

    for doc in docs:
        # latest commit touching this document
        latest_cf = (
            db.query(CommitFile)
            .join(Commit)
            .filter(CommitFile.document_id == doc.id)
            .order_by(desc(Commit.timestamp))
            .first()
        )
        latest_commit = db.get(Commit, latest_cf.commit_id) if latest_cf else None

        # current released revision
        latest_rev = (
            db.query(Revision)
            .filter(Revision.document_id == doc.id, Revision.status == "released")
            .order_by(desc(Revision.published_at))
            .first()
        )

        # unpushed (local-only) commits for this document
        unpushed = (
            db.query(CommitFile)
            .join(Commit)
            .filter(
                CommitFile.document_id == doc.id,
                Commit.is_local.is_(True),
                Commit.branch_id.is_(None),
            )
            .count()
        )

        # BOM entry count (how many components if it's an assembly)
        bom_count = db.query(BOMEntry).filter(BOMEntry.assembly_id == doc.id).count()

        result.append({
            "document_id": str(doc.id),
            "part_number": doc.part_number,
            "title": doc.title,
            "doc_type": doc.doc_type,
            "last_commit_hash": latest_commit.short_hash if latest_commit else None,
            "last_commit_by": latest_commit.author if latest_commit else None,
            "last_commit_at": latest_commit.timestamp.isoformat() if latest_commit else None,
            "current_revision": latest_rev.revision_code if latest_rev else None,
            "revision_status": latest_rev.status if latest_rev else "unreleased",
            "unpushed_commits": unpushed,
            "bom_entries": bom_count,
        })

    return {"repository_id": str(repo_id), "documents": result}
