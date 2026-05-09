from sqlalchemy import (
    Column,
    Integer,
    String,
    JSON,
    Float,
    DateTime,
    ForeignKey
)
from datetime import datetime

from app.core.database import Base


class Analysis(Base):

    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)

    evidence_id = Column(
        Integer,
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