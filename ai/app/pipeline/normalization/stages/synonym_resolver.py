"""
Atopsy — Synonym Resolution Engine.

Resolves colloquial and regional medical/forensic terms to
their canonical scientific equivalents. Tracks all substitutions
for audit trail. Supports Indian English variants.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger


# ─────────────────────────────────────────────
# Synonym Dictionaries
# ─────────────────────────────────────────────

ANATOMICAL_SYNONYMS: dict[str, str] = {
    "breastbone": "sternum",
    "kneecap": "patella",
    "shoulder blade": "scapula",
    "collarbone": "clavicle",
    "shinbone": "tibia",
    "thighbone": "femur",
    "backbone": "vertebral column",
    "windpipe": "trachea",
    "gullet": "esophagus",
    "food pipe": "esophagus",
    "voice box": "larynx",
    "adam's apple": "thyroid cartilage",
    "funny bone": "olecranon",
    "tailbone": "coccyx",
    "jawbone": "mandible",
    "cheekbone": "zygomatic bone",
    "skull cap": "calvarium",
    "temple bone": "temporal bone",
    "rib cage": "thoracic cage",
    "hip bone": "innominate bone",
    "womb": "uterus",
    "belly button": "umbilicus",
    "navel": "umbilicus",
    "armpit": "axilla",
    "groin area": "inguinal region",
    "palm": "palmar surface",
    "sole": "plantar surface",
    "eardrum": "tympanic membrane",
}

INJURY_SYNONYMS: dict[str, str] = {
    "black eye": "periorbital ecchymosis",
    "blood clot": "hematoma",
    "bleeding": "hemorrhage",
    "internal bleeding": "internal hemorrhage",
    "blood in chest": "hemothorax",
    "blood in abdomen": "hemoperitoneum",
    "blood in skull": "intracranial hemorrhage",
    "skull fracture": "cranial fracture",
    "broken neck": "cervical spine fracture",
    "broken back": "vertebral fracture",
    "collapsed lung": "pneumothorax",
    "dislocated": "dislocation",
    "swelling": "edema",
    "pus": "purulent discharge",
    "stitches": "sutures",
    "scar": "cicatrix",
    "rope mark": "ligature mark",
    "nail mark": "crescentic abrasion",
    "bite mark": "patterned contusion",
    "defence wound": "defense wound",
    "hesitation cut": "hesitation wound",
    "self-inflicted": "self-inflicted wound",
    "blunt injury": "blunt force trauma",
    "sharp injury": "sharp force trauma",
}

MEDICAL_SYNONYMS: dict[str, str] = {
    "heart attack": "myocardial infarction",
    "stroke": "cerebrovascular accident",
    "fit": "seizure",
    "fits": "seizures",
    "sugar disease": "diabetes mellitus",
    "blood pressure": "hypertension",
    "high bp": "hypertension",
    "low bp": "hypotension",
    "kidney failure": "renal failure",
    "liver failure": "hepatic failure",
    "lung infection": "pneumonia",
    "blood poisoning": "septicemia",
    "water in lungs": "pulmonary edema",
    "clot in lungs": "pulmonary embolism",
    "clot in legs": "deep vein thrombosis",
    "brain death": "cerebral death",
    "fatty liver": "hepatic steatosis",
    "enlarged heart": "cardiomegaly",
    "enlarged liver": "hepatomegaly",
    "enlarged spleen": "splenomegaly",
    "hardening of arteries": "atherosclerosis",
    "blockage": "occlusion",
    "narrowing": "stenosis",
    "inflammation": "inflammatory process",
    "infection": "infectious process",
    "cancer": "malignant neoplasm",
    "tumor": "neoplasm",
    "abscess": "localized collection of pus",
}

FORENSIC_SYNONYMS: dict[str, str] = {
    "rigor": "rigor mortis",
    "lividity": "livor mortis",
    "post mortem lividity": "livor mortis",
    "hypostasis": "livor mortis",
    "death stiffness": "rigor mortis",
    "body stiffness": "rigor mortis",
    "decomposition": "putrefaction",
    "decomposed body": "putrefied remains",
    "bloating": "post-mortem bloating",
    "maggots": "larval infestation",
    "insect activity": "entomological activity",
    "marbling": "post-mortem marbling",
    "skin slip": "post-mortem skin slippage",
    "green discoloration": "post-mortem discoloration",
    "purging": "post-mortem purging",
    "adipocere": "saponification",
    "mummification": "desiccation",
    "brought dead": "dead on arrival",
    "brought in dead": "dead on arrival",
    "found dead": "discovered deceased",
    "unnatural death": "non-natural death",
    "foul play": "suspicious circumstances",
    "unknown body": "unidentified remains",
}

INDIAN_ENGLISH_SYNONYMS: dict[str, str] = {
    "giddiness": "dizziness",
    "giddy": "dizzy",
    "loose motion": "diarrhea",
    "loose motions": "diarrhea",
    "passing motion": "defecation",
    "blood in motion": "hematochezia",
    "blood vomit": "hematemesis",
    "vomiting blood": "hematemesis",
    "difficulty in breathing": "dyspnea",
    "breathlessness": "dyspnea",
    "weakness": "asthenia",
    "body ache": "myalgia",
    "chest pain": "thoracic pain",
    "stomach pain": "abdominal pain",
    "head injury": "craniocerebral injury",
    "consuming poison": "ingestion of poison",
    "consumed poison": "ingested poison",
    "poison case": "suspected poisoning",
    "hanging body": "body found suspended",
    "burn injury": "thermal injury",
    "road accident": "road traffic accident",
    "rta": "road traffic accident",
}

# Combined dictionary for quick lookup
ALL_SYNONYMS: dict[str, str] = {
    **ANATOMICAL_SYNONYMS,
    **INJURY_SYNONYMS,
    **MEDICAL_SYNONYMS,
    **FORENSIC_SYNONYMS,
    **INDIAN_ENGLISH_SYNONYMS,
}


class SynonymSubstitution:
    """Record of a single synonym substitution."""

    __slots__ = ("original", "resolved", "category", "confidence", "position")

    def __init__(
        self,
        original: str,
        resolved: str,
        category: str = "",
        confidence: float = 0.9,
        position: int = 0,
    ) -> None:
        self.original = original
        self.resolved = resolved
        self.category = category
        self.confidence = confidence
        self.position = position

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "resolved": self.resolved,
            "category": self.category,
            "confidence": self.confidence,
            "position": self.position,
        }


class SynonymResolutionResult:
    """Result of synonym resolution on text."""

    def __init__(
        self,
        original_text: str,
        resolved_text: str,
        substitutions: list[SynonymSubstitution] | None = None,
    ) -> None:
        self.original_text = original_text
        self.resolved_text = resolved_text
        self.substitutions = substitutions or []

    @property
    def substitution_count(self) -> int:
        return len(self.substitutions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved_text": self.resolved_text,
            "substitution_count": self.substitution_count,
            "substitutions": [s.to_dict() for s in self.substitutions],
        }


def resolve_synonyms(text: str) -> SynonymResolutionResult:
    """
    Resolve all known synonyms in the text.

    Uses word-boundary-aware case-insensitive matching.
    Tracks all substitutions for audit trail.

    Args:
        text: Input text to process.

    Returns:
        SynonymResolutionResult with resolved text and substitution log.
    """
    if not text:
        return SynonymResolutionResult(text, text)

    resolved = text
    substitutions: list[SynonymSubstitution] = []

    # Sort by length (longest first) to avoid partial matches
    sorted_synonyms = sorted(ALL_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)

    for original, replacement in sorted_synonyms:
        # Word-boundary aware, case-insensitive search
        pattern = rf"\b{re.escape(original)}\b"
        matches = list(re.finditer(pattern, resolved, re.IGNORECASE))

        for match in reversed(matches):
            # Determine category
            category = _get_category(original)

            substitutions.append(SynonymSubstitution(
                original=match.group(),
                resolved=replacement,
                category=category,
                confidence=0.9,
                position=match.start(),
            ))

            # Replace in text
            resolved = resolved[:match.start()] + replacement + resolved[match.end():]

    return SynonymResolutionResult(
        original_text=text,
        resolved_text=resolved,
        substitutions=substitutions,
    )


def resolve_single(term: str) -> tuple[str, float]:
    """
    Resolve a single term. Returns (resolved_term, confidence).
    """
    key = term.lower().strip()
    if key in ALL_SYNONYMS:
        return ALL_SYNONYMS[key], 0.9
    return term, 1.0


def _get_category(term: str) -> str:
    """Determine which synonym category a term belongs to."""
    key = term.lower().strip()
    if key in ANATOMICAL_SYNONYMS:
        return "anatomical"
    elif key in INJURY_SYNONYMS:
        return "injury"
    elif key in MEDICAL_SYNONYMS:
        return "medical"
    elif key in FORENSIC_SYNONYMS:
        return "forensic"
    elif key in INDIAN_ENGLISH_SYNONYMS:
        return "indian_english"
    return "unknown"
