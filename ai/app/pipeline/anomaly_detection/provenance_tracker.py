"""
Atopsy — Anomaly Provenance Tracker (Layer 8).

Builds provenance maps and audit trails for anomaly/contradiction
findings. Links every finding back to its source entities,
evidence files, and raw text.
"""

from __future__ import annotations

import logging
from typing import Any

from app.pipeline.anomaly_detection.schemas import (
    AffectedEntity,
    AffectedTimelineEvent,
    AnomalyAuditEntry,
    AnomalyFinding,
    AnomalyProvenanceEntry,
    ContradictionFinding,
    FindingSeverity,
)

logger = logging.getLogger(__name__)


class AnomalyProvenanceTracker:
    """
    Builds provenance maps for anomaly/contradiction findings.

    Preserves source evidence for every finding and builds
    aggregated affected-entity and affected-event views.
    """

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def build_provenance_map(
        self,
        anomalies: list[AnomalyFinding],
        contradictions: list[ContradictionFinding],
    ) -> dict[str, list[AnomalyProvenanceEntry]]:
        """
        Build a provenance map indexed by finding ID.

        Args:
            anomalies: Anomaly findings.
            contradictions: Contradiction findings.

        Returns:
            Dict mapping finding_id to provenance entries.
        """
        self._audit.clear()
        provenance_map: dict[str, list[AnomalyProvenanceEntry]] = {}

        # Anomaly provenance
        for finding in anomalies:
            if finding.provenance:
                provenance_map[finding.finding_id] = finding.provenance

        # Contradiction provenance
        for finding in contradictions:
            entries: list[AnomalyProvenanceEntry] = []
            if finding.provenance:
                entries.extend(finding.provenance)

            # Also build from source_a / source_b
            if finding.source_a.entity_id:
                entries.append(
                    AnomalyProvenanceEntry(
                        evidence_file_id=finding.source_a.evidence_file_id,
                        entity_id=finding.source_a.entity_id,
                        raw_text=finding.source_a.raw_text,
                        canonical_value=finding.source_a.value,
                        confidence=finding.source_a.confidence,
                        page=finding.source_a.page,
                        document_source=finding.source_a.document_source,
                    )
                )
            if finding.source_b.entity_id:
                entries.append(
                    AnomalyProvenanceEntry(
                        evidence_file_id=finding.source_b.evidence_file_id,
                        entity_id=finding.source_b.entity_id,
                        raw_text=finding.source_b.raw_text,
                        canonical_value=finding.source_b.value,
                        confidence=finding.source_b.confidence,
                        page=finding.source_b.page,
                        document_source=finding.source_b.document_source,
                    )
                )

            if entries:
                provenance_map[finding.finding_id] = entries

        self._audit.append(
            AnomalyAuditEntry(
                stage="provenance_tracking",
                action="provenance_map_built",
                detail=(
                    f"Built provenance map with "
                    f"{len(provenance_map)} entries"
                ),
            )
        )

        return provenance_map

    def build_affected_entities(
        self,
        anomalies: list[AnomalyFinding],
        contradictions: list[ContradictionFinding],
    ) -> list[AffectedEntity]:
        """Build aggregated affected-entity view."""
        entity_map: dict[str, AffectedEntity] = {}

        all_findings: list[AnomalyFinding | ContradictionFinding] = []
        all_findings.extend(anomalies)
        all_findings.extend(contradictions)

        for finding in all_findings:
            entity_ids = getattr(finding, "affected_entity_ids", [])
            for eid in entity_ids:
                if eid not in entity_map:
                    entity_map[eid] = AffectedEntity(
                        entity_id=eid,
                        finding_ids=[],
                        highest_severity=FindingSeverity.LOW,
                    )

                ae = entity_map[eid]
                ae.finding_ids.append(finding.finding_id)

                # Track highest severity
                sev_order = {
                    FindingSeverity.LOW: 0,
                    FindingSeverity.MEDIUM: 1,
                    FindingSeverity.HIGH: 2,
                    FindingSeverity.CRITICAL: 3,
                }
                if sev_order.get(
                    finding.severity, 0
                ) > sev_order.get(ae.highest_severity, 0):
                    ae.highest_severity = finding.severity

        return list(entity_map.values())

    def build_affected_timeline_events(
        self,
        anomalies: list[AnomalyFinding],
        contradictions: list[ContradictionFinding],
    ) -> list[AffectedTimelineEvent]:
        """Build aggregated affected-timeline-event view."""
        event_map: dict[str, AffectedTimelineEvent] = {}

        all_findings: list[AnomalyFinding | ContradictionFinding] = []
        all_findings.extend(anomalies)
        all_findings.extend(contradictions)

        for finding in all_findings:
            event_ids = getattr(
                finding, "affected_timeline_event_ids", []
            )
            for evid in event_ids:
                if evid not in event_map:
                    event_map[evid] = AffectedTimelineEvent(
                        event_id=evid,
                        finding_ids=[],
                        highest_severity=FindingSeverity.LOW,
                    )

                ate = event_map[evid]
                ate.finding_ids.append(finding.finding_id)

                sev_order = {
                    FindingSeverity.LOW: 0,
                    FindingSeverity.MEDIUM: 1,
                    FindingSeverity.HIGH: 2,
                    FindingSeverity.CRITICAL: 3,
                }
                if sev_order.get(
                    finding.severity, 0
                ) > sev_order.get(ate.highest_severity, 0):
                    ate.highest_severity = finding.severity

        return list(event_map.values())

    def build_recommendations(
        self,
        anomalies: list[AnomalyFinding],
        contradictions: list[ContradictionFinding],
    ) -> list[str]:
        """Build a deduplicated list of recommendations."""
        seen: set[str] = set()
        recommendations: list[str] = []

        # Prioritize CRITICAL/HIGH findings
        all_findings = sorted(
            [*anomalies, *contradictions],
            key=lambda f: {
                FindingSeverity.CRITICAL: 0,
                FindingSeverity.HIGH: 1,
                FindingSeverity.MEDIUM: 2,
                FindingSeverity.LOW: 3,
            }.get(f.severity, 4),
        )

        for finding in all_findings:
            rec = getattr(finding, "recommendation", "")
            if rec and rec not in seen:
                seen.add(rec)
                recommendations.append(rec)

        return recommendations
