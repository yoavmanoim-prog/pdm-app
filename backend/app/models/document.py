import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # "detail" = a single manufactured part, "assembly" = made up of other parts
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False, default="detail")

    repository: Mapped["Repository"] = relationship(back_populates="documents")
    commit_files: Mapped[list["CommitFile"]] = relationship(back_populates="document")
    revisions: Mapped[list["Revision"]] = relationship(back_populates="document")

    bom_as_assembly: Mapped[list["BOMEntry"]] = relationship(
        back_populates="assembly",
        foreign_keys="BOMEntry.assembly_id"
    )
    bom_as_component: Mapped[list["BOMEntry"]] = relationship(
        back_populates="component",
        foreign_keys="BOMEntry.component_id"
    )
