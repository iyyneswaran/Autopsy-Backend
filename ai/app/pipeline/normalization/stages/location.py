"""
Atopsy — Location Normalization Stage.

Normalizes GPS coordinates, validates ranges,
and structures address information.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger


def normalize_location(
    raw: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Normalize a location dict into the canonical NormalizedLocation format.

    Accepts various input formats:
    - {"latitude": float, "longitude": float}
    - {"lat": float, "lon": float}
    - {"gps": {"latitude": ..., "longitude": ...}}
    - {"coordinates": "lat,lon"}
    """
    if not raw:
        return None

    result: dict[str, Any] = {"raw_value": str(raw)}

    # Extract coordinates from various input formats
    lat = _extract_coord(raw, ["latitude", "lat", "y"])
    lon = _extract_coord(raw, ["longitude", "lon", "lng", "long", "x"])

    # Try nested GPS
    if lat is None and "gps" in raw:
        gps = raw["gps"]
        if isinstance(gps, dict):
            lat = _extract_coord(gps, ["latitude", "lat"])
            lon = _extract_coord(gps, ["longitude", "lon", "lng"])

    # Try coordinate string "lat,lon"
    if lat is None and "coordinates" in raw:
        parsed = parse_coordinate_string(str(raw["coordinates"]))
        if parsed:
            lat, lon = parsed

    # Validate ranges
    if lat is not None and lon is not None:
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            result["latitude"] = round(lat, 8)
            result["longitude"] = round(lon, 8)
        else:
            result["latitude"] = None
            result["longitude"] = None
            result["warning"] = f"Invalid GPS: ({lat}, {lon})"

    # Altitude
    alt = _extract_coord(raw, ["altitude", "alt", "elevation"])
    if alt is not None:
        result["altitude_meters"] = round(float(alt), 2)

    # Address components
    for field in ["address", "city", "region", "state", "country", "country_code"]:
        if field in raw and raw[field]:
            if field == "state":
                result["region"] = str(raw[field])
            else:
                result[field] = str(raw[field])

    return result


def parse_coordinate_string(
    coord_str: str,
) -> tuple[float, float] | None:
    """
    Parse coordinate strings:
    - "40.7128, -74.0060"
    - "40°42'46\"N 74°0'22\"W"
    - "N40.7128 W74.0060"
    """
    # Decimal format: "lat, lon"
    decimal_match = re.match(
        r"(-?\d+\.?\d*)\s*[,;\s]\s*(-?\d+\.?\d*)",
        coord_str.strip(),
    )
    if decimal_match:
        try:
            lat = float(decimal_match.group(1))
            lon = float(decimal_match.group(2))
            return (lat, lon)
        except ValueError:
            pass

    # DMS format: 40°42'46"N 74°0'22"W
    dms_pattern = (
        r"(\d+)[°]\s*(\d+)[\'′]\s*(\d+\.?\d*)[\"″]?\s*([NSEW])"
    )
    matches = re.findall(dms_pattern, coord_str, re.IGNORECASE)
    if len(matches) >= 2:
        try:
            lat = _dms_to_decimal(*matches[0])
            lon = _dms_to_decimal(*matches[1])
            return (lat, lon)
        except (ValueError, IndexError):
            pass

    return None


def validate_gps(lat: float, lon: float) -> list[str]:
    """Validate GPS coordinates and return warnings."""
    warnings: list[str] = []

    if not (-90.0 <= lat <= 90.0):
        warnings.append(f"Latitude {lat} out of range [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        warnings.append(f"Longitude {lon} out of range [-180, 180]")
    if lat == 0.0 and lon == 0.0:
        warnings.append("GPS coordinates are (0, 0) — likely placeholder")

    return warnings


def _extract_coord(
    data: dict, keys: list[str]
) -> float | None:
    """Extract a numeric coordinate from a dict by trying multiple keys."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _dms_to_decimal(
    degrees: str, minutes: str, seconds: str, direction: str
) -> float:
    """Convert DMS (degrees, minutes, seconds) to decimal degrees."""
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if direction.upper() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 8)
