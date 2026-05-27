"""
Atopsy — Temporal Confidence Aggregator (Layer 6).

Aggregates confidence scores across temporal events,
relations, and the overall timeline.
"""

from __future__ import annotations

from app.pipeline.temporal.schemas import (
    TemporalAuditEntry,
    TemporalConflict,
    TemporalEvent,
    TemporalPrecision,
    TemporalRelation,
    TODCandidate,
    UncertaintyRange,
)


# ─────────────────────────────────────────────
# Precision weights
# ─────────────────────────────────────────────

PRECISION_WEIGHTS: dict[str, float] = {
    TemporalPrecision.EXACT.value: 1.0,
    TemporalPrecision.APPROXIMATE.value: 0.8,
    TemporalPrecision.RANGE.value: 0.7,
    TemporalPrecision.RELATIVE.value: 0.6,
    TemporalPrecision.INFERRED.value: 0.5,
    TemporalPrecision.UNKNOWN.value: 0.3,
}


class TemporalConfidenceAggregator:
    """
    Aggregates confidence metrics for the temporal timeline.

    Computes:
    - Per-event confidence adjusted by precision
    - Average event confidence
    - Timeline reliability score
    - Conflict-adjusted overall confidence
    """

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def aggregate(
        self,
        events: list[TemporalEvent],
        relations: list[TemporalRelation],
        conflicts: list[TemporalConflict],
        tod_candidates: list[TODCandidate],
        uncertainty_ranges: list[UncertaintyRange],
    ) -> float:
        """
        Compute overall timeline confidence.

        Args:
            events: All temporal events.
            relations: Temporal relations.
            conflicts: Detected conflicts.
            tod_candidates: TOD candidates.
            uncertainty_ranges: Uncertainty ranges.

        Returns:
            Overall confidence score (0.0–1.0).
        """
        self._audit.clear()

        if not events:
            return 0.0

        # 1. Average event confidence (precision-adjusted)
        adjusted_confs: list[float] = []
        for evt in events:
            prec = (
                evt.time_window.precision.value
                if hasattr(evt.time_window.precision, "value")
                else str(evt.time_window.precision)
            )
            weight = PRECISION_WEIGHTS.get(prec, 0.3)
            adjusted = evt.confidence * weight
            adjusted_confs.append(adjusted)

        avg_event_conf = sum(adjusted_confs) / len(adjusted_confs)

        # 2. Relation confidence
        avg_relation_conf = (
            sum(r.confidence for r in relations) / len(relations)
            if relations
            else 0.5
        )

        # 3. Conflict penalty
        conflict_penalty = min(0.3, len(conflicts) * 0.05)

        # 4. TOD candidate boost
        tod_boost = 0.0
        if tod_candidates:
            best_tod = max(c.confidence for c in tod_candidates)
            tod_boost = best_tod * 0.05  # Small boost for having TOD

        # 5. Coverage factor: how many events have resolved times
        resolved = sum(
            1
            for e in events
            if e.time_window.best_estimate
            or e.time_window.earliest
        )
        coverage = resolved / len(events) if events else 0.0

        # Overall: weighted combination
        overall = (
            avg_event_conf * 0.4
            + avg_relation_conf * 0.2
            + coverage * 0.3
            + tod_boost
            - conflict_penalty
        )
        overall = max(0.0, min(1.0, overall))

        self._audit.append(
            TemporalAuditEntry(
                stage="confidence_aggregation",
                action="aggregation_complete",
                detail=(
                    f"Overall: {overall:.4f} | "
                    f"Events: {avg_event_conf:.4f} | "
                    f"Relations: {avg_relation_conf:.4f} | "
                    f"Coverage: {coverage:.2f} | "
                    f"Conflicts: {len(conflicts)} (-{conflict_penalty:.2f}) | "
                    f"TOD boost: +{tod_boost:.4f}"
                ),
                confidence=overall,
            )
        )

        return round(overall, 4)

    def adjust_event_confidence(
        self, event: TemporalEvent
    ) -> float:
        """
        Adjust a single event's confidence by its temporal precision.

        Returns the adjusted confidence score.
        """
        prec = (
            event.time_window.precision.value
            if hasattr(event.time_window.precision, "value")
            else str(event.time_window.precision)
        )
        weight = PRECISION_WEIGHTS.get(prec, 0.3)
        return round(event.confidence * weight, 4)
