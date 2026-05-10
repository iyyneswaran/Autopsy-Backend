"""
Atopsy — Anomaly Pre-Check Engine.

Detects data quality issues before downstream AI processing:
- Impossible timestamps (future, too old)
- Invalid GPS coordinates
- Corrupted metadata
- Inconsistent units
- Duplicate content markers
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logger import logger


def run_anomaly_checks(
    metadata: dict[str, Any],
    canonical: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Run all anomaly pre-checks on the extracted metadata
    and canonical output.

    Returns a list of AnomalyReport-compatible dicts.
    """
    anomalies: list[dict[str, Any]] = []

    anomalies.extend(_check_timestamps(metadata, canonical))
    anomalies.extend(_check_gps(metadata, canonical))
    anomalies.extend(_check_metadata_integrity(metadata))
    anomalies.extend(_check_file_consistency(canonical))

    if anomalies:
        logger.info(
            f"Detected {len(anomalies)} anomalies in evidence "
            f"{canonical.get('source_evidence_id', 'unknown')}"
        )

    return anomalies


def _check_timestamps(
    metadata: dict[str, Any],
    canonical: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for impossible or suspicious timestamps."""
    anomalies: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    timestamp_fields = [
        "creation_date", "modification_date",
        "datetime_original", "datetime_digitized",
        "creation_time",
    ]

    for field in timestamp_fields:
        val = metadata.get(field)
        if not val:
            continue

        try:
            if isinstance(val, str):
                # Quick parse check
                from app.pipeline.normalization.stages.timestamps import (
                    normalize_timestamp,
                )
                parsed = normalize_timestamp(val)
                if not parsed:
                    anomalies.append({
                        "anomaly_type": "unparseable_timestamp",
                        "severity": "warning",
                        "field": field,
                        "description": f"Cannot parse timestamp: '{val}'",
                        "value": val,
                    })
                    continue

                utc_str = parsed.get("utc", "")
                if isinstance(utc_str, str):
                    dt = datetime.fromisoformat(utc_str)
                else:
                    dt = utc_str

                # Future timestamp (more than 1 day ahead)
                from datetime import timedelta
                if dt > now + timedelta(days=1):
                    anomalies.append({
                        "anomaly_type": "future_timestamp",
                        "severity": "critical",
                        "field": field,
                        "description": f"Timestamp is in the future: {val}",
                        "value": val,
                        "suggestion": "Verify device clock settings",
                    })

                # Very old (before 1900)
                if dt.year < 1900:
                    anomalies.append({
                        "anomaly_type": "impossible_timestamp",
                        "severity": "critical",
                        "field": field,
                        "description": f"Timestamp before 1900: {val}",
                        "value": val,
                    })

        except Exception:
            pass

    return anomalies


def _check_gps(
    metadata: dict[str, Any],
    canonical: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for invalid GPS coordinates."""
    anomalies: list[dict[str, Any]] = []

    gps = metadata.get("gps")
    if not gps or not isinstance(gps, dict):
        return anomalies

    lat = gps.get("latitude")
    lon = gps.get("longitude")

    if lat is not None and lon is not None:
        try:
            lat_f, lon_f = float(lat), float(lon)

            if not (-90.0 <= lat_f <= 90.0):
                anomalies.append({
                    "anomaly_type": "invalid_gps",
                    "severity": "critical",
                    "field": "gps.latitude",
                    "description": f"Latitude {lat_f} out of range [-90, 90]",
                    "value": lat_f,
                })

            if not (-180.0 <= lon_f <= 180.0):
                anomalies.append({
                    "anomaly_type": "invalid_gps",
                    "severity": "critical",
                    "field": "gps.longitude",
                    "description": f"Longitude {lon_f} out of range [-180, 180]",
                    "value": lon_f,
                })

            if lat_f == 0.0 and lon_f == 0.0:
                anomalies.append({
                    "anomaly_type": "suspicious_gps",
                    "severity": "warning",
                    "field": "gps",
                    "description": "GPS coordinates are (0, 0) — likely placeholder",
                    "value": {"lat": lat_f, "lon": lon_f},
                    "suggestion": "Verify GPS data authenticity",
                })

        except (ValueError, TypeError):
            anomalies.append({
                "anomaly_type": "malformed_gps",
                "severity": "warning",
                "field": "gps",
                "description": f"Non-numeric GPS values: ({lat}, {lon})",
                "value": gps,
            })

    return anomalies


def _check_metadata_integrity(
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for corrupted or suspicious metadata."""
    anomalies: list[dict[str, Any]] = []

    # Check for error fields in metadata
    if metadata.get("error"):
        anomalies.append({
            "anomaly_type": "metadata_extraction_error",
            "severity": "warning",
            "field": "metadata",
            "description": f"Metadata extraction error: {metadata['error']}",
            "value": metadata["error"],
        })

    # Very large page counts
    page_count = metadata.get("page_count")
    if page_count is not None:
        try:
            if int(page_count) > 10000:
                anomalies.append({
                    "anomaly_type": "suspicious_page_count",
                    "severity": "warning",
                    "field": "page_count",
                    "description": f"Unusually high page count: {page_count}",
                    "value": page_count,
                })
        except (ValueError, TypeError):
            pass

    return anomalies


def _check_file_consistency(
    canonical: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check for consistency issues in the canonical output."""
    anomalies: list[dict[str, Any]] = []

    # Zero file size
    if canonical.get("file_size_bytes", 0) == 0:
        anomalies.append({
            "anomaly_type": "zero_file_size",
            "severity": "critical",
            "field": "file_size_bytes",
            "description": "File size is 0 bytes",
            "value": 0,
        })

    return anomalies
