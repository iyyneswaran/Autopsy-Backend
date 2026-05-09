from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.core.database import Base


class Evidence(Base):

    __tablename__ = "evidence"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)

    case_id = Column("investigationId", UUID(as_uuid=True), ForeignKey("investigations.id"))

    file_name = Column("fileName", String, nullable=False)

    file_path = Column("filePath", String, nullable=False)

    file_hash = Column("fileHash", String, nullable=False)

    file_type = Column("type", String, nullable=False)
    
    file_size = Column("fileSize", Integer, default=0)

    uploaded_by = Column("uploadedById", UUID(as_uuid=True), ForeignKey("users.id"))

    created_at = Column("createdAt", DateTime, default=datetime.utcnow)

    case = relationship(
        "Case",
        back_populates="evidence_items"
    )

    uploader = relationship("User")