"""
Atopsy — TOD Estimation Engine (Layer 7).

Orchestrates forensic time-of-death estimation through a
7-stage fault-tolerant pipeline. Consumes ForensicEntityGraph,
CorrelationGraph, and ForensicTimeline outputs to produce a
TODEstimationResult with confidence-weighted candidates,
signal conflict detection, and full provenance.

Does NOT mutate upstream records.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.pipeline.correlation.schemas import CorrelationGraph
from app.pipeline.structuring.schemas import ForensicEntityGraph
from app.pipeline.temporal.schemas import (
    EventCategory,
    ForensicTimeline,
)
from app.pipeline.tod_estimation.candidate_ranker import CandidateRanker
from app.pipeline.tod_estimation.confidence_model import ConfidenceModel
from app.pipeline.tod_estimation.forensic_signal_weighter import (
    ForensicSignalWeighter,
)
from app.pipeline.tod_estimation.pmi_estimator import PMIEstimator
from app.pipeline.tod_estimation.provenance_tracker import ProvenanceTracker
from app.pipeline.tod_estimation.schemas import (
    FinalTODHypothesis,
    TODAuditEntry,
    TODEstimationResult,
    TODStageReport,
    TODWindow,
)
from app.pipeline.tod_estimation.tod_parser import TODParser
from app.pipeline.tod_estimation.tod_window_builder import TODWindowBuilder

logger = logging.getLogger(__name__)


class TODEstimationEngine:
    """
    TOD Estimation Engine — Layer 7.

    7-stage pipeline:
      1. Signal Extraction  — extract forensic signals from entities
      2. Window Building     — convert signals to TOD windows
      3. PMI Estimation      — dedicated PMI computation
      4. Signal Weighting    — assign reliability weights
      5. Candidate Ranking   — rank and select candidates
      6. Confidence Scoring  — compute confidence scores
      7. Provenance & Assembly — build final TODEstimationResult

    Each stage is independently fault-tolerant.
    """

    def __init__(self) -> None:
        self._parser = TODParser()
        self._window_builder = TODWindowBuilder()
        self._pmi_estimator = PMIEstimator()
        self._weighter = ForensicSignalWeighter()
        self._ranker = CandidateRanker()
        self._confidence_model = ConfidenceModel()
        self._provenance_tracker = ProvenanceTracker()

    def estimate(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        correlation_graph: CorrelationGraph | None = None,
        forensic_timeline: ForensicTimeline | None = None,
        case_id: str | None = None,
    ) -> TODEstimationResult:
        """
        Run the full TOD estimation pipeline.

        Args:
            entity_graphs: List of (evidence_file_id, ForensicEntityGraph)
                           tuples from Layer 4.
            correlation_graph: Optional CorrelationGraph from Layer 5.
            forensic_timeline: Optional ForensicTimeline from Layer 6.
            case_id: Optional case identifier.

        Returns:
            TODEstimationResult with all estimation outputs.
        """
        t_start = time.perf_counter()
        stage_reports: list[TODStageReport] = []
        all_audit: list[TODAuditEntry] = []
        evidence_file_ids = [eid for eid, _ in entity_graphs]

        logger.info(
            "TOD estimation engine starting: %d evidence files",
            len(entity_graphs),
        )

        # Determine examination time from timeline
        exam_time = self._find_examination_time(forensic_timeline)

        # ── Stage 1: Signal Extraction ────────────────────
        signals, sr = self._run_stage(
            "signal_extraction",
            lambda: self._parser.extract_signals(
                entity_graphs, forensic_timeline
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._parser.audit_entries)
        signals = signals or []

        # ── Stage 2: Window Building ──────────────────────
        signals_with_windows, sr = self._run_stage(
            "window_building",
            lambda: self._window_builder.build_windows(
                signals, exam_time
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._window_builder.audit_entries)
        signals = signals_with_windows or signals

        # ── Stage 3: PMI Estimation ───────────────────────
        ambient_temp = self._find_ambient_temp(signals)
        pmi_signals, sr = self._run_stage(
            "pmi_estimation",
            lambda: self._pmi_estimator.estimate(
                signals, exam_time, ambient_temp
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._pmi_estimator.audit_entries)
        signals = pmi_signals or signals

        # ── Stage 4: Signal Weighting ─────────────────────
        weighted_signals, sr = self._run_stage(
            "signal_weighting",
            lambda: self._weighter.weight_signals(signals),
        )
        stage_reports.append(sr)
        all_audit.extend(self._weighter.audit_entries)
        signals = weighted_signals or signals

        # ── Stage 5: Candidate Ranking ────────────────────
        rank_result, sr = self._run_stage(
            "candidate_ranking",
            lambda: self._ranker.rank(signals),
        )
        stage_reports.append(sr)
        all_audit.extend(self._ranker.audit_entries)
        candidates, conflicts = rank_result or ([], [])

        # ── Stage 6: Confidence Scoring ───────────────────
        confidence_scores, sr = self._run_stage(
            "confidence_scoring",
            lambda: self._confidence_model.compute(
                candidates, signals, conflicts
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._confidence_model.audit_entries)
        confidence_scores = confidence_scores or __import__(
            "app.pipeline.tod_estimation.schemas",
            fromlist=["TODConfidenceScores"],
        ).TODConfidenceScores()

        # ── Stage 7: Provenance & Assembly ────────────────
        provenance_result, sr = self._run_stage(
            "provenance_assembly",
            lambda: (
                self._provenance_tracker.build_provenance_map(
                    candidates, signals
                ),
                self._provenance_tracker.build_reasoning_trace(
                    signals, candidates, conflicts, confidence_scores
                ),
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._provenance_tracker.audit_entries)
        provenance_map, reasoning_trace = provenance_result or ({}, [])

        # Build final hypothesis
        final_hypothesis = self._build_final_hypothesis(
            candidates, confidence_scores
        )

        # Build estimated window from primary candidate
        primary = next(
            (c for c in candidates if c.is_primary), None
        )
        estimated_window = (
            primary.tod_window if primary else TODWindow()
        )

        t_elapsed = (time.perf_counter() - t_start) * 1000

        result = TODEstimationResult(
            schema_version="1.0.0",
            case_id=case_id,
            evidence_file_ids=sorted(evidence_file_ids),
            tod_candidates=candidates,
            estimated_window=estimated_window,
            confidence_scores=confidence_scores,
            supporting_signals=signals,
            signal_conflicts=conflicts,
            provenance_map=provenance_map,
            reasoning_trace=reasoning_trace,
            final_tod_hypothesis=final_hypothesis,
            audit_trail=all_audit,
            stage_reports=stage_reports,
            processing_time_ms=round(t_elapsed, 2),
            processed_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "TOD estimation complete: %d signals, %d candidates, "
            "%d conflicts in %.1fms",
            len(signals),
            len(candidates),
            len(conflicts),
            t_elapsed,
        )

        return result

    def _find_examination_time(
        self, timeline: ForensicTimeline | None
    ) -> datetime | None:
        """Find the examination event timestamp from the timeline."""
        if not timeline:
            return None

        for event in timeline.temporal_events:
            if event.category == EventCategory.EXAMINATION:
                tw = event.time_window
                best = tw.best_estimate or tw.earliest
                if best:
                    try:
                        dt = datetime.fromisoformat(best)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except (ValueError, TypeError):
                        continue

        return None

    def _find_ambient_temp(
        self, signals: list[Any]
    ) -> float | None:
        """
        Attempt to extract ambient temperature from
        environmental signals.
        """
        import re

        for signal in signals:
            if getattr(signal, "signal_type", None) and \
               signal.signal_type.value == "ENVIRONMENTAL":
                text = signal.raw_text or signal.normalized_value or ""
                # Try to find temperature values
                match = re.search(
                    r"(\d+(?:\.\d+)?)\s*°?\s*[Cc](?:elsius)?",
                    text,
                )
                if match:
                    try:
                        return float(match.group(1))
                    except (ValueError, TypeError):
                        continue

        return None

    def _build_final_hypothesis(
        self,
        candidates: list[Any],
        confidence_scores: Any,
    ) -> FinalTODHypothesis:
        """Build the final TOD hypothesis from ranked candidates."""
        primary = next(
            (c for c in candidates if c.is_primary), None
        )

        if not primary:
            return FinalTODHypothesis(
                hypothesis_id=str(uuid.uuid4()),
                summary="Insufficient evidence for TOD estimation",
                caveats=["No usable forensic signals with TOD windows found"],
            )

        caveats: list[str] = []
        if confidence_scores.conflict_penalty > 0:
            caveats.append(
                f"Conflicting signals detected "
                f"(penalty: {confidence_scores.conflict_penalty:.3f})"
            )
        if confidence_scores.missing_signal_penalty > 0:
            caveats.append(
                f"Some expected signal types are missing "
                f"(penalty: {confidence_scores.missing_signal_penalty:.3f})"
            )
        if primary.tod_window.window_hours and primary.tod_window.window_hours > 24:
            caveats.append(
                f"TOD window is broad "
                f"({primary.tod_window.window_hours:.1f} hours)"
            )

        supporting_ids = [
            c.candidate_id
            for c in candidates
            if not c.is_primary
            and c.confidence > 0.3
        ]

        return FinalTODHypothesis(
            hypothesis_id=str(uuid.uuid4()),
            tod_window=primary.tod_window,
            primary_candidate_id=primary.candidate_id,
            supporting_candidate_ids=supporting_ids,
            confidence=confidence_scores.overall_confidence,
            summary=(
                f"Best TOD estimate: "
                f"{primary.tod_window.earliest or '?'} to "
                f"{primary.tod_window.latest or '?'} "
                f"(confidence: {confidence_scores.overall_confidence:.3f})"
            ),
            caveats=caveats,
        )

    def _run_stage(
        self,
        stage_name: str,
        fn: Any,
    ) -> tuple[Any, TODStageReport]:
        """
        Run a pipeline stage with fault tolerance.

        Returns (result, stage_report). On failure, result is None.
        """
        t0 = time.perf_counter()
        try:
            result = fn()
            elapsed = (time.perf_counter() - t0) * 1000
            report = TODStageReport(
                stage=stage_name,
                status="completed",
                duration_ms=round(elapsed, 2),
                detail=f"Stage '{stage_name}' completed successfully",
            )
            logger.debug(
                "Stage '%s' completed in %.1fms", stage_name, elapsed
            )
            return result, report

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error(
                "Stage '%s' failed: %s", stage_name, exc, exc_info=True
            )
            report = TODStageReport(
                stage=stage_name,
                status="failed",
                duration_ms=round(elapsed, 2),
                detail=f"Stage '{stage_name}' failed",
                error=str(exc),
            )
            return None, report
