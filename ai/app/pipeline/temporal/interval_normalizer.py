"""
Atopsy — Interval Normalizer (Layer 6).

Normalizes time intervals and ranges from various forensic
expressions into standard UncertaintyRange objects.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.pipeline.temporal.schemas import (
    TemporalAuditEntry,
    TemporalExpression,
    TemporalPrecision,
    UncertaintyRange,
)


# ─────────────────────────────────────────────
# Unit conversion
# ─────────────────────────────────────────────

def _to_hours(value: float, unit: str) -> float:
    """Convert any time unit to hours."""
    u = unit.lower().rstrip("s")
    if u in ("hour", "hr"):
        return value
    if u in ("minute", "min"):
        return value / 60.0
    if u == "day":
        return value * 24.0
    if u == "week":
        return value * 168.0
    if u == "month":
        return value * 720.0
    return value


class IntervalNormalizer:
    """
    Normalizes time intervals from temporal expressions
    into standardized UncertaintyRange objects.

    Handles:
    - Numeric ranges (12-18 hours)
    - Approximate values (~15 hours)
    - Named intervals (overnight, early morning)
    - Decomposition stages with known time ranges
    """

    # Decomposition stage → typical hour ranges
    DECOMPOSITION_INTERVALS: dict[str, tuple[float, float]] = {
        "fresh": (0, 24),
        "early decomposition": (24, 72),
        "bloat": (72, 240),
        "active decay": (240, 720),
        "advanced decay": (720, 2160),
        "skeletonization": (2160, 8760),
    }

    # Named time-of-day → hour ranges
    NAMED_INTERVALS: dict[str, tuple[float, float]] = {
        "midnight": (0, 0),
        "early morning": (4, 7),
        "morning": (6, 12),
        "noon": (12, 12),
        "afternoon": (12, 17),
        "evening": (17, 21),
        "night": (21, 4),
        "overnight": (21, 6),
        "dawn": (5, 7),
        "dusk": (17, 19),
    }

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def normalize_intervals(
        self,
        expressions: list[TemporalExpression],
    ) -> list[UncertaintyRange]:
        """
        Normalize temporal expressions into UncertaintyRange objects.

        Args:
            expressions: Parsed temporal expressions.

        Returns:
            List of UncertaintyRange objects.
        """
        self._audit.clear()
        ranges: list[UncertaintyRange] = []

        for expr in expressions:
            ur = self._normalize_single(expr)
            if ur:
                ranges.append(ur)

        self._audit.append(
            TemporalAuditEntry(
                stage="interval_normalization",
                action="normalization_complete",
                detail=f"Normalized {len(ranges)} intervals from {len(expressions)} expressions",
            )
        )

        return ranges

    def _normalize_single(
        self, expr: TemporalExpression
    ) -> UncertaintyRange | None:
        """Normalize a single temporal expression."""
        text = expr.normalized_form or expr.raw_text
        if not text:
            return None

        # Try range extraction: "12.0–18.0 hours"
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*[–\-]\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?|minutes?|mins?|weeks?)",
            text,
            re.IGNORECASE,
        )
        if m:
            low = _to_hours(float(m.group(1)), m.group(3))
            high = _to_hours(float(m.group(2)), m.group(3))
            return UncertaintyRange(
                label=f"Interval: {expr.raw_text}",
                raw_expression=expr.raw_text,
                min_hours=low,
                max_hours=high,
                best_estimate_hours=(low + high) / 2,
                unit="hours",
                confidence=expr.confidence,
                source_evidence_id=expr.source_evidence_id,
            )

        # Try approximate: "~15.0 hours"
        m = re.search(
            r"~(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?|minutes?|mins?)",
            text,
            re.IGNORECASE,
        )
        if m:
            val = _to_hours(float(m.group(1)), m.group(2))
            margin = val * 0.2
            return UncertaintyRange(
                label=f"Approximate: {expr.raw_text}",
                raw_expression=expr.raw_text,
                min_hours=val - margin,
                max_hours=val + margin,
                best_estimate_hours=val,
                unit="hours",
                confidence=expr.confidence,
                source_evidence_id=expr.source_evidence_id,
            )

        # Try decomposition stage
        lower = text.lower()
        for stage, (lo, hi) in self.DECOMPOSITION_INTERVALS.items():
            if stage in lower:
                return UncertaintyRange(
                    label=f"Decomposition: {stage}",
                    raw_expression=expr.raw_text,
                    min_hours=lo,
                    max_hours=hi,
                    best_estimate_hours=(lo + hi) / 2,
                    unit="hours",
                    confidence=0.60,
                    source_evidence_id=expr.source_evidence_id,
                )

        return None

    def normalize_pmi(
        self,
        min_hours: float,
        max_hours: float,
        raw_text: str = "",
        evidence_file_id: str = "",
    ) -> UncertaintyRange:
        """
        Create an UncertaintyRange directly from PMI hour bounds.

        Convenience method for direct PMI normalization without
        going through expression parsing.
        """
        return UncertaintyRange(
            label=f"PMI: {min_hours:.1f}–{max_hours:.1f} hours",
            raw_expression=raw_text,
            min_hours=min_hours,
            max_hours=max_hours,
            best_estimate_hours=(min_hours + max_hours) / 2,
            unit="hours",
            confidence=0.70,
            source_evidence_id=evidence_file_id,
        )
