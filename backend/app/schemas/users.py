import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


def _normalize_email(v: str) -> str:
    """Lowercase + trim so 'Bob@Factory.com ' and 'bob@factory.com' are one user.
    Kept deliberately light (no email-validator dependency): we just require an @."""
    v = v.strip().lower()
    if "@" not in v or v.startswith("@") or v.endswith("@"):
        raise ValueError("invalid email address")
    return v


class UserSignup(BaseModel):
    """Public self-registration payload."""
    email: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None

    _norm_email = field_validator("email")(_normalize_email)


class UserLogin(BaseModel):
    email: str
    password: str

    _norm_email = field_validator("email")(_normalize_email)


class AdminUserCreate(BaseModel):
    """Admin-created account — can set role up front (unlike self-signup)."""
    email: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
    # any existing role name (admin/member or a custom role). The router checks
    # the role actually exists before assigning it.
    role: str = "member"

    _norm_email = field_validator("email")(_normalize_email)

    @field_validator("role")
    @classmethod
    def _clean_role(cls, v: str) -> str:
        return v.strip().lower()


class UserUpdate(BaseModel):
    """Admin edit — this is how 'granting permissions' happens: change role and/or
    activate/deactivate. Both optional so a request can touch just one."""
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _clean_role(cls, v: str | None) -> str | None:
        return v.strip().lower() if v is not None else None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    # effective privileges, resolved from the user's role (see User.privileges)
    privileges: list[str] = []
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True  # lets FastAPI build this straight from a SQLAlchemy row


class TokenResponse(BaseModel):
    """What /auth/login and /auth/signup return: the wristband plus who you are."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
