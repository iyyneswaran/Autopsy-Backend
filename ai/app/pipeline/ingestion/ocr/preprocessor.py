"""
Atopsy — Production-Grade Image Preprocessor.

Prepares document images for OCR through a configurable pipeline:
  Grayscale → Deskew → Denoise → CLAHE → Threshold → Border Removal → Upscale

Optimized for scanned Indian autopsy reports and low-quality documents.
"""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    PreprocessConfig,
    PreprocessResult,
)


def preprocess_image(
    image: np.ndarray,
    config: PreprocessConfig | None = None,
) -> tuple[np.ndarray, PreprocessResult]:
    """
    Apply full preprocessing pipeline to a document image.

    Args:
        image: Input BGR or grayscale image.
        config: Optional preprocessing configuration.

    Returns:
        Tuple of (processed_image, PreprocessResult metadata).
    """
    cfg = config or PreprocessConfig()
    start = time.monotonic()
    operations: list[str] = []

    h_orig, w_orig = image.shape[:2]

    # ── Step 1: Grayscale ────────────────────
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        operations.append("grayscale_conversion")
    else:
        gray = image.copy()

    quality_before = _quick_quality(gray)

    # ── Step 2: Deskew ───────────────────────
    deskew_angle = 0.0
    if cfg.enable_deskew:
        gray, deskew_angle = _deskew(gray)
        if abs(deskew_angle) > 0.1:
            operations.append(f"deskew({deskew_angle:.2f}°)")

    # ── Step 3: Denoise ──────────────────────
    if cfg.enable_denoise:
        gray = _denoise(gray, cfg.denoise_strength)
        operations.append("denoise")

    # ── Step 4: CLAHE Contrast Enhancement ───
    if cfg.enable_clahe:
        gray = _apply_clahe(
            gray,
            clip_limit=cfg.clahe_clip_limit,
            grid_size=cfg.clahe_grid_size,
        )
        operations.append("clahe_enhancement")

    # ── Step 5: Border Removal ───────────────
    if cfg.enable_border_removal:
        gray = _remove_borders(gray)
        operations.append("border_removal")

    # ── Step 6: Adaptive Thresholding ────────
    if cfg.enable_threshold:
        gray = _adaptive_threshold(
            gray,
            block_size=cfg.adaptive_threshold_block,
            c_val=cfg.adaptive_threshold_c,
        )
        operations.append("adaptive_threshold")

    # ── Step 7: Resolution Upscale ───────────
    if cfg.enable_upscale:
        gray, did_upscale = _upscale_if_needed(gray, cfg.target_dpi)
        if did_upscale:
            operations.append(f"upscale_to_{cfg.target_dpi}dpi")

    h_proc, w_proc = gray.shape[:2]
    quality_after = _quick_quality(gray)
    estimated_dpi = _estimate_dpi(w_proc, h_proc)
    elapsed = round((time.monotonic() - start) * 1000, 2)

    result = PreprocessResult(
        original_width=w_orig,
        original_height=h_orig,
        processed_width=w_proc,
        processed_height=h_proc,
        deskew_angle=round(deskew_angle, 4),
        estimated_dpi=estimated_dpi,
        operations_applied=operations,
        quality_before=round(quality_before, 4),
        quality_after=round(quality_after, 4),
        processing_time_ms=elapsed,
    )

    logger.debug(
        f"Preprocessing: {len(operations)} ops, "
        f"{w_orig}x{h_orig} → {w_proc}x{h_proc}, "
        f"quality {quality_before:.2f} → {quality_after:.2f}, "
        f"{elapsed:.1f}ms"
    )

    return gray, result


