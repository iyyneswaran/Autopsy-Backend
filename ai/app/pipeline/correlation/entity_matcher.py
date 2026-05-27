"""
Atopsy — Entity Matcher (Layer 5).

Cross-document entity matching: exact, fuzzy, inferred, and conflicting.
Uses canonical entity IDs and values from ForensicEntityGraph outputs.
Deterministic for exact matches; explainable similarity for fuzzy matches.
"""

from __future__ import annotations

import uuid
from difflib import SequenceMatcher
from typing import Any

from app.pipeline.correlation.schemas import (
    ClusterMember,
    CorrelationAuditEntry,
    CorrelationEdge,
    CorrelationEdgeType,
    MatchType,
    ProvenanceEntry,
)
from app.pipeline.structuring.schemas import (
    ForensicEntityGraph,
    StructuredEntity,
)

# ─────────────────────────────────────────────
# Match type thresholds
# ─────────────────────────────────────────────

EXACT_THRESHOLD: float = 1.0
FUZZY_HIGH_THRESHOLD: float = 0.85
FUZZY_LOW_THRESHOLD: float = 0.60

# Entity types eligible for cross-document matching
MATCHABLE_TYPES: set[str] = {
    "CASE_IDENTIFIER",
    "DECEASED_INFO",
    "CAUSE_OF_DEATH",
    "MANNER_OF_DEATH",
    "TIME_OF_DEATH",
    "EXAMINER",
    "TOXICOLOGY_FINDING",
    "INJURY",
    "SCENE_REFERENCE",
    "ANATOMICAL_REFERENCE",
    "ORGAN_FINDING",
}

