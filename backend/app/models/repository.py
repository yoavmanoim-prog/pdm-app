import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    # URL of the remote vault this repo syncs with (only relevant on local vaults)
    remote_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="repository")
    branches: Mapped[list["Branch"]] = relationship(back_populates="repository")
    commits: Mapped[list["Commit"]] = relationship(back_populates="repository")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="repository")
