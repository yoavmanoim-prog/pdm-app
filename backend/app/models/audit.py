import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    # what happened: "commit", "push", "merge", "publish", "upload", "branch_create", etc.
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # what kind of thing was acted on: "document", "commit", "revision", "branch"
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # UUID of the thing that was acted on — stored as string for flexibility
    entity_id: Mapped[str | None] = mapped_column(String(100))
    # flexible JSON for event-specific data, e.g. commit hash, file list, violation details
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # IP address of the actor — useful for security audits
    ip_address: Mapped[str | None] = mapped_column(String(50))
    # True = a protocol rule was broken during this action
    is_breach: Mapped[bool] = mapped_column(Boolean, default=False)

    repository: Mapped["Repository"] = relationship(back_populates="audit_events")
