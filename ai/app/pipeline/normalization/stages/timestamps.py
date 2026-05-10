"""
Atopsy — Timestamp Normalization Stage.

Converts heterogeneous date/time formats into UTC-normalized
NormalizedTimestamp objects with original value preservation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any

from app.core.logger import logger


# Common forensic date formats (ordered by likelihood)
DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",           # ISO 8601 with tz
    "%Y-%m-%dT%H:%M:%SZ",            # ISO 8601 UTC
    "%Y-%m-%dT%H:%M:%S.%f%z",        # ISO with microseconds
    "%Y-%m-%dT%H:%M:%S.%fZ",         # ISO with microseconds UTC
    "%Y-%m-%dT%H:%M:%S",             # ISO without tz
    "%Y-%m-%d %H:%M:%S",             # Standard datetime
    "%Y-%m-%d %H:%M:%S%z",           # Standard with tz
    "%Y-%m-%d",                       # Date only
    "%m/%d/%Y %H:%M:%S",             # US format
    "%m/%d/%Y %I:%M:%S %p",          # US 12-hour
    "%m/%d/%Y",                       # US date
    "%d/%m/%Y %H:%M:%S",             # EU format
    "%d/%m/%Y",                       # EU date
    "%d-%m-%Y %H:%M:%S",             # EU dash
    "%d-%m-%Y",                       # EU date dash
    "%B %d, %Y",                      # "January 15, 2024"
    "%b %d, %Y",                      # "Jan 15, 2024"
    "%Y%m%d%H%M%S",                   # Compact
    "%Y:%m:%d %H:%M:%S",             # EXIF format
    "%a %b %d %H:%M:%S %Y",          # ctime
    "%d %B %Y",                       # "15 January 2024"
    "%Y.%m.%d %H:%M:%S",             # Dot-separated
]

# Timezone abbreviation offsets
TZ_OFFSETS: dict[str, int] = {
    "UTC": 0, "GMT": 0, "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5, "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7, "IST": 5,  # +5:30 handled separately
    "JST": 9, "CET": 1, "CEST": 2, "AEST": 10,
}


def normalize_timestamp(
    value: Any,
    source_timezone: str | None = None,
) -> dict[str, Any] | None:
    """
    Normalize a timestamp value to UTC.

    Returns dict compatible with NormalizedTimestamp schema:
      {"utc": datetime, "original_value": str, "original_timezone": str, "precision": str}
    """
    if value is None:
        return None

    original_str = str(value).strip()
    if not original_str:
        return None

    # Already a datetime
    if isinstance(value, datetime):
        return _make_result(value, original_str, source_timezone)

    # Try parsing
    parsed = _parse_datetime(original_str)
    if parsed:
        return _make_result(parsed, original_str, source_timezone)

    # Try EXIF-style: "2024:01:15 14:30:00"
    exif_match = re.match(
        r"(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})",
        original_str,
    )
    if exif_match:
        try:
            g = exif_match.groups()
            dt = datetime(
                int(g[0]), int(g[1]), int(g[2]),
                int(g[3]), int(g[4]), int(g[5]),
                tzinfo=timezone.utc,
            )
            return _make_result(dt, original_str, source_timezone, "exact")
        except ValueError:
            pass

    # Try PDF date: "D:20240115143000+05'30'"
    pdf_match = re.match(
        r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})",
        original_str,
    )
    if pdf_match:
        try:
            g = pdf_match.groups()
            dt = datetime(
                int(g[0]), int(g[1]), int(g[2]),
                int(g[3]), int(g[4]), int(g[5]),
                tzinfo=timezone.utc,
            )
            return _make_result(dt, original_str, source_timezone, "exact")
        except ValueError:
            pass

    # Partial: year-month only
    ym_match = re.match(r"(\d{4})-(\d{2})$", original_str)
    if ym_match:
        try:
            dt = datetime(
                int(ym_match.group(1)),
                int(ym_match.group(2)),
                1,
                tzinfo=timezone.utc,
            )
            return _make_result(dt, original_str, source_timezone, "day")
        except ValueError:
            pass

    # Year only
    year_match = re.match(r"^(\d{4})$", original_str)
    if year_match:
        try:
            dt = datetime(int(year_match.group(1)), 1, 1, tzinfo=timezone.utc)
            return _make_result(dt, original_str, source_timezone, "estimated")
        except ValueError:
            pass

    logger.warning(f"Could not parse timestamp: '{original_str}'")
    return None


def _parse_datetime(s: str) -> datetime | None:
    """Try parsing with known formats."""
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _make_result(
    dt: datetime,
    original: str,
    tz: str | None,
    precision: str = "exact",
) -> dict[str, Any]:
    """Build the normalized timestamp result dict."""
    if dt.tzinfo is None:
        if tz and tz.upper() in TZ_OFFSETS:
            offset = TZ_OFFSETS[tz.upper()]
            dt = dt.replace(tzinfo=timezone(timedelta(hours=offset)))
        else:
            dt = dt.replace(tzinfo=timezone.utc)

    utc_dt = dt.astimezone(timezone.utc)

    return {
        "utc": utc_dt.isoformat(),
        "original_value": original,
        "original_timezone": tz,
        "precision": precision,
    }
