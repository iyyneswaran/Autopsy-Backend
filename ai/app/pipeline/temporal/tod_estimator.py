"""
Atopsy — TOD Estimator (Layer 6).

Time-of-death estimation support. Aggregates TOD-related
temporal events and produces TODCandidate objects with
confidence and evidence basis.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.pipeline.temporal.schemas import (
    EventCategory,
    ResolutionMethod,
    TemporalAuditEntry,
    TemporalEvent,
    TemporalPrecision,
    TimeWindow,
    TODCandidate,
    UncertaintyRange,
)


class TODEstimator:
    """
    Time-of-death estimation from temporal evidence.

    Aggregates multiple TOD-related temporal events and
    produces ranked TODCandidate objects.

    Supports:
    - PMI-based estimation (post-mortem interval)
    - Witness-based estimation (last seen alive)
    - Decomposition-based estimation
    - Multi-source confidence weighting
    """

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def estimate(
        self,
        events: list[TemporalEvent],
        uncertainty_ranges: list[UncertaintyRange],
    ) -> list[TODCandidate]:
        """
        Produce TOD candidates from temporal events.

        Args:
            events: All temporal events.
            uncertainty_ranges: PMI/interval uncertainty ranges.

        Returns:
            List of TODCandidate objects, ranked by confidence.
        """
        self._audit.clear()
        candidates: list[TODCandidate] = []

        # 1. Direct TOD events
        tod_events = [
            e for e in events
            if e.category == EventCategory.DEATH
            and "TIME_OF_DEATH" in (e.provenance.entity_type or "")
        ]
        for evt in tod_events:
            candidate = self._from_tod_event(evt)
            if candidate:
                candidates.append(candidate)

        # 2. PMI-based candidates from uncertainty ranges
        pmi_ranges = [
            ur for ur in uncertainty_ranges
            if "PMI" in (ur.label or "").upper()
            or "post-mortem" in (ur.raw_expression or "").lower()
        ]
        for ur in pmi_ranges:
            candidate = self._from_pmi_range(ur, events)
            if candidate:
                candidates.append(candidate)

        # 3. Last-seen-alive based estimation
        lsa_events = [
            e for e in events
            if e.category == EventCategory.LAST_SEEN_ALIVE
        ]
        for evt in lsa_events:
            candidate = self._from_last_seen(evt)
            if candidate:
                candidates.append(candidate)

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        self._audit.append(
            TemporalAuditEntry(
                stage="tod_estimation",
                action="estimation_complete",
                detail=(
                    f"Produced {len(candidates)} TOD candidates from "
                    f"{len(tod_events)} TOD events, "
                    f"{len(pmi_ranges)} PMI ranges, "
                    f"{len(lsa_events)} last-seen events"
                ),
            )
        )

        return candidates

    def _from_tod_event(
        self, event: TemporalEvent
    ) -> TODCandidate | None:
        """Create a TOD candidate from a direct TOD event."""
        tw = event.time_window
        if not tw.best_estimate and not tw.earliest and not tw.latest:
            # Check if we have temporal expressions with ranges
            for expr in event.temporal_expressions:
                if expr.time_window.best_estimate or expr.time_window.earliest:
                    tw = expr.time_window
                    break

        return TODCandidate(
            candidate_id=str(uuid.uuid4()),
            time_window=tw,
            estimation_method="direct_tod_entity",
            evidence_basis=[event.description],
            confidence=event.confidence,
            rationale=(
                f"Direct TOD from entity: {event.description}"
            ),
            source_evidence_ids=[event.provenance.evidence_file_id],
        )

    def _from_pmi_range(
        self,
        ur: UncertaintyRange,
        events: list[TemporalEvent],
    ) -> TODCandidate | None:
        """Create a TOD candidate from a PMI uncertainty range."""
        # The PMI range gives hours before examination
        # We need an examination event to anchor it
        exam_event = next(
            (e for e in events if e.category == EventCategory.EXAMINATION
             and e.time_window.best_estimate),
            None,
        )

        tw = TimeWindow(
            confidence=ur.confidence,
            precision=TemporalPrecision.RANGE,
        )

        # If we have an examination anchor, compute absolute window
        if exam_event and exam_event.time_window.best_estimate:
            from datetime import datetime, timedelta, timezone as tz

            try:
                exam_dt = datetime.fromisoformat(
                    exam_event.time_window.best_estimate
                )
                if exam_dt.tzinfo is None:
                    exam_dt = exam_dt.replace(tzinfo=tz.utc)

                if ur.max_hours is not None:
                    earliest = exam_dt - timedelta(hours=ur.max_hours)
                    tw.earliest = earliest.isoformat()
                if ur.min_hours is not None:
                    latest = exam_dt - timedelta(hours=ur.min_hours)
                    tw.latest = latest.isoformat()
                if ur.best_estimate_hours is not None:
                    best = exam_dt - timedelta(hours=ur.best_estimate_hours)
                    tw.best_estimate = best.isoformat()
            except (ValueError, TypeError):
                pass

        return TODCandidate(
            candidate_id=str(uuid.uuid4()),
            time_window=tw,
            estimation_method="pmi_range",
            evidence_basis=[ur.raw_expression or ur.label],
            confidence=ur.confidence,
            rationale=(
                f"PMI-based: {ur.min_hours:.1f}–{ur.max_hours:.1f} hours "
                f"before examination"
                if ur.min_hours is not None and ur.max_hours is not None
                else f"PMI-based: {ur.label}"
            ),
            source_evidence_ids=[ur.source_evidence_id] if ur.source_evidence_id else [],
        )

    def _from_last_seen(
        self, event: TemporalEvent
    ) -> TODCandidate | None:
        """Create a TOD candidate from a last-seen-alive event."""
        tw = event.time_window
        if not tw.best_estimate and not tw.earliest:
            return None

        # Death occurred after last seen alive
        # Create a window from last-seen to discovery/examination
        return TODCandidate(
            candidate_id=str(uuid.uuid4()),
            time_window=TimeWindow(
                earliest=tw.best_estimate or tw.earliest,
                latest=None,
                best_estimate=None,
                confidence=event.confidence * 0.7,
                precision=TemporalPrecision.APPROXIMATE,
            ),
            estimation_method="last_seen_alive",
            evidence_basis=[event.description],
            confidence=event.confidence * 0.7,
            rationale=(
                f"Last seen alive: {event.description}. "
                f"Death occurred after this time."
            ),
            source_evidence_ids=[event.provenance.evidence_file_id],
        )
