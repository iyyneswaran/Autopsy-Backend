from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey
)
from datetime import datetime

from app.core.database import Base


class AuditLog(Base):

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    action = Column(String, nullable=False)

    resource_type = Column(String)

    resource_id = Column(Integer)

    ip_address = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )