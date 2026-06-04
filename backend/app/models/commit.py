import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)

    # SHA-256 hash of the commit content — like a git commit hash
    # calculated from: author + message + timestamp + parent_hash + file changes
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # human-readable description of what changed
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # who made this commit
    author: Mapped[str] = mapped_column(String(255), nullable=False)

    # hash of the previous commit — how git builds a chain of history
    # null means this is the first commit (the "root commit")
    parent_hash: Mapped[str | None] = mapped_column(String(64))

    # which branch this commit belongs to, e.g. "main", "feature/add-holes"
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # relationships
    repository: Mapped["Repository"] = relationship(back_populates="commits")
    files: Mapped[list["CommitFile"]] = relationship(back_populates="commit")

    # a commit can have one formal revision stamped on it (Rev A, Rev B...)
    revision: Mapped["Revision | None"] = relationship(back_populates="commit")


class CommitFile(Base):
    __tablename__ = "commit_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    commit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commits.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)

    # what happened to this file: "added", "modified", or "deleted"
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # S3 key for the SVG snapshot of this document AT THIS COMMIT
    svg_key: Mapped[str | None] = mapped_column(String(500))

    # S3 key for a visual diff image showing what changed vs the previous version
    diff_key: Mapped[str | None] = mapped_column(String(500))

    # relationships
    commit: Mapped["Commit"] = relationship(back_populates="files")
    document: Mapped["Document"] = relationship(back_populates="commit_files")