# Map entity types to correlation edge types
_ENTITY_TO_EDGE: dict[str, CorrelationEdgeType] = {
    "CASE_IDENTIFIER": CorrelationEdgeType.SAME_CASE,
    "DECEASED_INFO": CorrelationEdgeType.SAME_PERSON,
    "CAUSE_OF_DEATH": CorrelationEdgeType.EVIDENTIARY_LINK,
    "MANNER_OF_DEATH": CorrelationEdgeType.EVIDENTIARY_LINK,
    "TIME_OF_DEATH": CorrelationEdgeType.TEMPORAL_LINK,
    "EXAMINER": CorrelationEdgeType.SAME_EXAMINER,
    "TOXICOLOGY_FINDING": CorrelationEdgeType.SAME_SUBSTANCE,
    "INJURY": CorrelationEdgeType.SAME_INJURY,
    "SCENE_REFERENCE": CorrelationEdgeType.SAME_LOCATION,
    "ANATOMICAL_REFERENCE": CorrelationEdgeType.EVIDENTIARY_LINK,
    "ORGAN_FINDING": CorrelationEdgeType.EVIDENTIARY_LINK,
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _normalize_for_comparison(value: str) -> str:
    """Normalize a value for case/whitespace-insensitive comparison."""
    return " ".join(value.lower().strip().split())


def _similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two strings."""
    na = _normalize_for_comparison(a)
    nb = _normalize_for_comparison(b)
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _make_provenance(
    entity: StructuredEntity, evidence_file_id: str
) -> ProvenanceEntry:
    """Build a ProvenanceEntry from a StructuredEntity."""
    return ProvenanceEntry(
        evidence_file_id=evidence_file_id,
        entity_id=entity.entity_id,
        entity_type=entity.entity_type.value
        if hasattr(entity.entity_type, "value")
        else str(entity.entity_type),
        canonical_value=entity.canonical_value,
        raw_text=entity.raw_value,
        confidence=entity.confidence,
        extraction_method=entity.provenance.extraction_method,
        page=entity.provenance.document_page,
    )


def _make_cluster_member(
    entity: StructuredEntity, evidence_file_id: str
) -> ClusterMember:
    """Build a ClusterMember from a StructuredEntity."""
    return ClusterMember(
        entity_id=entity.entity_id,
        evidence_file_id=evidence_file_id,
        entity_type=entity.entity_type.value
        if hasattr(entity.entity_type, "value")
        else str(entity.entity_type),
        canonical_value=entity.canonical_value,
        raw_value=entity.raw_value,
        confidence=entity.confidence,
        extraction_method=entity.provenance.extraction_method,
    )


# ─────────────────────────────────────────────
# Entity Matcher
# ─────────────────────────────────────────────


class EntityMatcher:
    """
    Cross-document entity matching engine.

    Compares entities from multiple ForensicEntityGraphs,
    producing CorrelationEdge results with match type classification.

    Supports:
    - Exact matching on canonical values
    - Fuzzy matching using sequence similarity
    - Sub-type aware matching (e.g., PM_NUMBER vs MLC_NUMBER)
    - Conflicting match detection
    """

    def __init__(
        self,
        fuzzy_high: float = FUZZY_HIGH_THRESHOLD,
        fuzzy_low: float = FUZZY_LOW_THRESHOLD,
    ) -> None:
        self.fuzzy_high = fuzzy_high
        self.fuzzy_low = fuzzy_low
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    def match_entities(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[CorrelationEdge]:
        """
        Match entities across multiple ForensicEntityGraphs.

        Args:
            graphs: List of (evidence_file_id, graph) tuples.

        Returns:
            List of CorrelationEdge objects representing matches.
        """
        self._audit.clear()
        edges: list[CorrelationEdge] = []

        # Flatten all entities with their source evidence ID
        entity_pool: list[tuple[str, StructuredEntity]] = []
        for efile_id, graph in graphs:
            for etype_key, entity_list in graph.entities.items():
                for entity in entity_list:
                    etype = (
                        entity.entity_type.value
                        if hasattr(entity.entity_type, "value")
                        else str(entity.entity_type)
                    )
                    if etype in MATCHABLE_TYPES:
                        entity_pool.append((efile_id, entity))

        # Pairwise comparison across different evidence files
        for i in range(len(entity_pool)):
            efile_a, entity_a = entity_pool[i]
            etype_a = (
                entity_a.entity_type.value
                if hasattr(entity_a.entity_type, "value")
                else str(entity_a.entity_type)
            )

            for j in range(i + 1, len(entity_pool)):
                efile_b, entity_b = entity_pool[j]
                etype_b = (
                    entity_b.entity_type.value
                    if hasattr(entity_b.entity_type, "value")
                    else str(entity_b.entity_type)
                )

                # Only compare same entity types
                if etype_a != etype_b:
                    continue

                # Skip same-document same-entity comparisons
                if (
                    efile_a == efile_b
                    and entity_a.entity_id == entity_b.entity_id
                ):
                    continue

                edge = self._compare_entities(
                    efile_a, entity_a, efile_b, entity_b
                )
                if edge is not None:
                    edges.append(edge)

        self._audit.append(
            CorrelationAuditEntry(
                stage="entity_matching",
                action="match_complete",
                detail=f"Produced {len(edges)} correlation edges from {len(entity_pool)} entities across {len(graphs)} documents",
                confidence=0.0,
            )
        )

        return edges

    def _compare_entities(
        self,
        efile_a: str,
        entity_a: StructuredEntity,
        efile_b: str,
        entity_b: StructuredEntity,
    ) -> CorrelationEdge | None:
        """Compare two entities and produce a CorrelationEdge if related."""
        sim = _similarity(entity_a.canonical_value, entity_b.canonical_value)

        if sim < self.fuzzy_low:
            # Check for conflicting match: same sub-type but very different values
            if (
                entity_a.sub_type
                and entity_a.sub_type == entity_b.sub_type
                and efile_a != efile_b
                and sim < 0.3
            ):
                return self._build_edge(
                    efile_a,
                    entity_a,
                    efile_b,
                    entity_b,
                    MatchType.CONFLICTING,
                    sim,
                    f"Conflicting values for {entity_a.sub_type}: "
                    f"'{entity_a.canonical_value}' vs '{entity_b.canonical_value}'",
                )
            return None

        if sim >= EXACT_THRESHOLD:
            match_type = MatchType.EXACT
            rationale = (
                f"Exact match on {entity_a.entity_type.value if hasattr(entity_a.entity_type, 'value') else entity_a.entity_type}: "
                f"'{entity_a.canonical_value}'"
            )
        elif sim >= self.fuzzy_high:
            match_type = MatchType.FUZZY
            rationale = (
                f"High-confidence fuzzy match ({sim:.2f}): "
                f"'{entity_a.canonical_value}' ≈ '{entity_b.canonical_value}'"
            )
        else:
            match_type = MatchType.FUZZY
            rationale = (
                f"Low-confidence fuzzy match ({sim:.2f}): "
                f"'{entity_a.canonical_value}' ~ '{entity_b.canonical_value}'"
            )

        return self._build_edge(
            efile_a, entity_a, efile_b, entity_b, match_type, sim, rationale
        )

    def _build_edge(
        self,
        efile_a: str,
        entity_a: StructuredEntity,
        efile_b: str,
        entity_b: StructuredEntity,
        match_type: MatchType,
        similarity: float,
        rationale: str,
    ) -> CorrelationEdge:
        """Construct a CorrelationEdge from matched entities."""
        etype = (
            entity_a.entity_type.value
            if hasattr(entity_a.entity_type, "value")
            else str(entity_a.entity_type)
        )
        edge_type = _ENTITY_TO_EDGE.get(
            etype, CorrelationEdgeType.CROSS_REFERENCE
        )

        # Confidence: combine source confidences with match quality
        conf = min(entity_a.confidence, entity_b.confidence) * similarity

        edge = CorrelationEdge(
            edge_id=str(uuid.uuid4()),
            source_entity_id=entity_a.entity_id,
            target_entity_id=entity_b.entity_id,
            source_evidence_id=efile_a,
            target_evidence_id=efile_b,
            edge_type=edge_type,
            match_type=match_type,
            confidence=round(conf, 4),
            weight=round(similarity, 4),
            rationale=rationale,
            similarity_score=round(similarity, 4),
            source_provenance=_make_provenance(entity_a, efile_a),
            target_provenance=_make_provenance(entity_b, efile_b),
        )

        self._audit.append(
            CorrelationAuditEntry(
                stage="entity_matching",
                action=f"{match_type.value}_match",
                entity_ids=[entity_a.entity_id, entity_b.entity_id],
                evidence_file_ids=[efile_a, efile_b],
                match_type=match_type.value,
                detail=rationale,
                confidence=conf,
            )
        )

        return edge
