"""
Atopsy — Forensic Document Section Detector.

Detects structural sections in Indian medico-legal documents
such as autopsy reports, FIRs, and toxicology reports. Returns
section boundaries with confidence scores for downstream
section-aware extraction.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger


# Section heading patterns for Indian medico-legal documents
_SECTION_PATTERNS: list[tuple[str, str, float]] = [
    # (regex_pattern, section_name, confidence)
    (r"(?:^|\n)\s*(?:EXTERNAL\s*EXAMINATION|External\s*Examination)\s*[:\-]?",
     "EXTERNAL_EXAMINATION", 0.90),
    (r"(?:^|\n)\s*(?:INTERNAL\s*EXAMINATION|Internal\s*Examination)\s*[:\-]?",
     "INTERNAL_EXAMINATION", 0.90),
    (r"(?:^|\n)\s*(?:OPINION|Opinion)\s*[:\-]?",
     "OPINION", 0.90),
    (r"(?:^|\n)\s*(?:TOXICOLOGY|Toxicology|CHEMICAL\s*ANALYSIS)\s*[:\-]?",
     "TOXICOLOGY", 0.85),
    (r"(?:^|\n)\s*(?:HISTOPATHOLOGY|Histopathology|MICROSCOPIC\s*EXAMINATION)\s*[:\-]?",
     "HISTOPATHOLOGY", 0.85),
    (r"(?:^|\n)\s*(?:INJURIES|List\s*of\s*Injuries|INJURY\s*FINDINGS)\s*[:\-]?",
     "INJURIES", 0.85),
    (r"(?:^|\n)\s*(?:SCENE\s*(?:OF\s*CRIME|DESCRIPTION)|Scene\s*(?:of\s*Crime|Description))\s*[:\-]?",
     "SCENE_DESCRIPTION", 0.80),
    (r"(?:^|\n)\s*(?:VISCERA\s*PRESERVATION|Viscera)\s*[:\-]?",
     "VISCERA", 0.80),
    (r"(?:^|\n)\s*(?:IDENTIFICATION\s*MARKS?|Identification\s*Marks?)\s*[:\-]?",
     "IDENTIFICATION", 0.80),
]


def detect_sections(text: str) -> list[dict[str, Any]]:
    """
    Detect document sections in Indian medico-legal text.

    Args:
        text: Full document text.

    Returns:
        List of sections with name, start/end char positions, and confidence.
        Sorted by start_char position.
    """
    if not text:
        return []

    matches: list[dict[str, Any]] = []

    for pattern, section_name, confidence in _SECTION_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            matches.append({
                "section_name": section_name,
                "start_char": m.start(),
                "end_char": m.end(),
                "heading_text": m.group(0).strip(),
                "confidence": confidence,
            })

    # Sort by position
    matches.sort(key=lambda x: x["start_char"])

    # Compute section content boundaries
    sections: list[dict[str, Any]] = []
    for i, match in enumerate(matches):
        content_start = match["end_char"]
        content_end = (
            matches[i + 1]["start_char"] if i + 1 < len(matches) else len(text)
        )
        sections.append({
            "section_name": match["section_name"],
            "start_char": match["start_char"],
            "end_char": content_end,
            "content_start": content_start,
            "content_end": content_end,
            "heading_text": match["heading_text"],
            "confidence": match["confidence"],
            "content_length": content_end - content_start,
        })

    # Add preamble if the first section doesn't start at the beginning
    if sections and sections[0]["start_char"] > 50:
        sections.insert(0, {
            "section_name": "PREAMBLE",
            "start_char": 0,
            "end_char": sections[0]["start_char"],
            "content_start": 0,
            "content_end": sections[0]["start_char"],
            "heading_text": "",
            "confidence": 0.70,
            "content_length": sections[0]["start_char"],
        })
    elif not sections and len(text) > 50:
        sections.append({
            "section_name": "PREAMBLE",
            "start_char": 0,
            "end_char": len(text),
            "content_start": 0,
            "content_end": len(text),
            "heading_text": "",
            "confidence": 0.50,
            "content_length": len(text),
        })

    logger.debug(
        f"Detected {len(sections)} sections: "
        f"{[s['section_name'] for s in sections]}"
    )
    return sections
