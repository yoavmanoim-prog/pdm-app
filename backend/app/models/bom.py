import uuid
from sqlalchemy import String, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class BOMEntry(Base):
    __tablename__ = "bom_entries"
    # a component can appear at most once in a given assembly's BOM
    __table_args__ = (
        UniqueConstraint("assembly_id", "component_id", name="uq_bom_assembly_component"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # the assembly drawing that contains this component
    assembly_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    # the component drawing used by the assembly
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # balloon number on the drawing, e.g. "3" or "A3"
    position: Mapped[str | None] = mapped_column(String(50))
    # the sequential number from the BOM table on the drawing
    find_number: Mapped[int | None] = mapped_column(Integer)
    # which formal revision of the component is used in this assembly
    part_revision: Mapped[str | None] = mapped_column(String(10))
    # material specification, e.g. "Aluminum 6061-T6"
    material: Mapped[str | None] = mapped_column(String(255))
    # description of the component's role in the assembly
    description: Mapped[str | None] = mapped_column(Text)
    # product family this part belongs to
    product_line: Mapped[str | None] = mapped_column(String(255))
    # "part" = raw manufactured component, "assembly" = made up of other parts
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="part")

    assembly: Mapped["Document"] = relationship(
        back_populates="bom_as_assembly",
        foreign_keys=[assembly_id]
    )
    component: Mapped["Document"] = relationship(
        back_populates="bom_as_component",
        foreign_keys=[component_id]
    )
