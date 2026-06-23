import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # unique role name. This is also the value stored in users.role — a user is
    # linked to its role BY NAME (not a FK), which keeps the existing role column
    # and tokens unchanged. Names are therefore immutable identities (no rename).
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # the privileges this role grants — a JSON list of strings from app.authz.PRIVILEGES
    privileges: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # built-in roles (admin/member) are seeded by migration and can't be deleted
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
