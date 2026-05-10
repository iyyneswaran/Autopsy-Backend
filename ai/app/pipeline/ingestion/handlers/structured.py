"""
Atopsy — Structured JSON Evidence Handler.

Handles: JSON evidence payloads ingested via API.
Validates schema, extracts structured metadata.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.logger import logger
from app.exceptions.pipeline import FileValidationError
from app.pipeline.ingestion.handlers.base import FileHandler


class StructuredHandler(FileHandler):

    @property
    def supported_mime_types(self) -> set[str]:
        return {"application/json"}

    def validate(self, file_path: str, mime_type: str) -> list[str]:
        warnings: list[str] = []
        if not os.path.exists(file_path):
            raise FileValidationError("JSON file does not exist", context={"file_path": file_path})
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, (dict, list)):
                warnings.append("JSON root is not an object or array")
        except json.JSONDecodeError as e:
            raise FileValidationError(
                f"Invalid JSON: {e}", context={"file_path": file_path}
            )
        return warnings

    def extract_metadata(self, file_path: str, mime_type: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {"meta_type": "structured"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                metadata["top_level_keys"] = list(data.keys())
                metadata["key_count"] = len(data)
            elif isinstance(data, list):
                metadata["record_count"] = len(data)
                if data and isinstance(data[0], dict):
                    metadata["sample_keys"] = list(data[0].keys())

            metadata["content_preview"] = json.dumps(data, default=str)[:2000]

        except Exception as e:
            metadata["error"] = str(e)
        return metadata
