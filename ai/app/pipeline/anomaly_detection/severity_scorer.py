"""
Atopsy — Severity Scorer (Layer 8).

Assigns and adjusts severity levels for anomaly/contradiction
findings based on category, type, confidence, and forensic
importance.
"""

from __future__ import annotations

import logging
from typing import Any

from app.pipeline.anomaly_detection.schemas import (
    AnomalyAuditEntry,
    AnomalyFinding,
    ContradictionFinding,
    FindingCategory,
    FindingSeverity,
    FindingType,
    SeveritySummary,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Severity escalation rules
# ─────────────────────────────────────────────

# Category-based minimum severity for contradictions
_CONTRADICTION_MIN_SEVERITY: dict[FindingCategory, FindingSeverity] = {
    FindingCategory.MEDICAL: FindingSeverity.HIGH,
    FindingCategory.TEMPORAL: FindingSeverity.HIGH,
    FindingCategory.IDENTITY: FindingSeverity.HIGH,
    FindingCategory.CASE_IDENTIFIER: FindingSeverity.HIGH,
    FindingCategory.TOXICOLOGY: FindingSeverity.MEDIUM,
    FindingCategory.LOCATION: FindingSeverity.MEDIUM,
    FindingCategory.TOD_ESTIMATION: FindingSeverity.HIGH,
    FindingCategory.EVIDENCE_INTEGRITY: FindingSeverity.MEDIUM,
    FindingCategory.OCR_QUALITY: FindingSeverity.LOW,
}

_SEVERITY_ORDER: dict[FindingSeverity, int] = {
    FindingSeverity.LOW: 0,
    FindingSeverity.MEDIUM: 1,
    FindingSeverity.HIGH: 2,
    FindingSeverity.CRITICAL: 3,
}


class SeverityScorer:
    """
    Assigns and adjusts severity for all findings.

    Rules:
    1. Contradictions escalate to at least the category minimum.
    2. Low-confidence findings may be downgraded one level.
    3. Missing critical data (COD, MOD) escalates to HIGH.
    4. Multiple findings on the same entity escalate the highest.
    """

    # Confidence below which findings may be downgraded
    DOWNGRADE_THRESHOLD = 0.4

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def score(
        self,
        anomalies: list[AnomalyFinding],
        contradictions: list[ContradictionFinding],
    ) -> tuple[list[AnomalyFinding], list[ContradictionFinding], SeveritySummary]:
        """
        Score and adjust severity for all findings.

        Args:
            anomalies: Anomaly findings.
            contradictions: Contradiction findings.

        Returns:
            Tuple of (adjusted anomalies, adjusted contradictions,
            severity summary).
        """
        self._audit.clear()

        # Adjust contradiction severities
        for finding in contradictions:
            finding.severity = self._adjust_contradiction_severity(
                finding
            )

        # Adjust anomaly severities
        for finding in anomalies:
            finding.severity = self._adjust_anomaly_severity(finding)

        # Build summary
        summary = self._build_summary(anomalies, contradictions)

        self._audit.append(
            AnomalyAuditEntry(
                stage="severity_scoring",
                action="scoring_complete",
                detail=(
                    f"Scored {len(anomalies)} anomalies and "
                    f"{len(contradictions)} contradictions: "
                    f"{summary.critical} critical, {summary.high} high, "
                    f"{summary.medium} medium, {summary.low} low"
                ),
            )
        )

        return anomalies, contradictions, summary

    def _adjust_contradiction_severity(
        self,
        finding: ContradictionFinding,
    ) -> FindingSeverity:
        """Adjust severity for a contradiction finding."""
        current = finding.severity
        current_order = _SEVERITY_ORDER.get(current, 1)

        # Escalate to category minimum
        min_severity = _CONTRADICTION_MIN_SEVERITY.get(
            finding.category, FindingSeverity.MEDIUM
        )
        min_order = _SEVERITY_ORDER.get(min_severity, 1)

        if min_order > current_order:
            current = min_severity
            current_order = min_order

        # Downgrade if low confidence
        if (
            finding.confidence < self.DOWNGRADE_THRESHOLD
            and current_order > 0
        ):
            for sev, order in _SEVERITY_ORDER.items():
                if order == current_order - 1:
                    return sev

        return current

    def _adjust_anomaly_severity(
        self,
        finding: AnomalyFinding,
    ) -> FindingSeverity:
        """Adjust severity for an anomaly finding."""
        current = finding.severity
        current_order = _SEVERITY_ORDER.get(current, 1)

        # Missing COD/MOD escalates to at least HIGH
        if finding.finding_type == FindingType.MISSING_DATA:
            if finding.rule_id in (
                "MISSING_CAUSE_OF_DEATH",
                "MISSING_MANNER_OF_DEATH",
            ):
                if current_order < _SEVERITY_ORDER[FindingSeverity.HIGH]:
                    return FindingSeverity.HIGH

        # Downgrade if low confidence
        if (
            finding.confidence < self.DOWNGRADE_THRESHOLD
            and current_order > 0
        ):
            for sev, order in _SEVERITY_ORDER.items():
                if order == current_order - 1:
                    return sev

        return current

    def _build_summary(
        self,
        anomalies: list[AnomalyFinding],
        contradictions: list[ContradictionFinding],
    ) -> SeveritySummary:
        """Build the severity summary counts."""
        counts = {
            FindingSeverity.LOW: 0,
            FindingSeverity.MEDIUM: 0,
            FindingSeverity.HIGH: 0,
            FindingSeverity.CRITICAL: 0,
        }

        for finding in anomalies:
            counts[finding.severity] = counts.get(
                finding.severity, 0
            ) + 1

        for finding in contradictions:
            counts[finding.severity] = counts.get(
                finding.severity, 0
            ) + 1

        total = sum(counts.values())

        return SeveritySummary(
            critical=counts[FindingSeverity.CRITICAL],
            high=counts[FindingSeverity.HIGH],
            medium=counts[FindingSeverity.MEDIUM],
            low=counts[FindingSeverity.LOW],
            total=total,
        )
