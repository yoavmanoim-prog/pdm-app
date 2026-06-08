import uuid
from datetime import datetime
from pydantic import BaseModel


class CommitFileResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    s3_key_pdf: str | None
    content_hash: str | None
    change_type: str  # "added", "modified", "deleted"

    class Config:
        from_attributes = True


class CommitResponse(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    branch_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    author: str
    message: str
    short_hash: str
    is_local: bool
    timestamp: datetime
    files: list[CommitFileResponse] = []

    class Config:
        from_attributes = True
