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


# ─────────────────────────────────────────────
# Extended Indian Forensic Abbreviations
# ─────────────────────────────────────────────

INDIAN_FORENSIC_ABBREVIATIONS: dict[str, str] = {
    # Indian medico-legal
    "mlc": "medico-legal case",
    "ipc": "Indian Penal Code",
    "crpc": "Code of Criminal Procedure",
    "fsl": "forensic science laboratory",
    "cfsl": "central forensic science laboratory",
    "dfs": "directorate of forensic science",
    "pmo": "post-mortem office",
    "cmo": "chief medical officer",
    "smo": "senior medical officer",
    "jmfc": "judicial magistrate first class",
    "io": "investigating officer",
    "sho": "station house officer",
    "ps": "police station",
    "fir": "first information report",
    "ddo": "dead body disposal order",
    "inquest": "inquest report",
    # Common Indian forensic terms
    "pm": "post-mortem",
    "pmr": "post-mortem report",
    "pme": "post-mortem examination",
    "alp": "aluminum phosphide",
    "opc": "organophosphorus compound",
    "opcp": "organophosphorus compound poisoning",
    "rta": "road traffic accident",
    "rtc": "road traffic collision",
    "sia": "self-inflicted injury attempt",
    "npa": "non-poisonous animal",
    "dob": "date of birth",
    "dod": "date of death",
    "doe": "date of examination",
    "dot": "date of treatment",
    "doa": "dead on arrival",
    # Additional medical
    "acs": "acute coronary syndrome",
    "chf": "congestive heart failure",
    "ckd": "chronic kidney disease",
    "cld": "chronic liver disease",
    "dcmp": "dilated cardiomyopathy",
    "lvh": "left ventricular hypertrophy",
    "rvf": "right ventricular failure",
    "lvf": "left ventricular failure",
    "mods": "multi-organ dysfunction syndrome",
    "dic": "disseminated intravascular coagulation",
    "ards": "acute respiratory distress syndrome",
    "gcs": "Glasgow Coma Scale",
    "rbs": "random blood sugar",
    "ecg": "electrocardiogram",
    "ct": "computed tomography",
    "mri": "magnetic resonance imaging",
    "usg": "ultrasonography",
}

# Merge into main dictionary
FORENSIC_ABBREVIATIONS.update(INDIAN_FORENSIC_ABBREVIATIONS)


# ─────────────────────────────────────────────
# Decomposition Stage Classification
# ─────────────────────────────────────────────

DECOMPOSITION_STAGES: dict[str, dict[str, Any]] = {
    "FRESH": {
        "order": 0,
        "description": "No visible decomposition",
        "indicators": [
            "no decomposition", "fresh", "well preserved",
            "no putrefactive changes", "body well maintained",
        ],
        "pmi_range": "0-24 hours",
    },
    "EARLY_DECOMPOSITION": {
        "order": 1,
        "description": "Early color changes, greenish discoloration of abdomen",
        "indicators": [
            "greenish discoloration", "early decomposition",
            "greenish discolouration", "green patch",
            "early putrefaction", "slight odor",
        ],
        "pmi_range": "1-3 days",
    },
    "BLOAT": {
        "order": 2,
        "description": "Gas accumulation causing distension",
        "indicators": [
            "bloating", "bloated", "distension", "distended",
            "gas formation", "swollen", "purging",
            "marbling", "protruding tongue", "foul odor",
        ],
        "pmi_range": "3-7 days",
    },
    "ACTIVE_DECAY": {
        "order": 3,
        "description": "Active tissue breakdown with insect activity",
        "indicators": [
            "active decay", "maggots", "larval activity",
            "skin slippage", "hair slippage", "liquefaction",
            "tissue breakdown", "foul smell", "putrefied",
        ],
        "pmi_range": "1-3 weeks",
    },
    "ADVANCED_DECAY": {
        "order": 4,
        "description": "Most soft tissue decomposed",
        "indicators": [
            "advanced decay", "advanced decomposition",
            "most soft tissue lost", "mummification",
            "adipocere", "saponification", "partial skeletonization",
        ],
        "pmi_range": "3 weeks - months",
    },
    "SKELETONIZATION": {
        "order": 5,
        "description": "Only skeletal remains",
        "indicators": [
            "skeletonization", "skeletonized", "skeletal remains",
            "bones only", "dry remains", "complete skeletonization",
        ],
        "pmi_range": "months - years",
    },
}

