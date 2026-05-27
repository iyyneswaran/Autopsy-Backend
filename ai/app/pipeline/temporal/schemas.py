"""
Atopsy — Temporal Intelligence Schemas (Layer 6).

Pydantic models for the forensic timeline output.
Covers temporal events, time windows, temporal relations,
conflicts, TOD candidates, uncertainty ranges, and the
top-level ForensicTimeline.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class TemporalPrecision(str, enum.Enum):
    """Precision level of a temporal expression."""

    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    RANGE = "RANGE"
    RELATIVE = "RELATIVE"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class TemporalRelationType(str, enum.Enum):
    """Temporal relation between two events (Allen's interval algebra)."""

    BEFORE = "BEFORE"
    AFTER = "AFTER"
    DURING = "DURING"
    CONTAINS = "CONTAINS"
    OVERLAPS = "OVERLAPS"
    MEETS = "MEETS"
    STARTS = "STARTS"
    FINISHES = "FINISHES"
    EQUALS = "EQUALS"
    CONCURRENT = "CONCURRENT"
    UNKNOWN = "UNKNOWN"


class TemporalConflictSeverity(str, enum.Enum):
    """Severity of a temporal conflict."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventCategory(str, enum.Enum):
    """Category of a forensic temporal event."""

    DEATH = "DEATH"
    DISCOVERY = "DISCOVERY"
    EXAMINATION = "EXAMINATION"
    LAST_SEEN_ALIVE = "LAST_SEEN_ALIVE"
    INCIDENT = "INCIDENT"
    REPORT_FILED = "REPORT_FILED"
    TOXICOLOGY_COLLECTION = "TOXICOLOGY_COLLECTION"
    SCENE_INVESTIGATION = "SCENE_INVESTIGATION"
    INJURY_INFLICTION = "INJURY_INFLICTION"
    HOSPITALIZATION = "HOSPITALIZATION"
    WITNESS_OBSERVATION = "WITNESS_OBSERVATION"
    DOCUMENT_CREATION = "DOCUMENT_CREATION"
    OTHER = "OTHER"


class ResolutionMethod(str, enum.Enum):
    """How a temporal expression was resolved."""

    DIRECT_PARSE = "DIRECT_PARSE"
    RELATIVE_ANCHOR = "RELATIVE_ANCHOR"
    INTERVAL_INFERENCE = "INTERVAL_INFERENCE"
    PMI_ESTIMATION = "PMI_ESTIMATION"
    CONTEXT_INFERENCE = "CONTEXT_INFERENCE"
    DOCUMENT_DATE = "DOCUMENT_DATE"
    UNRESOLVED = "UNRESOLVED"


# ─────────────────────────────────────────────
# Time Window
# ─────────────────────────────────────────────


class TimeWindow(BaseModel):
    """
    A time window representing uncertain timestamps.

    Uses earliest/latest bounds instead of forcing a single point.
    Both bounds are ISO 8601 strings to support timezone awareness.
    """

    earliest: str | None = None
    latest: str | None = None
    best_estimate: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    precision: TemporalPrecision = TemporalPrecision.UNKNOWN
    timezone_info: str | None = None


# ─────────────────────────────────────────────
# Temporal Expression
# ─────────────────────────────────────────────


class TemporalExpression(BaseModel):
    """
    A raw temporal expression extracted from text,
    paired with its normalized/parsed form.
    """

    raw_text: str = ""
    normalized_form: str = ""
    precision: TemporalPrecision = TemporalPrecision.UNKNOWN
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    resolution_method: ResolutionMethod = ResolutionMethod.UNRESOLVED
    anchor_event: str | None = None
    source_evidence_id: str = ""
    source_entity_id: str = ""
    page: int | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# ─────────────────────────────────────────────
# Temporal Event
# ─────────────────────────────────────────────


class TemporalEventProvenance(BaseModel):
    """Source provenance for a temporal event."""

    evidence_file_id: str = ""
    entity_id: str = ""
    entity_type: str = ""
    cluster_id: str | None = None
    extraction_method: str = ""
    raw_text: str = ""
    page: int | None = None


class TemporalEvent(BaseModel):
    """
    A forensic event with temporal positioning.

    Carries time window, category, provenance, and confidence.
    Observed vs. inferred distinction is preserved.
    """

    event_id: str = ""
    label: str = ""
    description: str = ""
    category: EventCategory = EventCategory.OTHER
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    temporal_expressions: list[TemporalExpression] = Field(
        default_factory=list
    )
    is_observed: bool = True
    is_anchor: bool = False
    provenance: TemporalEventProvenance = Field(
        default_factory=TemporalEventProvenance
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    resolution_method: ResolutionMethod = ResolutionMethod.UNRESOLVED
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Temporal Relation
# ─────────────────────────────────────────────


class TemporalRelation(BaseModel):
    """A temporal ordering relation between two events."""

    source_event_id: str = ""
    target_event_id: str = ""
    relation_type: TemporalRelationType = TemporalRelationType.UNKNOWN
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""
    is_inferred: bool = False


# ─────────────────────────────────────────────
# Temporal Conflict
# ─────────────────────────────────────────────


class TemporalConflictSource(BaseModel):
    """One side of a temporal conflict."""

    event_id: str = ""
    evidence_file_id: str = ""
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    raw_text: str = ""


class TemporalConflict(BaseModel):
    """
    A detected impossible or contradictory temporal sequence.

    Examples: event B happens before event A, but A must precede B;
    death occurs after the post-mortem examination date.
    """

    conflict_id: str = ""
    severity: TemporalConflictSeverity = TemporalConflictSeverity.MEDIUM
    description: str = ""
    conflict_type: str = ""
    source_a: TemporalConflictSource = Field(
        default_factory=TemporalConflictSource
    )
    source_b: TemporalConflictSource = Field(
        default_factory=TemporalConflictSource
    )
    resolution_hint: str = ""
    is_resolved: bool = False


# ─────────────────────────────────────────────
# TOD Candidate
# ─────────────────────────────────────────────


class TODCandidate(BaseModel):
    """
    A time-of-death estimate with method and confidence.

    Supports multiple TOD estimates from different evidence
    sources and estimation methods (PMI, witness, rigor, etc.).
    """

    candidate_id: str = ""
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    estimation_method: str = ""
    evidence_basis: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""
    source_evidence_ids: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Uncertainty Range
# ─────────────────────────────────────────────


class UncertaintyRange(BaseModel):
    """
    Explicit uncertainty representation for PMI and intervals.

    Preserves the original textual expression alongside
    the computed numeric range.
    """

    label: str = ""
    raw_expression: str = ""
    min_hours: float | None = None
    max_hours: float | None = None
    best_estimate_hours: float | None = None
    unit: str = "hours"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_evidence_id: str = ""


# ─────────────────────────────────────────────
# Audit Trail
# ─────────────────────────────────────────────


class TemporalAuditEntry(BaseModel):
    """A single entry in the temporal intelligence audit trail."""

    stage: str = ""
    action: str = ""
    event_ids: list[str] = Field(default_factory=list)
    detail: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─────────────────────────────────────────────
# Stage Report
# ─────────────────────────────────────────────


class TemporalStageReport(BaseModel):
    """Report for a single temporal pipeline stage."""

    stage: str
    status: str = "completed"
    duration_ms: float = 0.0
    items_processed: int = 0
    detail: str = ""
    error: str | None = None


# ─────────────────────────────────────────────
# Top-Level Timeline
# ─────────────────────────────────────────────


class ForensicTimeline(BaseModel):
    """
    Top-level output of the Temporal Intelligence Layer.

    Contains the ordered forensic timeline with events,
    temporal relations, conflicts, TOD candidates,
    uncertainty ranges, and audit trail.
    """

    schema_version: str = "1.0.0"
    case_id: str | None = None
    evidence_file_ids: list[str] = Field(default_factory=list)
    timeline: list[TemporalEvent] = Field(default_factory=list)
    temporal_events: list[TemporalEvent] = Field(default_factory=list)
    event_order: list[str] = Field(default_factory=list)
    time_windows: list[TimeWindow] = Field(default_factory=list)
    uncertainty_ranges: list[UncertaintyRange] = Field(default_factory=list)
    temporal_relations: list[TemporalRelation] = Field(default_factory=list)
    tod_candidates: list[TODCandidate] = Field(default_factory=list)
    temporal_conflicts: list[TemporalConflict] = Field(default_factory=list)
    temporal_audit: list[TemporalAuditEntry] = Field(default_factory=list)
    stage_reports: list[TemporalStageReport] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
