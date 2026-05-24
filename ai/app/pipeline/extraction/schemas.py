"""
Atopsy — OCR & NLP Extraction Schemas (Layer 3).

Pydantic models for the intermediate extraction pipeline output.
Covers text assembly, source spans, extracted spans, and the
top-level ExtractionEnvelope that bridges OCR output to entity
structuring.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Source-Level Metadata
# ─────────────────────────────────────────────


class SourceSpan(BaseModel):
    """Character-level provenance linking an extraction back to OCR output."""

    page: int = 0
    line: int = 0
    start_char: int = 0
    end_char: int = 0
    raw_text: str = ""


class TokenMetadata(BaseModel):
    """Per-token metadata from OCR word output."""

    text: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    bbox: dict[str, int] | None = None
    page: int = 0
    line_idx: int = 0


class LineMetadata(BaseModel):
    """Per-line metadata assembled from OCR lines/words."""

    text: str = ""
    tokens: list[TokenMetadata] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    bbox: dict[str, int] | None = None
    page: int = 0
    line_number: int = 0
    content_type: str = "UNKNOWN"


# ─────────────────────────────────────────────
# Assembled Document
# ─────────────────────────────────────────────


class PageText(BaseModel):
    """Assembled text for a single page with line-level metadata."""

    page_number: int = 0
    text: str = ""
    lines: list[LineMetadata] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    content_type: str = "UNKNOWN"
    language: str = ""
    ocr_engine: str = ""


class AssembledDocument(BaseModel):
    """Full document text assembled from OCR page results with hierarchy."""

    full_text: str = ""
    pages: list[PageText] = Field(default_factory=list)
    total_lines: int = 0
    total_tokens: int = 0
    average_confidence: float = Field(0.0, ge=0.0, le=1.0)
    languages_detected: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    assembly_time_ms: float = 0.0


# ─────────────────────────────────────────────
# Extracted Span
# ─────────────────────────────────────────────


class ExtractionMethod(str, enum.Enum):
    """How a span was extracted."""

    RULE_BASED = "rule_based"
    MODEL_ASSISTED = "model_assisted"
    HYBRID = "hybrid"


class ExtractedSpan(BaseModel):
    """A single NLP extraction with full provenance."""

    entity_type: str
    value: str
    source_span: SourceSpan = Field(default_factory=SourceSpan)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    extractor_id: str = ""
    extraction_method: str = "rule_based"
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_partial: bool = False


# ─────────────────────────────────────────────
# Pipeline Stage & Metadata
# ─────────────────────────────────────────────


class ExtractionStageReport(BaseModel):
    """Report for a single extraction pipeline stage."""

    stage: str
    status: str = "completed"
    duration_ms: float = 0.0
    detail: str = ""
    error: str | None = None


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction run."""

    evidence_file_id: str = ""
    document_id: str = ""
    extractors_used: list[str] = Field(default_factory=list)
    total_spans: int = 0
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    page_count: int = 0
    processing_time_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─────────────────────────────────────────────
# Top-Level Envelope
# ─────────────────────────────────────────────


class ExtractionEnvelope(BaseModel):
    """
    Top-level output of the OCR & NLP Extraction layer.

    Contains the assembled document text with full metadata hierarchy
    and all extracted spans with source provenance.
    """

    evidence_file_id: str = ""
    assembled_document: AssembledDocument = Field(
        default_factory=AssembledDocument
    )
    extracted_spans: list[ExtractedSpan] = Field(default_factory=list)
    metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)
    stage_reports: list[ExtractionStageReport] = Field(default_factory=list)
    schema_version: str = "1.0.0"