# ─────────────────────────────────────────────
# Internal Processing Functions
# ─────────────────────────────────────────────


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Correct document skew using Hough line detection.
    Returns (corrected_image, angle_corrected).
    """
    try:
        # Edge detection for line finding
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Detect lines via probabilistic Hough transform
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180,
            threshold=100,
            minLineLength=gray.shape[1] // 4,
            maxLineGap=20,
        )

        if lines is None or len(lines) == 0:
            return gray, 0.0

        # Compute median angle of detected lines
        angles: list[float] = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 - x1 == 0:
                continue
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Only consider near-horizontal lines (±30°)
            if abs(angle) < 30:
                angles.append(angle)

        if not angles:
            return gray, 0.0

        median_angle = float(np.median(angles))

        # Skip tiny corrections
        if abs(median_angle) < 0.3:
            return gray, 0.0

        # Limit correction to ±15°
        correction = max(-15.0, min(15.0, -median_angle))

        h, w = gray.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, correction, 1.0)
        corrected = cv2.warpAffine(
            gray, matrix, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        return corrected, correction

    except Exception as e:
        logger.warning(f"Deskew failed: {e}")
        return gray, 0.0


def _denoise(
    gray: np.ndarray,
    strength: int = 10,
) -> np.ndarray:
    """Apply non-local means denoising followed by bilateral filtering."""
    try:
        # Non-local means denoising (good for Gaussian noise)
        denoised = cv2.fastNlMeansDenoising(
            gray,
            h=strength,
            templateWindowSize=7,
            searchWindowSize=21,
        )
        # Light bilateral filter to preserve edges
        denoised = cv2.bilateralFilter(denoised, 5, 50, 50)
        return denoised
    except Exception as e:
        logger.warning(f"Denoising failed: {e}")
        return gray


def _apply_clahe(
    gray: np.ndarray,
    clip_limit: float = 2.0,
    grid_size: int = 8,
) -> np.ndarray:
    """
    Apply Contrast Limited Adaptive Histogram Equalization.
    Enhances local contrast without amplifying noise.
    """
    try:
        clahe = cv2.createCLAHE(
            clipLimit=clip_limit,
            tileGridSize=(grid_size, grid_size),
        )
        return clahe.apply(gray)
    except Exception as e:
        logger.warning(f"CLAHE failed: {e}")
        return gray


def _remove_borders(gray: np.ndarray) -> np.ndarray:
    """
    Remove dark borders and scanning artifacts using
    morphological operations and contour detection.
    """
    try:
        # Threshold to find content region
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return gray

        # Find largest contour (should be the document)
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)

        # Only crop if the content region is significantly smaller
        total_area = gray.shape[0] * gray.shape[1]
        content_area = w * h

        if content_area < total_area * 0.95 and content_area > total_area * 0.3:
            # Add small margin
            margin = 5
            x = max(0, x - margin)
            y = max(0, y - margin)
            w = min(gray.shape[1] - x, w + 2 * margin)
            h = min(gray.shape[0] - y, h + 2 * margin)
            return gray[y:y + h, x:x + w]

        return gray

    except Exception as e:
        logger.warning(f"Border removal failed: {e}")
        return gray


def _adaptive_threshold(
    gray: np.ndarray,
    block_size: int = 11,
    c_val: int = 2,
) -> np.ndarray:
    """
    Apply adaptive thresholding with automatic method selection.
    Uses Otsu for uniform backgrounds, adaptive Gaussian for complex ones.
    """
    try:
        # Check if image has uniform background (bimodal histogram)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        peaks = _count_histogram_peaks(hist)

        if peaks <= 2:
            # Bimodal → Otsu works well
            _, binary = cv2.threshold(
                gray, 0, 255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
        else:
            # Complex background → adaptive Gaussian
            # Ensure block_size is odd
            if block_size % 2 == 0:
                block_size += 1
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                block_size, c_val,
            )

        return binary

    except Exception as e:
        logger.warning(f"Thresholding failed: {e}")
        return gray


def _upscale_if_needed(
    gray: np.ndarray,
    target_dpi: int = 300,
) -> tuple[np.ndarray, bool]:
    """
    Upscale image if resolution is too low for OCR.
    Target: effective DPI >= target_dpi (assuming A4 page).
    """
    h, w = gray.shape[:2]
    current_dpi = _estimate_dpi(w, h)

    if current_dpi >= target_dpi * 0.8:
        return gray, False

    scale = target_dpi / max(current_dpi, 72)
    scale = min(scale, 4.0)  # Cap at 4x upscale

    if scale <= 1.1:
        return gray, False

    try:
        new_w = int(w * scale)
        new_h = int(h * scale)
        upscaled = cv2.resize(
            gray, (new_w, new_h),
            interpolation=cv2.INTER_CUBIC,
        )
        return upscaled, True
    except Exception as e:
        logger.warning(f"Upscale failed: {e}")
        return gray, False


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _quick_quality(gray: np.ndarray) -> float:
    """Fast quality estimate using Laplacian variance."""
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return min(1.0, lap_var / 1000.0)


def _estimate_dpi(w: int, h: int) -> int:
    """Estimate DPI assuming A4 paper (longer side = 11.69 in)."""
    longer = max(w, h)
    return max(72, min(1200, int(longer / 11.69)))


def _count_histogram_peaks(
    hist: np.ndarray,
    min_distance: int = 30,
) -> int:
    """Count significant peaks in a histogram."""
    smoothed = cv2.GaussianBlur(
        hist.reshape(-1, 1), (1, 15), 0
    ).flatten()
    threshold = smoothed.max() * 0.1

    peaks = 0
    in_peak = False
    for i in range(1, len(smoothed) - 1):
        if (
            smoothed[i] > threshold
            and smoothed[i] > smoothed[i - 1]
            and smoothed[i] > smoothed[i + 1]
        ):
            if not in_peak:
                peaks += 1
                in_peak = True
        elif smoothed[i] < threshold * 0.5:
            in_peak = False

    return peaks
