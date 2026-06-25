import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Branch(Base):
    __tablename__ = "branches"
    # only one OPEN branch per name in a repo; names are reusable once a
    # branch is merged/closed, so this is a partial unique index
    __table_args__ = (
        Index(
            "uq_branches_one_open_per_name",
            "repository_id",
            "name",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # the commit where this branch diverged from main — null means new repo
    base_commit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("commits.id"))
    # "open" = active, "merged" = merged into main, "closed" = abandoned
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    repository: Mapped["Repository"] = relationship(back_populates="branches")
    commits: Mapped[list["Commit"]] = relationship(
        back_populates="branch",
        foreign_keys="Commit.branch_id"
    )
