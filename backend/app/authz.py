"""Authorization: the privilege catalog and the dependency that gates an
endpoint on a privilege.

Roles (admin-managed — see app/models/role.py) bundle privileges. A user's
effective privileges are their role's privilege list, resolved live from the DB
on every request (so editing a role takes effect without re-login). Endpoints
declare what they need with require_privilege(...).
"""
from fastapi import Depends, HTTPException, status

# --- the fixed catalog admins compose roles from ---
MANAGE_USERS = "manage_users"        # create/edit/deactivate users, assign roles
MANAGE_ROLES = "manage_roles"        # create/edit/delete roles
APPROVE_DRAWING = "approve_drawing"  # sign off a drawing so it can be pushed
APPROVE_RELEASE = "approve_release"  # approve/deny release requests, publish revisions

PRIVILEGES = (MANAGE_USERS, MANAGE_ROLES, APPROVE_DRAWING, APPROVE_RELEASE)


def has_privilege(user, privilege: str) -> bool:
    """True if the user's role grants `privilege`. Safe on any user object —
    `privileges` is resolved by security.get_current_user (or the Role
    relationship); a user without it resolves to no privileges."""
    return privilege in (getattr(user, "privileges", None) or [])


def resolve_privileges(db, role_name: str) -> list[str]:
    """The privilege list for a role name, or [] if the role is unknown."""
    from app.models.role import Role  # local import: authz is imported very early
    role = db.query(Role).filter(Role.name == role_name).first()
    return list(role.privileges or []) if role else []


def require_privilege(privilege: str):
    """Dependency factory: 403 unless the current user's role grants `privilege`.
    Mirrors security.require_admin but parameterised by privilege."""
    from app.security import get_current_user  # lazy import avoids an import cycle

    def _dependency(current=Depends(get_current_user)):
        if not has_privilege(current, privilege):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{privilege}' privilege",
            )
        return current

    return _dependency
