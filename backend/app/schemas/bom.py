import uuid
from pydantic import BaseModel


class BOMEntryCreate(BaseModel):
    component_id: uuid.UUID
    quantity: int = 1
    position: str | None = None
    find_number: int | None = None
    part_revision: str | None = None
    material: str | None = None
    description: str | None = None
    item_type: str = "part"  # "part" or "assembly"


class BOMEntryResponse(BaseModel):
    id: uuid.UUID
    assembly_id: uuid.UUID
    component_id: uuid.UUID
    quantity: int
    position: str | None
    find_number: int | None
    part_revision: str | None
    material: str | None
    description: str | None
    item_type: str

    class Config:
        from_attributes = True
