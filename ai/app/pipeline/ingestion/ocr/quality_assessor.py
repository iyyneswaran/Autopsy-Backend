"""
Atopsy — Document Quality Assessment Engine.

Evaluates document image quality for OCR readiness.
Computes blur, noise, contrast, and resolution metrics
to determine if a document is suitable for text extraction.
"""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    LegibilityGrade,
    QualityAssessment,
    QualityMetrics,
)


def assess_quality(image: np.ndarray) -> QualityAssessment:
    """
    Assess the quality of a document image for OCR processing.

    Args:
        image: Input image as numpy array (BGR or grayscale).

    Returns:
        QualityAssessment with overall score, metrics, and legibility grade.
    """
    start = time.monotonic()

    # Convert to grayscale if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    h, w = gray.shape[:2]

    blur = _compute_blur_score(gray)
    noise = _compute_noise_score(gray)
    contrast = _compute_contrast_score(gray)
    resolution = _compute_resolution_score(w, h)
    brightness = _compute_brightness_score(gray)

    # Weighted overall score
    overall = (
        blur * 0.30
        + (1.0 - noise) * 0.20
        + contrast * 0.25
        + resolution * 0.15
        + brightness * 0.10
    )
    overall = round(max(0.0, min(1.0, overall)), 4)

    legibility = _score_to_legibility(overall)
    estimated_dpi = _estimate_dpi(w, h)

    warnings: list[str] = []
    if blur < 0.2:
        warnings.append("Image is significantly blurred")
    if noise > 0.7:
        warnings.append("High noise level detected")
    if contrast < 0.2:
        warnings.append("Very low contrast — text may be unreadable")
    if estimated_dpi < 150:
        warnings.append(f"Low effective resolution (~{estimated_dpi} DPI)")
    if brightness < 0.15 or brightness > 0.85:
        warnings.append("Brightness is outside ideal range")

    elapsed = round((time.monotonic() - start) * 1000, 2)

    return QualityAssessment(
        overall_score=overall,
        legibility=legibility,
        metrics=QualityMetrics(
            blur_score=round(blur, 4),
            noise_score=round(noise, 4),
            contrast_score=round(contrast, 4),
            resolution_score=round(resolution, 4),
            brightness_score=round(brightness, 4),
        ),
        estimated_dpi=estimated_dpi,
        width=w,
        height=h,
        warnings=warnings,
        passes_gate=overall >= 0.3,
    )


def passes_quality_gate(
    assessment: QualityAssessment,
    min_score: float = 0.3,
) -> bool:
    """Check if a document passes the minimum quality threshold."""
    return assessment.overall_score >= min_score


# ─────────────────────────────────────────────
# Individual Metric Computations
# ─────────────────────────────────────────────


def _compute_blur_score(gray: np.ndarray) -> float:
    """
    Compute sharpness score using Laplacian variance.
    Higher variance = sharper image = better for OCR.
    Normalized to 0-1 range.
    """
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Typical range: 0-5000+. Normalize with sigmoid-like mapping.
    # Documents with var > 500 are generally sharp enough.
    score = min(1.0, laplacian_var / 1000.0)
    return score


def _compute_noise_score(gray: np.ndarray) -> float:
    """
    Estimate noise level using high-frequency component analysis.
    Returns 0-1 where 0 = no noise, 1 = very noisy.
    """
    # Apply median blur and compare with original
    blurred = cv2.medianBlur(gray, 3)
    diff = cv2.absdiff(gray, blurred)
    noise_level = float(np.mean(diff)) / 255.0

    # Scale: typical document noise is 0.01-0.05
    score = min(1.0, noise_level * 10.0)
    return score


def _compute_contrast_score(gray: np.ndarray) -> float:
    """
    Compute contrast ratio from histogram analysis.
    Good documents have bimodal histograms (text vs background).
    """
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.flatten() / hist.sum()

    # Standard deviation of intensity distribution
    intensities = np.arange(256, dtype=np.float64)
    mean_val = np.sum(intensities * hist)
    std_val = np.sqrt(np.sum(((intensities - mean_val) ** 2) * hist))

    # Normalize: std of 60-80 is ideal for documents
    score = min(1.0, std_val / 80.0)
    return score


def _compute_resolution_score(w: int, h: int) -> float:
    """
    Score based on image resolution.
    A4 at 300 DPI ≈ 2480 x 3508.
    """
    total_pixels = w * h
    # Minimum useful: ~1M pixels (~150 DPI for A4)
    # Good: ~4M pixels (~300 DPI for A4)
    # Excellent: ~8M+ pixels
    if total_pixels >= 8_000_000:
        return 1.0
    elif total_pixels >= 4_000_000:
        return 0.85
    elif total_pixels >= 2_000_000:
        return 0.65
    elif total_pixels >= 1_000_000:
        return 0.45
    elif total_pixels >= 500_000:
        return 0.25
    else:
        return 0.1


def _compute_brightness_score(gray: np.ndarray) -> float:
    """
    Score based on average brightness.
    Ideal brightness for documents is 0.5-0.7 (white paper with dark text).
    Returns 0-1 where 0.5 is ideal.
    """
    mean_brightness = float(np.mean(gray)) / 255.0
    # Penalize very dark (<0.2) or very bright (>0.9) images
    if 0.4 <= mean_brightness <= 0.8:
        return 1.0 - abs(mean_brightness - 0.6)
    elif mean_brightness < 0.4:
        return max(0.0, mean_brightness / 0.4 * 0.5)
    else:
        return max(0.0, (1.0 - mean_brightness) / 0.2 * 0.5)


def _estimate_dpi(w: int, h: int) -> int:
    """
    Estimate effective DPI assuming A4 paper (8.27 x 11.69 inches).
    Uses the longer dimension as reference.
    """
    longer = max(w, h)
    # A4 longer side = 11.69 inches
    estimated = int(longer / 11.69)
    return max(72, min(1200, estimated))


def _score_to_legibility(score: float) -> LegibilityGrade:
    """Convert overall quality score to legibility grade."""
    if score >= 0.8:
        return LegibilityGrade.EXCELLENT
    elif score >= 0.6:
        return LegibilityGrade.GOOD
    elif score >= 0.4:
        return LegibilityGrade.FAIR
    elif score >= 0.2:
        return LegibilityGrade.POOR
    else:
        return LegibilityGrade.ILLEGIBLE
