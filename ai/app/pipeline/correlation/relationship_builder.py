"""
Atopsy — Relationship Builder (Layer 5).

Builds typed relationship edges between correlated entities.
Augments raw entity-matcher edges with inferred relationships
such as causal links (injury → cause of death), evidentiary links
(toxicology → manner of death), and temporal links.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.pipeline.correlation.schemas import (
    CorrelationAuditEntry,
    CorrelationEdge,
    CorrelationEdgeType,
    EntityCluster,
    MatchType,
    ProvenanceEntry,
)
from app.pipeline.structuring.schemas import ForensicEntityGraph, StructuredEntity

# ─────────────────────────────────────────────
# Inferred relationship rules
# ─────────────────────────────────────────────

# (source_type, target_type) → edge_type for inferred relationships
INFERRED_RULES: list[tuple[str, str, CorrelationEdgeType]] = [
    ("INJURY", "CAUSE_OF_DEATH", CorrelationEdgeType.CAUSAL_LINK),
    ("TOXICOLOGY_FINDING", "CAUSE_OF_DEATH", CorrelationEdgeType.CAUSAL_LINK),
    ("TOXICOLOGY_FINDING", "MANNER_OF_DEATH", CorrelationEdgeType.EVIDENTIARY_LINK),
    ("INJURY", "ANATOMICAL_REFERENCE", CorrelationEdgeType.EVIDENTIARY_LINK),
    ("ORGAN_FINDING", "CAUSE_OF_DEATH", CorrelationEdgeType.CAUSAL_LINK),
    ("TIME_OF_DEATH", "CAUSE_OF_DEATH", CorrelationEdgeType.TEMPORAL_LINK),
    ("EXAMINER", "CASE_IDENTIFIER", CorrelationEdgeType.EVIDENTIARY_LINK),
    ("SCENE_REFERENCE", "CASE_IDENTIFIER", CorrelationEdgeType.EVIDENTIARY_LINK),
    ("DECEASED_INFO", "CASE_IDENTIFIER", CorrelationEdgeType.SAME_CASE),
]


def _entity_type_str(entity: StructuredEntity) -> str:
    return (
        entity.entity_type.value
        if hasattr(entity.entity_type, "value")
        else str(entity.entity_type)
    )


class RelationshipBuilder:
    """
    Builds inter-entity relationship edges beyond direct matching.

    Augments the correlation graph with:
    - Inferred causal links (injuries → COD)
    - Evidentiary links (toxicology → MOD)
    - Temporal links (TOD → examination)
    - Cross-document relationships within entity clusters
    """

    def __init__(self) -> None:
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    def build_relationships(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
        existing_edges: list[CorrelationEdge],
        clusters: list[EntityCluster],
    ) -> list[CorrelationEdge]:
        """
        Build additional relationship edges from entity graphs.

        Args:
            graphs: Source entity graphs with evidence IDs.
            existing_edges: Already-established correlation edges.
            clusters: Entity clusters from case clustering.

        Returns:
            New inferred relationship edges.
        """
        self._audit.clear()
        new_edges: list[CorrelationEdge] = []

        # Track existing edge pairs to avoid duplicates
        existing_pairs: set[tuple[str, str]] = set()
        for edge in existing_edges:
            existing_pairs.add(
                (edge.source_entity_id, edge.target_entity_id)
            )
            existing_pairs.add(
                (edge.target_entity_id, edge.source_entity_id)
            )

        # Infer cross-type relationships within each document
        for efile_id, graph in graphs:
            inferred = self._infer_within_document(
                efile_id, graph, existing_pairs
            )
            new_edges.extend(inferred)

        # Infer relationships across documents using clusters
        cross_doc = self._infer_across_clusters(
            graphs, clusters, existing_pairs
        )
        new_edges.extend(cross_doc)

        self._audit.append(
            CorrelationAuditEntry(
                stage="relationship_building",
                action="build_complete",
                detail=f"Built {len(new_edges)} inferred relationship edges",
            )
        )

        return new_edges

    def _infer_within_document(
        self,
        efile_id: str,
        graph: ForensicEntityGraph,
        existing_pairs: set[tuple[str, str]],
    ) -> list[CorrelationEdge]:
        """Infer relationships between entity types within a single document."""
        edges: list[CorrelationEdge] = []

        for src_type, tgt_type, edge_type in INFERRED_RULES:
            src_entities = graph.entities.get(src_type, [])
            tgt_entities = graph.entities.get(tgt_type, [])

            for src in src_entities:
                for tgt in tgt_entities:
                    pair = (src.entity_id, tgt.entity_id)
                    if pair in existing_pairs:
                        continue

                    conf = min(src.confidence, tgt.confidence) * 0.7
                    edge = CorrelationEdge(
                        edge_id=str(uuid.uuid4()),
                        source_entity_id=src.entity_id,
                        target_entity_id=tgt.entity_id,
                        source_evidence_id=efile_id,
                        target_evidence_id=efile_id,
                        edge_type=edge_type,
                        match_type=MatchType.INFERRED,
                        confidence=round(conf, 4),
                        weight=0.7,
                        rationale=(
                            f"Inferred {edge_type.value}: "
                            f"{src_type}('{src.canonical_value}') → "
                            f"{tgt_type}('{tgt.canonical_value}') "
                            f"within same document"
                        ),
                        similarity_score=0.0,
                        source_provenance=ProvenanceEntry(
                            evidence_file_id=efile_id,
                            entity_id=src.entity_id,
                            entity_type=_entity_type_str(src),
                            canonical_value=src.canonical_value,
                            confidence=src.confidence,
                        ),
                        target_provenance=ProvenanceEntry(
                            evidence_file_id=efile_id,
                            entity_id=tgt.entity_id,
                            entity_type=_entity_type_str(tgt),
                            canonical_value=tgt.canonical_value,
                            confidence=tgt.confidence,
                        ),
                    )
                    edges.append(edge)
                    existing_pairs.add(pair)

        if edges:
            self._audit.append(
                CorrelationAuditEntry(
                    stage="relationship_building",
                    action="intra_document_inference",
                    evidence_file_ids=[efile_id],
                    match_type=MatchType.INFERRED.value,
                    detail=f"Inferred {len(edges)} relationships within document {efile_id[:8]}...",
                )
            )

        return edges

    def _infer_across_clusters(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
        clusters: list[EntityCluster],
        existing_pairs: set[tuple[str, str]],
    ) -> list[CorrelationEdge]:
        """Infer relationships across documents using entity clusters."""
        edges: list[CorrelationEdge] = []
        graph_map = {eid: g for eid, g in graphs}

        # For each cluster, link members that share the same case
        for cluster in clusters:
            if len(cluster.members) < 2:
                continue

            # Build cross-member edges within the cluster
            for i, member_a in enumerate(cluster.members):
                for member_b in cluster.members[i + 1 :]:
                    if member_a.evidence_file_id == member_b.evidence_file_id:
                        continue

                    pair = (member_a.entity_id, member_b.entity_id)
                    if pair in existing_pairs:
                        continue

                    conf = (
                        min(member_a.confidence, member_b.confidence)
                        * cluster.confidence
                    )

                    edge = CorrelationEdge(
                        edge_id=str(uuid.uuid4()),
                        source_entity_id=member_a.entity_id,
                        target_entity_id=member_b.entity_id,
                        source_evidence_id=member_a.evidence_file_id,
                        target_evidence_id=member_b.evidence_file_id,
                        edge_type=CorrelationEdgeType.CROSS_REFERENCE,
                        match_type=MatchType.INFERRED,
                        confidence=round(conf, 4),
                        weight=0.6,
                        rationale=(
                            f"Cross-document link via cluster '{cluster.canonical_label}': "
                            f"'{member_a.canonical_value}' ↔ '{member_b.canonical_value}'"
                        ),
                        similarity_score=0.0,
                        source_provenance=ProvenanceEntry(
                            evidence_file_id=member_a.evidence_file_id,
                            entity_id=member_a.entity_id,
                            entity_type=member_a.entity_type,
                            canonical_value=member_a.canonical_value,
                            confidence=member_a.confidence,
                        ),
                        target_provenance=ProvenanceEntry(
                            evidence_file_id=member_b.evidence_file_id,
                            entity_id=member_b.entity_id,
                            entity_type=member_b.entity_type,
                            canonical_value=member_b.canonical_value,
                            confidence=member_b.confidence,
                        ),
                    )
                    edges.append(edge)
                    existing_pairs.add(pair)

        if edges:
            self._audit.append(
                CorrelationAuditEntry(
                    stage="relationship_building",
                    action="cross_document_inference",
                    match_type=MatchType.INFERRED.value,
                    detail=f"Inferred {len(edges)} cross-document relationships via {len(clusters)} clusters",
                )
            )

        return edges
