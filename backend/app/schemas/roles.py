import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.authz import PRIVILEGES


def _valid_privileges(v: list[str]) -> list[str]:
    """Reject unknown privileges and de-dup, so a role can only carry capabilities
    the app actually enforces."""
    unknown = [p for p in v if p not in PRIVILEGES]
    if unknown:
        raise ValueError(f"unknown privileges: {unknown}; allowed: {list(PRIVILEGES)}")
    return sorted(set(v))


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    privileges: list[str] = []

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        return v.strip().lower()

    _priv = field_validator("privileges")(_valid_privileges)


class RoleUpdate(BaseModel):
    # only the privilege set is editable — the name is the role's identity (users
    # link to it by name), so renaming is not supported.
    privileges: list[str] = []

    _priv = field_validator("privileges")(_valid_privileges)


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    privileges: list[str]
    is_builtin: bool
    created_at: datetime

    class Config:
        from_attributes = True
