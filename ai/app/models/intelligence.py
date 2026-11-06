"""Additive workflow records. Shared users/cases remain Prisma-owned."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, UniqueConstraint, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSON
from app.core.database import Base


def now():
    return datetime.now(timezone.utc)


class CasePipelineRun(Base):
    __tablename__ = 'case_pipeline_runs'
    __table_args__ = (UniqueConstraint('case_id', 'version'), UniqueConstraint('case_id', 'request_key'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey('investigations.id'), nullable=False, index=True)
    requested_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    version = Column(Integer, nullable=False)
    request_key = Column(String(128), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    schema_version = Column(String(30), nullable=False, default='2.0.0')
    status = Column(String(20), nullable=False, default='QUEUED', index=True)
    evidence_ids = Column(JSON, nullable=False)
    retry_of = Column(UUID(as_uuid=True), ForeignKey('case_pipeline_runs.id'))
    warnings = Column(JSON, default=list)
    error = Column(Text)
    changes = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    completed_at = Column(DateTime(timezone=True))


class PipelineStage(Base):
    __tablename__ = 'case_pipeline_stages'
    __table_args__ = (UniqueConstraint('run_id', 'scope', 'name'), Index('ix_stage_cache', 'cache_key', 'status'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey('case_pipeline_runs.id'), nullable=False, index=True)
    scope = Column(String(40), nullable=False)
    name = Column(String(40), nullable=False)
    cache_key = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default='PENDING')
    schema_version = Column(String(30), default='2.0.0')
    input_version = Column(String(30), default='2.0.0')
    output = Column(JSON)
    record_id = Column(UUID(as_uuid=True))
    reused_from = Column(UUID(as_uuid=True), ForeignKey('case_pipeline_stages.id'))
    warnings = Column(JSON, default=list)
    error = Column(Text)
    duration_ms = Column(Float, default=0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))


class FindingReview(Base):
    __tablename__ = 'finding_reviews'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey('investigations.id'), nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey('case_pipeline_runs.id'), nullable=False)
    target_id = Column(String(200), nullable=False, index=True)
    state = Column(String(30), nullable=False)
    note = Column(Text, nullable=False)
    correction = Column(Text)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)


class HypothesisRevision(Base):
    __tablename__ = 'hypothesis_revisions'
    __table_args__ = (UniqueConstraint('hypothesis_id', 'version'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hypothesis_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    case_id = Column(UUID(as_uuid=True), ForeignKey('investigations.id'), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    notes = Column(Text, nullable=False, default='')
    status = Column(String(30), nullable=False, default='DRAFT')
    assessments = Column(JSON, nullable=False, default=list)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
