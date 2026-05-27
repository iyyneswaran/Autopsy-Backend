"""
Atopsy — Evidence Correlation Engine Schemas (Layer 5).

Pydantic models for the cross-document correlation graph output.
Covers entity clusters, correlation edges, contradictions, evidence
groups, provenance, confidence, and the top-level CorrelationGraph.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class MatchType(str, enum.Enum):
    """Classification of how two entities were matched."""

    EXACT = "EXACT"
    FUZZY = "FUZZY"
    INFERRED = "INFERRED"
    CONFLICTING = "CONFLICTING"


class CorrelationEdgeType(str, enum.Enum):
    """Types of relationships discovered during correlation."""

    SAME_PERSON = "SAME_PERSON"
    SAME_CASE = "SAME_CASE"
    SAME_INCIDENT = "SAME_INCIDENT"
    SAME_LOCATION = "SAME_LOCATION"
    SAME_INJURY = "SAME_INJURY"
    SAME_SUBSTANCE = "SAME_SUBSTANCE"
    SAME_EXAMINER = "SAME_EXAMINER"
    SAME_EVENT = "SAME_EVENT"
    CAUSAL_LINK = "CAUSAL_LINK"
    TEMPORAL_LINK = "TEMPORAL_LINK"
    EVIDENTIARY_LINK = "EVIDENTIARY_LINK"
    CROSS_REFERENCE = "CROSS_REFERENCE"


class ContradictionSeverity(str, enum.Enum):
    """Severity of a detected contradiction."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ClusterStatus(str, enum.Enum):
    """Status of an entity cluster."""

    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    TENTATIVE = "TENTATIVE"
    CONFLICTED = "CONFLICTED"


# ─────────────────────────────────────────────
# Provenance
# ─────────────────────────────────────────────


class ProvenanceEntry(BaseModel):
    """Source provenance for a correlation decision."""

    evidence_file_id: str = ""
    entity_id: str = ""
    entity_type: str = ""
    document_source: str = ""
    page: int | None = None
    raw_text: str = ""
    canonical_value: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    extraction_method: str = ""


# ─────────────────────────────────────────────
# Correlation Edge
# ─────────────────────────────────────────────


class CorrelationEdge(BaseModel):
    """
    A weighted link between two entities across documents.

    Every edge carries match type, confidence, rationale,
    and full source provenance for both endpoints.
    """

    edge_id: str = ""
    source_entity_id: str = ""
    target_entity_id: str = ""
    source_evidence_id: str = ""
    target_evidence_id: str = ""
    edge_type: CorrelationEdgeType = CorrelationEdgeType.CROSS_REFERENCE
    match_type: MatchType = MatchType.EXACT
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    weight: float = Field(1.0, ge=0.0)
    rationale: str = ""
    similarity_score: float = Field(0.0, ge=0.0, le=1.0)
    source_provenance: ProvenanceEntry = Field(default_factory=ProvenanceEntry)
    target_provenance: ProvenanceEntry = Field(default_factory=ProvenanceEntry)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─────────────────────────────────────────────
# Entity Cluster
# ─────────────────────────────────────────────


class ClusterMember(BaseModel):
    """A single entity member within a cluster."""

    entity_id: str = ""
    evidence_file_id: str = ""
    entity_type: str = ""
    canonical_value: str = ""
    raw_value: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    extraction_method: str = ""


class EntityCluster(BaseModel):
    """
    A group of entities from different documents believed
    to represent the same real-world entity.
    """

    cluster_id: str = ""
    canonical_label: str = ""
    entity_type: str = ""
    status: ClusterStatus = ClusterStatus.TENTATIVE
    members: list[ClusterMember] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_file_ids: list[str] = Field(default_factory=list)
    internal_edges: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Contradiction
# ─────────────────────────────────────────────


class ContradictionSource(BaseModel):
    """One side of a contradiction."""

    entity_id: str = ""
    evidence_file_id: str = ""
    value: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    raw_text: str = ""
    page: int | None = None


class Contradiction(BaseModel):
    """
    A detected conflict between two entity assertions
    across documents or within the same document.
    """

    contradiction_id: str = ""
    entity_type: str = ""
    field: str = ""
    severity: ContradictionSeverity = ContradictionSeverity.MEDIUM
    description: str = ""
    source_a: ContradictionSource = Field(default_factory=ContradictionSource)
    source_b: ContradictionSource = Field(default_factory=ContradictionSource)
    resolution_hint: str = ""
    is_resolved: bool = False
    resolved_value: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Evidence Group
# ─────────────────────────────────────────────


class EvidenceGroupMember(BaseModel):
    """An evidence file within a group."""

    evidence_file_id: str = ""
    document_type: str = ""
    original_filename: str = ""
    entity_count: int = 0
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class EvidenceGroup(BaseModel):
    """
    Evidence items linked to the same case or incident.
    Groups FIR, autopsy, toxicology, photos for a single case.
    """

    group_id: str = ""
    case_identifier: str = ""
    group_label: str = ""
    members: list[EvidenceGroupMember] = Field(default_factory=list)
    linking_entities: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""


# ─────────────────────────────────────────────
# Confidence Summary
# ─────────────────────────────────────────────


class ConfidenceSummary(BaseModel):
    """Aggregate confidence metrics for the correlation output."""

    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    average_edge_confidence: float = Field(0.0, ge=0.0, le=1.0)
    average_cluster_confidence: float = Field(0.0, ge=0.0, le=1.0)
    exact_match_count: int = 0
    fuzzy_match_count: int = 0
    inferred_match_count: int = 0
    conflicting_match_count: int = 0
    total_edges: int = 0
    total_clusters: int = 0
    total_contradictions: int = 0
    high_confidence_edges: int = 0
    low_confidence_edges: int = 0


# ─────────────────────────────────────────────
# Audit Trail
# ─────────────────────────────────────────────


class CorrelationAuditEntry(BaseModel):
    """A single entry in the correlation audit trail."""

    stage: str = ""
    action: str = ""
    entity_ids: list[str] = Field(default_factory=list)
    evidence_file_ids: list[str] = Field(default_factory=list)
    match_type: str = ""
    detail: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─────────────────────────────────────────────
# Stage Report
# ─────────────────────────────────────────────


class CorrelationStageReport(BaseModel):
    """Report for a single correlation pipeline stage."""

    stage: str
    status: str = "completed"
    duration_ms: float = 0.0
    items_processed: int = 0
    detail: str = ""
    error: str | None = None


# ─────────────────────────────────────────────
# Top-Level Correlation Graph
# ─────────────────────────────────────────────


class CorrelationGraph(BaseModel):
    """
    Top-level output of the Evidence Correlation Engine.

    Contains the full correlation result: entity clusters,
    relationship edges, contradictions, evidence groups,
    confidence summary, provenance map, and audit trail.
    """

    schema_version: str = "1.0.0"
    case_id: str | None = None
    evidence_file_ids: list[str] = Field(default_factory=list)
    correlation_graph: dict[str, list[CorrelationEdge]] = Field(
        default_factory=dict
    )
    entity_clusters: list[EntityCluster] = Field(default_factory=list)
    relationship_edges: list[CorrelationEdge] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    confidence_summary: ConfidenceSummary = Field(
        default_factory=ConfidenceSummary
    )
    provenance_map: dict[str, list[ProvenanceEntry]] = Field(
        default_factory=dict
    )
    correlation_audit: list[CorrelationAuditEntry] = Field(
        default_factory=list
    )
    stage_reports: list[CorrelationStageReport] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
