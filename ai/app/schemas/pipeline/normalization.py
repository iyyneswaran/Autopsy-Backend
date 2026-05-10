"""
Atopsy — Canonical Forensic Entity Schemas (Normalization Layer).

These are the standardized output schemas that all heterogeneous
forensic evidence gets normalized into. Designed for downstream
AI consumption (NLP, anomaly detection, timeline reconstruction).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ─────────────────────────────────────────────
# Base Canonical Schema
# ─────────────────────────────────────────────


class CanonicalBase(BaseModel):
    """Base for all canonical forensic entities."""

    model_config = ConfigDict(strict=True)

    schema_version: str = "1.0.0"
    source_evidence_id: UUID
    normalized_at: datetime
    confidence: float = Field(
        ge=0.0, le=1.0, default=1.0,
        description="Normalization confidence score"
    )


# ─────────────────────────────────────────────
# Temporal Event
# ─────────────────────────────────────────────


class NormalizedTimestamp(BaseModel):
    """
    Standardized timestamp with timezone awareness.
    All timestamps are converted to UTC with original preserved.
    """

    utc: datetime
    original_value: str | None = None
    original_timezone: str | None = None
    precision: str = "exact"  # exact | minute | hour | day | estimated


class TemporalEvent(CanonicalBase):
    """A single event in the forensic timeline."""

    event_type: str  # "evidence_created", "death", "observation"
    timestamp: NormalizedTimestamp
    description: str | None = None
    location: NormalizedLocation | None = None
    actors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Location
# ─────────────────────────────────────────────


class NormalizedLocation(BaseModel):
    """Standardized GPS / address location."""

    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    altitude_meters: float | None = None
    accuracy_meters: float | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = Field(None, max_length=3)
    raw_value: str | None = None


# ─────────────────────────────────────────────
# Victim / Subject Data
# ─────────────────────────────────────────────


class NormalizedMeasurement(BaseModel):
    """A measurement normalized to SI units."""

    value: float
    unit: str  # Always SI: kg, cm, °C, etc.
    original_value: float | None = None
    original_unit: str | None = None


class VictimData(CanonicalBase):
    """Normalized victim / subject information."""

    name: str | None = None
    age: int | None = Field(None, ge=0, le=200)
    gender: str | None = None
    height: NormalizedMeasurement | None = None
    weight: NormalizedMeasurement | None = None
    ethnicity: str | None = None
    identifying_marks: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Injury Observation
# ─────────────────────────────────────────────


class InjuryObservation(CanonicalBase):
    """Normalized injury observation from autopsy/medical records."""

    injury_type: str  # "laceration", "contusion", "fracture", etc.
    body_region: str  # "head", "thorax", "abdomen", etc.
    description: str
    severity: str | None = None  # "minor", "moderate", "severe", "fatal"
    mechanism: str | None = None  # "blunt_force", "sharp_force", "gunshot"
    dimensions: NormalizedMeasurement | None = None
    is_ante_mortem: bool | None = None
    raw_description: str | None = None


# ─────────────────────────────────────────────
# Autopsy Metadata
# ─────────────────────────────────────────────


class AutopsyMetadata(CanonicalBase):
    """Normalized autopsy report metadata."""

    case_number: str | None = None
    examiner: str | None = None
    examination_date: NormalizedTimestamp | None = None
    cause_of_death: str | None = None
    manner_of_death: str | None = None
    time_of_death: NormalizedTimestamp | None = None
    body_temperature: NormalizedMeasurement | None = None

    injuries: list[InjuryObservation] = Field(default_factory=list)
    toxicology: dict[str, Any] = Field(default_factory=dict)

    environmental_conditions: EnvironmentalConditions | None = None


# ─────────────────────────────────────────────
# Environmental Conditions
# ─────────────────────────────────────────────


class EnvironmentalConditions(CanonicalBase):
    """Normalized environmental / scene conditions."""

    temperature: NormalizedMeasurement | None = None
    humidity: float | None = Field(None, ge=0.0, le=100.0)
    weather: str | None = None
    lighting: str | None = None
    location: NormalizedLocation | None = None
    scene_description: str | None = None
    indoor: bool | None = None


# ─────────────────────────────────────────────
# Digital Evidence
# ─────────────────────────────────────────────


class DigitalEvidence(CanonicalBase):
    """Normalized digital evidence metadata."""

    file_type: str
    file_size_bytes: int
    creation_timestamp: NormalizedTimestamp | None = None
    modification_timestamp: NormalizedTimestamp | None = None
    device_info: dict[str, Any] = Field(default_factory=dict)
    location: NormalizedLocation | None = None
    content_summary: str | None = None
    extracted_text: str | None = None
    page_count: int | None = None
    duration_seconds: float | None = None


# ─────────────────────────────────────────────
# Evidence Record (top-level canonical wrapper)
# ─────────────────────────────────────────────


class EvidenceRecord(CanonicalBase):
    """
    Top-level canonical forensic entity.
    Wraps all normalized data for a single evidence file.
    This is the primary output of the normalization pipeline.
    """

    # File info
    original_filename: str
    mime_type: str
    category: str
    file_size_bytes: int
    sha256_hash: str

    # Normalized content
    digital_evidence: DigitalEvidence | None = None
    victim_data: VictimData | None = None
    autopsy_metadata: AutopsyMetadata | None = None
    environmental_conditions: EnvironmentalConditions | None = None
    injuries: list[InjuryObservation] = Field(default_factory=list)
    temporal_events: list[TemporalEvent] = Field(default_factory=list)
    locations: list[NormalizedLocation] = Field(default_factory=list)

    # Raw extracted metadata
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    # Quality
    quality_score: float = 0.0
    completeness_score: float = 0.0
    anomalies: list[str] = Field(default_factory=list)


# Fix forward references
TemporalEvent.model_rebuild()
AutopsyMetadata.model_rebuild()
