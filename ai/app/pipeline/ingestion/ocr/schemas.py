"""
Atopsy — OCR Pipeline Schemas.

Pydantic models and dataclasses for the forensic OCR pipeline.
Covers preprocessing, quality assessment, layout analysis,
OCR engine output, field extraction, and pipeline results.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class RegionType(str, enum.Enum):
    """Classification of a document layout region."""
    HEADER = "HEADER"
    BODY_TEXT = "BODY_TEXT"
    TABLE = "TABLE"
    HANDWRITTEN = "HANDWRITTEN"
    SIGNATURE = "SIGNATURE"
    STAMP = "STAMP"
    MARGIN_NOTE = "MARGIN_NOTE"
    IMAGE = "IMAGE"
    UNKNOWN = "UNKNOWN"


class ContentType(str, enum.Enum):
    """Whether text in a region is printed or handwritten."""
    PRINTED = "PRINTED"
    HANDWRITTEN = "HANDWRITTEN"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class LegibilityGrade(str, enum.Enum):
    """Overall legibility of a document or region."""
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    ILLEGIBLE = "ILLEGIBLE"


class OCREngine(str, enum.Enum):
    """Which OCR engine produced a result."""
    TESSERACT = "TESSERACT"
    GEMINI = "GEMINI"
    MERGED = "MERGED"


class PipelineStage(str, enum.Enum):
    """Stages of the OCR pipeline."""
    LOADING = "LOADING"
    QUALITY_ASSESSMENT = "QUALITY_ASSESSMENT"
    PREPROCESSING = "PREPROCESSING"
    LAYOUT_ANALYSIS = "LAYOUT_ANALYSIS"
    OCR_EXECUTION = "OCR_EXECUTION"
    FIELD_EXTRACTION = "FIELD_EXTRACTION"
    RESULT_ASSEMBLY = "RESULT_ASSEMBLY"


# ─────────────────────────────────────────────
# Preprocessing Schemas
# ─────────────────────────────────────────────


class PreprocessConfig(BaseModel):
    """Configuration for image preprocessing."""
    enable_deskew: bool = True
    enable_denoise: bool = True
    enable_clahe: bool = True
    enable_threshold: bool = True
    enable_border_removal: bool = True
    enable_upscale: bool = True
    target_dpi: int = 300
    clahe_clip_limit: float = 2.0
    clahe_grid_size: int = 8
    denoise_strength: int = 10
    adaptive_threshold_block: int = 11
    adaptive_threshold_c: int = 2


class PreprocessResult(BaseModel):
    """Result of image preprocessing."""
    original_width: int = 0
    original_height: int = 0
    processed_width: int = 0
    processed_height: int = 0
    deskew_angle: float = 0.0
    estimated_dpi: int = 0
    operations_applied: list[str] = Field(default_factory=list)
    quality_before: float = 0.0
    quality_after: float = 0.0
    processing_time_ms: float = 0.0


# ─────────────────────────────────────────────
# Quality Assessment Schemas
# ─────────────────────────────────────────────


class QualityMetrics(BaseModel):
    """Individual quality metrics for a document image."""
    blur_score: float = Field(0.0, description="Laplacian variance; higher = sharper")
    noise_score: float = Field(0.0, description="0-1; lower = less noise")
    contrast_score: float = Field(0.0, description="0-1; higher = better contrast")
    resolution_score: float = Field(0.0, description="0-1; based on effective DPI")
    brightness_score: float = Field(0.0, description="0-1; 0.5 = ideal brightness")


class QualityAssessment(BaseModel):
    """Complete quality assessment for a document image."""
    overall_score: float = Field(0.0, ge=0.0, le=1.0)
    legibility: LegibilityGrade = LegibilityGrade.UNKNOWN
    metrics: QualityMetrics = Field(default_factory=QualityMetrics)
    estimated_dpi: int = 0
    width: int = 0
    height: int = 0
    warnings: list[str] = Field(default_factory=list)
    passes_gate: bool = True


# ─────────────────────────────────────────────
# Layout Analysis Schemas
# ─────────────────────────────────────────────


class BoundingBox(BaseModel):
    """Axis-aligned bounding box."""
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


class LayoutRegion(BaseModel):
    """A detected region within a document page."""
    region_type: RegionType = RegionType.UNKNOWN
    bbox: BoundingBox = Field(default_factory=BoundingBox)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    content_type: ContentType = ContentType.UNKNOWN
    reading_order: int = 0


class LayoutAnalysis(BaseModel):
    """Complete layout analysis for a page."""
    regions: list[LayoutRegion] = Field(default_factory=list)
    has_tables: bool = False
    has_handwriting: bool = False
    has_stamps: bool = False
    dominant_content_type: ContentType = ContentType.UNKNOWN
    page_orientation: str = "portrait"
    analysis_time_ms: float = 0.0


# ─────────────────────────────────────────────
# OCR Engine Schemas
# ─────────────────────────────────────────────


class TesseractConfig(BaseModel):
    """Tesseract engine configuration."""
    languages: str = "eng"
    psm: int = 3
    oem: int = 3
    whitelist: str = ""
    dpi: int = 300


class GeminiConfig(BaseModel):
    """Gemini Vision OCR configuration."""
    model_name: str = "gemini-2.0-flash"
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    temperature: float = 0.1
    structured_extraction: bool = True


class OCRWord(BaseModel):
    """A single recognized word with confidence and position."""
    text: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    bbox: BoundingBox = Field(default_factory=BoundingBox)


class OCRLine(BaseModel):
    """A line of recognized text (group of words)."""
    text: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    words: list[OCRWord] = Field(default_factory=list)
    bbox: BoundingBox = Field(default_factory=BoundingBox)


class OCRPageResult(BaseModel):
    """OCR result for a single page or region."""
    text: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    engine: OCREngine = OCREngine.TESSERACT
    words: list[OCRWord] = Field(default_factory=list)
    lines: list[OCRLine] = Field(default_factory=list)
    language_detected: str = ""
    processing_time_ms: float = 0.0


class OCRPipelineConfig(BaseModel):
    """Configuration for the full OCR pipeline."""
    preprocess: PreprocessConfig = Field(default_factory=PreprocessConfig)
    tesseract: TesseractConfig = Field(default_factory=TesseractConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    min_quality_score: float = 0.3
    use_gemini_for_handwriting: bool = True
    gemini_confidence_threshold: float = 0.7
    max_pages: int = 200


# ─────────────────────────────────────────────
# Forensic Field Extraction Schemas
# ─────────────────────────────────────────────


class ForensicField(BaseModel):
    """A single extracted forensic field."""
    field_name: str
    value: Any = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_text: str = ""
    validation_status: str = "unvalidated"
    validation_message: str = ""


class DeceasedInfo(BaseModel):
    """Extracted information about the deceased."""
    name: ForensicField | None = None
    age: ForensicField | None = None
    gender: ForensicField | None = None
    identification_marks: list[ForensicField] = Field(default_factory=list)


class InjuryField(BaseModel):
    """A single extracted injury finding."""
    injury_type: str = ""
    body_region: str = ""
    description: str = ""
    dimensions: str = ""
    severity: str = ""
    confidence: float = 0.0


class ToxicologyField(BaseModel):
    """A single extracted toxicology finding."""
    substance: str = ""
    result: str = ""
    concentration: str = ""
    unit: str = ""
    confidence: float = 0.0


class ForensicFieldExtraction(BaseModel):
    """Complete structured field extraction from an autopsy report."""
    case_number: ForensicField | None = None
    deceased: DeceasedInfo = Field(default_factory=DeceasedInfo)
    cause_of_death: ForensicField | None = None
    manner_of_death: ForensicField | None = None
    time_of_death: ForensicField | None = None
    date_of_examination: ForensicField | None = None
    examining_doctor: ForensicField | None = None
    injuries: list[InjuryField] = Field(default_factory=list)
    toxicology: list[ToxicologyField] = Field(default_factory=list)
    external_examination: ForensicField | None = None
    internal_examination: ForensicField | None = None
    opinion: ForensicField | None = None
    extraction_confidence: float = 0.0
    extraction_engine: str = "gemini"


# ─────────────────────────────────────────────
# Pipeline Result Schemas
# ─────────────────────────────────────────────


class ProcessingStageReport(BaseModel):
    """Report for a single pipeline stage execution."""
    stage: PipelineStage
    status: str = "completed"
    duration_ms: float = 0.0
    detail: str = ""
    error: str | None = None


class PageOCRResult(BaseModel):
    """OCR result for a single page including all metadata."""
    page_number: int = 0
    text: str = ""
    confidence: float = 0.0
    engine: OCREngine = OCREngine.TESSERACT
    quality: QualityAssessment = Field(default_factory=QualityAssessment)
    preprocess: PreprocessResult = Field(default_factory=PreprocessResult)
    layout: LayoutAnalysis = Field(default_factory=LayoutAnalysis)
    words: list[OCRWord] = Field(default_factory=list)


class DocumentOCRResult(BaseModel):
    """Complete OCR pipeline result for a document."""
    document_id: str = ""
    full_text: str = ""
    overall_confidence: float = 0.0
    page_count: int = 0
    pages: list[PageOCRResult] = Field(default_factory=list)
    structured_fields: ForensicFieldExtraction | None = None
    quality_summary: QualityAssessment = Field(default_factory=QualityAssessment)
    pipeline_stages: list[ProcessingStageReport] = Field(default_factory=list)
    total_processing_time_ms: float = 0.0
    engines_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
