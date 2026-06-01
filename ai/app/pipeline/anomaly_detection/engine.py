"""
Atopsy — Anomaly & Contradiction Detection Engine (Layer 8).

Orchestrates comprehensive anomaly and contradiction detection
through a 7-stage fault-tolerant pipeline. Consumes all upstream
outputs (entity graphs, correlation graph, timeline, TOD result)
to produce a structured AnomalyReport.

Does NOT mutate upstream records.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.pipeline.correlation.schemas import CorrelationGraph
from app.pipeline.structuring.schemas import ForensicEntityGraph
from app.pipeline.temporal.schemas import ForensicTimeline
from app.pipeline.tod_estimation.schemas import TODEstimationResult
from app.pipeline.anomaly_detection.anomaly_rules import AnomalyRules
from app.pipeline.anomaly_detection.consistency_checker import (
    ConsistencyChecker,
)
from app.pipeline.anomaly_detection.contradiction_rules import (
    ContradictionRules,
)
from app.pipeline.anomaly_detection.entity_validator import EntityValidator
from app.pipeline.anomaly_detection.provenance_tracker import (
    AnomalyProvenanceTracker,
)
from app.pipeline.anomaly_detection.schemas import (
    AnomalyAuditEntry,
    AnomalyConfidenceScores,
    AnomalyReport,
    AnomalyStageReport,
    RuleHit,
)
from app.pipeline.anomaly_detection.severity_scorer import SeverityScorer
from app.pipeline.anomaly_detection.timeline_validator import (
    TimelineValidator,
)

logger = logging.getLogger(__name__)


class AnomalyDetectionEngine:
    """
    Anomaly & Contradiction Detection Engine — Layer 8.

    7-stage pipeline:
      1. Entity Validation       — per-entity rule checks
      2. Contradiction Detection — cross-doc contradictions
      3. Anomaly Detection       — missing data, OCR, numerics
      4. Timeline Validation     — temporal sequence checks
      5. Consistency Checking    — cross-entity/cluster checks
      6. Severity Scoring        — adjust and score severities
      7. Provenance & Assembly   — build final AnomalyReport

    Each stage is independently fault-tolerant.
    """

    def __init__(self) -> None:
        self._entity_validator = EntityValidator()
        self._contradiction_rules = ContradictionRules()
        self._anomaly_rules = AnomalyRules()
        self._timeline_validator = TimelineValidator()
        self._consistency_checker = ConsistencyChecker()
        self._severity_scorer = SeverityScorer()
        self._provenance_tracker = AnomalyProvenanceTracker()

    def detect(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        correlation_graph: CorrelationGraph | None = None,
        forensic_timeline: ForensicTimeline | None = None,
        tod_result: TODEstimationResult | None = None,
        case_id: str | None = None,
    ) -> AnomalyReport:
        """
        Run the full anomaly detection pipeline.

        Args:
            entity_graphs: List of (evidence_file_id, ForensicEntityGraph)
                           tuples from Layer 4.
            correlation_graph: Optional CorrelationGraph from Layer 5.
            forensic_timeline: Optional ForensicTimeline from Layer 6.
            tod_result: Optional TODEstimationResult from Layer 7.
            case_id: Optional case identifier.

        Returns:
            AnomalyReport with all detection outputs.
        """
        t_start = time.perf_counter()
        stage_reports: list[AnomalyStageReport] = []
        all_audit: list[AnomalyAuditEntry] = []
        evidence_file_ids = [eid for eid, _ in entity_graphs]

        logger.info(
            "Anomaly detection engine starting: %d evidence files",
            len(entity_graphs),
        )

        # Accumulate all findings
        all_anomalies = []
        all_contradictions = []

        # ── Stage 1: Entity Validation ────────────────────
        entity_findings, sr = self._run_stage(
            "entity_validation",
            lambda: self._entity_validator.validate(entity_graphs),
        )
        stage_reports.append(sr)
        all_audit.extend(self._entity_validator.audit_entries)
        if entity_findings:
            all_anomalies.extend(entity_findings)

        # ── Stage 2: Contradiction Detection ──────────────
        contradictions, sr = self._run_stage(
            "contradiction_detection",
            lambda: self._contradiction_rules.detect(
                entity_graphs, correlation_graph
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._contradiction_rules.audit_entries)
        if contradictions:
            all_contradictions.extend(contradictions)

        # ── Stage 3: Anomaly Detection ────────────────────
        anomalies, sr = self._run_stage(
            "anomaly_detection",
            lambda: self._anomaly_rules.detect(entity_graphs),
        )
        stage_reports.append(sr)
        all_audit.extend(self._anomaly_rules.audit_entries)
        if anomalies:
            all_anomalies.extend(anomalies)

        # ── Stage 4: Timeline Validation ──────────────────
        timeline_findings, sr = self._run_stage(
            "timeline_validation",
            lambda: self._timeline_validator.validate(
                forensic_timeline, tod_result
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._timeline_validator.audit_entries)
        if timeline_findings:
            all_anomalies.extend(timeline_findings)

        # ── Stage 5: Consistency Checking ─────────────────
        consistency_findings, sr = self._run_stage(
            "consistency_checking",
            lambda: self._consistency_checker.check(
                entity_graphs, correlation_graph, tod_result
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._consistency_checker.audit_entries)
        if consistency_findings:
            all_anomalies.extend(consistency_findings)

        # ── Stage 6: Severity Scoring ─────────────────────
        scored_result, sr = self._run_stage(
            "severity_scoring",
            lambda: self._severity_scorer.score(
                all_anomalies, all_contradictions
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._severity_scorer.audit_entries)
        if scored_result:
            all_anomalies, all_contradictions, severity_summary = (
                scored_result
            )
        else:
            from app.pipeline.anomaly_detection.schemas import SeveritySummary
            severity_summary = SeveritySummary()

        # ── Stage 7: Provenance & Assembly ────────────────
        assembly_result, sr = self._run_stage(
            "provenance_assembly",
            lambda: self._assemble_provenance(
                all_anomalies, all_contradictions
            ),
        )
        stage_reports.append(sr)
        all_audit.extend(self._provenance_tracker.audit_entries)

        if assembly_result:
            (
                provenance_map,
                affected_entities,
                affected_events,
                recommendations,
            ) = assembly_result
        else:
            provenance_map = {}
            affected_entities = []
            affected_events = []
            recommendations = []

        # Build rule hits
        rule_hits = self._build_rule_hits(
            all_anomalies, all_contradictions
        )

        # Build confidence scores
        confidence_scores = self._build_confidence_scores(
            all_anomalies, all_contradictions, rule_hits
        )

        t_elapsed = (time.perf_counter() - t_start) * 1000

        report = AnomalyReport(
            schema_version="1.0.0",
            case_id=case_id,
            evidence_file_ids=sorted(evidence_file_ids),
            anomalies=all_anomalies,
            contradictions=all_contradictions,
            severity_summary=severity_summary,
            affected_entities=affected_entities,
            affected_timeline_events=affected_events,
            rule_hits=rule_hits,
            confidence_scores=confidence_scores,
            provenance_map=provenance_map,
            audit_trail=all_audit,
            recommendations=recommendations,
            stage_reports=stage_reports,
            processing_time_ms=round(t_elapsed, 2),
            processed_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "Anomaly detection complete: %d anomalies, "
            "%d contradictions, %d rule hits in %.1fms",
            len(all_anomalies),
            len(all_contradictions),
            len(rule_hits),
            t_elapsed,
        )

        return report

    def _assemble_provenance(
        self, anomalies: list, contradictions: list
    ) -> tuple:
        """Assemble all provenance and affected views."""
        provenance_map = self._provenance_tracker.build_provenance_map(
            anomalies, contradictions
        )
        affected_entities = (
            self._provenance_tracker.build_affected_entities(
                anomalies, contradictions
            )
        )
        affected_events = (
            self._provenance_tracker.build_affected_timeline_events(
                anomalies, contradictions
            )
        )
        recommendations = (
            self._provenance_tracker.build_recommendations(
                anomalies, contradictions
            )
        )
        return (
            provenance_map,
            affected_entities,
            affected_events,
            recommendations,
        )

    def _build_rule_hits(
        self, anomalies: list, contradictions: list
    ) -> list[RuleHit]:
        """Build aggregated rule hit records."""
        rule_map: dict[str, RuleHit] = {}

        all_findings = [*anomalies, *contradictions]
        for finding in all_findings:
            rule_id = getattr(finding, "rule_id", "")
            if not rule_id:
                continue

            if rule_id not in rule_map:
                rule_map[rule_id] = RuleHit(
                    rule_id=rule_id,
                    rule_name=rule_id.replace("_", " ").title(),
                    finding_ids=[],
                    category=getattr(
                        finding,
                        "category",
                        None,
                    ),
                    description=getattr(finding, "title", ""),
                    hit_count=0,
                )

            rule_map[rule_id].finding_ids.append(finding.finding_id)
            rule_map[rule_id].hit_count += 1

        return list(rule_map.values())

    def _build_confidence_scores(
        self,
        anomalies: list,
        contradictions: list,
        rule_hits: list[RuleHit],
    ) -> AnomalyConfidenceScores:
        """Build aggregate confidence scores."""
        all_findings = [*anomalies, *contradictions]
        total = len(all_findings)

        if total == 0:
            return AnomalyConfidenceScores(
                overall_confidence=1.0,
                rules_evaluated=len(rule_hits),
            )

        confidences = [
            getattr(f, "confidence", 0.5) for f in all_findings
        ]
        avg_confidence = sum(confidences) / total
        high_conf = sum(1 for c in confidences if c >= 0.75)
        low_conf = sum(1 for c in confidences if c < 0.40)

        return AnomalyConfidenceScores(
            overall_confidence=round(avg_confidence, 3),
            average_finding_confidence=round(avg_confidence, 3),
            high_confidence_findings=high_conf,
            low_confidence_findings=low_conf,
            total_findings=total,
            rules_evaluated=len(rule_hits) + 10,  # base rule count
            rules_fired=len(rule_hits),
        )

    def _run_stage(
        self,
        stage_name: str,
        fn: Any,
    ) -> tuple[Any, AnomalyStageReport]:
        """
        Run a pipeline stage with fault tolerance.

        Returns (result, stage_report). On failure, result is None.
        """
        t0 = time.perf_counter()
        try:
            result = fn()
            elapsed = (time.perf_counter() - t0) * 1000

            findings_count = 0
            if isinstance(result, list):
                findings_count = len(result)
            elif isinstance(result, tuple) and len(result) >= 2:
                for item in result:
                    if isinstance(item, list):
                        findings_count += len(item)

            report = AnomalyStageReport(
                stage=stage_name,
                status="completed",
                duration_ms=round(elapsed, 2),
                findings_produced=findings_count,
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
            report = AnomalyStageReport(
                stage=stage_name,
                status="failed",
                duration_ms=round(elapsed, 2),
                detail=f"Stage '{stage_name}' failed",
                error=str(exc),
            )
            return None, report
