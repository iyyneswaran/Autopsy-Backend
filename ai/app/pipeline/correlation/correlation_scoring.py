"""
Atopsy — Correlation Scoring (Layer 5).

Confidence scoring for correlation edges, clusters, and overall graph.
Aggregates per-edge and per-cluster confidence into a ConfidenceSummary.
"""

from __future__ import annotations

from app.pipeline.correlation.schemas import (
    ConfidenceSummary,
    CorrelationAuditEntry,
    CorrelationEdge,
    Contradiction,
    EntityCluster,
    EvidenceGroup,
    MatchType,
)

# ─────────────────────────────────────────────
# Scoring weights
# ─────────────────────────────────────────────

MATCH_TYPE_WEIGHTS: dict[str, float] = {
    MatchType.EXACT.value: 1.0,
    MatchType.FUZZY.value: 0.8,
    MatchType.INFERRED.value: 0.6,
    MatchType.CONFLICTING.value: 0.2,
}

HIGH_CONFIDENCE_THRESHOLD: float = 0.75
LOW_CONFIDENCE_THRESHOLD: float = 0.40


class CorrelationScorer:
    """
    Aggregates confidence metrics across the correlation graph.

    Produces a ConfidenceSummary with overall statistics,
    match type distribution, and edge/cluster counts.
    """

    def __init__(self) -> None:
        self._audit: list[CorrelationAuditEntry] = []

    @property
    def audit_entries(self) -> list[CorrelationAuditEntry]:
        return list(self._audit)

    def score(
        self,
        edges: list[CorrelationEdge],
        clusters: list[EntityCluster],
        contradictions: list[Contradiction],
        evidence_groups: list[EvidenceGroup],
    ) -> ConfidenceSummary:
        """
        Compute aggregate confidence summary.

        Args:
            edges: All correlation edges.
            clusters: All entity clusters.
            contradictions: All detected contradictions.
            evidence_groups: All evidence groups.

        Returns:
            ConfidenceSummary with aggregate metrics.
        """
        self._audit.clear()

        # Edge statistics
        exact = sum(1 for e in edges if e.match_type == MatchType.EXACT)
        fuzzy = sum(1 for e in edges if e.match_type == MatchType.FUZZY)
        inferred = sum(1 for e in edges if e.match_type == MatchType.INFERRED)
        conflicting = sum(
            1 for e in edges if e.match_type == MatchType.CONFLICTING
        )
        high_conf = sum(
            1 for e in edges if e.confidence >= HIGH_CONFIDENCE_THRESHOLD
        )
        low_conf = sum(
            1 for e in edges if e.confidence < LOW_CONFIDENCE_THRESHOLD
        )

        # Average confidences
        avg_edge = (
            sum(e.confidence for e in edges) / len(edges) if edges else 0.0
        )
        avg_cluster = (
            sum(c.confidence for c in clusters) / len(clusters)
            if clusters
            else 0.0
        )

        # Overall confidence: weighted combination
        # Penalize for contradictions, reward for high-confidence edges
        contradiction_penalty = min(
            0.3, len(contradictions) * 0.05
        )
        overall = max(0.0, (avg_edge * 0.6 + avg_cluster * 0.4) - contradiction_penalty)

        summary = ConfidenceSummary(
            overall_confidence=round(overall, 4),
            average_edge_confidence=round(avg_edge, 4),
            average_cluster_confidence=round(avg_cluster, 4),
            exact_match_count=exact,
            fuzzy_match_count=fuzzy,
            inferred_match_count=inferred,
            conflicting_match_count=conflicting,
            total_edges=len(edges),
            total_clusters=len(clusters),
            total_contradictions=len(contradictions),
            high_confidence_edges=high_conf,
            low_confidence_edges=low_conf,
        )

        self._audit.append(
            CorrelationAuditEntry(
                stage="correlation_scoring",
                action="scoring_complete",
                detail=(
                    f"Overall confidence: {overall:.4f} | "
                    f"Edges: {len(edges)} (exact={exact}, fuzzy={fuzzy}, "
                    f"inferred={inferred}, conflicting={conflicting}) | "
                    f"Clusters: {len(clusters)} | "
                    f"Contradictions: {len(contradictions)}"
                ),
                confidence=overall,
            )
        )

        return summary

    def rescore_edge(self, edge: CorrelationEdge) -> float:
        """
        Rescore a single edge using match-type weighting.

        Returns the adjusted confidence.
        """
        weight = MATCH_TYPE_WEIGHTS.get(
            edge.match_type.value
            if hasattr(edge.match_type, "value")
            else str(edge.match_type),
            0.5,
        )
        return round(edge.confidence * weight, 4)
