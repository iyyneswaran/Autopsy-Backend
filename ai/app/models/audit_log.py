from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class AuditLog(Base):

    __tablename__ = "audit_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)

    user_id = Column("userId", UUID(as_uuid=True), ForeignKey("users.id"))

    action = Column(String, nullable=False)

    resource_type = Column("entity", String)

    resource_id = Column("entityId", String)

    ip_address = Column("ipAddress", String)

    created_at = Column("createdAt", DateTime, default=datetime.utcnow)