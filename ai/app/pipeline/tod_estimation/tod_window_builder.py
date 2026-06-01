"""
Atopsy — TOD Window Builder (Layer 7).

Converts forensic signals into concrete TOD time windows.
Applies forensic rules for each signal type: rigor stages,
lividity fixation, cooling approximations, PMI backward
computation, and decomposition staging.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from app.pipeline.tod_estimation.schemas import (
    ForensicSignal,
    SignalType,
    TODAuditEntry,
    TODPrecision,
    TODWindow,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Forensic timing rules (hours post-mortem)
# ─────────────────────────────────────────────

# Rigor mortis staging
_RIGOR_STAGES: dict[str, tuple[float, float]] = {
    "absent": (0.0, 2.0),
    "onset": (2.0, 6.0),
    "developing": (2.0, 6.0),
    "partial": (4.0, 8.0),
    "present": (2.0, 12.0),
    "complete": (6.0, 12.0),
    "fully developed": (6.0, 12.0),
    "well developed": (8.0, 14.0),
    "passing off": (24.0, 48.0),
    "resolved": (36.0, 72.0),
    "breaking": (24.0, 48.0),
}

# Lividity staging
_LIVIDITY_STAGES: dict[str, tuple[float, float]] = {
    "absent": (0.0, 0.5),
    "faint": (0.5, 2.0),
    "developing": (1.0, 4.0),
    "present": (0.5, 8.0),
    "well developed": (4.0, 8.0),
    "unfixed": (0.5, 8.0),
    "partially fixed": (6.0, 12.0),
    "fixed": (8.0, 12.0),
    "completely fixed": (10.0, 24.0),
}

# Decomposition staging (very broad ranges)
_DECOMPOSITION_STAGES: dict[str, tuple[float, float]] = {
    "fresh": (0.0, 24.0),
    "early": (24.0, 72.0),
    "bloating": (48.0, 120.0),
    "advanced": (120.0, 360.0),
    "skeletonization": (360.0, 8760.0),
    "greenish discoloration": (24.0, 72.0),
    "marbling": (48.0, 96.0),
    "skin slip": (72.0, 168.0),
    "maggot": (24.0, 720.0),
    "insect activity": (24.0, 720.0),
    "putrefaction": (48.0, 168.0),
}

# PMI range patterns
_PMI_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*"
    r"(hours?|hrs?|days?|minutes?|mins?)",
    re.IGNORECASE,
)

_PMI_APPROX_RE = re.compile(
    r"(?:about|approximately|around|roughly|nearly|~)\s*"
    r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?|minutes?|mins?)",
    re.IGNORECASE,
)


class TODWindowBuilder:
    """
    Converts forensic signals into TOD time windows.

    Each signal type has forensic-specific conversion rules:
    - Rigor mortis → stage-based hour ranges
    - Lividity → fixation timing rules
    - Body cooling → simplified Henssge approximation
    - PMI statements → backward computation from anchor
    - Decomposition → stage-based broad ranges
    - Last seen alive → open-ended window
    - Discovery → latest possible death bound
    """

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def build_windows(
        self,
        signals: list[ForensicSignal],
        examination_time: datetime | None = None,
    ) -> list[ForensicSignal]:
        """
        Populate TOD windows on each signal.

        Modifies signals in place and returns them.

        Args:
            signals: Forensic signals with raw text.
            examination_time: Anchor datetime for backward
                              computation (e.g., autopsy start).

        Returns:
            Signals with populated tod_window fields.
        """
        self._audit.clear()
        built_count = 0

        for signal in signals:
            # Skip if window is already populated (e.g., from Layer 6)
            if (
                signal.tod_window.earliest
                or signal.tod_window.latest
                or signal.tod_window.best_estimate
            ):
                built_count += 1
                continue

            window = self._build_window(signal, examination_time)
            if window:
                signal.tod_window = window
                built_count += 1

        self._audit.append(
            TODAuditEntry(
                stage="window_building",
                action="windows_built",
                signal_ids=[s.signal_id for s in signals],
                detail=(
                    f"Built {built_count} windows from "
                    f"{len(signals)} signals"
                ),
            )
        )

        return signals

    def _build_window(
        self,
        signal: ForensicSignal,
        exam_time: datetime | None,
    ) -> TODWindow | None:
        """Build a TOD window for a single signal."""
        text = signal.normalized_value or signal.raw_text or ""
        text_lower = text.lower()

        if signal.signal_type == SignalType.RIGOR_MORTIS:
            return self._window_from_stage_table(
                text_lower, _RIGOR_STAGES, exam_time, "rigor"
            )

        if signal.signal_type == SignalType.LIVIDITY:
            return self._window_from_stage_table(
                text_lower, _LIVIDITY_STAGES, exam_time, "lividity"
            )

        if signal.signal_type == SignalType.DECOMPOSITION:
            return self._window_from_stage_table(
                text_lower, _DECOMPOSITION_STAGES, exam_time, "decomposition"
            )

        if signal.signal_type == SignalType.PMI_STATEMENT:
            return self._window_from_pmi(text, exam_time)

        if signal.signal_type == SignalType.BODY_COOLING:
            return self._window_from_cooling(text_lower, exam_time)

        # For other signal types, return None (no window inferrable)
        return None

    def _window_from_stage_table(
        self,
        text: str,
        table: dict[str, tuple[float, float]],
        exam_time: datetime | None,
        stage_label: str,
    ) -> TODWindow | None:
        """Match text against a stage table and compute window."""
        matched_min: float | None = None
        matched_max: float | None = None

        for keyword, (min_h, max_h) in table.items():
            if keyword in text:
                if matched_min is None or min_h < matched_min:
                    matched_min = min_h
                if matched_max is None or max_h > matched_max:
                    matched_max = max_h

        if matched_min is None or matched_max is None:
            return None

        return self._hours_to_window(
            matched_min, matched_max, exam_time, TODPrecision.RANGE
        )

    def _window_from_pmi(
        self, text: str, exam_time: datetime | None
    ) -> TODWindow | None:
        """Parse PMI range expression and compute window."""
        # Try range pattern: "12 to 24 hours"
        match = _PMI_RANGE_RE.search(text)
        if match:
            min_val = float(match.group(1))
            max_val = float(match.group(2))
            unit = match.group(3).lower()
            min_h = self._to_hours(min_val, unit)
            max_h = self._to_hours(max_val, unit)
            return self._hours_to_window(
                min_h, max_h, exam_time, TODPrecision.RANGE
            )

        # Try approximate pattern: "about 18 hours"
        match = _PMI_APPROX_RE.search(text)
        if match:
            val = float(match.group(1))
            unit = match.group(2).lower()
            hours = self._to_hours(val, unit)
            # ±20% uncertainty for approximate values
            min_h = hours * 0.8
            max_h = hours * 1.2
            return self._hours_to_window(
                min_h, max_h, exam_time, TODPrecision.APPROXIMATE
            )

        return None

    def _window_from_cooling(
        self, text: str, exam_time: datetime | None
    ) -> TODWindow | None:
        """Estimate TOD window from body cooling description."""
        # Simplified Henssge-like heuristics
        if "cold to touch" in text or "cold" in text:
            return self._hours_to_window(
                12.0, 36.0, exam_time, TODPrecision.RANGE
            )
        if "warm to touch" in text or "warm" in text:
            return self._hours_to_window(
                0.0, 6.0, exam_time, TODPrecision.RANGE
            )
        if "cool" in text:
            return self._hours_to_window(
                6.0, 18.0, exam_time, TODPrecision.RANGE
            )
        return None

    def _hours_to_window(
        self,
        min_hours: float,
        max_hours: float,
        exam_time: datetime | None,
        precision: TODPrecision,
    ) -> TODWindow:
        """Convert hour ranges before examination to a TOD window."""
        best_hours = (min_hours + max_hours) / 2.0
        window_span = max_hours - min_hours

        # Confidence decreases with wider windows
        confidence = max(0.1, 1.0 - (window_span / 100.0))

        earliest: str | None = None
        latest: str | None = None
        best_estimate: str | None = None

        if exam_time:
            if exam_time.tzinfo is None:
                exam_time = exam_time.replace(tzinfo=timezone.utc)
            earliest_dt = exam_time - timedelta(hours=max_hours)
            latest_dt = exam_time - timedelta(hours=min_hours)
            best_dt = exam_time - timedelta(hours=best_hours)
            earliest = earliest_dt.isoformat()
            latest = latest_dt.isoformat()
            best_estimate = best_dt.isoformat()

        return TODWindow(
            earliest=earliest,
            latest=latest,
            best_estimate=best_estimate,
            window_hours=window_span,
            confidence=round(confidence, 3),
            precision=precision,
        )

    @staticmethod
    def _to_hours(value: float, unit: str) -> float:
        """Convert a value with unit to hours."""
        unit = unit.lower().rstrip("s")
        if unit in ("day",):
            return value * 24.0
        if unit in ("minute", "min"):
            return value / 60.0
        return value  # default: hours
