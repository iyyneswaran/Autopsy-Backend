"""
Atopsy — Toxicology Normalization Stage.

Standardizes substance names, concentration units, and classifies
findings by therapeutic/toxic/lethal levels. Includes Indian-specific
common poisons and metabolite-to-parent-drug mapping.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger


# ─────────────────────────────────────────────
# Substance Standardization
# ─────────────────────────────────────────────

SUBSTANCE_SYNONYMS: dict[str, str] = {
    "ethyl alcohol": "ethanol", "alcohol": "ethanol", "etoh": "ethanol",
    "ethyl": "ethanol", "blood alcohol": "ethanol",
    "marijuana": "cannabis", "thc": "cannabis", "ganja": "cannabis",
    "bhang": "cannabis", "charas": "cannabis",
    "heroin": "diacetylmorphine", "smack": "diacetylmorphine", "brown sugar": "diacetylmorphine",
    "morphine sulfate": "morphine", "mscontin": "morphine",
    "diazepam": "diazepam", "valium": "diazepam",
    "alprazolam": "alprazolam", "xanax": "alprazolam",
    "lorazepam": "lorazepam", "ativan": "lorazepam",
    "meth": "methamphetamine", "crystal meth": "methamphetamine",
    "coke": "cocaine", "crack": "cocaine",
    "rat poison": "aluminum_phosphide", "celphos": "aluminum_phosphide",
    "sulphas": "aluminum_phosphide",
    "kuchla": "strychnine", "nux vomica": "strychnine",
    "dhatura": "datura_stramonium", "datura": "datura_stramonium",
    "oleander": "nerium_oleander", "kaner": "nerium_oleander",
    "opium": "opiate", "afeem": "opiate",
    "sleeping pills": "barbiturate", "phenobarbitone": "phenobarbital",
    "organo phosphorus": "organophosphate", "op compound": "organophosphate",
    "op poison": "organophosphate", "insecticide": "organophosphate",
    "pesticide": "organophosphate",
    "potassium cyanide": "cyanide", "kcn": "cyanide",
    "white phosphorus": "phosphorus", "yellow phosphorus": "phosphorus",
    "carbolic acid": "phenol", "lysol": "phenol",
    "copper sulphate": "copper_sulfate", "neela thotha": "copper_sulfate",
    "zinc phosphide": "zinc_phosphide",
    "paraquat": "paraquat", "endosulfan": "endosulfan",
    "malathion": "malathion", "chlorpyrifos": "chlorpyrifos",
    "monocrotophos": "monocrotophos", "phorate": "phorate",
}

# ─────────────────────────────────────────────
# Metabolite → Parent Drug Mapping
# ─────────────────────────────────────────────

METABOLITE_MAP: dict[str, str] = {
    "6-monoacetylmorphine": "diacetylmorphine",
    "6-mam": "diacetylmorphine",
    "benzoylecgonine": "cocaine",
    "ecgonine methyl ester": "cocaine",
    "nordiazepam": "diazepam",
    "oxazepam": "diazepam",
    "alpha-hydroxyalprazolam": "alprazolam",
    "norfentanyl": "fentanyl",
    "noroxycodone": "oxycodone",
    "eddp": "methadone",
    "amphetamine": "methamphetamine",
    "11-nor-9-carboxy-thc": "cannabis",
    "thc-cooh": "cannabis",
    "cotinine": "nicotine",
    "acetaldehyde": "ethanol",
}

# ─────────────────────────────────────────────
# Concentration Level Classification (mg/dL unless noted)
# ─────────────────────────────────────────────

LEVEL_THRESHOLDS: dict[str, dict[str, tuple[float, float]]] = {
    "ethanol": {
        "therapeutic": (0.0, 50.0),
        "toxic": (100.0, 400.0),
        "lethal": (400.0, 9999.0),
    },
    "morphine": {  # ng/mL
        "therapeutic": (10.0, 70.0),
        "toxic": (200.0, 500.0),
        "lethal": (500.0, 9999.0),
    },
    "diazepam": {  # ng/mL
        "therapeutic": (100.0, 1000.0),
        "toxic": (2000.0, 5000.0),
        "lethal": (5000.0, 9999.0),
    },
    "phenobarbital": {  # ug/mL
        "therapeutic": (10.0, 40.0),
        "toxic": (50.0, 80.0),
        "lethal": (80.0, 9999.0),
    },
    "cocaine": {  # ng/mL
        "therapeutic": (0.0, 0.0),
        "toxic": (100.0, 500.0),
        "lethal": (500.0, 9999.0),
    },
    "methamphetamine": {  # ng/mL
        "therapeutic": (10.0, 50.0),
        "toxic": (200.0, 500.0),
        "lethal": (500.0, 9999.0),
    },
    "cyanide": {  # mg/L
        "therapeutic": (0.0, 0.0),
        "toxic": (0.5, 3.0),
        "lethal": (3.0, 9999.0),
    },
    "organophosphate": {
        "therapeutic": (0.0, 0.0),
        "toxic": (0.0, 0.0),
        "lethal": (0.0, 9999.0),
    },
}

# ─────────────────────────────────────────────
# Unit Normalization
# ─────────────────────────────────────────────

UNIT_CONVERSIONS: dict[tuple[str, str], float] = {
    ("g/dl", "mg/dl"): 1000.0,
    ("g/l", "mg/dl"): 100.0,
    ("mg/l", "mg/dl"): 0.1,
    ("ug/ml", "ng/ml"): 1000.0,
    ("mg/ml", "ng/ml"): 1_000_000.0,
    ("ug/l", "ng/ml"): 1.0,
    ("ug/dl", "ng/ml"): 10.0,
    ("mmol/l", "mg/dl"): 4.6,  # approximate for ethanol
}

UNIT_ALIASES: dict[str, str] = {
    "mg/dl": "mg/dL", "mg/100ml": "mg/dL",
    "ng/ml": "ng/mL", "ug/ml": "ug/mL",
    "mg/l": "mg/L", "ug/l": "ug/L",
    "g/dl": "g/dL", "g/l": "g/L",
    "mmol/l": "mmol/L",
    "%": "%", "percent": "%",
    "ppm": "ppm",
}


class NormalizedToxicologyFinding:
    """A normalized toxicology finding."""

    def __init__(
        self,
        substance: str,
        original_substance: str,
        result: str,
        concentration: float | None = None,
        unit: str = "",
        original_concentration: str = "",
        original_unit: str = "",
        level_classification: str = "",
        is_metabolite: bool = False,
        parent_drug: str = "",
        confidence: float = 0.7,
    ) -> None:
        self.substance = substance
        self.original_substance = original_substance
        self.result = result
        self.concentration = concentration
        self.unit = unit
        self.original_concentration = original_concentration
        self.original_unit = original_unit
        self.level_classification = level_classification
        self.is_metabolite = is_metabolite
        self.parent_drug = parent_drug
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "substance": self.substance,
            "original_substance": self.original_substance,
            "result": self.result,
            "concentration": self.concentration,
            "unit": self.unit,
            "original_concentration": self.original_concentration,
            "original_unit": self.original_unit,
            "level_classification": self.level_classification,
            "is_metabolite": self.is_metabolite,
            "parent_drug": self.parent_drug,
            "confidence": self.confidence,
        }


def normalize_toxicology(
    findings: list[dict[str, Any]],
) -> list[NormalizedToxicologyFinding]:
    """
    Normalize a list of raw toxicology findings.

    Each finding dict should have keys like:
      substance, result, concentration, unit

    Returns list of NormalizedToxicologyFinding objects.
    """
    results: list[NormalizedToxicologyFinding] = []

    for finding in findings:
        try:
            normalized = _normalize_single(finding)
            results.append(normalized)
        except Exception as e:
            logger.warning(f"Toxicology normalization failed: {e}")
            results.append(NormalizedToxicologyFinding(
                substance=str(finding.get("substance", "unknown")),
                original_substance=str(finding.get("substance", "")),
                result=str(finding.get("result", "")),
                confidence=0.3,
            ))

    return results


def _normalize_single(finding: dict[str, Any]) -> NormalizedToxicologyFinding:
    """Normalize a single toxicology finding."""
    raw_substance = str(finding.get("substance", "")).strip()
    raw_result = str(finding.get("result", "")).strip()
    raw_conc = str(finding.get("concentration", "")).strip()
    raw_unit = str(finding.get("unit", "")).strip()

    # Standardize substance name
    substance = _standardize_substance(raw_substance)

    # Check metabolite mapping
    is_metabolite = False
    parent_drug = ""
    sub_lower = substance.lower()
    if sub_lower in METABOLITE_MAP:
        is_metabolite = True
        parent_drug = METABOLITE_MAP[sub_lower]

    # Standardize result
    result = _standardize_result(raw_result)

    # Parse and normalize concentration
    concentration = None
    unit = raw_unit
    if raw_conc:
        try:
            concentration = float(re.sub(r"[^\d\.]", "", raw_conc))
        except (ValueError, TypeError):
            pass

    if raw_unit:
        unit = UNIT_ALIASES.get(raw_unit.lower().strip(), raw_unit)

    # Classify level
    level = ""
    if concentration is not None and substance.lower() in LEVEL_THRESHOLDS:
        level = _classify_level(substance.lower(), concentration)

    return NormalizedToxicologyFinding(
        substance=substance,
        original_substance=raw_substance,
        result=result,
        concentration=concentration,
        unit=unit,
        original_concentration=raw_conc,
        original_unit=raw_unit,
        level_classification=level,
        is_metabolite=is_metabolite,
        parent_drug=parent_drug,
        confidence=0.8 if concentration is not None else 0.6,
    )


def _standardize_substance(name: str) -> str:
    """Map substance name to canonical form."""
    key = name.lower().strip()
    return SUBSTANCE_SYNONYMS.get(key, name)


def _standardize_result(result: str) -> str:
    """Standardize qualitative results."""
    r = result.lower().strip()
    if r in ("positive", "pos", "+", "detected", "present"):
        return "POSITIVE"
    elif r in ("negative", "neg", "-", "not detected", "absent", "nil", "none"):
        return "NEGATIVE"
    elif r in ("trace", "minimal"):
        return "TRACE"
    elif r in ("pending", "awaited"):
        return "PENDING"
    return result


def _classify_level(substance: str, concentration: float) -> str:
    """Classify concentration as therapeutic/toxic/lethal."""
    thresholds = LEVEL_THRESHOLDS.get(substance)
    if not thresholds:
        return ""

    for level, (low, high) in [
        ("lethal", thresholds.get("lethal", (9999, 9999))),
        ("toxic", thresholds.get("toxic", (9999, 9999))),
        ("therapeutic", thresholds.get("therapeutic", (0, 0))),
    ]:
        if low <= concentration <= high:
            return level

    if concentration > 0:
        # Above therapeutic but below toxic
        return "elevated"
    return "normal"
