import uuid
from datetime import datetime
from pydantic import BaseModel


class BranchCreate(BaseModel):
    name: str
    created_by: str


class BranchResponse(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    name: str
    base_commit_id: uuid.UUID | None
    status: str
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True
