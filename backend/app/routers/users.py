import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, ROLE_ADMIN
from app.schemas.users import AdminUserCreate, UserUpdate, UserResponse
from app.security import hash_password, require_admin

# every route here is admin-only: require_admin runs get_current_user first, then
# checks the role, so a member or anonymous caller never reaches the handler.
router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


def _active_admin_count(db: Session) -> int:
    """How many active admins remain — used to refuse changes that would lock
    everyone out of user management."""
    return db.query(User).filter(User.role == ROLE_ADMIN, User.is_active.is_(True)).count()


@router.get("", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)):
    """All users, newest first — the admin console's main table."""
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: AdminUserCreate, db: Session = Depends(get_db)):
    """Admin-created account. Unlike self-signup, the admin chooses the role."""
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
):
    """Grant/revoke permissions: change role and/or activate-deactivate.

    Guard rail: we never let the LAST active admin demote or deactivate
    themselves, otherwise no one could ever manage users again."""
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

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    """Remove an account. You cannot delete yourself (use another admin) and you
    cannot delete the last active admin."""
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
