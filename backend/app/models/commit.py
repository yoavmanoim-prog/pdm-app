import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean, JSON  # JSON kept for Commit.diff_report and protocol_violations
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    # the previous commit in the chain — null means first commit
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("commits.id"))
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # first 8 chars of SHA-256 hash — shown in logs e.g. "a1b2c3d4"
    short_hash: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    # True = only on local vault, False = pushed to remote
    is_local: Mapped[bool] = mapped_column(Boolean, default=True)
    # JSON summary of SVG element changes in this commit
    diff_report: Mapped[dict | None] = mapped_column(JSON)
    # JSON list of protocol violations found at commit time
    protocol_violations: Mapped[list | None] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    repository: Mapped["Repository"] = relationship(back_populates="commits")
    branch: Mapped["Branch | None"] = relationship(
        back_populates="commits",
        foreign_keys=[branch_id]
    )
    files: Mapped[list["CommitFile"]] = relationship(back_populates="commit")


class CommitFile(Base):
    __tablename__ = "commit_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    commit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commits.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    # permanent S3 key for the PDF at this exact commit
    s3_key_pdf: Mapped[str | None] = mapped_column(String(500))
    # SHA-256 of PDF content — used to reject commits with no actual changes
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # "added", "modified", or "deleted"
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)

    commit: Mapped["Commit"] = relationship(back_populates="files")
    document: Mapped["Document"] = relationship(back_populates="commit_files")
