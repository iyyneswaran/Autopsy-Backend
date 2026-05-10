"""
Atopsy — Data Quality Scoring Engine.

Generates completeness, confidence, and overall quality scores
for normalized forensic evidence records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID


# Fields that contribute to quality scoring, by category
QUALITY_FIELDS: dict[str, list[str]] = {
    "core": [
        "original_filename", "mime_type", "category",
        "file_size_bytes", "sha256_hash",
    ],
    "digital_evidence": [
        "file_type", "file_size_bytes",
        "creation_timestamp", "modification_timestamp",
        "device_info", "content_summary",
    ],
    "temporal": [
        "temporal_events",
    ],
    "location": [
        "locations",
    ],
    "content": [
        "raw_metadata",
    ],
}


def compute_quality_report(
    evidence_file_id: str,
    canonical: dict[str, Any],
    anomalies: list[dict[str, Any]],
    stage_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compute a comprehensive quality report for a normalized record.

    Returns a QualityReport-compatible dict.
    """
    field_reports: list[dict[str, Any]] = []
    total_fields = 0
    present_fields = 0
    valid_fields = 0
    missing_fields: list[str] = []

    # ── Check core fields ────────────────────

    for field in QUALITY_FIELDS["core"]:
        total_fields += 1
        val = canonical.get(field)
        is_present = val is not None and val != "" and val != 0
        is_valid = is_present

        if is_present:
            present_fields += 1
        else:
            missing_fields.append(field)

        if is_valid:
            valid_fields += 1

        field_reports.append({
            "field_name": field,
            "is_present": is_present,
            "is_valid": is_valid,
            "confidence": 1.0 if is_valid else 0.0,
            "warnings": [],
        })

    # ── Check digital evidence ───────────────

    de = canonical.get("digital_evidence", {})
    if de:
        for field in QUALITY_FIELDS["digital_evidence"]:
            total_fields += 1
            val = de.get(field)
            is_present = val is not None and val != "" and val != {}
            is_valid = is_present

            if is_present:
                present_fields += 1
            else:
                missing_fields.append(f"digital_evidence.{field}")

            if is_valid:
                valid_fields += 1

            field_reports.append({
                "field_name": f"digital_evidence.{field}",
                "is_present": is_present,
                "is_valid": is_valid,
                "confidence": 1.0 if is_valid else 0.0,
                "warnings": [],
            })

    # ── Check temporal events ────────────────

    total_fields += 1
    events = canonical.get("temporal_events", [])
    has_events = len(events) > 0
    if has_events:
        present_fields += 1
        valid_fields += 1
    else:
        missing_fields.append("temporal_events")

    field_reports.append({
        "field_name": "temporal_events",
        "is_present": has_events,
        "is_valid": has_events,
        "confidence": 1.0 if has_events else 0.0,
        "warnings": [],
    })

    # ── Check locations ──────────────────────

    total_fields += 1
    locations = canonical.get("locations", [])
    has_locations = len(locations) > 0
    if has_locations:
        present_fields += 1
        valid_fields += 1
    else:
        missing_fields.append("locations")

    field_reports.append({
        "field_name": "locations",
        "is_present": has_locations,
        "is_valid": has_locations,
        "confidence": 1.0 if has_locations else 0.0,
        "warnings": [],
    })

    # ── Compute scores ───────────────────────

    completeness = present_fields / total_fields if total_fields > 0 else 0.0
    validity = valid_fields / total_fields if total_fields > 0 else 0.0

    # Anomaly penalty
    anomaly_penalty = min(len(anomalies) * 0.1, 0.5)
    critical_anomalies = sum(
        1 for a in anomalies if a.get("severity") == "critical"
    )
    anomaly_penalty += critical_anomalies * 0.15

    # Confidence score (combination of completeness and validity)
    confidence = (completeness * 0.4 + validity * 0.6)

    # Overall quality = weighted combination minus anomaly penalties
    overall = max(0.0, (completeness * 0.3 + validity * 0.4 + confidence * 0.3) - anomaly_penalty)

    return {
        "evidence_file_id": evidence_file_id,
        "overall_quality_score": round(overall, 4),
        "completeness_score": round(completeness, 4),
        "confidence_score": round(confidence, 4),
        "total_fields": total_fields,
        "present_fields": present_fields,
        "valid_fields": valid_fields,
        "missing_fields": missing_fields,
        "field_reports": field_reports,
        "anomalies": anomalies,
        "stage_reports": stage_reports or [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
