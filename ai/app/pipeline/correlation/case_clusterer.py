"""
Atopsy — Case Clusterer (Layer 5).

Groups evidence items by shared case identifiers, victim identities,
and incident references. Builds EvidenceGroup objects linking
FIR, autopsy, toxicology, and scene reports for the same case.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from app.pipeline.correlation.schemas import (
    ClusterStatus,
    CorrelationAuditEntry,
    CorrelationEdge,
    CorrelationEdgeType,
    EntityCluster,
    ClusterMember,
    EvidenceGroup,
    EvidenceGroupMember,
    MatchType,
)
from app.pipeline.structuring.schemas import ForensicEntityGraph, StructuredEntity

# Entity types that serve as case identifiers
CASE_LINKING_TYPES: set[str] = {
    "CASE_IDENTIFIER",
    "DECEASED_INFO",
}

# Sub-types for case linking
CASE_ID_SUBTYPES: set[str] = {
    "PM_NUMBER",
    "CASE_NUMBER",
    "MLC_NUMBER",
    "FIR_NUMBER",
}


def _entity_type_str(entity: StructuredEntity) -> str:
    """Get entity type as string."""
    return (
        entity.entity_type.value
        if hasattr(entity.entity_type, "value")
        else str(entity.entity_type)
    )


class CaseClusterer:
    """
    Groups evidence files into case clusters based on shared
    identifiers and victim information.

    Strategy:
    1. Extract case identifiers from each evidence file.
    2. Group files sharing identical case IDs (exact match).
    3. Group files sharing victim name/age/gender (fuzzy match).
    4. Merge overlapping groups into unified EvidenceGroups.
    """

    def __init__(self) -> None:
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    def cluster_by_case(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
        edges: list[CorrelationEdge],
    ) -> tuple[list[EvidenceGroup], list[EntityCluster]]:
        """
        Cluster evidence files by case and build entity clusters.

        Args:
            graphs: List of (evidence_file_id, graph) tuples.
            edges: Pre-computed correlation edges from EntityMatcher.

        Returns:
            Tuple of (evidence_groups, entity_clusters).
        """
        self._audit.clear()

        # Build evidence groups from case identifier edges
        evidence_groups = self._build_evidence_groups(graphs, edges)

        # Build entity clusters from edges
        entity_clusters = self._build_entity_clusters(graphs, edges)

        self._audit.append(
            CorrelationAuditEntry(
                stage="case_clustering",
                action="clustering_complete",
                detail=(
                    f"Formed {len(evidence_groups)} evidence groups "
                    f"and {len(entity_clusters)} entity clusters"
                ),
            )
        )

        return evidence_groups, entity_clusters

    def _build_evidence_groups(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
        edges: list[CorrelationEdge],
    ) -> list[EvidenceGroup]:
        """Build evidence groups from case-linking edges."""
        # Union-find to group evidence files
        parent: dict[str, str] = {}
        for efile_id, _ in graphs:
            parent[efile_id] = efile_id

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Union evidence files connected by case/person edges
        case_edge_types = {
            CorrelationEdgeType.SAME_CASE,
            CorrelationEdgeType.SAME_PERSON,
            CorrelationEdgeType.SAME_INCIDENT,
        }
        for edge in edges:
            if (
                edge.edge_type in case_edge_types
                and edge.match_type != MatchType.CONFLICTING
                and edge.confidence >= 0.5
            ):
                if (
                    edge.source_evidence_id in parent
                    and edge.target_evidence_id in parent
                ):
                    union(edge.source_evidence_id, edge.target_evidence_id)

        # Gather groups
        groups_map: dict[str, list[str]] = defaultdict(list)
        for efile_id in parent:
            groups_map[find(efile_id)].append(efile_id)

        # Build EvidenceGroup objects
        graph_map = {eid: g for eid, g in graphs}
        evidence_groups: list[EvidenceGroup] = []

        for root, member_ids in groups_map.items():
            if len(member_ids) < 2:
                continue

            # Find case identifier for labeling
            case_label = self._find_case_label(member_ids, graph_map)

            members: list[EvidenceGroupMember] = []
            for mid in member_ids:
                g = graph_map.get(mid)
                entity_count = g.metrics.total_entities if g else 0
                confidence = g.metrics.average_confidence if g else 0.0
                members.append(
                    EvidenceGroupMember(
                        evidence_file_id=mid,
                        document_type=self._infer_doc_type(g) if g else "unknown",
                        entity_count=entity_count,
                        confidence=confidence,
                    )
                )

            avg_conf = (
                sum(m.confidence for m in members) / len(members)
                if members
                else 0.0
            )
            evidence_groups.append(
                EvidenceGroup(
                    group_id=str(uuid.uuid4()),
                    case_identifier=case_label,
                    group_label=f"Case: {case_label}" if case_label else f"Evidence Group ({len(members)} files)",
                    members=members,
                    linking_entities=[],
                    confidence=round(avg_conf, 4),
                    rationale=f"Grouped by shared case identifiers across {len(members)} evidence files",
                )
            )

            self._audit.append(
                CorrelationAuditEntry(
                    stage="case_clustering",
                    action="evidence_group_formed",
                    evidence_file_ids=member_ids,
                    detail=f"Group '{case_label}' with {len(members)} members",
                    confidence=avg_conf,
                )
            )

        return evidence_groups

    def _build_entity_clusters(
        self,
        graphs: list[tuple[str, ForensicEntityGraph]],
        edges: list[CorrelationEdge],
    ) -> list[EntityCluster]:
        """Build entity clusters from correlated edges."""
        # Group edges by entity pairs into clusters
        # Use union-find on entity IDs
        parent: dict[str, str] = {}
        entity_info: dict[str, tuple[str, StructuredEntity]] = {}

        # Collect all entities
        for efile_id, graph in graphs:
            for etype_key, entity_list in graph.entities.items():
                for entity in entity_list:
                    parent[entity.entity_id] = entity.entity_id
                    entity_info[entity.entity_id] = (efile_id, entity)

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Union matched entities (skip conflicting)
        for edge in edges:
            if (
                edge.match_type != MatchType.CONFLICTING
                and edge.confidence >= 0.4
                and edge.source_entity_id in parent
                and edge.target_entity_id in parent
            ):
                union(edge.source_entity_id, edge.target_entity_id)

        # Gather clusters
        cluster_map: dict[str, list[str]] = defaultdict(list)
        for eid in parent:
            cluster_map[find(eid)].append(eid)

        clusters: list[EntityCluster] = []
        for root, member_ids in cluster_map.items():
            if len(member_ids) < 2:
                continue

            # Build cluster
            members: list[ClusterMember] = []
            efile_ids: set[str] = set()
            confidences: list[float] = []
            entity_type = ""

            for mid in member_ids:
                info = entity_info.get(mid)
                if not info:
                    continue
                efile_id, entity = info
                entity_type = _entity_type_str(entity)
                efile_ids.add(efile_id)
                confidences.append(entity.confidence)
                members.append(
                    ClusterMember(
                        entity_id=entity.entity_id,
                        evidence_file_id=efile_id,
                        entity_type=entity_type,
                        canonical_value=entity.canonical_value,
                        raw_value=entity.raw_value,
                        confidence=entity.confidence,
                        extraction_method=entity.provenance.extraction_method,
                    )
                )

            if not members:
                continue

            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            # Determine status
            has_conflict = any(
                e.match_type == MatchType.CONFLICTING
                and (
                    e.source_entity_id in member_ids
                    or e.target_entity_id in member_ids
                )
                for e in edges
            )
            if has_conflict:
                status = ClusterStatus.CONFLICTED
            elif avg_conf >= 0.8:
                status = ClusterStatus.CONFIRMED
            elif avg_conf >= 0.6:
                status = ClusterStatus.PROBABLE
            else:
                status = ClusterStatus.TENTATIVE

            # Canonical label: highest-confidence member's value
            best = max(members, key=lambda m: m.confidence)

            clusters.append(
                EntityCluster(
                    cluster_id=str(uuid.uuid4()),
                    canonical_label=best.canonical_value,
                    entity_type=entity_type,
                    status=status,
                    members=members,
                    confidence=round(avg_conf, 4),
                    rationale=f"Clustered {len(members)} {entity_type} entities across {len(efile_ids)} documents",
                    evidence_file_ids=sorted(efile_ids),
                )
            )

        self._audit.append(
            CorrelationAuditEntry(
                stage="case_clustering",
                action="entity_clusters_built",
                detail=f"Built {len(clusters)} entity clusters",
            )
        )

        return clusters

    def _find_case_label(
        self,
        evidence_ids: list[str],
        graph_map: dict[str, ForensicEntityGraph],
    ) -> str:
        """Find the best case identifier label for a group."""
        for eid in evidence_ids:
            graph = graph_map.get(eid)
            if not graph:
                continue
            case_entities = graph.entities.get("CASE_IDENTIFIER", [])
            for entity in case_entities:
                if entity.canonical_value:
                    return entity.canonical_value
        return "UNKNOWN"

    def _infer_doc_type(self, graph: ForensicEntityGraph) -> str:
        """Infer document type from entity distribution."""
        types_found = set(graph.entities.keys())
        if "INTERNAL_EXAMINATION" in types_found or "ORGAN_FINDING" in types_found:
            return "autopsy_report"
        if "TOXICOLOGY_FINDING" in types_found and len(types_found) <= 3:
            return "toxicology_report"
        if "SCENE_REFERENCE" in types_found:
            return "scene_report"
        if "CASE_IDENTIFIER" in types_found:
            return "fir_document"
        return "forensic_document"
