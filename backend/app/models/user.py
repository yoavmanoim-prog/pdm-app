import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

# Built-in role names, seeded by migration 0010. "admin" carries every privilege
# (incl. managing users/roles); "member" carries none. Admins create more roles
# at runtime — these two just can't be deleted. A user's `role` column stores the
# role NAME, which links it to a Role row (see role_obj below).
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

    # link to the Role row BY NAME (users.role == roles.name) — not a FK, so the
    # role column stays a plain string. Eager-loaded so listing users resolves
    # each one's privileges in a single join.
    role_obj: Mapped["Role"] = relationship(
        "Role",
        primaryjoin="foreign(User.role) == Role.name",
        viewonly=True,
        uselist=False,
        lazy="joined",
    )

    @property
    def privileges(self) -> list[str]:
        """The user's effective privileges. Prefers an explicitly-set value
        (security.get_current_user sets this on the LOCAL vault from the remote's
        /auth/me, where there's no Role row to join); otherwise resolves from the
        linked Role. Empty if neither is available."""
        explicit = getattr(self, "_privileges", None)
        if explicit is not None:
            return explicit
        return list(self.role_obj.privileges) if self.role_obj else []

    @privileges.setter
    def privileges(self, value):
        self._privileges = list(value or [])

    @property
    def is_admin(self) -> bool:
        # "admin" = whoever can manage users (kept for backward-compat callers)
        from app.authz import MANAGE_USERS
        return MANAGE_USERS in self.privileges
