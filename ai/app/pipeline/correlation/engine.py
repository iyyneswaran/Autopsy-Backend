"""
Atopsy — Evidence Correlation Engine (Layer 5).

Orchestrates cross-document entity correlation through a 7-stage
fault-tolerant pipeline. Consumes ForensicEntityGraph outputs from
Layer 4 and produces a CorrelationGraph with entity clusters,
relationship edges, contradictions, and evidence groups.

Does NOT mutate upstream records.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.pipeline.correlation.case_clusterer import CaseClusterer
from app.pipeline.correlation.contradiction_detector import ContradictionDetector
from app.pipeline.correlation.correlation_scoring import CorrelationScorer
from app.pipeline.correlation.entity_matcher import EntityMatcher
from app.pipeline.correlation.graph_builder import GraphBuilder
from app.pipeline.correlation.provenance_tracker import CorrelationProvenanceTracker
from app.pipeline.correlation.relationship_builder import RelationshipBuilder
from app.pipeline.correlation.schemas import (
    CorrelationAuditEntry,
    CorrelationGraph,
    CorrelationStageReport,
)
from app.pipeline.structuring.schemas import ForensicEntityGraph

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """
    Evidence Correlation Engine — Layer 5.

    7-stage pipeline:
      1. Entity Matching    — cross-document entity comparison
      2. Case Clustering    — group evidence by case/incident
      3. Relationship Build — infer causal/evidentiary/temporal links
      4. Contradiction Det. — detect conflicting assertions
      5. Scoring            — compute confidence summary
      6. Provenance Track   — assemble provenance map
      7. Graph Assembly     — build final CorrelationGraph

    Each stage is independently fault-tolerant.
    """

    def __init__(
        self,
        fuzzy_high_threshold: float = 0.85,
        fuzzy_low_threshold: float = 0.60,
        contradiction_threshold: float = 0.40,
    ) -> None:
        self._matcher = EntityMatcher(
            fuzzy_high=fuzzy_high_threshold,
            fuzzy_low=fuzzy_low_threshold,
        )
        self._clusterer = CaseClusterer()
        self._relationship_builder = RelationshipBuilder()
        self._contradiction_detector = ContradictionDetector(
            threshold=contradiction_threshold
        )
        self._scorer = CorrelationScorer()
        self._provenance_tracker = CorrelationProvenanceTracker()
        self._graph_builder = GraphBuilder()

    def correlate(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        case_id: str | None = None,
    ) -> CorrelationGraph:
        """
        Run the full correlation pipeline.

        Args:
            entity_graphs: List of (evidence_file_id, ForensicEntityGraph)
                           tuples from Layer 4.
            case_id: Optional case identifier for labeling.

        Returns:
            CorrelationGraph with all correlation results.
        """
        t_start = time.perf_counter()
        stage_reports: list[CorrelationStageReport] = []
        all_audit: list[CorrelationAuditEntry] = []
        evidence_file_ids = [eid for eid, _ in entity_graphs]

        logger.info(
            "Correlation engine starting: %d evidence files", len(entity_graphs)
        )

        # ── Stage 1: Entity Matching ─────────────────────
        edges, sr = self._run_stage(
            "entity_matching",
            lambda: self._matcher.match_entities(entity_graphs),
        )
        stage_reports.append(sr)
        all_audit.extend(self._matcher.audit_entries)

        # ── Stage 2: Case Clustering ─────────────────────
        cluster_result, sr = self._run_stage(
            "case_clustering",
            lambda: self._clusterer.cluster_by_case(entity_graphs, edges),
        )
        stage_reports.append(sr)
        all_audit.extend(self._clusterer.audit_entries)
        evidence_groups, entity_clusters = cluster_result or ([], [])

        # ── Stage 3: Relationship Building ───────────────
        inferred_edges, sr = self._run_stage(
            "relationship_building",
            lambda: self._relationship_builder.build_relationships(
                entity_graphs, edges, entity_clusters
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._relationship_builder.audit_entries)
        all_edges = edges + (inferred_edges or [])

        # ── Stage 4: Contradiction Detection ─────────────
        contradictions, sr = self._run_stage(
            "contradiction_detection",
            lambda: self._contradiction_detector.detect_contradictions(
                entity_graphs, all_edges, entity_clusters
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._contradiction_detector.audit_entries)
        contradictions = contradictions or []

        # ── Stage 5: Correlation Scoring ─────────────────
        confidence_summary, sr = self._run_stage(
            "correlation_scoring",
            lambda: self._scorer.score(
                all_edges, entity_clusters, contradictions, evidence_groups
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._scorer.audit_entries)

        # ── Stage 6: Provenance Tracking ─────────────────
        _, sr = self._run_stage(
            "provenance_tracking",
            lambda: self._track_provenance(all_edges, entity_clusters),
        )
        stage_reports.append(sr)
        all_audit.extend(self._provenance_tracker.audit_entries)

        # ── Stage 7: Graph Assembly ──────────────────────
        t_elapsed = (time.perf_counter() - t_start) * 1000

        from app.pipeline.correlation.schemas import ConfidenceSummary

        graph, sr = self._run_stage(
            "graph_assembly",
            lambda: self._graph_builder.build(
                evidence_file_ids=evidence_file_ids,
                edges=all_edges,
                clusters=entity_clusters,
                contradictions=contradictions,
                evidence_groups=evidence_groups,
                confidence_summary=confidence_summary or ConfidenceSummary(),
                provenance_map=self._provenance_tracker.provenance_map,
                audit_trail=all_audit,
                stage_reports=stage_reports,
                processing_time_ms=t_elapsed,
                case_id=case_id,
            ),
        )
        stage_reports.append(sr)

        if graph is None:
            # Catastrophic fallback: return minimal graph
            graph = CorrelationGraph(
                evidence_file_ids=evidence_file_ids,
                stage_reports=stage_reports,
                correlation_audit=all_audit,
                processing_time_ms=t_elapsed,
            )

        logger.info(
            "Correlation engine complete: %d edges, %d clusters, "
            "%d contradictions in %.1fms",
            len(all_edges),
            len(entity_clusters),
            len(contradictions),
            t_elapsed,
        )

        return graph

    def _track_provenance(
        self,
        edges: list,
        clusters: list,
    ) -> None:
        """Track provenance for edges and clusters."""
        self._provenance_tracker.track_edges(edges)
        self._provenance_tracker.track_clusters(clusters)

    def _run_stage(
        self,
        stage_name: str,
        fn: Any,
    ) -> tuple[Any, CorrelationStageReport]:
        """
        Run a pipeline stage with fault tolerance.

        Returns (result, stage_report). On failure, result is None
        and the stage report captures the error.
        """
        t0 = time.perf_counter()
        try:
            result = fn()
            elapsed = (time.perf_counter() - t0) * 1000
            report = CorrelationStageReport(
                stage=stage_name,
                status="completed",
                duration_ms=round(elapsed, 2),
                detail=f"Stage '{stage_name}' completed successfully",
            )
            logger.debug("Stage '%s' completed in %.1fms", stage_name, elapsed)
            return result, report

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error(
                "Stage '%s' failed: %s", stage_name, exc, exc_info=True
            )
            report = CorrelationStageReport(
                stage=stage_name,
                status="failed",
                duration_ms=round(elapsed, 2),
                detail=f"Stage '{stage_name}' failed",
                error=str(exc),
            )
            return None, report
