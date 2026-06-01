"""
Atopsy — Contradiction Rules (Layer 8).

Rule-based contradiction detection across entity types.
Each rule compares entities from correlation clusters and
entity graphs to detect conflicting assertions.
"""

from __future__ import annotations

import logging
import uuid
from difflib import SequenceMatcher
from typing import Any

from app.pipeline.correlation.schemas import (
    CorrelationGraph,
    EntityCluster,
)
from app.pipeline.structuring.schemas import (
    EntityType,
    ForensicEntityGraph,
    StructuredEntity,
)
from app.pipeline.anomaly_detection.schemas import (
    AnomalyProvenanceEntry,
    ContradictionFinding,
    FindingCategory,
    FindingSeverity,
    FindingSource,
    FindingType,
    AnomalyAuditEntry,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Entity type → finding category / severity
# ─────────────────────────────────────────────

_ENTITY_CATEGORY_MAP: dict[str, FindingCategory] = {
    "CASE_IDENTIFIER": FindingCategory.CASE_IDENTIFIER,
    "DECEASED_INFO": FindingCategory.IDENTITY,
    "CAUSE_OF_DEATH": FindingCategory.MEDICAL,
    "MANNER_OF_DEATH": FindingCategory.MEDICAL,
    "TIME_OF_DEATH": FindingCategory.TEMPORAL,
    "INJURY": FindingCategory.MEDICAL,
    "TOXICOLOGY_FINDING": FindingCategory.TOXICOLOGY,
    "SCENE_REFERENCE": FindingCategory.LOCATION,
    "EXAMINER": FindingCategory.EVIDENCE_INTEGRITY,
    "ORGAN_FINDING": FindingCategory.MEDICAL,
    "EXTERNAL_EXAMINATION": FindingCategory.MEDICAL,
    "INTERNAL_EXAMINATION": FindingCategory.MEDICAL,
}

_ENTITY_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "CAUSE_OF_DEATH": FindingSeverity.CRITICAL,
    "MANNER_OF_DEATH": FindingSeverity.CRITICAL,
    "TIME_OF_DEATH": FindingSeverity.HIGH,
    "DECEASED_INFO": FindingSeverity.HIGH,
    "CASE_IDENTIFIER": FindingSeverity.HIGH,
    "INJURY": FindingSeverity.MEDIUM,
    "TOXICOLOGY_FINDING": FindingSeverity.MEDIUM,
    "SCENE_REFERENCE": FindingSeverity.MEDIUM,
    "ORGAN_FINDING": FindingSeverity.MEDIUM,
    "EXAMINER": FindingSeverity.LOW,
    "EXTERNAL_EXAMINATION": FindingSeverity.LOW,
    "INTERNAL_EXAMINATION": FindingSeverity.LOW,
}

# Similarity threshold below which values are contradictory
_CONTRADICTION_THRESHOLD = 0.40

# Entity types that should be singleton per case (only one value)
_SINGLETON_TYPES: set[str] = {
    "CAUSE_OF_DEATH",
    "MANNER_OF_DEATH",
    "TIME_OF_DEATH",
}


