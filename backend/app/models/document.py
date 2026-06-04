import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # which repository this document belongs to
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)

    # file path within the repo, e.g. "assemblies/panel/panel-001"
    path: Mapped[str] = mapped_column(String(500), nullable=False)

    # human-readable name, e.g. "Main Panel Assembly"
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # S3 key pointing to the current SVG file in storage
    # SVG is used internally because it can be diff'd (compared line by line)
    current_svg_key: Mapped[str | None] = mapped_column(String(500))

    # part number used in BOM entries, e.g. "PNL-001-A"
    part_number: Mapped[str | None] = mapped_column(String(100))

    # soft-delete flag — we never physically delete documents, just mark them deleted
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # relationships
    repository: Mapped["Repository"] = relationship(back_populates="documents")
    commit_files: Mapped[list["CommitFile"]] = relationship(back_populates="document")

    # BOM relationships — a document can be a parent assembly or a child part
    bom_as_parent: Mapped[list["BOMEntry"]] = relationship(
        back_populates="parent_document",
        foreign_keys="BOMEntry.parent_document_id"
    )
    bom_as_child: Mapped[list["BOMEntry"]] = relationship(
        back_populates="child_document",
        foreign_keys="BOMEntry.child_document_id"
    )
