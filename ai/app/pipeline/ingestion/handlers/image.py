"""
Atopsy — Image File Handler.

Handles: JPG, PNG, TIFF, BMP
Extracts: EXIF metadata, GPS coordinates, timestamps, device info.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.logger import logger
from app.exceptions.pipeline import (
    FileValidationError,
    MetadataExtractionError,
)
from app.pipeline.ingestion.handlers.base import FileHandler


class ImageHandler(FileHandler):
    """Handles image file types with EXIF extraction."""

    @property
    def supported_mime_types(self) -> set[str]:
        return {
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/bmp",
        }

    def validate(
        self, file_path: str, mime_type: str
    ) -> list[str]:
        warnings: list[str] = []

        if not os.path.exists(file_path):
            raise FileValidationError(
                "Image file does not exist",
                context={"file_path": file_path},
            )

        if os.path.getsize(file_path) == 0:
            raise FileValidationError(
                "Image file is empty",
                context={"file_path": file_path},
            )

        # Validate with Pillow
        try:
            from PIL import Image

            img = Image.open(file_path)
            img.verify()  # Check integrity without fully loading
            warnings_info = []

        except ImportError:
            warnings.append("Pillow not installed — skipping image validation")
        except Exception as e:
            warnings.append(f"Image validation warning: {e}")

        return warnings

    def extract_metadata(
        self, file_path: str, mime_type: str
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {"meta_type": "exif"}

        # Basic image properties via Pillow
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS

            img = Image.open(file_path)
            metadata["width"] = img.width
            metadata["height"] = img.height
            metadata["format"] = img.format
            metadata["mode"] = img.mode  # RGB, RGBA, L, etc.

            # Extract EXIF
            exif_data = img.getexif()
            if exif_data:
                exif_dict: dict[str, Any] = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    # Convert bytes to string for JSON serialization
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", errors="replace")
                        except Exception:
                            value = str(value)
                    exif_dict[tag_name] = value

                metadata["exif"] = exif_dict
                metadata["datetime_original"] = exif_dict.get(
                    "DateTimeOriginal"
                )
                metadata["datetime_digitized"] = exif_dict.get(
                    "DateTimeDigitized"
                )
                metadata["camera_make"] = exif_dict.get("Make")
                metadata["camera_model"] = exif_dict.get("Model")
                metadata["software"] = exif_dict.get("Software")
                metadata["orientation"] = exif_dict.get("Orientation")

                # Extract GPS info
                gps_info = self._extract_gps(exif_data)
                if gps_info:
                    metadata["gps"] = gps_info

            img.close()

        except ImportError:
            logger.warning("Pillow not installed")
            metadata["warning"] = "Pillow not available"

        except Exception as e:
            logger.warning(f"Pillow extraction failed: {e}")
            metadata["pillow_error"] = str(e)

        # Additional EXIF via exifread (more comprehensive)
        try:
            import exifread

            with open(file_path, "rb") as f:
                tags = exifread.process_file(f, details=False)

            exifread_data: dict[str, str] = {}
            for key, value in tags.items():
                exifread_data[key] = str(value)

            metadata["exifread"] = exifread_data

            # GPS from exifread if not already found
            if "gps" not in metadata:
                gps = self._extract_gps_from_exifread(tags)
                if gps:
                    metadata["gps"] = gps

        except ImportError:
            pass  # exifread is optional
        except Exception as e:
            logger.debug(f"exifread extraction failed: {e}")

        return metadata

    # ── GPS Extraction ──────────────────────

    def _extract_gps(
        self, exif_data
    ) -> dict[str, float] | None:
        """Extract GPS coordinates from Pillow EXIF data."""
        try:
            from PIL.ExifTags import IFD

            gps_ifd = exif_data.get_ifd(IFD.GPSInfo)
            if not gps_ifd:
                return None

            def _to_degrees(value) -> float:
                """Convert GPS coordinate tuple to decimal degrees."""
                if isinstance(value, (list, tuple)) and len(value) == 3:
                    d = float(value[0])
                    m = float(value[1])
                    s = float(value[2])
                    return d + (m / 60.0) + (s / 3600.0)
                return float(value)

            lat = gps_ifd.get(2)  # GPSLatitude
            lat_ref = gps_ifd.get(1)  # GPSLatitudeRef
            lon = gps_ifd.get(4)  # GPSLongitude
            lon_ref = gps_ifd.get(3)  # GPSLongitudeRef
            alt = gps_ifd.get(6)  # GPSAltitude

            if lat and lon:
                latitude = _to_degrees(lat)
                longitude = _to_degrees(lon)

                if lat_ref == "S":
                    latitude = -latitude
                if lon_ref == "W":
                    longitude = -longitude

                result = {
                    "latitude": round(latitude, 8),
                    "longitude": round(longitude, 8),
                }
                if alt is not None:
                    result["altitude"] = float(alt)

                return result

        except Exception as e:
            logger.debug(f"GPS extraction from Pillow failed: {e}")

        return None

    def _extract_gps_from_exifread(
        self, tags: dict
    ) -> dict[str, float] | None:
        """Extract GPS from exifread tags."""
        try:

            def _tag_to_degrees(tag_value) -> float:
                values = tag_value.values
                d = float(values[0].num) / float(values[0].den)
                m = float(values[1].num) / float(values[1].den)
                s = float(values[2].num) / float(values[2].den)
                return d + (m / 60.0) + (s / 3600.0)

            lat_tag = tags.get("GPS GPSLatitude")
            lat_ref = tags.get("GPS GPSLatitudeRef")
            lon_tag = tags.get("GPS GPSLongitude")
            lon_ref = tags.get("GPS GPSLongitudeRef")

            if lat_tag and lon_tag:
                lat = _tag_to_degrees(lat_tag)
                lon = _tag_to_degrees(lon_tag)

                if lat_ref and str(lat_ref) == "S":
                    lat = -lat
                if lon_ref and str(lon_ref) == "W":
                    lon = -lon

                return {
                    "latitude": round(lat, 8),
                    "longitude": round(lon, 8),
                }

        except Exception as e:
            logger.debug(f"GPS extraction from exifread failed: {e}")

        return None
