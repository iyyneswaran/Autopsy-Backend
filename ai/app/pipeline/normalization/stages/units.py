"""
Atopsy — Unit Conversion Stage.

Converts imperial/non-SI measurements to SI units.
Preserves original values for audit trail.
"""

from __future__ import annotations

from typing import Any


# Conversion functions: (multiplier, offset) or callable
CONVERSIONS: dict[tuple[str, str], tuple[float, float]] = {
    # Temperature
    ("fahrenheit", "celsius"): (5 / 9, -32 * 5 / 9),
    ("kelvin", "celsius"): (1.0, -273.15),
    # Length
    ("inches", "centimeters"): (2.54, 0),
    ("feet", "centimeters"): (30.48, 0),
    ("yards", "meters"): (0.9144, 0),
    ("miles", "kilometers"): (1.60934, 0),
    # Weight
    ("lbs", "kilograms"): (0.453592, 0),
    ("pounds", "kilograms"): (0.453592, 0),
    ("ounces", "grams"): (28.3495, 0),
    ("oz", "grams"): (28.3495, 0),
    ("stones", "kilograms"): (6.35029, 0),
    # Volume
    ("gallons", "liters"): (3.78541, 0),
    ("quarts", "liters"): (0.946353, 0),
    ("fluid_ounces", "milliliters"): (29.5735, 0),
    ("fl_oz", "milliliters"): (29.5735, 0),
}

# Unit aliases → canonical form
UNIT_ALIASES: dict[str, str] = {
    "f": "fahrenheit", "°f": "fahrenheit", "deg f": "fahrenheit",
    "c": "celsius", "°c": "celsius", "deg c": "celsius",
    "k": "kelvin",
    "in": "inches", "inch": "inches", "\"": "inches",
    "ft": "feet", "foot": "feet", "'": "feet",
    "yd": "yards", "yard": "yards",
    "mi": "miles", "mile": "miles",
    "lb": "lbs", "pound": "pounds",
    "oz": "ounces", "ounce": "ounces",
    "gal": "gallons", "gallon": "gallons",
    "cm": "centimeters", "centimeter": "centimeters",
    "m": "meters", "meter": "meters",
    "km": "kilometers", "kilometer": "kilometers",
    "kg": "kilograms", "kilogram": "kilograms",
    "g": "grams", "gram": "grams",
    "l": "liters", "liter": "liters",
    "ml": "milliliters", "milliliter": "milliliters",
}


def normalize_unit(canonical_from: str) -> str:
    """Resolve a unit string to its canonical form."""
    return UNIT_ALIASES.get(canonical_from.lower().strip(), canonical_from.lower().strip())


def convert_measurement(
    value: float,
    from_unit: str,
    to_unit: str | None = None,
) -> dict[str, Any]:
    """
    Convert a measurement value to SI units.

    Returns:
        {
            "value": float (converted),
            "unit": str (SI unit),
            "original_value": float,
            "original_unit": str,
        }
    """
    canonical_from = normalize_unit(from_unit)

    # Find target SI unit
    target = to_unit
    conversion_key = None

    if target:
        target = normalize_unit(target)
        conversion_key = (canonical_from, target)
    else:
        # Auto-detect SI target
        for (src, dst) in CONVERSIONS:
            if src == canonical_from:
                target = dst
                conversion_key = (src, dst)
                break

    # No conversion needed (already SI or unknown)
    if not conversion_key or conversion_key not in CONVERSIONS:
        return {
            "value": value,
            "unit": canonical_from,
            "original_value": value,
            "original_unit": from_unit,
        }

    # Special case: Fahrenheit → Celsius (not linear)
    if conversion_key == ("fahrenheit", "celsius"):
        converted = (value - 32) * 5 / 9
    else:
        multiplier, offset = CONVERSIONS[conversion_key]
        converted = value * multiplier + offset

    return {
        "value": round(converted, 4),
        "unit": target,
        "original_value": value,
        "original_unit": from_unit,
    }


def convert_temperature(
    value: float, from_unit: str
) -> dict[str, Any]:
    """Convenience: convert any temperature to Celsius."""
    return convert_measurement(value, from_unit, "celsius")


def convert_weight(
    value: float, from_unit: str
) -> dict[str, Any]:
    """Convenience: convert any weight to kilograms."""
    return convert_measurement(value, from_unit, "kilograms")


def convert_length(
    value: float, from_unit: str
) -> dict[str, Any]:
    """Convenience: convert any length to centimeters."""
    return convert_measurement(value, from_unit, "centimeters")
