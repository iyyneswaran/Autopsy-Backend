"""
Atopsy — Data Quality Report Schemas.

Schemas for normalization quality metrics, anomaly reports,
and completeness scoring.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class FieldQualityReport(BaseModel):
    """Quality assessment for a single field."""

    field_name: str
    is_present: bool = False
    is_valid: bool = False
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    original_value: Any = None
    normalized_value: Any = None


class AnomalyReport(BaseModel):
    """A single detected anomaly in the evidence data."""

    anomaly_type: str  # "impossible_timestamp", "invalid_gps", etc.
    severity: str = "warning"  # "info", "warning", "critical"
    field: str | None = None
    description: str
    value: Any = None
    suggestion: str | None = None


class StageReport(BaseModel):
    """Report for a single normalization stage."""

    stage_name: str
    status: str = "completed"  # "completed", "partial", "failed", "skipped"
    duration_ms: float = 0.0
    fields_processed: int = 0
    fields_modified: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class QualityReport(BaseModel):
    """Comprehensive quality report for a normalized evidence record."""

    model_config = ConfigDict(from_attributes=True)

    evidence_file_id: UUID
    overall_quality_score: float = Field(ge=0.0, le=1.0, default=0.0)
    completeness_score: float = Field(ge=0.0, le=1.0, default=0.0)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)

    total_fields: int = 0
    present_fields: int = 0
    valid_fields: int = 0
    missing_fields: list[str] = Field(default_factory=list)

    field_reports: list[FieldQualityReport] = Field(default_factory=list)
    anomalies: list[AnomalyReport] = Field(default_factory=list)
    stage_reports: list[StageReport] = Field(default_factory=list)

    generated_at: datetime | None = None


class NormalizationResponse(BaseModel):
    """API response after normalization completes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_file_id: UUID
    status: str
    schema_version: str
    quality_score: float
    completeness_score: float
    confidence_score: float
    anomaly_count: int
    stages_completed: list[str]
    stages_failed: list[str]
    created_at: datetime
    completed_at: datetime | None
