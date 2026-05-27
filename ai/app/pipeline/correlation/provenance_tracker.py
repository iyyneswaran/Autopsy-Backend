"""
Atopsy — Provenance Tracker (Layer 5).

Assembles and validates provenance chains for correlation decisions.
Every edge, cluster, and contradiction gets a full provenance trail
linking back to source documents, entities, and extraction methods.
"""

from __future__ import annotations

from collections import defaultdict

from app.pipeline.correlation.schemas import (
    CorrelationAuditEntry,
    CorrelationEdge,
    EntityCluster,
    ProvenanceEntry,
)


class CorrelationProvenanceTracker:
    """
    Manages provenance for all correlation outputs.

    Builds a provenance_map keyed by entity_id or edge_id,
    containing all source ProvenanceEntry records that contributed
    to a correlation decision.
    """

    def __init__(self) -> None:
        self._provenance_map: dict[str, list[ProvenanceEntry]] = defaultdict(
            list
        )
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    @property
    def provenance_map(self) -> dict[str, list[ProvenanceEntry]]:
        return dict(self._provenance_map)

    def track_edges(self, edges: list[CorrelationEdge]) -> None:
        """
        Record provenance for all correlation edges.

        Each edge contributes source and target provenance entries
        keyed by the edge ID.
        """
        for edge in edges:
            key = edge.edge_id
            self._provenance_map[key].append(edge.source_provenance)
            self._provenance_map[key].append(edge.target_provenance)

            # Also index by entity IDs for entity-level lookup
            self._provenance_map[edge.source_entity_id].append(
                edge.source_provenance
            )
            self._provenance_map[edge.target_entity_id].append(
                edge.target_provenance
            )

        self._audit.append(
            CorrelationAuditEntry(
                stage="provenance_tracking",
                action="edges_tracked",
                detail=f"Tracked provenance for {len(edges)} edges",
            )
        )

    def track_clusters(self, clusters: list[EntityCluster]) -> None:
        """
        Record provenance for all entity clusters.

        Each cluster's members contribute provenance entries
        keyed by the cluster ID.
        """
        for cluster in clusters:
            key = cluster.cluster_id
            for member in cluster.members:
                self._provenance_map[key].append(
                    ProvenanceEntry(
                        evidence_file_id=member.evidence_file_id,
                        entity_id=member.entity_id,
                        entity_type=member.entity_type,
                        canonical_value=member.canonical_value,
                        raw_text=member.raw_value,
                        confidence=member.confidence,
                        extraction_method=member.extraction_method,
                    )
                )

        self._audit.append(
            CorrelationAuditEntry(
                stage="provenance_tracking",
                action="clusters_tracked",
                detail=f"Tracked provenance for {len(clusters)} clusters",
            )
        )

    def get_provenance(self, key: str) -> list[ProvenanceEntry]:
        """Get all provenance entries for a given key (edge_id, entity_id, or cluster_id)."""
        return list(self._provenance_map.get(key, []))

    def get_evidence_files_for_entity(self, entity_id: str) -> list[str]:
        """Get all evidence file IDs that contributed to an entity's provenance."""
        entries = self._provenance_map.get(entity_id, [])
        return list({e.evidence_file_id for e in entries if e.evidence_file_id})

    def validate_provenance(self) -> list[str]:
        """
        Validate that all provenance entries have required fields.
        Returns list of warning messages.
        """
        warnings: list[str] = []
        for key, entries in self._provenance_map.items():
            for entry in entries:
                if not entry.evidence_file_id:
                    warnings.append(
                        f"Provenance entry for '{key}' missing evidence_file_id"
                    )
                if not entry.entity_id:
                    warnings.append(
                        f"Provenance entry for '{key}' missing entity_id"
                    )
        return warnings
