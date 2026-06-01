from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class SchematicBase(BaseModel):
    part_number: str
    vehicle_make: str | None = None
    model: str | None = None
    description: str | None = None


class SchematicResponse(SchematicBase):
    id: UUID
    s3_key: str
    version: int
    parent_id: UUID | None = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DownloadResponse(BaseModel):
    url: str
