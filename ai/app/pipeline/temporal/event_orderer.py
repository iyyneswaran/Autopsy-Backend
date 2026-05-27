"""
Atopsy — Event Orderer (Layer 6).

Orders temporal events using time window comparisons and
known forensic sequence constraints.
Produces temporal relations and a linearized event order.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.pipeline.temporal.schemas import (
    TemporalAuditEntry,
    TemporalEvent,
    TemporalPrecision,
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
# Known forensic sequence constraints
# ─────────────────────────────────────────────

# (category_A, category_B) → A must be BEFORE B
KNOWN_ORDER: list[tuple[str, str]] = [
    ("LAST_SEEN_ALIVE", "DEATH"),
    ("LAST_SEEN_ALIVE", "DISCOVERY"),
    ("INCIDENT", "DEATH"),
    ("DEATH", "DISCOVERY"),
    ("DEATH", "EXAMINATION"),
    ("DEATH", "REPORT_FILED"),
    ("DISCOVERY", "EXAMINATION"),
    ("DISCOVERY", "REPORT_FILED"),
    ("INJURY_INFLICTION", "DEATH"),
    ("INJURY_INFLICTION", "EXAMINATION"),
    ("TOXICOLOGY_COLLECTION", "EXAMINATION"),
    ("SCENE_INVESTIGATION", "EXAMINATION"),
]


class EventOrderer:
    """
    Orders temporal events using time window comparisons
    and known forensic sequence constraints.

    Strategy:
    1. Compare time windows between event pairs.
    2. Apply known forensic ordering constraints.
    3. Infer ordering for events without absolute times.
    4. Produce temporal relations and linear event order.
    """

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def order_events(
        self,
        events: list[TemporalEvent],
    ) -> tuple[list[str], list[TemporalRelation]]:
        """
        Order events and produce temporal relations.

        Args:
            events: List of temporal events.

        Returns:
            Tuple of (ordered event IDs, temporal relations).
        """
        self._audit.clear()
        relations: list[TemporalRelation] = []

        # 1. Time-window based ordering
        tw_relations = self._order_by_time_window(events)
        relations.extend(tw_relations)

        # 2. Known forensic constraints
        constraint_relations = self._apply_constraints(events)
        relations.extend(constraint_relations)

        # 3. Deduplicate relations
        relations = self._deduplicate_relations(relations)

        # 4. Linearize event order
        event_order = self._linearize(events, relations)

        self._audit.append(
            TemporalAuditEntry(
                stage="event_ordering",
                action="ordering_complete",
                event_ids=event_order,
                detail=f"Ordered {len(events)} events with {len(relations)} temporal relations",
            )
        )

        return event_order, relations

    def _order_by_time_window(
        self, events: list[TemporalEvent]
    ) -> list[TemporalRelation]:
        """Compare time windows to determine ordering."""
        relations: list[TemporalRelation] = []

        for i, evt_a in enumerate(events):
            tw_a = evt_a.time_window
            for evt_b in events[i + 1 :]:
                tw_b = evt_b.time_window

                relation = self._compare_windows(
                    evt_a.event_id, tw_a, evt_b.event_id, tw_b
                )
                if relation:
                    relations.append(relation)

        return relations

    def _compare_windows(
        self,
        id_a: str,
        tw_a: TimeWindow,
        id_b: str,
        tw_b: TimeWindow,
    ) -> TemporalRelation | None:
        """Compare two time windows and produce a relation."""
        # Need at least best_estimate or earliest/latest
        best_a = _parse_iso(tw_a.best_estimate) or _parse_iso(tw_a.latest)
        best_b = _parse_iso(tw_b.best_estimate) or _parse_iso(tw_b.latest)

        if best_a is None or best_b is None:
            return None

        latest_a = _parse_iso(tw_a.latest) or best_a
        earliest_b = _parse_iso(tw_b.earliest) or best_b
        earliest_a = _parse_iso(tw_a.earliest) or best_a
        latest_b = _parse_iso(tw_b.latest) or best_b

        # Determine relation type
        if latest_a < earliest_b:
            # A completely before B
            rel_type = TemporalRelationType.BEFORE
            conf = min(tw_a.confidence, tw_b.confidence)
            rationale = f"Time window A ends before B begins"
        elif latest_b < earliest_a:
            # B completely before A
            rel_type = TemporalRelationType.AFTER
            conf = min(tw_a.confidence, tw_b.confidence)
            rationale = f"Time window B ends before A begins"
        elif best_a == best_b:
            rel_type = TemporalRelationType.CONCURRENT
            conf = min(tw_a.confidence, tw_b.confidence) * 0.9
            rationale = "Same best estimate timestamp"
        elif earliest_a <= earliest_b and latest_a >= latest_b:
            # A contains B
            rel_type = TemporalRelationType.CONTAINS
            conf = min(tw_a.confidence, tw_b.confidence) * 0.8
            rationale = "Time window A contains B"
        elif earliest_b <= earliest_a and latest_b >= latest_a:
            # B contains A
            rel_type = TemporalRelationType.DURING
            conf = min(tw_a.confidence, tw_b.confidence) * 0.8
            rationale = "Time window A is during B"
        elif best_a < best_b:
            rel_type = TemporalRelationType.BEFORE
            conf = min(tw_a.confidence, tw_b.confidence) * 0.7
            rationale = "Best estimate A precedes B (windows may overlap)"
        else:
            rel_type = TemporalRelationType.AFTER
            conf = min(tw_a.confidence, tw_b.confidence) * 0.7
            rationale = "Best estimate A follows B (windows may overlap)"

        return TemporalRelation(
            source_event_id=id_a,
            target_event_id=id_b,
            relation_type=rel_type,
            confidence=round(conf, 4),
            rationale=rationale,
            is_inferred=False,
        )

    def _apply_constraints(
        self, events: list[TemporalEvent]
    ) -> list[TemporalRelation]:
        """Apply known forensic ordering constraints."""
        relations: list[TemporalRelation] = []

        # Build category index
        by_category: dict[str, list[TemporalEvent]] = {}
        for evt in events:
            cat = (
                evt.category.value
                if hasattr(evt.category, "value")
                else str(evt.category)
            )
            by_category.setdefault(cat, []).append(evt)

        for cat_before, cat_after in KNOWN_ORDER:
            events_before = by_category.get(cat_before, [])
            events_after = by_category.get(cat_after, [])

            for eb in events_before:
                for ea in events_after:
                    relations.append(
                        TemporalRelation(
                            source_event_id=eb.event_id,
                            target_event_id=ea.event_id,
                            relation_type=TemporalRelationType.BEFORE,
                            confidence=0.85,
                            rationale=(
                                f"Forensic constraint: {cat_before} "
                                f"must precede {cat_after}"
                            ),
                            is_inferred=True,
                        )
                    )

        return relations

    def _deduplicate_relations(
        self, relations: list[TemporalRelation]
    ) -> list[TemporalRelation]:
        """Deduplicate relations, keeping highest confidence."""
        best: dict[tuple[str, str], TemporalRelation] = {}
        for rel in relations:
            key = (rel.source_event_id, rel.target_event_id)
            existing = best.get(key)
            if existing is None or rel.confidence > existing.confidence:
                best[key] = rel
        return list(best.values())

    def _linearize(
        self,
        events: list[TemporalEvent],
        relations: list[TemporalRelation],
    ) -> list[str]:
        """
        Produce a linear ordering of event IDs using topological sort.

        Falls back to time-window-based sorting if graph is cyclic.
        """
        # Build adjacency list for BEFORE relations
        from collections import defaultdict, deque

        adj: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {e.event_id: 0 for e in events}

        for rel in relations:
            if rel.relation_type == TemporalRelationType.BEFORE:
                adj[rel.source_event_id].append(rel.target_event_id)
                in_degree.setdefault(rel.target_event_id, 0)
                in_degree[rel.source_event_id]  # ensure exists
                in_degree[rel.target_event_id] = (
                    in_degree.get(rel.target_event_id, 0) + 1
                )

        # Kahn's algorithm
        queue: deque[str] = deque()
        for eid, deg in in_degree.items():
            if deg == 0:
                queue.append(eid)

        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If topological sort didn't include all events, fall back
        if len(order) < len(events):
            remaining = [e.event_id for e in events if e.event_id not in set(order)]
            # Sort remaining by best_estimate
            evt_map = {e.event_id: e for e in events}
            remaining.sort(
                key=lambda eid: _parse_iso(
                    evt_map[eid].time_window.best_estimate
                )
                or datetime.max.replace(tzinfo=timezone.utc)
            )
            order.extend(remaining)

        return order
