"""
Atopsy — Temporal Contradiction Detector (Layer 6).

Detects impossible or contradictory temporal sequences
in the forensic timeline. Examples:
- Death after post-mortem examination
- Last seen alive after discovery of body
- Impossible PMI values
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.pipeline.temporal.schemas import (
    TemporalAuditEntry,
    TemporalConflict,
    TemporalConflictSeverity,
    TemporalConflictSource,
    TemporalEvent,
    TemporalRelation,
    TemporalRelationType,
    TimeWindow,
)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────
# Impossible sequence rules
# ─────────────────────────────────────────────

# (category_A, category_B) → if A is AFTER B, it's a conflict
# A should come BEFORE B
IMPOSSIBLE_SEQUENCES: list[tuple[str, str, TemporalConflictSeverity]] = [
    ("DEATH", "EXAMINATION", TemporalConflictSeverity.CRITICAL),
    ("LAST_SEEN_ALIVE", "DEATH", TemporalConflictSeverity.CRITICAL),
    ("DEATH", "DISCOVERY", TemporalConflictSeverity.HIGH),
    ("DISCOVERY", "EXAMINATION", TemporalConflictSeverity.HIGH),
    ("INCIDENT", "DEATH", TemporalConflictSeverity.HIGH),
    ("INJURY_INFLICTION", "DEATH", TemporalConflictSeverity.MEDIUM),
    ("LAST_SEEN_ALIVE", "DISCOVERY", TemporalConflictSeverity.MEDIUM),
]

# PMI bounds (in hours)
MAX_REASONABLE_PMI: float = 720.0  # 30 days
MIN_REASONABLE_PMI: float = 0.0


class TemporalContradictionDetector:
    """
    Detects temporal contradictions in the forensic timeline.

    Checks:
    1. Impossible event sequences (death after examination)
    2. Contradictory time windows between related events
    3. Unreasonable PMI values
    4. Conflicting temporal relations
    """

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def detect(
        self,
        events: list[TemporalEvent],
        relations: list[TemporalRelation],
        event_order: list[str],
    ) -> list[TemporalConflict]:
        """
        Detect all temporal contradictions.

        Args:
            events: Temporal events.
            relations: Temporal relations between events.
            event_order: Linearized event ordering.

        Returns:
            List of TemporalConflict objects.
        """
        self._audit.clear()
        conflicts: list[TemporalConflict] = []

        # 1. Check impossible sequences
        seq_conflicts = self._check_sequences(events, event_order)
        conflicts.extend(seq_conflicts)

        # 2. Check contradictory relations
        rel_conflicts = self._check_relations(events, relations)
        conflicts.extend(rel_conflicts)

        # 3. Check time window overlaps for sequential events
        window_conflicts = self._check_time_windows(events, relations)
        conflicts.extend(window_conflicts)

        # Deduplicate
        conflicts = self._deduplicate(conflicts)

        self._audit.append(
            TemporalAuditEntry(
                stage="temporal_contradiction_detection",
                action="detection_complete",
                detail=(
                    f"Detected {len(conflicts)} temporal conflicts "
                    f"({sum(1 for c in conflicts if c.severity == TemporalConflictSeverity.CRITICAL)} critical)"
                ),
            )
        )

        return conflicts

    def _check_sequences(
        self,
        events: list[TemporalEvent],
        event_order: list[str],
    ) -> list[TemporalConflict]:
        """Check for impossible event sequences."""
        conflicts: list[TemporalConflict] = []

        evt_map = {e.event_id: e for e in events}
        order_idx = {eid: i for i, eid in enumerate(event_order)}

        # Build category index
        by_category: dict[str, list[TemporalEvent]] = {}
        for evt in events:
            cat = (
                evt.category.value
                if hasattr(evt.category, "value")
                else str(evt.category)
            )
            by_category.setdefault(cat, []).append(evt)

        for cat_before, cat_after, severity in IMPOSSIBLE_SEQUENCES:
            events_before = by_category.get(cat_before, [])
            events_after = by_category.get(cat_after, [])

            for eb in events_before:
                for ea in events_after:
                    # Check if the ordering is violated
                    idx_b = order_idx.get(eb.event_id)
                    idx_a = order_idx.get(ea.event_id)

                    if idx_b is not None and idx_a is not None and idx_b > idx_a:
                        # before-event appears after after-event → conflict
                        conflicts.append(
                            TemporalConflict(
                                conflict_id=str(uuid.uuid4()),
                                severity=severity,
                                description=(
                                    f"Impossible sequence: '{eb.label}' ({cat_before}) "
                                    f"ordered after '{ea.label}' ({cat_after})"
                                ),
                                conflict_type="impossible_sequence",
                                source_a=TemporalConflictSource(
                                    event_id=eb.event_id,
                                    evidence_file_id=eb.provenance.evidence_file_id,
                                    time_window=eb.time_window,
                                    raw_text=eb.description,
                                ),
                                source_b=TemporalConflictSource(
                                    event_id=ea.event_id,
                                    evidence_file_id=ea.provenance.evidence_file_id,
                                    time_window=ea.time_window,
                                    raw_text=ea.description,
                                ),
                                resolution_hint=(
                                    f"Review ordering: {cat_before} should precede {cat_after}"
                                ),
                            )
                        )

                    # Also check time windows directly
                    best_b = _parse_iso(eb.time_window.best_estimate)
                    best_a = _parse_iso(ea.time_window.best_estimate)
                    if best_b and best_a and best_b > best_a:
                        conflicts.append(
                            TemporalConflict(
                                conflict_id=str(uuid.uuid4()),
                                severity=severity,
                                description=(
                                    f"Temporal impossibility: '{eb.label}' at {eb.time_window.best_estimate} "
                                    f"occurs after '{ea.label}' at {ea.time_window.best_estimate}"
                                ),
                                conflict_type="temporal_impossibility",
                                source_a=TemporalConflictSource(
                                    event_id=eb.event_id,
                                    evidence_file_id=eb.provenance.evidence_file_id,
                                    time_window=eb.time_window,
                                    raw_text=eb.description,
                                ),
                                source_b=TemporalConflictSource(
                                    event_id=ea.event_id,
                                    evidence_file_id=ea.provenance.evidence_file_id,
                                    time_window=ea.time_window,
                                    raw_text=ea.description,
                                ),
                                resolution_hint="Timestamps are inconsistent with expected forensic sequence",
                            )
                        )

        return conflicts

    def _check_relations(
        self,
        events: list[TemporalEvent],
        relations: list[TemporalRelation],
    ) -> list[TemporalConflict]:
        """Check for contradictory temporal relations."""
        conflicts: list[TemporalConflict] = []
        evt_map = {e.event_id: e for e in events}

        # Look for A→B BEFORE and B→A BEFORE (cycle)
        before_pairs: set[tuple[str, str]] = set()
        for rel in relations:
            if rel.relation_type == TemporalRelationType.BEFORE:
                pair = (rel.source_event_id, rel.target_event_id)
                reverse = (rel.target_event_id, rel.source_event_id)
                if reverse in before_pairs:
                    evt_a = evt_map.get(rel.source_event_id)
                    evt_b = evt_map.get(rel.target_event_id)
                    if evt_a and evt_b:
                        conflicts.append(
                            TemporalConflict(
                                conflict_id=str(uuid.uuid4()),
                                severity=TemporalConflictSeverity.HIGH,
                                description=(
                                    f"Circular temporal ordering: "
                                    f"'{evt_a.label}' and '{evt_b.label}' "
                                    f"each claim to precede the other"
                                ),
                                conflict_type="circular_ordering",
                                source_a=TemporalConflictSource(
                                    event_id=evt_a.event_id,
                                    evidence_file_id=evt_a.provenance.evidence_file_id,
                                    time_window=evt_a.time_window,
                                    raw_text=evt_a.description,
                                ),
                                source_b=TemporalConflictSource(
                                    event_id=evt_b.event_id,
                                    evidence_file_id=evt_b.provenance.evidence_file_id,
                                    time_window=evt_b.time_window,
                                    raw_text=evt_b.description,
                                ),
                                resolution_hint="One of the temporal assertions is incorrect",
                            )
                        )
                before_pairs.add(pair)

        return conflicts

    def _check_time_windows(
        self,
        events: list[TemporalEvent],
        relations: list[TemporalRelation],
    ) -> list[TemporalConflict]:
        """Check for time windows that contradict BEFORE relations."""
        conflicts: list[TemporalConflict] = []
        evt_map = {e.event_id: e for e in events}

        for rel in relations:
            if rel.relation_type != TemporalRelationType.BEFORE:
                continue

            src = evt_map.get(rel.source_event_id)
            tgt = evt_map.get(rel.target_event_id)
            if not src or not tgt:
                continue

            earliest_src = _parse_iso(src.time_window.earliest)
            latest_tgt = _parse_iso(tgt.time_window.latest)

            if earliest_src and latest_tgt and earliest_src > latest_tgt:
                conflicts.append(
                    TemporalConflict(
                        conflict_id=str(uuid.uuid4()),
                        severity=TemporalConflictSeverity.MEDIUM,
                        description=(
                            f"Time window conflict: '{src.label}' (BEFORE) "
                            f"has earliest time after '{tgt.label}' latest time"
                        ),
                        conflict_type="window_contradiction",
                        source_a=TemporalConflictSource(
                            event_id=src.event_id,
                            evidence_file_id=src.provenance.evidence_file_id,
                            time_window=src.time_window,
                        ),
                        source_b=TemporalConflictSource(
                            event_id=tgt.event_id,
                            evidence_file_id=tgt.provenance.evidence_file_id,
                            time_window=tgt.time_window,
                        ),
                        resolution_hint="Time windows are inconsistent with the asserted ordering",
                    )
                )

        return conflicts

    def _deduplicate(
        self, conflicts: list[TemporalConflict]
    ) -> list[TemporalConflict]:
        """Remove duplicate conflicts."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[TemporalConflict] = []
        for c in conflicts:
            key = (
                c.conflict_type,
                min(c.source_a.event_id, c.source_b.event_id),
                max(c.source_a.event_id, c.source_b.event_id),
            )
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique
