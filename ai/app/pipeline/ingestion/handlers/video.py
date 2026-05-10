"""
Atopsy — Video Metadata Handler.

Handles: MP4, AVI, MOV
Extracts: codec, duration, resolution, frame rate, timestamps via ffprobe.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from app.core.logger import logger
from app.exceptions.pipeline import FileValidationError
from app.pipeline.ingestion.handlers.base import FileHandler


class VideoHandler(FileHandler):

    @property
    def supported_mime_types(self) -> set[str]:
        return {"video/mp4", "video/x-msvideo", "video/quicktime"}

    def validate(self, file_path: str, mime_type: str) -> list[str]:
        warnings: list[str] = []
        if not os.path.exists(file_path):
            raise FileValidationError("Video file does not exist", context={"file_path": file_path})
        if os.path.getsize(file_path) == 0:
            raise FileValidationError("Video file is empty", context={"file_path": file_path})
        try:
            with open(file_path, "rb") as f:
                header = f.read(12)
            if mime_type == "video/mp4" and b"ftyp" not in header:
                warnings.append("MP4 may be malformed — missing ftyp box")
            if mime_type == "video/x-msvideo" and not header.startswith(b"RIFF"):
                warnings.append("AVI may be malformed — missing RIFF header")
        except Exception as e:
            warnings.append(f"Header check failed: {e}")
        return warnings

    def extract_metadata(self, file_path: str, mime_type: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {"meta_type": "video"}
        ffprobe_data = self._extract_with_ffprobe(file_path)
        if ffprobe_data:
            metadata.update(ffprobe_data)
            return metadata
        opencv_data = self._extract_with_opencv(file_path)
        if opencv_data:
            metadata.update(opencv_data)
            return metadata
        metadata["warning"] = "No video metadata extractor available"
        return metadata

    def _extract_with_ffprobe(self, file_path: str) -> dict[str, Any] | None:
        try:
            cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
                   "-show_format", "-show_streams", file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            probe = json.loads(result.stdout)
            md: dict[str, Any] = {}
            fmt = probe.get("format", {})
            md["container_format"] = fmt.get("format_long_name")
            md["duration_seconds"] = float(fmt.get("duration", 0))
            md["bit_rate"] = int(fmt.get("bit_rate", 0))
            tags = fmt.get("tags", {})
            md["creation_time"] = tags.get("creation_time")
            for stream in probe.get("streams", []):
                if stream.get("codec_type") == "video":
                    md["video_codec"] = stream.get("codec_long_name")
                    md["width"] = stream.get("width")
                    md["height"] = stream.get("height")
                    r = stream.get("r_frame_rate", "0/1")
                    try:
                        n, d = r.split("/")
                        md["frame_rate"] = round(float(n) / float(d), 2) if float(d) else 0
                    except (ValueError, ZeroDivisionError):
                        md["frame_rate"] = None
                elif stream.get("codec_type") == "audio":
                    md["audio_codec"] = stream.get("codec_long_name")
                    md["sample_rate"] = stream.get("sample_rate")
            return md
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        except Exception:
            return None

    def _extract_with_opencv(self, file_path: str) -> dict[str, Any] | None:
        try:
            import cv2
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return None
            md: dict[str, Any] = {}
            md["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            md["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            md["frame_rate"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps and fps > 0:
                md["duration_seconds"] = round(frames / fps, 2)
            cap.release()
            return md
        except ImportError:
            return None
        except Exception:
            return None