class ContradictionRules:
    """
    Rule-based contradiction detection across entity types.

    Detects:
    - Cross-document entity value conflicts
    - Singleton entity contradictions (COD, MOD, TOD)
    - Intra-cluster value conflicts
    - Sub-type specific contradictions (name, age, gender)
    """

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def detect(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        correlation_graph: CorrelationGraph | None = None,
    ) -> list[ContradictionFinding]:
        """
        Detect contradictions across entity graphs.

        Args:
            entity_graphs: (evidence_file_id, ForensicEntityGraph) pairs.
            correlation_graph: Optional correlated entity clusters.

        Returns:
            List of contradiction findings.
        """
        self._audit.clear()
        findings: list[ContradictionFinding] = []

        # 1. Cross-document singleton contradictions
        findings.extend(
            self._detect_singleton_contradictions(entity_graphs)
        )

        # 2. Cluster-based contradictions
        if correlation_graph:
            findings.extend(
                self._detect_cluster_contradictions(correlation_graph)
            )

        # 3. Cross-document identity contradictions
        findings.extend(
            self._detect_identity_contradictions(entity_graphs)
        )

        # 4. Import Layer 5 contradictions (if not already covered)
        if correlation_graph and correlation_graph.contradictions:
            findings.extend(
                self._import_layer5_contradictions(correlation_graph)
            )

        self._audit.append(
            AnomalyAuditEntry(
                stage="contradiction_detection",
                action="detection_complete",
                finding_ids=[f.finding_id for f in findings],
                detail=f"Detected {len(findings)} contradictions",
            )
        )

        return findings

    def _detect_singleton_contradictions(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[ContradictionFinding]:
        """Detect contradictions in singleton entity types across docs."""
        findings: list[ContradictionFinding] = []

        # Collect all entities by type across documents
        type_entities: dict[str, list[tuple[str, StructuredEntity]]] = {}

        for evidence_id, graph in entity_graphs:
            for entity_type_key, entities in graph.entities.items():
                if entity_type_key not in _SINGLETON_TYPES:
                    continue
                if entity_type_key not in type_entities:
                    type_entities[entity_type_key] = []
                for entity in entities:
                    type_entities[entity_type_key].append(
                        (evidence_id, entity)
                    )

        # Compare across documents
        for entity_type, entity_pairs in type_entities.items():
            for i, (eid_a, ent_a) in enumerate(entity_pairs):
                for eid_b, ent_b in entity_pairs[i + 1:]:
                    if eid_a == eid_b:
                        continue  # Same document

                    val_a = (
                        ent_a.canonical_value or ent_a.raw_value or ""
                    ).strip()
                    val_b = (
                        ent_b.canonical_value or ent_b.raw_value or ""
                    ).strip()

                    if not val_a or not val_b:
                        continue

                    similarity = SequenceMatcher(
                        None,
                        val_a.lower(),
                        val_b.lower(),
                    ).ratio()

                    if similarity < _CONTRADICTION_THRESHOLD:
                        findings.append(
                            self._build_contradiction(
                                entity_type=entity_type,
                                field=entity_type,
                                eid_a=eid_a,
                                ent_a=ent_a,
                                val_a=val_a,
                                eid_b=eid_b,
                                ent_b=ent_b,
                                val_b=val_b,
                                similarity=similarity,
                                rule_id="SINGLETON_CROSS_DOC",
                            )
                        )

        return findings

    def _detect_cluster_contradictions(
        self,
        correlation_graph: CorrelationGraph,
    ) -> list[ContradictionFinding]:
        """Detect contradictions within entity clusters."""
        findings: list[ContradictionFinding] = []

        for cluster in correlation_graph.entity_clusters:
            if cluster.status.value != "CONFLICTED":
                continue

            members = cluster.members
            for i, ma in enumerate(members):
                for mb in members[i + 1:]:
                    val_a = (
                        ma.canonical_value or ma.raw_value or ""
                    ).strip()
                    val_b = (
                        mb.canonical_value or mb.raw_value or ""
                    ).strip()

                    if not val_a or not val_b:
                        continue

                    similarity = SequenceMatcher(
                        None, val_a.lower(), val_b.lower()
                    ).ratio()

                    if similarity < _CONTRADICTION_THRESHOLD:
                        findings.append(
                            ContradictionFinding(
                                finding_id=str(uuid.uuid4()),
                                finding_type=FindingType.CONTRADICTION,
                                category=_ENTITY_CATEGORY_MAP.get(
                                    cluster.entity_type,
                                    FindingCategory.EVIDENCE_INTEGRITY,
                                ),
                                severity=_ENTITY_SEVERITY_MAP.get(
                                    cluster.entity_type,
                                    FindingSeverity.MEDIUM,
                                ),
                                title=(
                                    f"Cluster contradiction: "
                                    f"{cluster.entity_type}"
                                ),
                                description=(
                                    f"Conflicting values in cluster "
                                    f"'{cluster.canonical_label}': "
                                    f"'{val_a}' vs '{val_b}'"
                                ),
                                field=cluster.entity_type,
                                value_a=val_a,
                                value_b=val_b,
                                source_a=FindingSource(
                                    entity_id=ma.entity_id,
                                    evidence_file_id=ma.evidence_file_id,
                                    value=val_a,
                                    confidence=ma.confidence,
                                ),
                                source_b=FindingSource(
                                    entity_id=mb.entity_id,
                                    evidence_file_id=mb.evidence_file_id,
                                    value=val_b,
                                    confidence=mb.confidence,
                                ),
                                similarity_score=round(similarity, 3),
                                affected_entity_ids=[
                                    ma.entity_id, mb.entity_id
                                ],
                                affected_evidence_ids=[
                                    ma.evidence_file_id,
                                    mb.evidence_file_id,
                                ],
                                rule_id="CLUSTER_CONFLICT",
                                confidence=max(
                                    ma.confidence, mb.confidence
                                ),
                                resolution_hint=(
                                    "Review source documents for the "
                                    "conflicted cluster"
                                ),
                            )
                        )

        return findings

    def _detect_identity_contradictions(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[ContradictionFinding]:
        """Detect name/age/gender contradictions for deceased info."""
        findings: list[ContradictionFinding] = []

        deceased_entities: list[tuple[str, StructuredEntity]] = []
        for evidence_id, graph in entity_graphs:
            for entity in graph.entities.get("DECEASED_INFO", []):
                deceased_entities.append((evidence_id, entity))

        # Compare sub_type-matched pairs (name vs name, age vs age)
        subtype_groups: dict[str, list[tuple[str, StructuredEntity]]] = {}
        for eid, ent in deceased_entities:
            st = (ent.sub_type or "general").lower()
            if st not in subtype_groups:
                subtype_groups[st] = []
            subtype_groups[st].append((eid, ent))

        for subtype, pairs in subtype_groups.items():
            for i, (eid_a, ent_a) in enumerate(pairs):
                for eid_b, ent_b in pairs[i + 1:]:
                    if eid_a == eid_b:
                        continue

                    val_a = (
                        ent_a.canonical_value or ent_a.raw_value or ""
                    ).strip()
                    val_b = (
                        ent_b.canonical_value or ent_b.raw_value or ""
                    ).strip()

                    if not val_a or not val_b:
                        continue

                    similarity = SequenceMatcher(
                        None, val_a.lower(), val_b.lower()
                    ).ratio()

                    if similarity < _CONTRADICTION_THRESHOLD:
                        findings.append(
                            self._build_contradiction(
                                entity_type="DECEASED_INFO",
                                field=f"deceased_{subtype}",
                                eid_a=eid_a,
                                ent_a=ent_a,
                                val_a=val_a,
                                eid_b=eid_b,
                                ent_b=ent_b,
                                val_b=val_b,
                                similarity=similarity,
                                rule_id=f"IDENTITY_{subtype.upper()}",
                            )
                        )

        return findings

    def _import_layer5_contradictions(
        self,
        correlation_graph: CorrelationGraph,
    ) -> list[ContradictionFinding]:
        """Import contradictions already detected by Layer 5."""
        findings: list[ContradictionFinding] = []

        for contra in correlation_graph.contradictions:
            findings.append(
                ContradictionFinding(
                    finding_id=str(uuid.uuid4()),
                    finding_type=FindingType.CONTRADICTION,
                    category=_ENTITY_CATEGORY_MAP.get(
                        contra.entity_type,
                        FindingCategory.EVIDENCE_INTEGRITY,
                    ),
                    severity=FindingSeverity(contra.severity.value),
                    title=(
                        f"Layer 5 contradiction: {contra.entity_type}"
                    ),
                    description=contra.description,
                    field=contra.field,
                    value_a=contra.source_a.value,
                    value_b=contra.source_b.value,
                    source_a=FindingSource(
                        entity_id=contra.source_a.entity_id,
                        evidence_file_id=contra.source_a.evidence_file_id,
                        value=contra.source_a.value,
                        confidence=contra.source_a.confidence,
                        raw_text=contra.source_a.raw_text,
                        page=contra.source_a.page,
                    ),
                    source_b=FindingSource(
                        entity_id=contra.source_b.entity_id,
                        evidence_file_id=contra.source_b.evidence_file_id,
                        value=contra.source_b.value,
                        confidence=contra.source_b.confidence,
                        raw_text=contra.source_b.raw_text,
                        page=contra.source_b.page,
                    ),
                    affected_entity_ids=[
                        contra.source_a.entity_id,
                        contra.source_b.entity_id,
                    ],
                    affected_evidence_ids=[
                        contra.source_a.evidence_file_id,
                        contra.source_b.evidence_file_id,
                    ],
                    rule_id="LAYER5_IMPORT",
                    confidence=max(
                        contra.source_a.confidence,
                        contra.source_b.confidence,
                    ),
                    resolution_hint=contra.resolution_hint,
                    is_resolved=contra.is_resolved,
                    metadata={"layer5_contradiction_id": contra.contradiction_id},
                )
            )

        return findings

    def _build_contradiction(
        self,
        entity_type: str,
        field: str,
        eid_a: str,
        ent_a: StructuredEntity,
        val_a: str,
        eid_b: str,
        ent_b: StructuredEntity,
        val_b: str,
        similarity: float,
        rule_id: str,
    ) -> ContradictionFinding:
        """Build a standard contradiction finding."""
        return ContradictionFinding(
            finding_id=str(uuid.uuid4()),
            finding_type=FindingType.CONTRADICTION,
            category=_ENTITY_CATEGORY_MAP.get(
                entity_type, FindingCategory.EVIDENCE_INTEGRITY
            ),
            severity=_ENTITY_SEVERITY_MAP.get(
                entity_type, FindingSeverity.MEDIUM
            ),
            title=f"Contradicting {entity_type} across documents",
            description=(
                f"'{val_a}' (from {eid_a}) contradicts "
                f"'{val_b}' (from {eid_b})"
            ),
            field=field,
            value_a=val_a,
            value_b=val_b,
            source_a=FindingSource(
                entity_id=ent_a.entity_id,
                evidence_file_id=eid_a,
                value=val_a,
                confidence=ent_a.confidence,
                raw_text=ent_a.raw_value or "",
            ),
            source_b=FindingSource(
                entity_id=ent_b.entity_id,
                evidence_file_id=eid_b,
                value=val_b,
                confidence=ent_b.confidence,
                raw_text=ent_b.raw_value or "",
            ),
            similarity_score=round(similarity, 3),
            affected_entity_ids=[ent_a.entity_id, ent_b.entity_id],
            affected_evidence_ids=[eid_a, eid_b],
            rule_id=rule_id,
            confidence=max(ent_a.confidence, ent_b.confidence),
            resolution_hint=(
                "Review source documents and prefer higher-confidence value"
                if abs(ent_a.confidence - ent_b.confidence) > 0.2
                else "Manual review required — similar confidence levels"
            ),
        )