INJURY_SEVERITY: dict[str, list[str]] = {
    "SUPERFICIAL": [
        "superficial", "minor scratch", "slight", "small abrasion",
        "insignificant", "trivial",
    ],
    "MINOR": [
        "minor", "simple", "small", "non-grievous",
        "abrasion", "superficial laceration",
    ],
    "MODERATE": [
        "moderate", "significant", "deep laceration",
        "contusion", "tissue damage",
    ],
    "SEVERE": [
        "severe", "extensive", "deep wound", "compound fracture",
        "major vessel", "organ damage", "grievous",
    ],
    "CRITICAL": [
        "critical", "life-threatening", "major organ",
        "massive hemorrhage", "multiple organ", "brain injury",
    ],
    "FATAL": [
        "fatal", "lethal", "incompatible with life",
        "death", "died", "succumbed", "expired",
    ],
}

WOUND_AGE: dict[str, dict[str, Any]] = {
    "FRESH": {
        "hours": (0, 6),
        "indicators": [
            "fresh", "bleeding", "active bleeding", "raw",
            "bright red", "no healing", "recent",
        ],
    },
    "RECENT": {
        "hours": (6, 24),
        "indicators": [
            "recent", "clotted", "dried blood", "swollen",
            "inflammatory", "reddish", "edematous",
        ],
    },
    "HEALING": {
        "hours": (24, 168),
        "indicators": [
            "healing", "granulation", "scab", "crusted",
            "yellowish", "brownish", "resolving",
        ],
    },
    "OLD": {
        "hours": (168, 99999),
        "indicators": [
            "old", "healed", "scar", "cicatrix",
            "fibrosis", "organized", "chronic",
        ],
    },
}

CAUSE_OF_DEATH_CLASSIFICATION: dict[str, list[str]] = {
    "NATURAL_DISEASE": [
        "natural", "disease", "cardiac", "myocardial",
        "coronary", "stroke", "cerebrovascular",
        "pulmonary embolism", "pneumonia", "cancer",
    ],
    "POISONING": [
        "poison", "toxic", "overdose", "ingestion",
        "organophosph", "cyanide", "aluminum phosphide",
        "drug", "chemical",
    ],
    "ASPHYXIA": [
        "asphyx", "strangul", "hanging", "suffoc",
        "throttling", "smothering", "choking",
        "ligature", "compression of neck",
    ],
    "DROWNING": [
        "drowning", "submersion", "immersion",
        "water in lungs", "diatom",
    ],
    "BURNS": [
        "burn", "scald", "thermal", "flame",
        "kerosene", "acid", "chemical burn",
    ],
    "BLUNT_FORCE": [
        "blunt force", "blunt trauma", "head injury",
        "craniocerebral", "fall", "assault",
        "vehicular", "rta", "road traffic",
    ],
    "SHARP_FORCE": [
        "sharp force", "stab", "incised", "cut throat",
        "slash", "chop", "hack",
    ],
    "FIREARM": [
        "firearm", "gunshot", "bullet", "shooting",
        "rifle", "pistol",
    ],
    "ELECTROCUTION": [
        "electrocution", "electric", "lightning",
        "current", "shock",
    ],
    "MULTIPLE_INJURIES": [
        "multiple injuries", "polytrauma", "combined",
    ],
}


# ─────────────────────────────────────────────
# New Classification Functions
# ─────────────────────────────────────────────


def classify_injury_severity(description: str) -> str:
    """Classify injury severity from description text."""
    desc_lower = description.lower()
    # Check from most severe to least
    for severity in ["FATAL", "CRITICAL", "SEVERE", "MODERATE", "MINOR", "SUPERFICIAL"]:
        if any(kw in desc_lower for kw in INJURY_SEVERITY[severity]):
            return severity
    return "UNCLASSIFIED"


def classify_decomposition_stage(description: str) -> str:
    """Classify decomposition stage from description text."""
    desc_lower = description.lower()
    # Check from most advanced to least
    for stage in ["SKELETONIZATION", "ADVANCED_DECAY", "ACTIVE_DECAY",
                   "BLOAT", "EARLY_DECOMPOSITION", "FRESH"]:
        indicators = DECOMPOSITION_STAGES[stage]["indicators"]
        if any(ind in desc_lower for ind in indicators):
            return stage
    return "UNDETERMINED"


def classify_wound_age(description: str) -> str:
    """Classify wound age from description text."""
    desc_lower = description.lower()
    for age in ["OLD", "HEALING", "RECENT", "FRESH"]:
        if any(ind in desc_lower for ind in WOUND_AGE[age]["indicators"]):
            return age
    return "UNDETERMINED"


def classify_cause_of_death(description: str) -> str:
    """Classify cause of death into broad categories."""
    desc_lower = description.lower()
    for category, keywords in CAUSE_OF_DEATH_CLASSIFICATION.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return "UNDETERMINED"

