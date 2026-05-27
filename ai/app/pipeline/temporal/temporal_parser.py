"""
Atopsy — Temporal Parser (Layer 6).

Extracts and parses temporal expressions from text and entities.
Supports absolute dates, relative references, ranges, and
Indian medico-legal temporal formats.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.pipeline.temporal.schemas import (
    TemporalAuditEntry,
    TemporalExpression,
    TemporalPrecision,
    TimeWindow,
    ResolutionMethod,
)

# ─────────────────────────────────────────────
# Regex patterns for temporal extraction
# ─────────────────────────────────────────────

# Absolute date patterns
_DATE_PATTERNS: list[tuple[str, str]] = [
    # DD/MM/YYYY or DD-MM-YYYY
    (r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", "DD/MM/YYYY"),
    # YYYY-MM-DD (ISO)
    (r"\b(\d{4})-(\d{2})-(\d{2})\b", "YYYY-MM-DD"),
    # "25 January 2024", "25th January 2024"
    (
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})\b",
        "DD_MONTH_YYYY",
    ),
    # "January 25, 2024"
    (
        r"\b(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        "MONTH_DD_YYYY",
    ),
]

# Time patterns
_TIME_PATTERNS: list[tuple[str, str]] = [
    # HH:MM AM/PM
    (r"\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)\b", "HH:MM_AMPM"),
    # HH:MM (24h)
    (r"\b(\d{1,2}):(\d{2})\b", "HH:MM_24H"),
    # "around midnight", "about noon"
    (r"\b(?:around|about|approximately)\s+(midnight|noon)\b", "APPROX_TIME"),
]

# Relative time patterns
_RELATIVE_PATTERNS: list[tuple[str, str]] = [
    # "about X hours prior/before/ago"
    (
        r"\b(?:about|approximately|around|roughly)\s+"
        r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?|days?)\s+"
        r"(?:prior|before|ago|earlier)\b",
        "APPROX_RELATIVE",
    ),
    # "X hours prior/before/ago"
    (
        r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?|days?)\s+"
        r"(?:prior|before|ago|earlier)\b",
        "EXACT_RELATIVE",
    ),
    # "X to Y hours prior" or "X-Y hours prior"
    (
        r"\b(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*"
        r"(hours?|hrs?|minutes?|mins?|days?)\s+"
        r"(?:prior|before|ago|earlier)\b",
        "RANGE_RELATIVE",
    ),
    # "between X and Y pm/am"
    (
        r"\bbetween\s+(\d{1,2})\s*(?:and|&)\s*(\d{1,2})\s*"
        r"(am|pm|AM|PM)?\b",
        "BETWEEN_TIMES",
    ),
    # "last seen around midnight"
    (
        r"\blast\s+seen\s+(?:around|about|approximately)?\s*"
        r"(.+?)(?:\.|,|$)",
        "LAST_SEEN",
    ),
]

# PMI / TOD patterns (Indian medico-legal)
_PMI_PATTERNS: list[tuple[str, str]] = [
    # "post-mortem interval estimated at 12-18 hours"
    (
        r"\b(?:post[- ]?mortem\s+interval|PMI)\s*"
        r"(?:estimated|approximately|about|of)?\s*"
        r"(?:at|:)?\s*(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*"
        r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?)\b",
        "PMI_RANGE",
    ),
    # "time of death approximately 12-18 hours prior"
    (
        r"\b(?:time\s+of\s+death|TOD|estimated\s+TOD)\s*"
        r"(?::|\s+)\s*(?:approximately|about|around)?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*"
        r"(hours?|hrs?|days?)\s*(?:prior|before|ago)?\b",
        "TOD_RANGE",
    ),
    # "death occurred approximately X hours before"
    (
        r"\bdeath\s+(?:occurred|happened)\s+"
        r"(?:approximately|about|around)\s+"
        r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?)\s+"
        r"(?:before|prior|ago)\b",
        "DEATH_APPROX",
    ),
]

# Month name to number mapping
_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _unit_to_hours(value: float, unit: str) -> float:
    """Convert a time unit to hours."""
    unit = unit.lower().rstrip("s")
    if unit in ("hour", "hr"):
        return value
    if unit in ("minute", "min"):
        return value / 60.0
    if unit == "day":
        return value * 24.0
    return value


class TemporalParser:
    """
    Parses temporal expressions from text and entity values.

    Supports:
    - Absolute dates (DD/MM/YYYY, ISO, named months)
    - Time expressions (HH:MM AM/PM, midnight, noon)
    - Relative references (X hours prior, about Y days ago)
    - Range expressions (12-18 hours, between 8 and 9 pm)
    - PMI/TOD forensic expressions
    """

    def __init__(self) -> None:
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def parse_text(
        self,
        text: str,
        evidence_file_id: str = "",
        entity_id: str = "",
        page: int | None = None,
    ) -> list[TemporalExpression]:
        """
        Extract all temporal expressions from a text string.

        Args:
            text: The text to parse.
            evidence_file_id: Source evidence file.
            entity_id: Source entity.
            page: Source page number.

        Returns:
            List of parsed TemporalExpression objects.
        """
        expressions: list[TemporalExpression] = []

        # Absolute dates
        for pattern, fmt in _DATE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                expr = self._parse_date_match(
                    match, fmt, evidence_file_id, entity_id, page
                )
                if expr:
                    expressions.append(expr)

        # Relative time
        for pattern, fmt in _RELATIVE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                expr = self._parse_relative_match(
                    match, fmt, evidence_file_id, entity_id, page
                )
                if expr:
                    expressions.append(expr)

        # PMI / TOD patterns
        for pattern, fmt in _PMI_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                expr = self._parse_pmi_match(
                    match, fmt, evidence_file_id, entity_id, page
                )
                if expr:
                    expressions.append(expr)

        self._audit.append(
            TemporalAuditEntry(
                stage="temporal_parsing",
                action="text_parsed",
                detail=f"Extracted {len(expressions)} temporal expressions from text ({len(text)} chars)",
            )
        )

        return expressions

    def _parse_date_match(
        self,
        match: re.Match,
        fmt: str,
        evidence_file_id: str,
        entity_id: str,
        page: int | None,
    ) -> TemporalExpression | None:
        """Parse an absolute date match."""
        raw = match.group(0)
        try:
            if fmt == "DD/MM/YYYY":
                day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                dt = datetime(year, month, day, tzinfo=timezone.utc)
            elif fmt == "YYYY-MM-DD":
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                dt = datetime(year, month, day, tzinfo=timezone.utc)
            elif fmt == "DD_MONTH_YYYY":
                day = int(match.group(1))
                month = _MONTH_MAP.get(match.group(2).lower(), 1)
                year = int(match.group(3))
                dt = datetime(year, month, day, tzinfo=timezone.utc)
            elif fmt == "MONTH_DD_YYYY":
                month = _MONTH_MAP.get(match.group(1).lower(), 1)
                day = int(match.group(2))
                year = int(match.group(3))
                dt = datetime(year, month, day, tzinfo=timezone.utc)
            else:
                return None

            iso = dt.isoformat()
            return TemporalExpression(
                raw_text=raw,
                normalized_form=iso,
                precision=TemporalPrecision.EXACT,
                time_window=TimeWindow(
                    earliest=iso,
                    latest=iso,
                    best_estimate=iso,
                    confidence=0.90,
                    precision=TemporalPrecision.EXACT,
                ),
                resolution_method=ResolutionMethod.DIRECT_PARSE,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.90,
            )
        except (ValueError, OverflowError):
            return None

    def _parse_relative_match(
        self,
        match: re.Match,
        fmt: str,
        evidence_file_id: str,
        entity_id: str,
        page: int | None,
    ) -> TemporalExpression | None:
        """Parse a relative time match."""
        raw = match.group(0)

        if fmt == "APPROX_RELATIVE":
            value = float(match.group(1))
            unit = match.group(2)
            hours = _unit_to_hours(value, unit)
            margin = hours * 0.2  # ±20% uncertainty for "approximately"
            return TemporalExpression(
                raw_text=raw,
                normalized_form=f"~{hours:.1f} hours prior",
                precision=TemporalPrecision.APPROXIMATE,
                time_window=TimeWindow(
                    confidence=0.65,
                    precision=TemporalPrecision.APPROXIMATE,
                ),
                resolution_method=ResolutionMethod.RELATIVE_ANCHOR,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.65,
            )

        elif fmt == "EXACT_RELATIVE":
            value = float(match.group(1))
            unit = match.group(2)
            hours = _unit_to_hours(value, unit)
            return TemporalExpression(
                raw_text=raw,
                normalized_form=f"{hours:.1f} hours prior",
                precision=TemporalPrecision.RELATIVE,
                time_window=TimeWindow(
                    confidence=0.75,
                    precision=TemporalPrecision.RELATIVE,
                ),
                resolution_method=ResolutionMethod.RELATIVE_ANCHOR,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.75,
            )

        elif fmt == "RANGE_RELATIVE":
            low = float(match.group(1))
            high = float(match.group(2))
            unit = match.group(3)
            low_h = _unit_to_hours(low, unit)
            high_h = _unit_to_hours(high, unit)
            return TemporalExpression(
                raw_text=raw,
                normalized_form=f"{low_h:.1f}–{high_h:.1f} hours prior",
                precision=TemporalPrecision.RANGE,
                time_window=TimeWindow(
                    confidence=0.70,
                    precision=TemporalPrecision.RANGE,
                ),
                resolution_method=ResolutionMethod.RELATIVE_ANCHOR,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.70,
            )

        elif fmt == "BETWEEN_TIMES":
            return TemporalExpression(
                raw_text=raw,
                normalized_form=raw,
                precision=TemporalPrecision.RANGE,
                time_window=TimeWindow(
                    confidence=0.70,
                    precision=TemporalPrecision.RANGE,
                ),
                resolution_method=ResolutionMethod.DIRECT_PARSE,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.70,
            )

        return None

    def _parse_pmi_match(
        self,
        match: re.Match,
        fmt: str,
        evidence_file_id: str,
        entity_id: str,
        page: int | None,
    ) -> TemporalExpression | None:
        """Parse a PMI/TOD range match."""
        raw = match.group(0)

        if fmt in ("PMI_RANGE", "TOD_RANGE"):
            low = float(match.group(1))
            high = float(match.group(2))
            unit = match.group(3)
            low_h = _unit_to_hours(low, unit)
            high_h = _unit_to_hours(high, unit)
            mid = (low_h + high_h) / 2
            return TemporalExpression(
                raw_text=raw,
                normalized_form=f"PMI: {low_h:.1f}–{high_h:.1f} hours",
                precision=TemporalPrecision.RANGE,
                time_window=TimeWindow(
                    confidence=0.70,
                    precision=TemporalPrecision.RANGE,
                ),
                resolution_method=ResolutionMethod.PMI_ESTIMATION,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.70,
            )

        elif fmt == "DEATH_APPROX":
            value = float(match.group(1))
            unit = match.group(2)
            hours = _unit_to_hours(value, unit)
            return TemporalExpression(
                raw_text=raw,
                normalized_form=f"~{hours:.1f} hours prior to examination",
                precision=TemporalPrecision.APPROXIMATE,
                time_window=TimeWindow(
                    confidence=0.60,
                    precision=TemporalPrecision.APPROXIMATE,
                ),
                resolution_method=ResolutionMethod.PMI_ESTIMATION,
                source_evidence_id=evidence_file_id,
                source_entity_id=entity_id,
                page=page,
                confidence=0.60,
            )

        return None
