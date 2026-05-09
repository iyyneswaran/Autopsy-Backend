from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.core.database import Base


class Case(Base):

    __tablename__ = "investigations"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    
    case_number = Column("caseNumber", String, nullable=True)

    title = Column(String, nullable=False)

    description = Column(Text)

    status = Column(String, default="OPEN")

    created_by = Column("createdById", UUID(as_uuid=True), ForeignKey("users.id"))

    created_at = Column("createdAt", DateTime, default=datetime.utcnow)

    creator = relationship("User")

    evidence_items = relationship(
        "Evidence",
        back_populates="case"
    )