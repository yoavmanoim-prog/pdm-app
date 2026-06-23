import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import remote_auth
from app.authz import MANAGE_ROLES, require_privilege
from app.config import settings
from app.database import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.roles import RoleCreate, RoleUpdate, RoleResponse
from app.security import get_current_user

router = APIRouter(prefix="/roles", tags=["roles"])

_bearer = HTTPBearer(auto_error=False)


def _authority() -> bool:
    """True on the remote vault (owns the roles table). A local vault forwards
    role operations to the remote, like the users router does."""
    return settings.VAULT_MODE == "remote"


def _token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str | None:
    return creds.credentials if creds else None


@router.get("", response_model=list[RoleResponse])
def list_roles(
    db: Session = Depends(get_db),
    token: str = Depends(_token),
    current: User = Depends(get_current_user),
):
    """All roles. Readable by any logged-in user — the admin console uses it both
    for the Roles page and to populate the user role dropdown."""
    if not _authority():
        return remote_auth.remote_request("GET", "/roles", token=token)
    return db.query(Role).order_by(Role.is_builtin.desc(), Role.name).all()


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    body: RoleCreate,
    db: Session = Depends(get_db),
    token: str = Depends(_token),
    current: User = Depends(require_privilege(MANAGE_ROLES)),
):
    """Create a custom role (name + privileges). Names are unique identities."""
    if not _authority():
        return remote_auth.remote_request("POST", "/roles", token=token, json=body.model_dump())
    if db.query(Role).filter(Role.name == body.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
    role = Role(name=body.name, privileges=body.privileges, is_builtin=False)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    token: str = Depends(_token),
    current: User = Depends(require_privilege(MANAGE_ROLES)),
):
    """Edit a role's privileges. Built-in roles (admin/member) are immutable to
    avoid locking everyone out of management."""
    if not _authority():
        return remote_auth.remote_request("PUT", f"/roles/{role_id}", token=token, json=body.model_dump())
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_builtin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in roles cannot be edited")
    role.privileges = body.privileges
    db.commit()
    db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    token: str = Depends(_token),
    current: User = Depends(require_privilege(MANAGE_ROLES)),
):
    """Delete a custom role. Refused for built-ins or roles still assigned to a
    user (reassign those users first)."""
    if not _authority():
        remote_auth.remote_request("DELETE", f"/roles/{role_id}", token=token)
        return None
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_builtin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in roles cannot be deleted")
    if db.query(User).filter(User.role == role.name).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role is still assigned to users")
    db.delete(role)
    db.commit()
    return None
