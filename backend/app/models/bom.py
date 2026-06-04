import uuid
from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class BOMEntry(Base):
    __tablename__ = "bom_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # the assembly drawing that contains this part
    parent_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )

    # the component drawing being used in this assembly
    child_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )

    # how many of this part appear in the assembly
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # position identifier on the drawing, e.g. "Item 1", "Pos. A3"
    position: Mapped[str | None] = mapped_column(String(50))

    # which formal revision of the child part is used here, e.g. "B"
    # important: assemblies must not reference draft (unreleased) parts
    part_revision: Mapped[str | None] = mapped_column(String(10))

    # what material this part is made of, e.g. "Aluminum 6061-T6", "Stainless 304"
    material: Mapped[str | None] = mapped_column(String(255))

    # description of this part's role in the assembly
    description: Mapped[str | None] = mapped_column(Text)

    # product family or line this part belongs to, e.g. "Panel Series X", "Frame Assembly Y"
    product_line: Mapped[str | None] = mapped_column(String(255))

    # "part" = a raw manufactured component, "assembly" = made up of other parts
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="part")

    # relationships — foreign_keys required because both FKs point to the same table
    parent_document: Mapped["Document"] = relationship(
        back_populates="bom_as_parent",
        foreign_keys=[parent_document_id]
    )
    child_document: Mapped["Document"] = relationship(
        back_populates="bom_as_child",
        foreign_keys=[child_document_id]
    )
