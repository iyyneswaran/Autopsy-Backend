"""
Atopsy — Medical Terminology Standardization Stage.

Normalizes forensic abbreviations, injury terms,
toxicology references, and pathology vocabulary.
"""

from __future__ import annotations

import re
from typing import Any


# ─────────────────────────────────────────────
# Abbreviation Expansion Dictionary
# ─────────────────────────────────────────────

FORENSIC_ABBREVIATIONS: dict[str, str] = {
    # General forensic
    "cod": "cause of death",
    "mod": "manner of death",
    "tod": "time of death",
    "pmi": "post-mortem interval",
    "doa": "dead on arrival",
    "gsw": "gunshot wound",
    "bft": "blunt force trauma",
    "sft": "sharp force trauma",
    "mvca": "motor vehicle collision accident",
    "mva": "motor vehicle accident",
    # Anatomical
    "ant": "anterior",
    "post": "posterior",
    "lat": "lateral",
    "med": "medial",
    "sup": "superior",
    "inf": "inferior",
    "rt": "right",
    "lt": "left",
    "bilat": "bilateral",
    # Medical
    "htn": "hypertension",
    "dm": "diabetes mellitus",
    "cad": "coronary artery disease",
    "mi": "myocardial infarction",
    "cva": "cerebrovascular accident",
    "copd": "chronic obstructive pulmonary disease",
    "pe": "pulmonary embolism",
    "dvt": "deep vein thrombosis",
    "ards": "acute respiratory distress syndrome",
    "tbi": "traumatic brain injury",
    "sdh": "subdural hematoma",
    "edh": "epidural hematoma",
    "sah": "subarachnoid hemorrhage",
    "ich": "intracerebral hemorrhage",
    # Toxicology
    "bac": "blood alcohol concentration",
    "etoh": "ethanol",
    "thc": "tetrahydrocannabinol",
    "bzo": "benzodiazepine",
    "opi": "opiate",
    "amp": "amphetamine",
    "meth": "methamphetamine",
    "pcp": "phencyclidine",
    "coc": "cocaine",
    # Units
    "ng/ml": "nanograms per milliliter",
    "mg/dl": "milligrams per deciliter",
    "ug/l": "micrograms per liter",
}

# ─────────────────────────────────────────────
# Injury Type Normalization
# ─────────────────────────────────────────────

INJURY_TYPE_MAP: dict[str, str] = {
    "cut": "laceration",
    "cuts": "laceration",
    "slash": "laceration",
    "tear": "laceration",
    "bruise": "contusion",
    "bruising": "contusion",
    "ecchymosis": "contusion",
    "hematoma": "contusion",
    "break": "fracture",
    "broken": "fracture",
    "crack": "fracture",
    "cracked": "fracture",
    "burn": "thermal_burn",
    "burns": "thermal_burn",
    "scald": "thermal_burn",
    "scrape": "abrasion",
    "scratch": "abrasion",
    "graze": "abrasion",
    "stab": "puncture_wound",
    "pierce": "puncture_wound",
    "puncture": "puncture_wound",
    "bullet": "gunshot_wound",
    "gunshot": "gunshot_wound",
    "shooting": "gunshot_wound",
    "strangle": "ligature_strangulation",
    "suffocate": "asphyxiation",
    "drown": "drowning",
    "drowning": "drowning",
    "poison": "toxicological",
    "overdose": "toxicological",
}

# ─────────────────────────────────────────────
# Body Region Normalization
# ─────────────────────────────────────────────

BODY_REGION_MAP: dict[str, str] = {
    "head": "head",
    "skull": "head",
    "cranium": "head",
    "face": "head",
    "forehead": "head",
    "temple": "head",
    "neck": "neck",
    "throat": "neck",
    "cervical": "neck",
    "chest": "thorax",
    "thorax": "thorax",
    "rib": "thorax",
    "ribs": "thorax",
    "lung": "thorax",
    "heart": "thorax",
    "abdomen": "abdomen",
    "stomach": "abdomen",
    "belly": "abdomen",
    "liver": "abdomen",
    "kidney": "abdomen",
    "spleen": "abdomen",
    "pelvis": "pelvis",
    "hip": "pelvis",
    "groin": "pelvis",
    "arm": "upper_extremity",
    "shoulder": "upper_extremity",
    "elbow": "upper_extremity",
    "wrist": "upper_extremity",
    "hand": "upper_extremity",
    "finger": "upper_extremity",
    "leg": "lower_extremity",
    "thigh": "lower_extremity",
    "knee": "lower_extremity",
    "ankle": "lower_extremity",
    "foot": "lower_extremity",
    "toe": "lower_extremity",
    "back": "posterior_trunk",
    "spine": "posterior_trunk",
    "lumbar": "posterior_trunk",
}

# ─────────────────────────────────────────────
# Manner of Death Normalization
# ─────────────────────────────────────────────

MANNER_OF_DEATH_MAP: dict[str, str] = {
    "natural": "natural",
    "accident": "accidental",
    "accidental": "accidental",
    "suicide": "suicide",
    "homicide": "homicide",
    "murder": "homicide",
    "undetermined": "undetermined",
    "pending": "pending_investigation",
    "unknown": "undetermined",
}


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────


def expand_abbreviation(text: str) -> str:
    """Expand known forensic abbreviations in text."""
    if not text:
        return text

    words = text.split()
    expanded = []
    for word in words:
        clean = word.lower().strip(".,;:()")
        if clean in FORENSIC_ABBREVIATIONS:
            expanded.append(FORENSIC_ABBREVIATIONS[clean])
        else:
            expanded.append(word)
    return " ".join(expanded)


def normalize_injury_type(injury: str) -> str:
    """Normalize injury type to canonical form."""
    key = injury.lower().strip()
    return INJURY_TYPE_MAP.get(key, key)


def normalize_body_region(region: str) -> str:
    """Normalize body region to canonical form."""
    key = region.lower().strip()
    return BODY_REGION_MAP.get(key, key)


def normalize_manner_of_death(manner: str) -> str:
    """Normalize manner of death to canonical form."""
    key = manner.lower().strip()
    return MANNER_OF_DEATH_MAP.get(key, key)


def standardize_medical_text(text: str) -> str:
    """Apply full medical text standardization pipeline."""
    if not text:
        return text

    text = expand_abbreviation(text)
    # Normalize common patterns
    text = re.sub(r"\b(approx\.?|approximately)\b", "approximately", text, flags=re.I)
    text = re.sub(r"\b(yr|yrs|y\.o\.)\b", "years old", text, flags=re.I)
    text = re.sub(r"\b(wt|wgt)\b", "weight", text, flags=re.I)
    text = re.sub(r"\b(ht|hgt)\b", "height", text, flags=re.I)

    return text
