from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class User(Base):

    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)

    name = Column("firstName", String, nullable=False)

    email = Column(String, unique=True, nullable=False)

    password_hash = Column("passwordHash", String, nullable=False)

    role = Column(String, nullable=False)

    created_at = Column("createdAt", DateTime, default=datetime.utcnow)