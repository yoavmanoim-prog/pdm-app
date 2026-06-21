import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import remote_auth
from app.config import settings
from app.database import get_db
from app.models.user import User, ROLE_ADMIN
from app.schemas.users import AdminUserCreate, UserUpdate, UserResponse
from app.security import hash_password, require_admin

# every route here is admin-only: require_admin runs get_current_user first, then
# checks the role, so a member or anonymous caller never reaches the handler.
router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])

_bearer = HTTPBearer(auto_error=False)


def _authority() -> bool:
    """True on the remote vault (owns the user table). A local vault forwards
    every user operation to the remote so accounts live in one place."""
    return settings.VAULT_MODE == "remote"


def _token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str | None:
    """The caller's raw token, forwarded to the remote vault when proxying."""
    return creds.credentials if creds else None


def _active_admin_count(db: Session) -> int:
    """How many active admins remain — used to refuse changes that would lock
    everyone out of user management."""
    return db.query(User).filter(User.role == ROLE_ADMIN, User.is_active.is_(True)).count()


@router.get("", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), token: str = Depends(_token)):
    """All users, newest first — the admin console's main table."""
    if not _authority():
        return remote_auth.remote_request("GET", "/users", token=token)
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: AdminUserCreate, db: Session = Depends(get_db), token: str = Depends(_token)):
    """Admin-created account. Unlike self-signup, the admin chooses the role."""
    if not _authority():
        return remote_auth.remote_request("POST", "/users", token=token, json=body.model_dump())
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
    token: str = Depends(_token),
):
    """Grant/revoke permissions: change role and/or activate-deactivate.

    Guard rail: we never let the LAST active admin demote or deactivate
    themselves, otherwise no one could ever manage users again. A permission
    change bumps token_version, which logs the affected user out everywhere."""
    if not _authority():
        return remote_auth.remote_request(
            "PATCH", f"/users/{user_id}", token=token, json=body.model_dump(exclude_none=True),
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # would this change remove the final active admin?
    demoting = body.role is not None and body.role != ROLE_ADMIN and user.role == ROLE_ADMIN
    deactivating = body.is_active is False and user.is_active and user.role == ROLE_ADMIN
    if (demoting or deactivating) and _active_admin_count(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the last active admin",
        )

    role_changed = body.role is not None and body.role != user.role
    active_changed = body.is_active is not None and body.is_active != user.is_active
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    # any permission change invalidates the user's existing tokens (forced re-login)
    if role_changed or active_changed:
        user.token_version += 1
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
    token: str = Depends(_token),
):
    """Remove an account. You cannot delete yourself (use another admin) and you
    cannot delete the last active admin."""
    if not _authority():
        remote_auth.remote_request("DELETE", f"/users/{user_id}", token=token)
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    if user.role == ROLE_ADMIN and user.is_active and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the last active admin")
    db.delete(user)
    db.commit()
    return None
