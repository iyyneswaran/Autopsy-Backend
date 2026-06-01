"""
Atopsy — Timeline Validator (Layer 8).

Temporal sequence validation that consumes the ForensicTimeline
from Layer 6, re-validates temporal conflicts with broader rules,
and checks for impossible durations and ordering inconsistencies.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.pipeline.temporal.schemas import (
    EventCategory,
    ForensicTimeline,
    TemporalConflict,
    TemporalEvent,
)
from app.pipeline.tod_estimation.schemas import TODEstimationResult
from app.pipeline.anomaly_detection.schemas import (
    AnomalyAuditEntry,
    AnomalyFinding,
    FindingCategory,
    FindingSeverity,
    FindingType,
)

logger = logging.getLogger(__name__)


# Maximum reasonable durations (hours)
_MAX_DURATIONS: dict[str, float] = {
    "EXAMINATION": 24.0,      # Autopsy should not take > 24h
    "SCENE_INVESTIGATION": 48.0,
    "TOXICOLOGY_COLLECTION": 4.0,
    "HOSPITALIZATION": 8760.0,  # 1 year max
}

# Event pairs where A must precede B
_REQUIRED_ORDER: list[tuple[EventCategory, EventCategory, str]] = [
    (
        EventCategory.LAST_SEEN_ALIVE,
        EventCategory.DEATH,
        "Last seen alive must precede death",
    ),
    (
        EventCategory.DEATH,
        EventCategory.DISCOVERY,
        "Death must precede discovery",
    ),
    (
        EventCategory.DEATH,
        EventCategory.EXAMINATION,
        "Death must precede examination",
    ),
    (
        EventCategory.DISCOVERY,
        EventCategory.EXAMINATION,
        "Discovery should precede examination",
    ),
    (
        EventCategory.INCIDENT,
        EventCategory.REPORT_FILED,
        "Incident should precede report filing",
    ),
]


class TimelineValidator:
    """
    Temporal sequence validation for forensic timelines.

    Validates:
    - Required event ordering (death before exam, etc.)
    - Impossible event durations
    - TOD candidates vs timeline events
    - Layer 6 conflict re-validation
    """

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def validate(
        self,
        forensic_timeline: ForensicTimeline | None,
        tod_result: TODEstimationResult | None = None,
    ) -> list[AnomalyFinding]:
        """
        Validate the forensic timeline.

        Args:
            forensic_timeline: Layer 6 timeline.
            tod_result: Layer 7 TOD result.

        Returns:
            List of timeline-related findings.
        """
        self._audit.clear()
        findings: list[AnomalyFinding] = []

        if not forensic_timeline:
            return findings

        events = forensic_timeline.temporal_events

        # 1. Required ordering checks
        findings.extend(self._check_required_order(events))

        # 2. Impossible durations
        findings.extend(self._check_event_durations(events))

        # 3. Import Layer 6 temporal conflicts
        findings.extend(
            self._import_temporal_conflicts(
                forensic_timeline.temporal_conflicts
            )
        )

        # 4. TOD vs timeline consistency
        if tod_result:
            findings.extend(
                self._check_tod_vs_timeline(tod_result, events)
            )

        self._audit.append(
            AnomalyAuditEntry(
                stage="timeline_validation",
                action="validation_complete",
                finding_ids=[f.finding_id for f in findings],
                detail=(
                    f"Timeline validation produced {len(findings)} findings "
                    f"from {len(events)} events"
                ),
            )
        )

        return findings

    def _check_required_order(
        self,
        events: list[TemporalEvent],
    ) -> list[AnomalyFinding]:
        """Check that required event orderings are satisfied."""
        findings: list[AnomalyFinding] = []

        # Index events by category
        cat_events: dict[EventCategory, list[TemporalEvent]] = {}
        for event in events:
            if event.category not in cat_events:
                cat_events[event.category] = []
            cat_events[event.category].append(event)

        for cat_a, cat_b, description in _REQUIRED_ORDER:
            events_a = cat_events.get(cat_a, [])
            events_b = cat_events.get(cat_b, [])

            for ea in events_a:
                for eb in events_b:
                    violation = self._check_order_violation(
                        ea, eb, description
                    )
                    if violation:
                        findings.append(violation)

        return findings

    def _check_order_violation(
        self,
        event_a: TemporalEvent,
        event_b: TemporalEvent,
        description: str,
    ) -> AnomalyFinding | None:
        """Check if event_a's latest is after event_b's earliest."""
        tw_a = event_a.time_window
        tw_b = event_b.time_window

        # Get the latest possible time for A
        a_time = tw_a.latest or tw_a.best_estimate
        # Get the earliest possible time for B
        b_time = tw_b.earliest or tw_b.best_estimate

        if not a_time or not b_time:
            return None

        try:
            dt_a = datetime.fromisoformat(a_time)
            dt_b = datetime.fromisoformat(b_time)
        except (ValueError, TypeError):
            return None

        if dt_a > dt_b:
            return AnomalyFinding(
                finding_id=str(uuid.uuid4()),
                finding_type=FindingType.ANOMALY,
                category=FindingCategory.TEMPORAL,
                severity=FindingSeverity.CRITICAL,
                title=f"Impossible event order: {event_a.category.value} → {event_b.category.value}",
                description=(
                    f"{description}: '{event_a.label}' "
                    f"({a_time}) occurs after "
                    f"'{event_b.label}' ({b_time})"
                ),
                affected_entity_ids=[
                    event_a.provenance.entity_id,
                    event_b.provenance.entity_id,
                ],
                affected_evidence_ids=[
                    event_a.provenance.evidence_file_id,
                    event_b.provenance.evidence_file_id,
                ],
                affected_timeline_event_ids=[
                    event_a.event_id,
                    event_b.event_id,
                ],
                rule_id="IMPOSSIBLE_ORDER",
                confidence=0.9,
                recommendation=(
                    "Verify timestamps in source documents; "
                    "one or both may contain errors"
                ),
            )

        return None

    def _check_event_durations(
        self,
        events: list[TemporalEvent],
    ) -> list[AnomalyFinding]:
        """Check for impossibly long or short event durations."""
        findings: list[AnomalyFinding] = []

        for event in events:
            tw = event.time_window
            if not tw.earliest or not tw.latest:
                continue

            try:
                dt_e = datetime.fromisoformat(tw.earliest)
                dt_l = datetime.fromisoformat(tw.latest)
                duration_hours = (dt_l - dt_e).total_seconds() / 3600.0
            except (ValueError, TypeError):
                continue

            # Negative duration
            if duration_hours < 0:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.TEMPORAL,
                        severity=FindingSeverity.CRITICAL,
                        title=f"Negative event duration: {event.label}",
                        description=(
                            f"Event '{event.label}' has earliest "
                            f"({tw.earliest}) after latest ({tw.latest})"
                        ),
                        affected_timeline_event_ids=[event.event_id],
                        affected_evidence_ids=[
                            event.provenance.evidence_file_id
                        ],
                        rule_id="NEGATIVE_DURATION",
                        confidence=0.95,
                        recommendation="Timestamp extraction error likely",
                    )
                )
                continue

            # Check against max durations
            cat_key = event.category.value
            max_dur = _MAX_DURATIONS.get(cat_key)
            if max_dur and duration_hours > max_dur:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.TEMPORAL,
                        severity=FindingSeverity.MEDIUM,
                        title=(
                            f"Unreasonable duration: {event.label}"
                        ),
                        description=(
                            f"Event '{event.label}' spans "
                            f"{duration_hours:.1f} hours "
                            f"(max expected: {max_dur:.0f})"
                        ),
                        affected_timeline_event_ids=[event.event_id],
                        affected_evidence_ids=[
                            event.provenance.evidence_file_id
                        ],
                        rule_id="UNREASONABLE_DURATION",
                        confidence=0.75,
                        recommendation=(
                            "Duration may indicate timestamp error "
                            "or multiple events merged"
                        ),
                    )
                )

        return findings

    def _import_temporal_conflicts(
        self,
        conflicts: list[TemporalConflict],
    ) -> list[AnomalyFinding]:
        """Import Layer 6 temporal conflicts as findings."""
        findings: list[AnomalyFinding] = []

        for conflict in conflicts:
            findings.append(
                AnomalyFinding(
                    finding_id=str(uuid.uuid4()),
                    finding_type=FindingType.ANOMALY,
                    category=FindingCategory.TEMPORAL,
                    severity=FindingSeverity(conflict.severity.value),
                    title=f"Temporal conflict: {conflict.conflict_type}",
                    description=conflict.description,
                    affected_timeline_event_ids=[
                        conflict.source_a.event_id,
                        conflict.source_b.event_id,
                    ],
                    affected_evidence_ids=[
                        conflict.source_a.evidence_file_id,
                        conflict.source_b.evidence_file_id,
                    ],
                    rule_id=f"LAYER6_{conflict.conflict_type}",
                    confidence=0.85,
                    recommendation=conflict.resolution_hint or (
                        "Review temporal assertions in source documents"
                    ),
                    metadata={
                        "layer6_conflict_id": conflict.conflict_id,
                    },
                )
            )

        return findings

    def _check_tod_vs_timeline(
        self,
        tod_result: TODEstimationResult,
        events: list[TemporalEvent],
    ) -> list[AnomalyFinding]:
        """Check TOD candidates against timeline events."""
        findings: list[AnomalyFinding] = []

        primary_window = tod_result.estimated_window
        if not primary_window.earliest and not primary_window.latest:
            return findings

        tod_earliest = primary_window.earliest
        tod_latest = primary_window.latest

        for event in events:
            tw = event.time_window
            event_time = tw.best_estimate or tw.earliest

            if not event_time:
                continue

            # Last seen alive should be before TOD
            if event.category == EventCategory.LAST_SEEN_ALIVE:
                if tod_earliest:
                    try:
                        dt_event = datetime.fromisoformat(event_time)
                        dt_tod = datetime.fromisoformat(tod_earliest)
                        if dt_event > dt_tod:
                            findings.append(
                                AnomalyFinding(
                                    finding_id=str(uuid.uuid4()),
                                    finding_type=FindingType.ANOMALY,
                                    category=FindingCategory.TOD_ESTIMATION,
                                    severity=FindingSeverity.CRITICAL,
                                    title=(
                                        "Last seen alive after "
                                        "TOD estimate"
                                    ),
                                    description=(
                                        f"'{event.label}' ({event_time}) "
                                        f"is after earliest TOD "
                                        f"({tod_earliest})"
                                    ),
                                    affected_timeline_event_ids=[
                                        event.event_id
                                    ],
                                    rule_id="LSA_AFTER_TOD",
                                    confidence=0.9,
                                    recommendation=(
                                        "Either TOD estimate or "
                                        "last-seen-alive timestamp "
                                        "may be incorrect"
                                    ),
                                )
                            )
                    except (ValueError, TypeError):
                        continue

        return findings
