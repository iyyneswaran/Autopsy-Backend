"""
Atopsy — Relative Time Resolver (Layer 6).

Resolves relative temporal references to absolute or windowed
timestamps using anchor events (examination date, document date).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.pipeline.temporal.schemas import (
    ResolutionMethod,
    TemporalAuditEntry,
    TemporalEvent,
    TemporalExpression,
    TemporalPrecision,
    TimeWindow,
)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _parse_iso(s: str) -> datetime | None:
    """Attempt to parse an ISO 8601 string."""
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _extract_hours_from_normalized(normalized: str) -> tuple[float, float] | None:
    """Extract hour range from normalized form like '12.0-18.0 hours prior'."""
    import re

    # Range: "12.0–18.0 hours"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[–\-]\s*(\d+(?:\.\d+)?)\s*hours?", normalized)
    if m:
        return float(m.group(1)), float(m.group(2))

    # Approximate: "~15.0 hours prior"
    m = re.search(r"~?(\d+(?:\.\d+)?)\s*hours?", normalized)
    if m:
        val = float(m.group(1))
        margin = val * 0.2
        return val - margin, val + margin

    return None


class RelativeTimeResolver:
    """
    Resolves relative temporal expressions to absolute time windows.

    Uses anchor events (examination date, document creation date)
    to compute absolute earliest/latest bounds for relative expressions
    like "about 12 hours prior" or "PMI: 12-18 hours".
    """

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def resolve(
        self,
        events: list[TemporalEvent],
        anchor_datetime: datetime | None = None,
    ) -> list[TemporalEvent]:
        """
        Resolve relative time expressions in events to absolute windows.

        Args:
            events: List of temporal events with expressions.
            anchor_datetime: The reference datetime (e.g., examination time).
                             If None, looks for anchor events.

        Returns:
            Updated events with resolved time windows.
        """
        self._audit.clear()
        resolved_count = 0

        # Find anchor datetime from events if not provided
        if anchor_datetime is None:
            anchor_datetime = self._find_anchor(events)

        if anchor_datetime is None:
            self._audit.append(
                TemporalAuditEntry(
                    stage="relative_time_resolution",
                    action="no_anchor_found",
                    detail="No anchor datetime available; relative expressions remain unresolved",
                )
            )
            return events

        for event in events:
            for expr in event.temporal_expressions:
                if expr.precision in (
                    TemporalPrecision.RELATIVE,
                    TemporalPrecision.APPROXIMATE,
                    TemporalPrecision.RANGE,
                ) and expr.resolution_method in (
                    ResolutionMethod.RELATIVE_ANCHOR,
                    ResolutionMethod.PMI_ESTIMATION,
                ):
                    resolved = self._resolve_expression(
                        expr, anchor_datetime
                    )
                    if resolved:
                        expr.time_window = resolved
                        expr.resolution_method = ResolutionMethod.RELATIVE_ANCHOR
                        resolved_count += 1

                        # Update event time window if not set
                        if event.time_window.best_estimate is None:
                            event.time_window = resolved

        self._audit.append(
            TemporalAuditEntry(
                stage="relative_time_resolution",
                action="resolution_complete",
                detail=(
                    f"Resolved {resolved_count} relative expressions "
                    f"using anchor: {anchor_datetime.isoformat()}"
                ),
            )
        )

        return events

    def _find_anchor(self, events: list[TemporalEvent]) -> datetime | None:
        """Find the best anchor datetime from events."""
        # Prefer examination events, then document creation, then any exact event
        for event in events:
            if event.is_anchor and event.time_window.best_estimate:
                dt = _parse_iso(event.time_window.best_estimate)
                if dt:
                    return dt

        for event in events:
            if event.category.value in ("EXAMINATION", "DOCUMENT_CREATION"):
                if event.time_window.best_estimate:
                    dt = _parse_iso(event.time_window.best_estimate)
                    if dt:
                        return dt

        for event in events:
            if event.time_window.best_estimate:
                dt = _parse_iso(event.time_window.best_estimate)
                if dt and event.time_window.precision == TemporalPrecision.EXACT:
                    return dt

        return None

    def _resolve_expression(
        self,
        expr: TemporalExpression,
        anchor: datetime,
    ) -> TimeWindow | None:
        """Resolve a single relative expression against an anchor."""
        hours_range = _extract_hours_from_normalized(expr.normalized_form)
        if hours_range is None:
            return None

        min_hours, max_hours = hours_range

        # "Prior" means subtract from anchor
        earliest = anchor - timedelta(hours=max_hours)
        latest = anchor - timedelta(hours=min_hours)
        best = anchor - timedelta(hours=(min_hours + max_hours) / 2)

        return TimeWindow(
            earliest=earliest.isoformat(),
            latest=latest.isoformat(),
            best_estimate=best.isoformat(),
            confidence=expr.confidence,
            precision=TemporalPrecision.RANGE,
            timezone_info=str(anchor.tzinfo) if anchor.tzinfo else None,
        )
