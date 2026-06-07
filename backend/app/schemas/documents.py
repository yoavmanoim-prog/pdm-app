import uuid
from pydantic import BaseModel


class DocumentCreate(BaseModel):
    part_number: str   # engineering identifier e.g. "ENG-001-A"
    title: str         # human-readable name e.g. "Main Frame Bracket"
    doc_type: str = "detail"  # "detail" = single part, "assembly" = made of other parts


class DocumentResponse(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    part_number: str
    title: str
    doc_type: str

    class Config:
        from_attributes = True  # lets Pydantic read from SQLAlchemy model objects
