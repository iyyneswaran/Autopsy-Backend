"""
Atopsy — Confidence Calibration & Multi-Source Fusion.

Calibrates extraction confidence by combining OCR-level and NLP-level
scores. Handles multi-source fusion when both rule-based and model-assisted
extractors produce overlapping results, and flags low-confidence spans.
"""

from __future__ import annotations

from typing import Any

from app.core.logger import logger
from app.pipeline.extraction.schemas import ExtractedSpan


# ─────────────────────────────────────────────
# Confidence Calibration
# ─────────────────────────────────────────────


def calibrate_span_confidence(
    span: ExtractedSpan,
    ocr_confidence: float,
) -> float:
    """
    Calibrate a span's confidence using the underlying OCR confidence.

    Final confidence = extraction_confidence × ocr_confidence.
    Clamped to [0.0, 1.0].

    Args:
        span: The extracted span.
        ocr_confidence: OCR-level confidence for the source page/region.

    Returns:
        Calibrated confidence score.
    """
    calibrated = round(span.confidence * max(0.0, min(1.0, ocr_confidence)), 4)
    return max(0.0, min(1.0, calibrated))


def calibrate_all(
    spans: list[ExtractedSpan],
    page_confidences: dict[int, float],
) -> list[ExtractedSpan]:
    """
    Calibrate confidence for all spans using page-level OCR confidence.

    Args:
        spans: List of extracted spans.
        page_confidences: Mapping of page number → OCR confidence.

    Returns:
        Spans with calibrated confidence scores.
    """
    calibrated: list[ExtractedSpan] = []
    for span in spans:
        page = span.source_span.page
        ocr_conf = page_confidences.get(page, 1.0)
        new_conf = calibrate_span_confidence(span, ocr_conf)
        updated = span.model_copy(update={"confidence": new_conf})
        calibrated.append(updated)
    return calibrated


# ─────────────────────────────────────────────
# Multi-Source Fusion
# ─────────────────────────────────────────────


def fuse_multi_source(
    spans: list[ExtractedSpan],
    similarity_threshold: float = 0.8,
) -> list[ExtractedSpan]:
    """
    Fuse overlapping spans from multiple extractors.

    When regex and model-assisted extractors produce the same entity type
    with similar values, keep the highest-confidence version. Mark the
    chosen span's extraction_method as 'hybrid' if sources agree.

    Args:
        spans: All extracted spans (may contain duplicates).
        similarity_threshold: Value similarity threshold for merging.

    Returns:
        De-duplicated span list.
    """
    if not spans:
        return spans

    # Group by entity type
    groups: dict[str, list[ExtractedSpan]] = {}
    for span in spans:
        groups.setdefault(span.entity_type, []).append(span)

    fused: list[ExtractedSpan] = []

    for entity_type, group in groups.items():
        if len(group) <= 1:
            fused.extend(group)
            continue

        # Separate by extractor
        by_extractor: dict[str, list[ExtractedSpan]] = {}
        for s in group:
            by_extractor.setdefault(s.extractor_id, []).append(s)

        if len(by_extractor) <= 1:
            # All from same extractor — no fusion needed
            fused.extend(group)
            continue

        # Cross-extractor fusion
        used: set[int] = set()
        for i, span_a in enumerate(group):
            if i in used:
                continue
            best = span_a
            for j, span_b in enumerate(group):
                if j <= i or j in used:
                    continue
                if span_a.extractor_id == span_b.extractor_id:
                    continue
                if _values_similar(span_a.value, span_b.value, similarity_threshold):
                    used.add(j)
                    if span_b.confidence > best.confidence:
                        best = span_b
                    # Mark as hybrid fusion
                    best = best.model_copy(update={
                        "extraction_method": "hybrid",
                        "confidence": max(best.confidence, span_a.confidence),
                        "metadata": {
                            **best.metadata,
                            "fused_from": [span_a.extractor_id, span_b.extractor_id],
                        },
                    })
            fused.append(best)

    logger.debug(
        f"Confidence fusion: {len(spans)} spans → {len(fused)} after dedup"
    )
    return fused


# ─────────────────────────────────────────────
# Low-Confidence Flagging
# ─────────────────────────────────────────────


def flag_low_confidence(
    spans: list[ExtractedSpan],
    threshold: float = 0.3,
) -> list[ExtractedSpan]:
    """
    Mark spans below the confidence threshold as partial extractions.

    Args:
        spans: Extracted spans.
        threshold: Minimum confidence for a full extraction.

    Returns:
        Spans with is_partial set for low-confidence items.
    """
    flagged: list[ExtractedSpan] = []
    low_count = 0
    for span in spans:
        if span.confidence < threshold:
            span = span.model_copy(update={"is_partial": True})
            low_count += 1
        flagged.append(span)

    if low_count > 0:
        logger.info(
            f"Flagged {low_count}/{len(spans)} spans as low-confidence "
            f"(threshold={threshold})"
        )
    return flagged


# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────


def _values_similar(a: str, b: str, threshold: float) -> bool:
    """Check if two values are similar enough to consider duplicates."""
    if not a or not b:
        return False

    a_lower = a.strip().lower()
    b_lower = b.strip().lower()

    # Exact match
    if a_lower == b_lower:
        return True

    # Containment check
    if a_lower in b_lower or b_lower in a_lower:
        return True

    # Simple token overlap (Jaccard-like)
    tokens_a = set(a_lower.split())
    tokens_b = set(b_lower.split())
    if not tokens_a or not tokens_b:
        return False
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)
    return jaccard >= threshold
