"""
Atopsy — Language Detection for Forensic Documents.

Detects primary language and mixed-language content in forensic
text using Unicode range analysis and common word detection.
Supports English, Hindi (Devanagari), and mixed-language content
common in Indian medico-legal documents.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger


# Common Hindi words (transliterated) found in medico-legal docs
_HINDI_INDICATORS = {
    "naam", "umar", "ling", "pata", "mrityu", "karan",
    "postmortem", "shav", "pareeksha", "jaanch", "vishleshan",
    "thana", "mukhbir", "ghayal", "mrit", "sharir",
}

# Devanagari Unicode range
_DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")
_LATIN_PATTERN = re.compile(r"[a-zA-Z]")


def detect_language(text: str) -> dict[str, Any]:
    """
    Detect language(s) in forensic document text.

    Args:
        text: Document text to analyze.

    Returns:
        Dict with primary_language, languages list, confidence,
        and per-script character counts.
    """
    if not text or len(text.strip()) < 5:
        return {
            "primary_language": "unknown",
            "languages": [],
            "confidence": 0.0,
            "script_analysis": {},
        }

    devanagari_chars = len(_DEVANAGARI_PATTERN.findall(text))
    latin_chars = len(_LATIN_PATTERN.findall(text))
    total_alpha = devanagari_chars + latin_chars

    if total_alpha == 0:
        return {
            "primary_language": "unknown",
            "languages": [],
            "confidence": 0.0,
            "script_analysis": {
                "devanagari_chars": 0,
                "latin_chars": 0,
            },
        }

    devanagari_ratio = devanagari_chars / total_alpha
    latin_ratio = latin_chars / total_alpha

    # Check for Hindi indicators in transliterated text
    words_lower = set(text.lower().split())
    hindi_word_count = len(words_lower & _HINDI_INDICATORS)

    languages: list[str] = []
    primary = "english"
    confidence = 0.9

    if devanagari_ratio > 0.5:
        primary = "hindi"
        languages.append("hindi")
        if latin_ratio > 0.1:
            languages.append("english")
            primary = "hindi"
            confidence = 0.85
    elif devanagari_ratio > 0.1 or hindi_word_count > 2:
        primary = "mixed"
        languages = ["english", "hindi"]
        confidence = 0.75
    else:
        primary = "english"
        languages.append("english")
        if hindi_word_count > 0:
            languages.append("hindi")
            confidence = 0.80

    result = {
        "primary_language": primary,
        "languages": languages,
        "confidence": confidence,
        "script_analysis": {
            "devanagari_chars": devanagari_chars,
            "latin_chars": latin_chars,
            "devanagari_ratio": round(devanagari_ratio, 4),
            "latin_ratio": round(latin_ratio, 4),
            "hindi_word_indicators": hindi_word_count,
        },
    }

    logger.debug(
        f"Language detection: primary={primary}, "
        f"scripts=dev:{devanagari_chars}/lat:{latin_chars}"
    )
    return result


def detect_line_languages(text: str) -> list[dict[str, Any]]:
    """
    Detect language per line for mixed-language documents.

    Args:
        text: Document text.

    Returns:
        List of dicts with line_number, text, and detected language.
    """
    results: list[dict[str, Any]] = []
    for idx, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if not stripped:
            continue
        lang_info = detect_language(stripped)
        results.append({
            "line_number": idx,
            "text": stripped[:200],
            "language": lang_info["primary_language"],
            "confidence": lang_info["confidence"],
        })
    return results
