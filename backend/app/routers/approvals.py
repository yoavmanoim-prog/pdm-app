import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import remote_auth
from app.authz import APPROVE_DRAWING, has_privilege
from app.config import settings
from app.database import get_db
from app.models.commit import Commit, CommitFile
from app.models.document import Document
from app.models.role import Role
from app.models.user import User
from app.security import get_current_user

router = APIRouter(prefix="/repos", tags=["approvals"])
# approvers (the people who CAN sign off) live in the user store, so this one is
# served by the remote and proxied by the local vault — hence its own router.
approvers_router = APIRouter(tags=["approvals"])

_bearer = HTTPBearer(auto_error=False)


def _token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str | None:
    return creds.credentials if creds else None


class ApprovalRequest(BaseModel):
    # who signed off. Omitted = approve as the current user (only allowed if they
    # hold approve_drawing). Set = credit a chosen approver picked from the
    # eligible list (how a non-privileged pusher records who approved a drawing).
    approver_id: uuid.UUID | None = None
    approver_name: str | None = None


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
    """Sign off a drawing version in `user`'s name (used for self-approval).
    Stores the display name, falling back to email if they have none."""
    cf.approved_by = user.full_name or user.email
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


@approvers_router.get("/approvers")
def list_approvers(
    db: Session = Depends(get_db),
    token: str = Depends(_token),
    current: User = Depends(get_current_user),
):
    """Users who hold approve_drawing — the choices a non-privileged user picks
    from when recording who signed off. Served by the remote (user store);
    proxied by the local vault."""
    if settings.VAULT_MODE != "remote":
        return remote_auth.remote_request("GET", "/approvers", token=token)
    approver_roles = [r.name for r in db.query(Role).all() if APPROVE_DRAWING in (r.privileges or [])]
    if not approver_roles:
        return []
    users = (
        db.query(User)
        .filter(User.role.in_(approver_roles), User.is_active.is_(True))
        .order_by(User.email)
        .all()
    )
    return [{"id": str(u.id), "email": u.email, "full_name": u.full_name} for u in users]


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
    body: ApprovalRequest | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Sign off the drawing's current unpushed version.

    - With no approver in the body, the CURRENT user signs off — but only if they
      hold approve_drawing.
    - With an approver chosen (by a non-privileged pusher), the approval is
      credited to that person. The remote re-validates on push that the named
      approver actually holds the privilege (anti-forgery)."""
    cf = latest_unpushed_file(db, repo_id, doc_id)
    if cf is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No unpushed changes to approve for this drawing")

    body = body or ApprovalRequest()
    if body.approver_id is not None:
        cf.approved_by_id = body.approver_id
        cf.approved_by = body.approver_name
        cf.approved_at = datetime.utcnow()
    elif has_privilege(current, APPROVE_DRAWING):
        stamp_approval(cf, current)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an approver — you don't hold the approve_drawing privilege",
        )
    db.commit()
    return _state(cf, db.get(Document, doc_id))


@router.delete("/{repo_id}/documents/{doc_id}/approve")
def unapprove_drawing(
    repo_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
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
    return _state(cf, db.get(Document, doc_id))
