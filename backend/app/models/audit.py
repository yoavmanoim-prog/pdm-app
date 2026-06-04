import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)

    # what type of action occurred — e.g. "commit", "push", "merge", "revision_released", "branch_created"
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # who performed this action
    actor: Mapped[str] = mapped_column(String(255), nullable=False)

    # flexible JSON field for event-specific data
    # e.g. for a commit: {"hash": "abc123", "message": "Added holes", "branch": "main"}
    # e.g. for a revision: {"revision_code": "A", "commit_hash": "abc123"}
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # audit events are never deleted — this timestamp is the permanent record
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # relationship
    repository: Mapped["Repository"] = relationship(back_populates="audit_events")
