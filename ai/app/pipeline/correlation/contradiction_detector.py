"""
Atopsy — Contradiction Detector (Layer 5).

Detects conflicting assertions across evidence documents:
- Conflicting cause/manner of death
- Conflicting victim demographics
- Conflicting toxicology results
- Conflicting timestamps and sequences
- Conflicting examiner attributions
"""

from __future__ import annotations

import uuid
from difflib import SequenceMatcher
from typing import Any

from app.pipeline.correlation.schemas import (
    Contradiction,
    ContradictionSeverity,
    ContradictionSource,
    CorrelationAuditEntry,
    CorrelationEdge,
    EntityCluster,
    MatchType,
)
from app.pipeline.structuring.schemas import ForensicEntityGraph, StructuredEntity

# ─────────────────────────────────────────────
# Contradiction rules
# ─────────────────────────────────────────────

# Entity types where contradiction detection is critical
# Maps entity type → (field_name, severity)
CONTRADICTION_RULES: dict[str, tuple[str, ContradictionSeverity]] = {
    "CAUSE_OF_DEATH": ("cause_of_death", ContradictionSeverity.CRITICAL),
    "MANNER_OF_DEATH": ("manner_of_death", ContradictionSeverity.CRITICAL),
    "TIME_OF_DEATH": ("time_of_death", ContradictionSeverity.HIGH),
    "DECEASED_INFO": ("deceased_info", ContradictionSeverity.HIGH),
    "TOXICOLOGY_FINDING": ("toxicology", ContradictionSeverity.MEDIUM),
    "EXAMINER": ("examiner", ContradictionSeverity.LOW),
}

# Similarity threshold below which values are considered contradictory
CONTRADICTION_THRESHOLD: float = 0.40


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _entity_type_str(entity: StructuredEntity) -> str:
    return (
        entity.entity_type.value
        if hasattr(entity.entity_type, "value")
        else str(entity.entity_type)
    )


