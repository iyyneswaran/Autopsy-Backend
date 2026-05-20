"""
Atopsy — Document Layout Analysis Engine.

Detects and classifies regions within document images:
headers, body text, tables, handwritten areas, signatures, stamps.
Uses contour analysis and edge density heuristics.
"""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    BoundingBox,
    ContentType,
    LayoutAnalysis,
    LayoutRegion,
    RegionType,
)


def analyze_layout(image: np.ndarray) -> LayoutAnalysis:
    """
    Analyze document layout to identify text regions and their types.

    Args:
        image: Grayscale or BGR document image.

    Returns:
        LayoutAnalysis with classified regions and reading order.
    """
    start = time.monotonic()

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    h, w = gray.shape[:2]

    # Detect text blocks using morphological operations
    regions = _detect_text_blocks(gray)

    # Classify each region
    classified: list[LayoutRegion] = []
    for i, (x, y, rw, rh) in enumerate(regions):
        roi = gray[y:y + rh, x:x + rw]
        if roi.size == 0:
            continue

        region_type = _classify_region(roi, x, y, rw, rh, w, h)
        content_type = _detect_content_type(roi)

        classified.append(LayoutRegion(
            region_type=region_type,
            bbox=BoundingBox(x=x, y=y, w=rw, h=rh),
            confidence=_compute_region_confidence(roi, region_type),
            content_type=content_type,
            reading_order=i,
        ))

    # Sort by reading order (top-to-bottom, left-to-right)
    classified = _assign_reading_order(classified)

    # Detect structural elements
    has_tables = _detect_tables(gray)
    has_handwriting = any(
        r.content_type == ContentType.HANDWRITTEN for r in classified
    )
    has_stamps = any(
        r.region_type == RegionType.STAMP for r in classified
    )

    dominant = _determine_dominant_content(classified)
    orientation = "landscape" if w > h * 1.2 else "portrait"

    elapsed = round((time.monotonic() - start) * 1000, 2)

    return LayoutAnalysis(
        regions=classified,
        has_tables=has_tables,
        has_handwriting=has_handwriting,
        has_stamps=has_stamps,
        dominant_content_type=dominant,
        page_orientation=orientation,
        analysis_time_ms=elapsed,
    )


# ─────────────────────────────────────────────
# Text Block Detection
# ─────────────────────────────────────────────


def _detect_text_blocks(
    gray: np.ndarray,
) -> list[tuple[int, int, int, int]]:
    """
    Detect text block regions using morphological closing.
    Returns list of (x, y, w, h) bounding rectangles.
    """
    h, w = gray.shape[:2]

    # Invert and threshold
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # Horizontal kernel to connect text within lines
    h_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(w // 30, 15), 1)
    )
    h_dilated = cv2.dilate(binary, h_kernel, iterations=1)

    # Vertical kernel to connect lines into blocks
    v_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(h // 60, 5))
    )
    dilated = cv2.dilate(h_dilated, v_kernel, iterations=2)

    # Close gaps
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (15, 15)
    )
    closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, close_kernel)

    # Find contours
    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    min_area = (w * h) * 0.001  # Minimum 0.1% of page area
    regions: list[tuple[int, int, int, int]] = []

    for cnt in contours:
        x, y, rw, rh = cv2.boundingRect(cnt)
        area = rw * rh
        if area >= min_area and rw > 20 and rh > 10:
            regions.append((x, y, rw, rh))

    return regions


# ─────────────────────────────────────────────
# Region Classification
# ─────────────────────────────────────────────


def _classify_region(
    roi: np.ndarray,
    x: int, y: int, rw: int, rh: int,
    page_w: int, page_h: int,
) -> RegionType:
    """Classify a region based on position, shape, and content."""
    # Position-based heuristics
    relative_y = y / page_h
    relative_x = x / page_w
    aspect = rw / max(rh, 1)

    # Header: top 15% of page, wide
    if relative_y < 0.15 and rw > page_w * 0.4:
        return RegionType.HEADER

    # Margin note: narrow, on left/right edge
    if rw < page_w * 0.2 and (relative_x < 0.1 or relative_x > 0.8):
        return RegionType.MARGIN_NOTE

    # Signature: bottom 20%, small area
    if relative_y > 0.8 and rw < page_w * 0.4 and rh < page_h * 0.1:
        return RegionType.SIGNATURE

    # Stamp: roughly square, small-medium
    area_ratio = (rw * rh) / (page_w * page_h)
    if 0.7 < aspect < 1.4 and 0.005 < area_ratio < 0.05:
        edge_density = _compute_edge_density(roi)
        if edge_density > 0.15:
            return RegionType.STAMP

    # Table: check for grid-like structure
    if _has_grid_structure(roi):
        return RegionType.TABLE

    return RegionType.BODY_TEXT


