import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

# Role values. "admin" can manage other users (set role, activate/deactivate);
# "member" has normal app access. Kept as plain strings (not a DB enum) so new
# roles can be added later without a migration — see ROLES for the allowed set.
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
ROLES = (ROLE_ADMIN, ROLE_MEMBER)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # login identifier — unique, case-insensitive in practice (we lowercase on write)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    # bcrypt hash — never the plaintext password
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # "admin" or "member" — see ROLES above
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_MEMBER)
    # an admin can deactivate an account without deleting it; inactive users can't log in
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # bumped whenever the account's permissions change (role edit, deactivation).
    # Every JWT embeds the version it was minted at; a token whose version no
    # longer matches is rejected, so a role change forces the user to log in again.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN
