import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Schematic(Base):
    __tablename__ = "schematics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_number = Column(Text, nullable=False, index=True)
    vehicle_make = Column(Text)
    model = Column(Text)
    description = Column(Text)
    s3_key = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("schematics.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    deleted = Column(Boolean, default=False)

    versions = relationship("Schematic", backref="parent", remote_side=[id])