def _detect_content_type(roi: np.ndarray) -> ContentType:
    """
    Determine if a region contains printed or handwritten text
    using edge density and stroke width analysis.
    """
    if roi.size == 0:
        return ContentType.UNKNOWN

    edge_density = _compute_edge_density(roi)
    stroke_var = _compute_stroke_variance(roi)

    # Handwriting: higher edge density variation, irregular strokes
    # Printed text: uniform edge density, consistent strokes
    if stroke_var > 0.4 and edge_density > 0.08:
        return ContentType.HANDWRITTEN
    elif stroke_var < 0.2:
        return ContentType.PRINTED
    else:
        return ContentType.MIXED


# ─────────────────────────────────────────────
# Feature Computation
# ─────────────────────────────────────────────


def _compute_edge_density(roi: np.ndarray) -> float:
    """Compute the ratio of edge pixels to total pixels."""
    if roi.size == 0:
        return 0.0
    edges = cv2.Canny(roi, 50, 150)
    return float(np.count_nonzero(edges)) / edges.size


def _compute_stroke_variance(roi: np.ndarray) -> float:
    """
    Estimate stroke width variance using distance transform.
    Handwriting has higher variance than printed text.
    """
    if roi.size == 0:
        return 0.0

    try:
        _, binary = cv2.threshold(
            roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
        nonzero = dist[dist > 0]
        if len(nonzero) < 10:
            return 0.0
        return min(1.0, float(np.std(nonzero)) / max(float(np.mean(nonzero)), 0.1))
    except Exception:
        return 0.0


def _compute_region_confidence(
    roi: np.ndarray,
    region_type: RegionType,
) -> float:
    """Compute confidence in the region classification."""
    # Base confidence from content density
    if roi.size == 0:
        return 0.0

    _, binary = cv2.threshold(
        roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    density = float(np.count_nonzero(binary)) / binary.size

    # Reasonable text density is 0.1-0.5
    if 0.05 < density < 0.6:
        return min(0.95, 0.5 + density)
    return max(0.3, 0.5 - abs(density - 0.3))


def _has_grid_structure(roi: np.ndarray) -> bool:
    """Check if a region has table-like grid structure."""
    if roi.size == 0:
        return False

    h, w = roi.shape[:2]
    if h < 40 or w < 40:
        return False

    try:
        edges = cv2.Canny(roi, 50, 150)

        # Detect horizontal lines
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 4, 1))
        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        h_count = len(cv2.findContours(
            h_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )[0])

        # Detect vertical lines
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 4))
        v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)
        v_count = len(cv2.findContours(
            v_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )[0])

        # Table needs at least 2 horizontal and 2 vertical lines
        return h_count >= 2 and v_count >= 2

    except Exception:
        return False


def _detect_tables(gray: np.ndarray) -> bool:
    """Quick check if the page contains any table structures."""
    return _has_grid_structure(gray)


# ─────────────────────────────────────────────
# Reading Order & Helpers
# ─────────────────────────────────────────────


def _assign_reading_order(
    regions: list[LayoutRegion],
) -> list[LayoutRegion]:
    """
    Sort regions in reading order: top-to-bottom, left-to-right.
    Groups regions into horizontal bands, then sorts within each band.
    """
    if not regions:
        return regions

    # Sort by y-coordinate first
    sorted_regions = sorted(regions, key=lambda r: (r.bbox.y, r.bbox.x))

    # Group into bands (regions within 5% vertical overlap)
    bands: list[list[LayoutRegion]] = []
    current_band: list[LayoutRegion] = [sorted_regions[0]]
    band_y = sorted_regions[0].bbox.y

    for region in sorted_regions[1:]:
        if abs(region.bbox.y - band_y) < region.bbox.h * 0.5:
            current_band.append(region)
        else:
            bands.append(current_band)
            current_band = [region]
            band_y = region.bbox.y
    bands.append(current_band)

    # Sort within each band by x-coordinate
    ordered: list[LayoutRegion] = []
    for band in bands:
        band.sort(key=lambda r: r.bbox.x)
        ordered.extend(band)

    # Assign reading order
    for i, region in enumerate(ordered):
        region.reading_order = i

    return ordered


def _determine_dominant_content(
    regions: list[LayoutRegion],
) -> ContentType:
    """Determine the dominant content type across all regions."""
    if not regions:
        return ContentType.UNKNOWN

    counts: dict[ContentType, int] = {}
    for r in regions:
        area = r.bbox.w * r.bbox.h
        counts[r.content_type] = counts.get(r.content_type, 0) + area

    if not counts:
        return ContentType.UNKNOWN

    return max(counts, key=counts.get)  # type: ignore[arg-type]
