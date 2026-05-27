"""
Atopsy — Temporal Intelligence Engine (Layer 6).

Orchestrates forensic timeline construction through a 7-stage
fault-tolerant pipeline. Consumes ForensicEntityGraph and
CorrelationGraph outputs to produce a ForensicTimeline.

Does NOT mutate upstream records.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.pipeline.correlation.schemas import CorrelationGraph
from app.pipeline.structuring.schemas import ForensicEntityGraph
from app.pipeline.temporal.confidence_aggregator import (
    TemporalConfidenceAggregator,
)
from app.pipeline.temporal.event_orderer import EventOrderer
from app.pipeline.temporal.interval_normalizer import IntervalNormalizer
from app.pipeline.temporal.relative_time_resolver import RelativeTimeResolver
from app.pipeline.temporal.schemas import (
    ForensicTimeline,
    TemporalAuditEntry,
    TemporalStageReport,
    TimeWindow,
)
from app.pipeline.temporal.temporal_contradiction_detector import (
    TemporalContradictionDetector,
)
from app.pipeline.temporal.timeline_builder import TimelineBuilder
from app.pipeline.temporal.tod_estimator import TODEstimator

logger = logging.getLogger(__name__)


class TemporalEngine:
    """
    Temporal Intelligence Engine — Layer 6.

    7-stage pipeline:
      1. Event Construction  — build temporal events from entities
      2. Interval Normalization — normalize time intervals/ranges
      3. Relative Resolution — resolve relative times to windows
      4. Event Ordering      — order events temporally
      5. Contradiction Det.  — detect temporal impossibilities
      6. TOD Estimation      — produce time-of-death candidates
      7. Confidence & Assembly — score and build ForensicTimeline

    Each stage is independently fault-tolerant.
    """

    def __init__(
        self,
        anchor_datetime: datetime | None = None,
    ) -> None:
        self._timeline_builder = TimelineBuilder()
        self._interval_normalizer = IntervalNormalizer()
        self._relative_resolver = RelativeTimeResolver()
        self._event_orderer = EventOrderer()
        self._contradiction_detector = TemporalContradictionDetector()
        self._tod_estimator = TODEstimator()
        self._confidence_aggregator = TemporalConfidenceAggregator()
        self._anchor_datetime = anchor_datetime

    def build_timeline(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        correlation_graph: CorrelationGraph | None = None,
        case_id: str | None = None,
    ) -> ForensicTimeline:
        """
        Run the full temporal intelligence pipeline.

        Args:
            entity_graphs: List of (evidence_file_id, ForensicEntityGraph)
                           tuples from Layer 4.
            correlation_graph: Optional CorrelationGraph from Layer 5.
            case_id: Optional case identifier.

        Returns:
            ForensicTimeline with all temporal results.
        """
        t_start = time.perf_counter()
        stage_reports: list[TemporalStageReport] = []
        all_audit: list[TemporalAuditEntry] = []
        evidence_file_ids = [eid for eid, _ in entity_graphs]

        logger.info(
            "Temporal engine starting: %d evidence files", len(entity_graphs)
        )

        # ── Stage 1: Event Construction ──────────────────
        events, sr = self._run_stage(
            "event_construction",
            lambda: self._timeline_builder.build_events(
                entity_graphs, correlation_graph
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._timeline_builder.audit_entries)
        events = events or []

        # ── Stage 2: Interval Normalization ──────────────
        all_expressions = []
        for evt in events:
            all_expressions.extend(evt.temporal_expressions)

        uncertainty_ranges, sr = self._run_stage(
            "interval_normalization",
            lambda: self._interval_normalizer.normalize_intervals(
                all_expressions
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._interval_normalizer.audit_entries)
        uncertainty_ranges = uncertainty_ranges or []

        # ── Stage 3: Relative Time Resolution ────────────
        resolved_events, sr = self._run_stage(
            "relative_time_resolution",
            lambda: self._relative_resolver.resolve(
                events, self._anchor_datetime
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._relative_resolver.audit_entries)
        events = resolved_events or events

        # ── Stage 4: Event Ordering ──────────────────────
        order_result, sr = self._run_stage(
            "event_ordering",
            lambda: self._event_orderer.order_events(events),
        )
        stage_reports.append(sr)
        all_audit.extend(self._event_orderer.audit_entries)
        event_order, temporal_relations = order_result or ([], [])

        # ── Stage 5: Contradiction Detection ─────────────
        conflicts, sr = self._run_stage(
            "temporal_contradiction_detection",
            lambda: self._contradiction_detector.detect(
                events, temporal_relations, event_order
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._contradiction_detector.audit_entries)
        conflicts = conflicts or []

        # ── Stage 6: TOD Estimation ──────────────────────
        tod_candidates, sr = self._run_stage(
            "tod_estimation",
            lambda: self._tod_estimator.estimate(events, uncertainty_ranges),
        )
        stage_reports.append(sr)
        all_audit.extend(self._tod_estimator.audit_entries)
        tod_candidates = tod_candidates or []

        # ── Stage 7: Confidence & Assembly ───────────────
        overall_confidence, sr = self._run_stage(
            "confidence_aggregation",
            lambda: self._confidence_aggregator.aggregate(
                events,
                temporal_relations,
                conflicts,
                tod_candidates,
                uncertainty_ranges,
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._confidence_aggregator.audit_entries)
        overall_confidence = overall_confidence or 0.0

        t_elapsed = (time.perf_counter() - t_start) * 1000

        # Collect all unique time windows
        time_windows = [
            e.time_window for e in events
            if e.time_window.best_estimate
            or e.time_window.earliest
            or e.time_window.latest
        ]

        # Sort timeline events by event_order
        order_map = {eid: i for i, eid in enumerate(event_order)}
        sorted_events = sorted(
            events,
            key=lambda e: order_map.get(e.event_id, len(events)),
        )

        timeline = ForensicTimeline(
            schema_version="1.0.0",
            case_id=case_id,
            evidence_file_ids=sorted(evidence_file_ids),
            timeline=sorted_events,
            temporal_events=events,
            event_order=event_order,
            time_windows=time_windows,
            uncertainty_ranges=uncertainty_ranges,
            temporal_relations=temporal_relations,
            tod_candidates=tod_candidates,
            temporal_conflicts=conflicts,
            temporal_audit=all_audit,
            stage_reports=stage_reports,
            processing_time_ms=round(t_elapsed, 2),
            processed_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "Temporal engine complete: %d events, %d relations, "
            "%d conflicts, %d TOD candidates in %.1fms",
            len(events),
            len(temporal_relations),
            len(conflicts),
            len(tod_candidates),
            t_elapsed,
        )

        return timeline

    def _run_stage(
        self,
        stage_name: str,
        fn: Any,
    ) -> tuple[Any, TemporalStageReport]:
        """
        Run a pipeline stage with fault tolerance.

        Returns (result, stage_report). On failure, result is None.
        """
        t0 = time.perf_counter()
        try:
            result = fn()
            elapsed = (time.perf_counter() - t0) * 1000
            report = TemporalStageReport(
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
            report = TemporalStageReport(
                stage=stage_name,
                status="failed",
                duration_ms=round(elapsed, 2),
                detail=f"Stage '{stage_name}' failed",
                error=str(exc),
            )
            return None, report
