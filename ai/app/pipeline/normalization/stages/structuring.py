"""
Atopsy — Canonical Schema Structuring Stage.

Converts raw extracted metadata into the canonical
EvidenceRecord forensic schema for downstream AI consumption.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.logger import logger
from app.pipeline.normalization.stages.cleaning import clean_text, clean_dict_values
from app.pipeline.normalization.stages.timestamps import normalize_timestamp
from app.pipeline.normalization.stages.location import normalize_location
from app.pipeline.normalization.stages.medical import (
    standardize_medical_text,
    normalize_injury_type,
    normalize_body_region,
    normalize_manner_of_death,
)
from app.pipeline.normalization.stages.units import convert_measurement


def build_canonical_output(
    evidence_file_id: str,
    original_filename: str,
    mime_type: str,
    category: str,
    file_size: int,
    sha256_hash: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a canonical EvidenceRecord from raw extracted metadata.

    This is the final structuring stage that produces the
    standardized forensic intelligence object.
    """
    now = datetime.now(timezone.utc).isoformat()

    canonical: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_evidence_id": evidence_file_id,
        "normalized_at": now,
        "confidence": 1.0,
        "original_filename": original_filename,
        "mime_type": mime_type,
        "category": category,
        "file_size_bytes": file_size,
        "sha256_hash": sha256_hash,
    }

    # ── Digital Evidence ──────────────────────
    digital_evidence = _build_digital_evidence(
        evidence_file_id, metadata, mime_type, file_size
    )
    canonical["digital_evidence"] = digital_evidence

    # ── Temporal Events ──────────────────────
    temporal_events = _extract_temporal_events(
        evidence_file_id, metadata
    )
    canonical["temporal_events"] = temporal_events

    # ── Locations ────────────────────────────
    locations = _extract_locations(metadata)
    canonical["locations"] = locations

    # ── Raw metadata (cleaned) ───────────────
    canonical["raw_metadata"] = clean_dict_values(metadata)

    return canonical


def _build_digital_evidence(
    evidence_id: str,
    metadata: dict[str, Any],
    mime_type: str,
    file_size: int,
) -> dict[str, Any]:
    """Build the DigitalEvidence section."""
    de: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_evidence_id": evidence_id,
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "confidence": 1.0,
        "file_type": mime_type,
        "file_size_bytes": file_size,
    }

    # Timestamps
    for key in [
        "creation_date", "datetime_original", "creation_time",
        "CreationDate", "DateTimeOriginal",
    ]:
        val = metadata.get(key)
        if val:
            ts = normalize_timestamp(val)
            if ts:
                de["creation_timestamp"] = ts
                break

    for key in [
        "modification_date", "ModDate", "datetime_digitized",
    ]:
        val = metadata.get(key)
        if val:
            ts = normalize_timestamp(val)
            if ts:
                de["modification_timestamp"] = ts
                break

    # Device info
    device_info: dict[str, Any] = {}
    if metadata.get("camera_make"):
        device_info["make"] = metadata["camera_make"]
    if metadata.get("camera_model"):
        device_info["model"] = metadata["camera_model"]
    if metadata.get("software"):
        device_info["software"] = metadata["software"]
    if device_info:
        de["device_info"] = device_info

    # Location from EXIF GPS
    gps = metadata.get("gps")
    if gps:
        de["location"] = normalize_location(gps)

    # Content summary
    preview = metadata.get("content_preview")
    if preview:
        de["content_summary"] = clean_text(str(preview))[:500]
        de["extracted_text"] = clean_text(str(preview))

    # Document-specific
    if metadata.get("page_count"):
        de["page_count"] = int(metadata["page_count"])

    # Video-specific
    if metadata.get("duration_seconds"):
        de["duration_seconds"] = float(metadata["duration_seconds"])

    # Image dimensions
    if metadata.get("width") and metadata.get("height"):
        de["device_info"] = de.get("device_info", {})
        de["device_info"]["resolution"] = (
            f"{metadata['width']}x{metadata['height']}"
        )

    return de


def _extract_temporal_events(
    evidence_id: str,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract all datable events from metadata."""
    events: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    timestamp_fields = {
        "creation_date": "evidence_created",
        "modification_date": "evidence_modified",
        "datetime_original": "photo_taken",
        "datetime_digitized": "photo_digitized",
        "creation_time": "video_recorded",
        "CreationDate": "evidence_created",
        "ModDate": "evidence_modified",
        "DateTimeOriginal": "photo_taken",
    }

    for field, event_type in timestamp_fields.items():
        val = metadata.get(field)
        if val:
            ts = normalize_timestamp(val)
            if ts:
                events.append({
                    "schema_version": "1.0.0",
                    "source_evidence_id": evidence_id,
                    "normalized_at": now,
                    "confidence": 0.9,
                    "event_type": event_type,
                    "timestamp": ts,
                    "description": f"Extracted from metadata field: {field}",
                })

    return events


def _extract_locations(
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract all location data from metadata."""
    locations: list[dict[str, Any]] = []

    gps = metadata.get("gps")
    if gps:
        loc = normalize_location(gps)
        if loc and loc.get("latitude") is not None:
            locations.append(loc)

    return locations
