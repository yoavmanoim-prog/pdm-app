import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)

    # the commit this revision is stamped on — revisions are permanent labels on commits
    commit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commits.id"), nullable=False, unique=True)

    # the revision letter: "A", "B", "C"...
    # the protocol engine enforces no skipping — can't go from A to C
    revision_code: Mapped[str] = mapped_column(String(10), nullable=False)

    # short title for this release, e.g. "Initial release" or "Added mounting holes"
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # who formally approved and released this revision
    released_by: Mapped[str] = mapped_column(String(255), nullable=False)

    released_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # optional engineering notes or change description
    notes: Mapped[str | None] = mapped_column(Text)

    # enforce uniqueness: same repo can't have two "Rev A" revisions
    __table_args__ = (
        UniqueConstraint("repository_id", "revision_code", name="uq_revision_per_repo"),
    )

    # relationships
    repository: Mapped["Repository"] = relationship(back_populates="revisions")
    commit: Mapped["Commit"] = relationship(back_populates="revision")
