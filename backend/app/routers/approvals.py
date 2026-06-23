import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.authz import APPROVE_DRAWING, require_privilege
from app.database import get_db
from app.models.commit import Commit, CommitFile
from app.models.document import Document
from app.models.user import User
from app.security import get_current_user

router = APIRouter(prefix="/repos", tags=["approvals"])


def latest_unpushed_file(db: Session, repo_id: uuid.UUID, doc_id: uuid.UUID) -> CommitFile | None:
    """The most recent UNPUSHED (is_local) commit_file for a document — i.e. the
    drawing version that a push would send. This is what gets approved; a newer
    commit produces a newer row, so approval always tracks the version on deck."""
    return (
        db.query(CommitFile)
        .join(Commit, CommitFile.commit_id == Commit.id)
        .filter(
            Commit.repository_id == repo_id,
            Commit.is_local.is_(True),
            CommitFile.document_id == doc_id,
        )
        .order_by(Commit.timestamp.desc())
        .first()
    )


def stamp_approval(cf: CommitFile, user: User) -> None:
    """Sign off a drawing version in `user`'s name."""
    cf.approved_by = user.email
    cf.approved_by_id = user.id
    cf.approved_at = datetime.utcnow()


def _state(cf: CommitFile, doc: Document) -> dict:
    return {
        "document_id": str(doc.id),
        "part_number": doc.part_number,
        "title": doc.title,
        "approved": cf.approved_by_id is not None,
        "approved_by": cf.approved_by,
        "approved_at": cf.approved_at.isoformat() if cf.approved_at else None,
    }


@router.get("/{repo_id}/approvals")
def list_approvals(
    repo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Every drawing with unpushed changes + its approval state — drives the
    per-drawing Approve buttons and badges. One row per document (its head)."""
    rows = (
        db.query(CommitFile, Document)
        .join(Commit, CommitFile.commit_id == Commit.id)
        .join(Document, CommitFile.document_id == Document.id)
        .filter(Commit.repository_id == repo_id, Commit.is_local.is_(True))
        .order_by(Commit.timestamp.desc())
        .all()
    )
    seen: dict[uuid.UUID, dict] = {}
    for cf, doc in rows:
        if doc.id not in seen:  # first = latest (ordered desc)
            seen[doc.id] = _state(cf, doc)
    return list(seen.values())


@router.post("/{repo_id}/documents/{doc_id}/approve")
def approve_drawing(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_privilege(APPROVE_DRAWING)),
):
    """Sign off the drawing's current unpushed version in the approver's name."""
    cf = latest_unpushed_file(db, repo_id, doc_id)
    if cf is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No unpushed changes to approve for this drawing")
    stamp_approval(cf, current)
    db.commit()
    doc = db.get(Document, doc_id)
    return _state(cf, doc)


@router.delete("/{repo_id}/documents/{doc_id}/approve")
def unapprove_drawing(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_privilege(APPROVE_DRAWING)),
):
    """Withdraw approval from the drawing's current unpushed version."""
    cf = latest_unpushed_file(db, repo_id, doc_id)
    if cf is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No unpushed changes for this drawing")
    cf.approved_by = None
    cf.approved_by_id = None
    cf.approved_at = None
    db.commit()
    doc = db.get(Document, doc_id)
    return _state(cf, doc)
