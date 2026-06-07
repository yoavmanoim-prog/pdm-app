import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # revision belongs to a specific document, not the whole repository
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    commit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commits.id"), nullable=False)
    # "A", "B", "C"... — I and O are skipped (look like 1 and 0)
    revision_code: Mapped[str] = mapped_column(String(10), nullable=False)
    # "draft", "released", or "obsolete" (previous revision becomes obsolete on new release)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_by: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    # mandatory for Rev B and later — describes what changed
    change_note: Mapped[str | None] = mapped_column(Text)
    # True = all protocol rules passed at publish time
    passed_protocol: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON list of any violations found at publish time
    violations: Mapped[list | None] = mapped_column(JSON)

    document: Mapped["Document"] = relationship(back_populates="revisions")
