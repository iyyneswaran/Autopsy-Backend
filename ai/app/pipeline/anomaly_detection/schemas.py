"""
Atopsy — Anomaly & Contradiction Detection Schemas (Layer 8).

Pydantic models for the forensic anomaly and contradiction
detection output. Covers finding types, severity levels,
contradiction and anomaly findings, rule hits, severity
summaries, and the top-level AnomalyReport.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class FindingType(str, enum.Enum):
    """Classification of a detection finding."""

    CONTRADICTION = "CONTRADICTION"
    ANOMALY = "ANOMALY"
    INCONSISTENCY = "INCONSISTENCY"
    MISSING_DATA = "MISSING_DATA"
    OCR_ARTIFACT = "OCR_ARTIFACT"


class FindingSeverity(str, enum.Enum):
    """Severity level of a finding."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingCategory(str, enum.Enum):
    """Domain category of a finding."""

    CASE_IDENTIFIER = "CASE_IDENTIFIER"
    IDENTITY = "IDENTITY"
    MEDICAL = "MEDICAL"
    TEMPORAL = "TEMPORAL"
    TOXICOLOGY = "TOXICOLOGY"
    LOCATION = "LOCATION"
    EVIDENCE_INTEGRITY = "EVIDENCE_INTEGRITY"
    OCR_QUALITY = "OCR_QUALITY"
    TOD_ESTIMATION = "TOD_ESTIMATION"


# ─────────────────────────────────────────────
# Provenance
# ─────────────────────────────────────────────


class AnomalyProvenanceEntry(BaseModel):
    """Source provenance for an anomaly/contradiction finding."""

    evidence_file_id: str = ""
    entity_id: str = ""
    entity_type: str = ""
    raw_text: str = ""
    canonical_value: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    extraction_method: str = ""
    page: int | None = None
    document_source: str = ""


# ─────────────────────────────────────────────
# Finding Source (for contradictions)
# ─────────────────────────────────────────────


class FindingSource(BaseModel):
    """One side of a contradiction or comparison."""

    entity_id: str = ""
    evidence_file_id: str = ""
    value: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    raw_text: str = ""
    page: int | None = None
    document_source: str = ""


# ─────────────────────────────────────────────
# Anomaly Finding
# ─────────────────────────────────────────────


class AnomalyFinding(BaseModel):
    """
    A detected anomaly in the forensic evidence.

    Covers missing data, impossible values, suspicious
    OCR artifacts, and other non-contradiction issues.
    """

    finding_id: str = ""
    finding_type: FindingType = FindingType.ANOMALY
    category: FindingCategory = FindingCategory.EVIDENCE_INTEGRITY
    severity: FindingSeverity = FindingSeverity.MEDIUM
    title: str = ""
    description: str = ""
    affected_entity_ids: list[str] = Field(default_factory=list)
    affected_evidence_ids: list[str] = Field(default_factory=list)
    affected_timeline_event_ids: list[str] = Field(default_factory=list)
    rule_id: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    provenance: list[AnomalyProvenanceEntry] = Field(default_factory=list)
    recommendation: str = ""
    is_resolved: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Contradiction Finding
# ─────────────────────────────────────────────


class ContradictionFinding(BaseModel):
    """
    A detected contradiction between two evidence assertions.

    Extends finding structure with specific source A/B
    comparison, similarity score, and resolution hints.
    """

    finding_id: str = ""
    finding_type: FindingType = FindingType.CONTRADICTION
    category: FindingCategory = FindingCategory.MEDICAL
    severity: FindingSeverity = FindingSeverity.HIGH
    title: str = ""
    description: str = ""
    field: str = ""
    value_a: str = ""
    value_b: str = ""
    source_a: FindingSource = Field(default_factory=FindingSource)
    source_b: FindingSource = Field(default_factory=FindingSource)
    similarity_score: float = Field(0.0, ge=0.0, le=1.0)
    affected_entity_ids: list[str] = Field(default_factory=list)
    affected_evidence_ids: list[str] = Field(default_factory=list)
    rule_id: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    provenance: list[AnomalyProvenanceEntry] = Field(default_factory=list)
    recommendation: str = ""
    resolution_hint: str = ""
    is_resolved: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Rule Hit
# ─────────────────────────────────────────────


class RuleHit(BaseModel):
    """Record of a detection rule that fired."""

    rule_id: str = ""
    rule_name: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    category: FindingCategory = FindingCategory.EVIDENCE_INTEGRITY
    description: str = ""
    hit_count: int = 0


# ─────────────────────────────────────────────
# Severity Summary
# ─────────────────────────────────────────────


class SeveritySummary(BaseModel):
    """Aggregate counts by severity level."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0


# ─────────────────────────────────────────────
# Confidence Scores
# ─────────────────────────────────────────────


class AnomalyConfidenceScores(BaseModel):
    """Aggregate confidence metrics for the anomaly report."""

    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    average_finding_confidence: float = Field(0.0, ge=0.0, le=1.0)
    high_confidence_findings: int = 0
    low_confidence_findings: int = 0
    total_findings: int = 0
    rules_evaluated: int = 0
    rules_fired: int = 0


# ─────────────────────────────────────────────
# Affected Entities & Events
# ─────────────────────────────────────────────


class AffectedEntity(BaseModel):
    """An entity affected by one or more findings."""

    entity_id: str = ""
    entity_type: str = ""
    evidence_file_id: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    highest_severity: FindingSeverity = FindingSeverity.LOW


class AffectedTimelineEvent(BaseModel):
    """A timeline event affected by one or more findings."""

    event_id: str = ""
    event_label: str = ""
    evidence_file_id: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    highest_severity: FindingSeverity = FindingSeverity.LOW


# ─────────────────────────────────────────────
# Audit Trail
# ─────────────────────────────────────────────


class AnomalyAuditEntry(BaseModel):
    """A single entry in the anomaly detection audit trail."""

    stage: str = ""
    action: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    detail: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AnomalyStageReport(BaseModel):
    """Report for a single anomaly detection pipeline stage."""

    stage: str
    status: str = "completed"
    duration_ms: float = 0.0
    items_processed: int = 0
    findings_produced: int = 0
    detail: str = ""
    error: str | None = None


# ─────────────────────────────────────────────
# Top-Level Report
# ─────────────────────────────────────────────


class AnomalyReport(BaseModel):
    """
    Top-level output of the Anomaly & Contradiction Detection Engine.

    Contains all anomalies, contradictions, severity summary,
    affected entities and events, rule hits, confidence scores,
    provenance map, audit trail, and recommendations.
    """

    schema_version: str = "1.0.0"
    case_id: str | None = None
    evidence_file_ids: list[str] = Field(default_factory=list)
    anomalies: list[AnomalyFinding] = Field(default_factory=list)
    contradictions: list[ContradictionFinding] = Field(default_factory=list)
    severity_summary: SeveritySummary = Field(
        default_factory=SeveritySummary
    )
    affected_entities: list[AffectedEntity] = Field(default_factory=list)
    affected_timeline_events: list[AffectedTimelineEvent] = Field(
        default_factory=list
    )
    rule_hits: list[RuleHit] = Field(default_factory=list)
    confidence_scores: AnomalyConfidenceScores = Field(
        default_factory=AnomalyConfidenceScores
    )
    provenance_map: dict[str, list[AnomalyProvenanceEntry]] = Field(
        default_factory=dict
    )
    audit_trail: list[AnomalyAuditEntry] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    stage_reports: list[AnomalyStageReport] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
