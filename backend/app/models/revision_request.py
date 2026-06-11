import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class RevisionRequest(Base):
    __tablename__ = "revision_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    proposed_revision_code: Mapped[str] = mapped_column(String(10), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text)
    # "pending", "approved", "denied"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])
