"""
Atopsy — Graph Builder (Layer 5).

Assembles the final CorrelationGraph from all correlation components:
edges, clusters, contradictions, evidence groups, confidence summary,
provenance map, and audit trail.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from app.pipeline.correlation.schemas import (
    ConfidenceSummary,
    Contradiction,
    CorrelationAuditEntry,
    CorrelationEdge,
    CorrelationGraph,
    CorrelationStageReport,
    EntityCluster,
    EvidenceGroup,
    ProvenanceEntry,
)


class GraphBuilder:
    """
    Assembles the final CorrelationGraph.

    Organizes edges into a graph structure keyed by evidence file ID,
    attaches clusters, contradictions, evidence groups, and metadata.
    """

    def __init__(self) -> None:
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    def build(
        self,
        evidence_file_ids: list[str],
        edges: list[CorrelationEdge],
        clusters: list[EntityCluster],
        contradictions: list[Contradiction],
        evidence_groups: list[EvidenceGroup],
        confidence_summary: ConfidenceSummary,
        provenance_map: dict[str, list[ProvenanceEntry]],
        audit_trail: list[CorrelationAuditEntry],
        stage_reports: list[CorrelationStageReport],
        processing_time_ms: float,
        case_id: str | None = None,
    ) -> CorrelationGraph:
        """
        Build the final CorrelationGraph.

        Args:
            evidence_file_ids: All evidence files processed.
            edges: All correlation edges.
            clusters: All entity clusters.
            contradictions: All detected contradictions.
            evidence_groups: All evidence groups.
            confidence_summary: Aggregate confidence.
            provenance_map: Full provenance index.
            audit_trail: Collected audit entries.
            stage_reports: Per-stage reports.
            processing_time_ms: Total processing time.
            case_id: Optional case identifier.

        Returns:
            Complete CorrelationGraph.
        """
        # Build graph dict: edges grouped by source evidence file
        correlation_graph: dict[str, list[CorrelationEdge]] = defaultdict(list)
        for edge in edges:
            correlation_graph[edge.source_evidence_id].append(edge)

        graph = CorrelationGraph(
            schema_version="1.0.0",
            case_id=case_id,
            evidence_file_ids=sorted(evidence_file_ids),
            correlation_graph=dict(correlation_graph),
            entity_clusters=clusters,
            relationship_edges=edges,
            contradictions=contradictions,
            evidence_groups=evidence_groups,
            confidence_summary=confidence_summary,
            provenance_map=provenance_map,
            correlation_audit=audit_trail,
            stage_reports=stage_reports,
            processing_time_ms=processing_time_ms,
            processed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._audit.append(
            CorrelationAuditEntry(
                stage="graph_building",
                action="graph_assembled",
                evidence_file_ids=sorted(evidence_file_ids),
                detail=(
                    f"Graph assembled: {len(edges)} edges, "
                    f"{len(clusters)} clusters, "
                    f"{len(contradictions)} contradictions, "
                    f"{len(evidence_groups)} evidence groups"
                ),
                confidence=confidence_summary.overall_confidence,
            )
        )

        return graph

    def merge_incremental(
        self,
        existing: CorrelationGraph,
        new_edges: list[CorrelationEdge],
        new_clusters: list[EntityCluster],
        new_contradictions: list[Contradiction],
        new_evidence_ids: list[str],
    ) -> CorrelationGraph:
        """
        Incrementally merge new correlation results into an existing graph.

        Supports incremental updates when new evidence arrives
        without full reprocessing.

        Args:
            existing: The existing CorrelationGraph.
            new_edges: New edges to add.
            new_clusters: New clusters to merge.
            new_contradictions: New contradictions.
            new_evidence_ids: New evidence file IDs.

        Returns:
            Updated CorrelationGraph.
        """
        # Merge edges
        all_edges = list(existing.relationship_edges) + new_edges

        # Merge evidence IDs
        all_ids = sorted(
            set(existing.evidence_file_ids) | set(new_evidence_ids)
        )

        # Merge clusters (naive append — future: merge overlapping)
        all_clusters = list(existing.entity_clusters) + new_clusters

        # Merge contradictions
        all_contradictions = list(existing.contradictions) + new_contradictions

        # Rebuild graph dict
        correlation_graph: dict[str, list[CorrelationEdge]] = defaultdict(list)
        for edge in all_edges:
            correlation_graph[edge.source_evidence_id].append(edge)

        # Update counts in confidence summary
        summary = existing.confidence_summary.model_copy()
        summary.total_edges = len(all_edges)
        summary.total_clusters = len(all_clusters)
        summary.total_contradictions = len(all_contradictions)

        existing.correlation_graph = dict(correlation_graph)
        existing.entity_clusters = all_clusters
        existing.relationship_edges = all_edges
        existing.contradictions = all_contradictions
        existing.evidence_file_ids = all_ids
        existing.confidence_summary = summary
        existing.processed_at = datetime.now(timezone.utc).isoformat()

        self._audit.append(
            CorrelationAuditEntry(
                stage="graph_building",
                action="incremental_merge",
                evidence_file_ids=new_evidence_ids,
                detail=(
                    f"Merged {len(new_edges)} new edges, "
                    f"{len(new_clusters)} new clusters from "
                    f"{len(new_evidence_ids)} new evidence files"
                ),
            )
        )

        return existing
