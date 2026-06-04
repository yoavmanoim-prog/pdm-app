# Import all models here so SQLAlchemy can find them when creating tables.
# Any model not imported here won't be picked up by Alembic migrations.
from app.models.base import Base
from app.models.repository import Repository
from app.models.document import Document
from app.models.commit import Commit, CommitFile
from app.models.bom import BOMEntry
from app.models.revision import Revision
from app.models.audit import AuditEvent

__all__ = [
    "Base",
    "Repository",
    "Document",
    "Commit",
    "CommitFile",
    "BOMEntry",
    "Revision",
    "AuditEvent",
]
