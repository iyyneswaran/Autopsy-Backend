"""
Atopsy — TOD Estimation Engine Schemas (Layer 7).

Pydantic models for the forensic time-of-death estimation output.
Covers forensic signals, TOD windows, weighted candidates,
signal conflicts, reasoning traces, and the top-level
TODEstimationResult.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class SignalType(str, enum.Enum):
    """Classification of forensic TOD signal sources."""

    PMI_STATEMENT = "PMI_STATEMENT"
    BODY_COOLING = "BODY_COOLING"
    LIVIDITY = "LIVIDITY"
    RIGOR_MORTIS = "RIGOR_MORTIS"
    LAST_SEEN_ALIVE = "LAST_SEEN_ALIVE"
    WITNESS_TIMELINE = "WITNESS_TIMELINE"
    MEDICAL_EVIDENCE = "MEDICAL_EVIDENCE"
    SCENE_EVIDENCE = "SCENE_EVIDENCE"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    TOXICOLOGY = "TOXICOLOGY"
    DECOMPOSITION = "DECOMPOSITION"
    DIRECT_EXAMINER = "DIRECT_EXAMINER"
    DISCOVERY_TIME = "DISCOVERY_TIME"


class SignalConfidenceLevel(str, enum.Enum):
    """How directly the signal was observed vs. inferred."""

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    ESTIMATED = "ESTIMATED"
    SPECULATIVE = "SPECULATIVE"


class TODPrecision(str, enum.Enum):
    """Precision level of a TOD estimate."""

    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    RANGE = "RANGE"
    RELATIVE = "RELATIVE"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class ConflictSeverity(str, enum.Enum):
    """Severity of a signal conflict."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ─────────────────────────────────────────────
# Provenance
# ─────────────────────────────────────────────


class TODProvenanceEntry(BaseModel):
    """Source provenance for a TOD estimation decision."""

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
# TOD Window
# ─────────────────────────────────────────────


class TODWindow(BaseModel):
    """
    A time-of-death window preserving uncertainty.

    Never collapses to a false exact value. Uses earliest/latest
    bounds and explicitly tracks precision and confidence.
    """

    earliest: str | None = None
    latest: str | None = None
    best_estimate: str | None = None
    window_hours: float | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    precision: TODPrecision = TODPrecision.UNKNOWN


# ─────────────────────────────────────────────
# Forensic Signal
# ─────────────────────────────────────────────


class ForensicSignal(BaseModel):
    """
    A raw forensic signal relevant to TOD estimation.

    Preserves the original text alongside its normalized
    interpretation, signal type classification, and provenance.
    """

    signal_id: str = ""
    signal_type: SignalType = SignalType.MEDICAL_EVIDENCE
    confidence_level: SignalConfidenceLevel = SignalConfidenceLevel.OBSERVED
    raw_text: str = ""
    normalized_value: str = ""
    tod_window: TODWindow = Field(default_factory=TODWindow)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    weight: float = Field(0.0, ge=0.0, le=1.0)
    evidence_file_id: str = ""
    entity_id: str = ""
    entity_type: str = ""
    provenance: TODProvenanceEntry = Field(
        default_factory=TODProvenanceEntry
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Signal Conflict
# ─────────────────────────────────────────────


class SignalConflict(BaseModel):
    """
    A detected conflict between two forensic signals.

    Two signals are in conflict when their TOD windows
    do not overlap and cannot be reconciled.
    """

    conflict_id: str = ""
    signal_a_id: str = ""
    signal_b_id: str = ""
    conflict_type: str = ""
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    description: str = ""
    window_a_summary: str = ""
    window_b_summary: str = ""
    resolution_hint: str = ""
    is_resolved: bool = False


# ─────────────────────────────────────────────
# TOD Candidate V2
# ─────────────────────────────────────────────


class TODCandidateV2(BaseModel):
    """
    An extended TOD candidate with full forensic reasoning.

    Supports multiple candidate windows rather than forcing
    a single exact timestamp. Each candidate carries its
    supporting signals, conflicting signals, confidence,
    and a human-readable rationale.
    """

    candidate_id: str = ""
    tod_window: TODWindow = Field(default_factory=TODWindow)
    estimation_method: str = ""
    supporting_signals: list[str] = Field(default_factory=list)
    conflicting_signals: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""
    provenance_entries: list[TODProvenanceEntry] = Field(
        default_factory=list
    )
    is_primary: bool = False
    rank: int = 0
    corroboration_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Reasoning Trace
# ─────────────────────────────────────────────


class ReasoningStep(BaseModel):
    """A single step in the TOD reasoning trace."""

    step_index: int = 0
    action: str = ""
    input_signals: list[str] = Field(default_factory=list)
    output: str = ""
    rationale: str = ""
    confidence_delta: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─────────────────────────────────────────────
# Confidence Scores
# ─────────────────────────────────────────────


class TODConfidenceScores(BaseModel):
    """Aggregate confidence metrics for the TOD estimation."""

    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    primary_candidate_confidence: float = Field(0.0, ge=0.0, le=1.0)
    signal_agreement_score: float = Field(0.0, ge=0.0, le=1.0)
    corroboration_bonus: float = 0.0
    conflict_penalty: float = 0.0
    missing_signal_penalty: float = 0.0
    total_signals: int = 0
    supporting_signal_count: int = 0
    conflicting_signal_count: int = 0


# ─────────────────────────────────────────────
# Final Hypothesis
# ─────────────────────────────────────────────


class FinalTODHypothesis(BaseModel):
    """
    The engine's best overall TOD hypothesis.

    This is NOT a forced exact value — it is the most
    plausible window with full uncertainty preserved.
    """

    hypothesis_id: str = ""
    tod_window: TODWindow = Field(default_factory=TODWindow)
    primary_candidate_id: str = ""
    supporting_candidate_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    summary: str = ""
    caveats: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Audit & Stage Reports
# ─────────────────────────────────────────────


class TODAuditEntry(BaseModel):
    """A single entry in the TOD estimation audit trail."""

    stage: str = ""
    action: str = ""
    signal_ids: list[str] = Field(default_factory=list)
    detail: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class TODStageReport(BaseModel):
    """Report for a single TOD estimation pipeline stage."""

    stage: str
    status: str = "completed"
    duration_ms: float = 0.0
    items_processed: int = 0
    detail: str = ""
    error: str | None = None


# ─────────────────────────────────────────────
# Top-Level Result
# ─────────────────────────────────────────────


class TODEstimationResult(BaseModel):
    """
    Top-level output of the TOD Estimation Engine.

    Contains all TOD candidates, the estimated window,
    confidence scores, supporting signals, signal conflicts,
    provenance map, reasoning trace, and final hypothesis.
    """

    schema_version: str = "1.0.0"
    case_id: str | None = None
    evidence_file_ids: list[str] = Field(default_factory=list)
    tod_candidates: list[TODCandidateV2] = Field(default_factory=list)
    estimated_window: TODWindow = Field(default_factory=TODWindow)
    confidence_scores: TODConfidenceScores = Field(
        default_factory=TODConfidenceScores
    )
    supporting_signals: list[ForensicSignal] = Field(default_factory=list)
    signal_conflicts: list[SignalConflict] = Field(default_factory=list)
    provenance_map: dict[str, list[TODProvenanceEntry]] = Field(
        default_factory=dict
    )
    reasoning_trace: list[ReasoningStep] = Field(default_factory=list)
    final_tod_hypothesis: FinalTODHypothesis = Field(
        default_factory=FinalTODHypothesis
    )
    audit_trail: list[TODAuditEntry] = Field(default_factory=list)
    stage_reports: list[TODStageReport] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
