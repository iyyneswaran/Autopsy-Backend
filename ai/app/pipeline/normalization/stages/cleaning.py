"""
Atopsy — Text Cleaning Stage.

Normalizes encoding, whitespace, Unicode, and special characters
for forensic text data.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def clean_text(text: str | None) -> str | None:
    """Apply full text normalization pipeline."""
    if not text or not isinstance(text, str):
        return text

    text = normalize_unicode(text)
    text = normalize_whitespace(text)
    text = remove_control_characters(text)
    text = normalize_line_endings(text)
    return text.strip()


def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFC form."""
    return unicodedata.normalize("NFC", text)


def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace into single spaces (preserving newlines)."""
    lines = text.split("\n")
    cleaned = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    return "\n".join(cleaned)


def remove_control_characters(text: str) -> str:
    """Remove non-printable control characters (keep newlines/tabs)."""
    return "".join(
        ch for ch in text
        if unicodedata.category(ch) != "Cc" or ch in ("\n", "\r", "\t")
    )


def normalize_line_endings(text: str) -> str:
    """Convert all line endings to Unix-style \\n."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_encoding(raw_bytes: bytes) -> dict[str, Any]:
    """Detect text encoding with confidence score."""
    try:
        import chardet
        result = chardet.detect(raw_bytes)
        return {
            "encoding": result.get("encoding", "utf-8"),
            "confidence": result.get("confidence", 0.0),
            "language": result.get("language"),
        }
    except ImportError:
        return {"encoding": "utf-8", "confidence": 0.5, "language": None}


def clean_dict_values(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively clean all string values in a dict."""
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned[key] = clean_text(value)
        elif isinstance(value, dict):
            cleaned[key] = clean_dict_values(value)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_dict_values(v) if isinstance(v, dict)
                else clean_text(v) if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            cleaned[key] = value
    return cleaned
