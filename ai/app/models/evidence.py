from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base


class Evidence(Base):

    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(
        Integer,
        ForeignKey("cases.id")
    )

    file_name = Column(String, nullable=False)

    file_path = Column(String, nullable=False)

    file_hash = Column(String, nullable=False)

    file_type = Column(String, nullable=False)

    uploaded_by = Column(
        Integer,
        ForeignKey("users.id")
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    case = relationship(
        "Case",
        back_populates="evidence_items"
    )

    uploader = relationship("User")