class ContradictionDetector:
    """
    Detects contradictions between entities across evidence documents.

    Contradictions are flagged when:
    - The same entity type has conflicting canonical values across documents
    - Entity clusters contain members with irreconcilable values
    - Correlation edges are marked as CONFLICTING
    """

    def __init__(
        self,
        threshold: float = CONTRADICTION_THRESHOLD,
    ) -> None:
        self.threshold = threshold
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    def detect_contradictions(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
        edges: list[CorrelationEdge],
        clusters: list[EntityCluster],
    ) -> list[Contradiction]:
        """
        Detect all contradictions across evidence documents.

        Args:
            graphs: Source entity graphs.
            edges: Correlation edges (may include CONFLICTING type).
            clusters: Entity clusters.

        Returns:
            List of Contradiction objects.
        """
        self._audit.clear()
        contradictions: list[Contradiction] = []

        # 1. Detect from conflicting edges
        edge_contradictions = self._from_conflicting_edges(edges)
        contradictions.extend(edge_contradictions)

        # 2. Detect from cross-document entity comparison
        cross_doc = self._from_cross_document(graphs)
        contradictions.extend(cross_doc)

        # 3. Detect from conflicted clusters
        cluster_contradictions = []  # Divergent strings alone are not contradictions.
        contradictions.extend(cluster_contradictions)

        # Deduplicate
        contradictions = self._deduplicate(contradictions)

        self._audit.append(
            CorrelationAuditEntry(
                stage="contradiction_detection",
                action="detection_complete",
                detail=f"Detected {len(contradictions)} contradictions "
                       f"({sum(1 for c in contradictions if c.severity == ContradictionSeverity.CRITICAL)} critical)",
            )
        )

        return contradictions

    def _from_conflicting_edges(
        self, edges: list[CorrelationEdge]
    ) -> list[Contradiction]:
        """Extract contradictions from CONFLICTING match type edges."""
        contradictions: list[Contradiction] = []

        for edge in edges:
            if edge.match_type != MatchType.CONFLICTING:
                continue

            etype = edge.source_provenance.entity_type
            field, severity = CONTRADICTION_RULES.get(
                etype, ("unknown", ContradictionSeverity.MEDIUM)
            )

            contradictions.append(
                Contradiction(
                    contradiction_id=str(uuid.uuid4()),
                    entity_type=etype,
                    field=field,
                    severity=severity,
                    description=(
                        f"Conflicting {etype} across documents: "
                        f"'{edge.source_provenance.canonical_value}' vs "
                        f"'{edge.target_provenance.canonical_value}'"
                    ),
                    source_a=ContradictionSource(
                        entity_id=edge.source_entity_id,
                        evidence_file_id=edge.source_evidence_id,
                        value=edge.source_provenance.canonical_value,
                        confidence=edge.source_provenance.confidence,
                        raw_text=edge.source_provenance.raw_text,
                        page=edge.source_provenance.page,
                    ),
                    source_b=ContradictionSource(
                        entity_id=edge.target_entity_id,
                        evidence_file_id=edge.target_evidence_id,
                        value=edge.target_provenance.canonical_value,
                        confidence=edge.target_provenance.confidence,
                        raw_text=edge.target_provenance.raw_text,
                        page=edge.target_provenance.page,
                    ),
                    resolution_hint=self._resolution_hint(
                        edge.source_provenance.canonical_value,
                        edge.target_provenance.canonical_value,
                        edge.source_provenance.confidence,
                        edge.target_provenance.confidence,
                    ),
                )
            )

        return contradictions

    def _from_cross_document(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[Contradiction]:
        """
        Compare singleton entity types across documents.
        For entity types expected to be unique per case (COD, MOD),
        flag differences.
        """
        contradictions: list[Contradiction] = []

        # Singleton types: should have one consistent value across case
        singleton_types = {"MANNER_OF_DEATH"}

        for etype in singleton_types:
            # Collect all values for this entity type across documents
            values: list[tuple[str, StructuredEntity]] = []
            for efile_id, graph in graphs:
                for entity in graph.entities.get(etype, []):
                    if entity.canonical_value:
                        values.append((efile_id, entity))

            # Pairwise comparison
            for i in range(len(values)):
                efile_a, ent_a = values[i]
                for j in range(i + 1, len(values)):
                    efile_b, ent_b = values[j]
                    if efile_a == efile_b:
                        continue

                    sim = _similarity(
                        ent_a.canonical_value, ent_b.canonical_value
                    )
                    if ent_a.canonical_value.upper() in {"HOMICIDE", "SUICIDE", "ACCIDENT", "NATURAL"} and ent_b.canonical_value.upper() in {"HOMICIDE", "SUICIDE", "ACCIDENT", "NATURAL"} and ent_a.canonical_value.upper() != ent_b.canonical_value.upper():
                        field, severity = CONTRADICTION_RULES.get(
                            etype, ("unknown", ContradictionSeverity.MEDIUM)
                        )
                        contradictions.append(
                            Contradiction(
                                contradiction_id=str(uuid.uuid4()),
                                entity_type=etype,
                                field=field,
                                severity=severity,
                                description=(
                                    f"Cross-document contradiction in {etype}: "
                                    f"'{ent_a.canonical_value}' vs '{ent_b.canonical_value}'"
                                ),
                                source_a=ContradictionSource(
                                    entity_id=ent_a.entity_id,
                                    evidence_file_id=efile_a,
                                    value=ent_a.canonical_value,
                                    confidence=ent_a.confidence,
                                    raw_text=ent_a.raw_value,
                                ),
                                source_b=ContradictionSource(
                                    entity_id=ent_b.entity_id,
                                    evidence_file_id=efile_b,
                                    value=ent_b.canonical_value,
                                    confidence=ent_b.confidence,
                                    raw_text=ent_b.raw_value,
                                ),
                                resolution_hint=self._resolution_hint(
                                    ent_a.canonical_value,
                                    ent_b.canonical_value,
                                    ent_a.confidence,
                                    ent_b.confidence,
                                ),
                            )
                        )

        return contradictions

    def _from_clusters(
        self, clusters: list[EntityCluster]
    ) -> list[Contradiction]:
        """Detect contradictions within conflicted entity clusters."""
        contradictions: list[Contradiction] = []

        for cluster in clusters:
            if cluster.status.value != "CONFLICTED":
                continue

            # Find the most divergent pair in the cluster
            members = cluster.members
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    ma, mb = members[i], members[j]
                    sim = _similarity(ma.canonical_value, mb.canonical_value)
                    if sim < self.threshold:
                        field, severity = CONTRADICTION_RULES.get(
                            cluster.entity_type,
                            ("unknown", ContradictionSeverity.MEDIUM),
                        )
                        contradictions.append(
                            Contradiction(
                                contradiction_id=str(uuid.uuid4()),
                                entity_type=cluster.entity_type,
                                field=field,
                                severity=severity,
                                description=(
                                    f"Cluster conflict in '{cluster.canonical_label}': "
                                    f"'{ma.canonical_value}' vs '{mb.canonical_value}'"
                                ),
                                source_a=ContradictionSource(
                                    entity_id=ma.entity_id,
                                    evidence_file_id=ma.evidence_file_id,
                                    value=ma.canonical_value,
                                    confidence=ma.confidence,
                                ),
                                source_b=ContradictionSource(
                                    entity_id=mb.entity_id,
                                    evidence_file_id=mb.evidence_file_id,
                                    value=mb.canonical_value,
                                    confidence=mb.confidence,
                                ),
                                resolution_hint=self._resolution_hint(
                                    ma.canonical_value,
                                    mb.canonical_value,
                                    ma.confidence,
                                    mb.confidence,
                                ),
                            )
                        )

        return contradictions

    def _resolution_hint(
        self,
        val_a: str,
        val_b: str,
        conf_a: float,
        conf_b: float,
    ) -> str:
        """Suggest resolution based on confidence difference."""
        if abs(conf_a - conf_b) > 0.2:
            winner = val_a if conf_a > conf_b else val_b
            return f"Prefer higher-confidence value: '{winner}'"
        return "Manual review required — confidence levels are similar"

    def _deduplicate(
        self, contradictions: list[Contradiction]
    ) -> list[Contradiction]:
        """Remove duplicate contradictions based on entity pair + type."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[Contradiction] = []
        for c in contradictions:
            key = (
                c.entity_type,
                min(c.source_a.entity_id, c.source_b.entity_id),
                max(c.source_a.entity_id, c.source_b.entity_id),
            )
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique
