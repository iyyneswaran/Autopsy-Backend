from sqlalchemy import (
    Column,
    String,
    JSON,
    Float,
    DateTime,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class Analysis(Base):

    __tablename__ = "analysis"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)

    evidence_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id")
    )

    analysis_type = Column(String, nullable=False)

    result_json = Column(JSON)

    confidence_score = Column(Float)

    model_version = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )