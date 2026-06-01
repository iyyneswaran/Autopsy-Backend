"""
Atopsy — PMI Estimator (Layer 7).

Dedicated post-mortem interval computation module.
Parses PMI range expressions, computes absolute TOD windows
by subtracting PMI from examination timestamps, and supports
temperature-adjusted ranges.
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
# PMI parsing patterns
# ─────────────────────────────────────────────

_RANGE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*"
    r"(hours?|hrs?|days?)",
    re.IGNORECASE,
)

_SINGLE_PATTERN = re.compile(
    r"(?:about|approximately|around|roughly|~)?\s*"
    r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?)",
    re.IGNORECASE,
)

_PRIOR_PATTERN = re.compile(
    r"(before|prior\s+to|preceding)\s+"
    r"(examination|autopsy|post[\s\-]?mortem)",
    re.IGNORECASE,
)


class PMIEstimator:
    """
    Dedicated PMI computation for TOD estimation.

    Processes PMI-type signals and computes absolute TOD
    windows anchored to examination events.
    """

    # Default temperature correction factor
    # > 1.0 = warmer (faster decomp, shorter effective PMI)
    # < 1.0 = cooler (slower decomp, longer effective PMI)
    DEFAULT_TEMP_FACTOR = 1.0

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def estimate(
        self,
        signals: list[ForensicSignal],
        examination_time: datetime | None = None,
        ambient_temperature_c: float | None = None,
    ) -> list[ForensicSignal]:
        """
        Process PMI signals and compute TOD windows.

        Focuses exclusively on PMI_STATEMENT signals.
        Other signal types are passed through unchanged.

        Args:
            signals: All forensic signals.
            examination_time: Autopsy/examination start time.
            ambient_temperature_c: Ambient temperature in Celsius
                                    for temperature adjustment.

        Returns:
            Signals with PMI-based windows computed.
        """
        self._audit.clear()
        pmi_count = 0

        temp_factor = self._compute_temp_factor(ambient_temperature_c)

        for signal in signals:
            if signal.signal_type != SignalType.PMI_STATEMENT:
                continue

            # Skip if window already computed
            if signal.tod_window.earliest or signal.tod_window.latest:
                pmi_count += 1
                continue

            window = self._compute_pmi_window(
                signal.raw_text or signal.normalized_value or "",
                examination_time,
                temp_factor,
            )
            if window:
                signal.tod_window = window
                pmi_count += 1

        self._audit.append(
            TODAuditEntry(
                stage="pmi_estimation",
                action="pmi_computed",
                detail=(
                    f"Computed {pmi_count} PMI-based windows, "
                    f"temp_factor={temp_factor:.2f}"
                ),
            )
        )

        return signals

    def _compute_pmi_window(
        self,
        text: str,
        exam_time: datetime | None,
        temp_factor: float,
    ) -> TODWindow | None:
        """Compute a TOD window from a PMI text expression."""
        hours_range = self._parse_pmi_hours(text)
        if hours_range is None:
            return None

        min_hours, max_hours = hours_range

        # Apply temperature correction
        min_hours *= temp_factor
        max_hours *= temp_factor

        best_hours = (min_hours + max_hours) / 2.0
        window_span = max_hours - min_hours

        # Confidence: tighter ranges = higher confidence
        confidence = max(0.2, min(0.95, 1.0 - (window_span / 60.0)))

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
            window_hours=round(window_span, 2),
            confidence=round(confidence, 3),
            precision=TODPrecision.RANGE,
        )

    def _parse_pmi_hours(
        self, text: str
    ) -> tuple[float, float] | None:
        """Parse a PMI expression into (min_hours, max_hours)."""
        # Try range pattern first: "12 to 24 hours"
        match = _RANGE_PATTERN.search(text)
        if match:
            val_a = float(match.group(1))
            val_b = float(match.group(2))
            unit = match.group(3).lower()
            min_h = self._to_hours(min(val_a, val_b), unit)
            max_h = self._to_hours(max(val_a, val_b), unit)
            return (min_h, max_h)

        # Try single value: "about 18 hours"
        match = _SINGLE_PATTERN.search(text)
        if match:
            val = float(match.group(1))
            unit = match.group(2).lower()
            hours = self._to_hours(val, unit)
            # ±25% uncertainty for single values
            return (hours * 0.75, hours * 1.25)

        return None

    def _compute_temp_factor(
        self, ambient_temp_c: float | None
    ) -> float:
        """
        Compute temperature correction factor for PMI.

        Based on simplified Henssge nomogram adjustment:
        - Standard reference: 20°C ambient
        - Higher temp → decomposition faster → shorter effective PMI
        - Lower temp → decomposition slower → longer effective PMI
        """
        if ambient_temp_c is None:
            return self.DEFAULT_TEMP_FACTOR

        reference_temp = 20.0
        diff = ambient_temp_c - reference_temp

        # ~5% adjustment per degree Celsius difference
        factor = 1.0 - (diff * 0.05)

        # Clamp to reasonable range
        return max(0.3, min(3.0, factor))

    @staticmethod
    def _to_hours(value: float, unit: str) -> float:
        """Convert value with unit to hours."""
        unit = unit.lower().rstrip("s")
        if unit in ("day",):
            return value * 24.0
        return value
