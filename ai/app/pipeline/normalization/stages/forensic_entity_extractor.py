"""
Atopsy — Forensic Entity Extraction Stage.

Extracts typed forensic entities from OCR text and structured fields:
deceased info, injuries, toxicology findings, cause/manner of death,
anatomical references, and examination findings.

Supports Indian autopsy report formats with Hindi transliterations.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger


class ForensicEntity:
    """A single extracted forensic entity."""

    __slots__ = (
        "entity_type", "raw_value", "normalized_value",
        "confidence", "source_start", "source_end",
    )

    def __init__(
        self,
        entity_type: str,
        raw_value: str,
        normalized_value: str = "",
        confidence: float = 0.7,
        source_start: int = 0,
        source_end: int = 0,
    ) -> None:
        self.entity_type = entity_type
        self.raw_value = raw_value
        self.normalized_value = normalized_value or raw_value
        self.confidence = confidence
        self.source_start = source_start
        self.source_end = source_end

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "confidence": self.confidence,
            "source_span": [self.source_start, self.source_end],
        }


class ForensicEntitySet:
    """Categorized collection of forensic entities."""

    def __init__(self) -> None:
        self.deceased_info: list[ForensicEntity] = []
        self.injuries: list[ForensicEntity] = []
        self.toxicology: list[ForensicEntity] = []
        self.cause_of_death: list[ForensicEntity] = []
        self.manner_of_death: list[ForensicEntity] = []
        self.time_of_death: list[ForensicEntity] = []
        self.examining_doctor: list[ForensicEntity] = []
        self.case_identifier: list[ForensicEntity] = []
        self.anatomical_references: list[ForensicEntity] = []
        self.organ_findings: list[ForensicEntity] = []
        self.external_examination: list[ForensicEntity] = []
        self.internal_examination: list[ForensicEntity] = []

    @property
    def all_entities(self) -> list[ForensicEntity]:
        return (
            self.deceased_info + self.injuries + self.toxicology
            + self.cause_of_death + self.manner_of_death
            + self.time_of_death + self.examining_doctor
            + self.case_identifier + self.anatomical_references
            + self.organ_findings + self.external_examination
            + self.internal_examination
        )

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "deceased_info": [e.to_dict() for e in self.deceased_info],
            "injuries": [e.to_dict() for e in self.injuries],
            "toxicology": [e.to_dict() for e in self.toxicology],
            "cause_of_death": [e.to_dict() for e in self.cause_of_death],
            "manner_of_death": [e.to_dict() for e in self.manner_of_death],
            "time_of_death": [e.to_dict() for e in self.time_of_death],
            "examining_doctor": [e.to_dict() for e in self.examining_doctor],
            "case_identifier": [e.to_dict() for e in self.case_identifier],
            "anatomical_references": [e.to_dict() for e in self.anatomical_references],
            "organ_findings": [e.to_dict() for e in self.organ_findings],
            "external_examination": [e.to_dict() for e in self.external_examination],
            "internal_examination": [e.to_dict() for e in self.internal_examination],
            "total_entities": len(self.all_entities),
        }


def extract_forensic_entities(
    text: str,
    structured_fields: dict[str, Any] | None = None,
) -> ForensicEntitySet:
    """
    Extract forensic entities from raw text and optional structured data.

    Args:
        text: OCR-extracted or raw text from forensic document.
        structured_fields: Optional pre-extracted structured fields.

    Returns:
        ForensicEntitySet with categorized entities.
    """
    result = ForensicEntitySet()

    if not text and not structured_fields:
        return result

    if text:
        result.case_identifier = _extract_case_ids(text)
        result.deceased_info = _extract_deceased(text)
        result.cause_of_death = _extract_cod(text)
        result.manner_of_death = _extract_mod(text)
        result.time_of_death = _extract_tod(text)
        result.examining_doctor = _extract_doctor(text)
        result.injuries = _extract_injury_entities(text)
        result.toxicology = _extract_tox_entities(text)
        result.anatomical_references = _extract_anatomical(text)
        result.organ_findings = _extract_organ_findings(text)

    # Enrich from structured fields
    if structured_fields:
        _enrich_from_structured(result, structured_fields)

    logger.debug(f"Extracted {len(result.all_entities)} forensic entities")
    return result


# ─────────────────────────────────────────────
# Extraction Functions
# ─────────────────────────────────────────────


def _extract_case_ids(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    patterns = [
        (r"(?:P\.?M\.?\s*No\.?\s*[:\-]?\s*)(\S+[\d/\-]+\S*)", "PM_NUMBER"),
        (r"(?:Case\s*No\.?\s*[:\-]?\s*)(\S+[\d/\-]+\S*)", "CASE_NUMBER"),
        (r"(?:M\.?L\.?C\.?\s*No\.?\s*[:\-]?\s*)(\S+)", "MLC_NUMBER"),
        (r"(?:FIR\s*No\.?\s*[:\-]?\s*)(\S+)", "FIR_NUMBER"),
    ]
    for pattern, sub_type in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(ForensicEntity(
                entity_type="CASE_IDENTIFIER",
                raw_value=m.group(1).strip(),
                normalized_value=m.group(1).strip(),
                confidence=0.85,
                source_start=m.start(),
                source_end=m.end(),
            ))
    return entities


def _extract_deceased(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    # Name
    for m in re.finditer(
        r"(?:Name\s*(?:of\s*(?:deceased|dead\s*body))?\s*[:\-]\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|Age)",
        text, re.IGNORECASE,
    ):
        entities.append(ForensicEntity("DECEASED_NAME", m.group(1).strip(),
                                       confidence=0.75, source_start=m.start(), source_end=m.end()))
    # Age
    for m in re.finditer(r"(?:Age\s*[:\-]?\s*)(\d+)\s*(?:years?|yrs?)", text, re.IGNORECASE):
        entities.append(ForensicEntity("DECEASED_AGE", m.group(1).strip(),
                                       confidence=0.8, source_start=m.start(), source_end=m.end()))
    # Gender
    for m in re.finditer(r"(?:Sex|Gender)\s*[:\-]\s*(Male|Female|M|F)\b", text, re.IGNORECASE):
        val = m.group(1).strip().upper()
        normalized = "Male" if val in ("M", "MALE") else "Female"
        entities.append(ForensicEntity("DECEASED_GENDER", m.group(1).strip(), normalized,
                                       confidence=0.9, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_cod(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    for m in re.finditer(
        r"(?:Cause\s*of\s*Death|C\.?O\.?D\.?)\s*[:\-]\s*(.*?)(?:\n\n|\n(?=[A-Z])|\.\s*\n|$)",
        text, re.IGNORECASE | re.DOTALL,
    ):
        val = m.group(1).strip()
        if len(val) > 3:
            entities.append(ForensicEntity("CAUSE_OF_DEATH", val[:500],
                                           confidence=0.8, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_mod(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    for m in re.finditer(
        r"(?:Manner\s*of\s*Death|M\.?O\.?D\.?)\s*[:\-]\s*(.*?)(?:\n|$)",
        text, re.IGNORECASE,
    ):
        entities.append(ForensicEntity("MANNER_OF_DEATH", m.group(1).strip(),
                                       confidence=0.8, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_tod(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    for m in re.finditer(
        r"(?:Time\s*of\s*Death|T\.?O\.?D\.?|PMI)\s*[:\-]\s*(.*?)(?:\n|$)",
        text, re.IGNORECASE,
    ):
        entities.append(ForensicEntity("TIME_OF_DEATH", m.group(1).strip(),
                                       confidence=0.7, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_doctor(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    patterns = [
        r"(?:(?:Performed|Conducted)\s*by\s*[:\-]?\s*(?:Dr\.?\s*)?)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|$)",
        r"(?:Dr\.?\s+)([A-Z][a-zA-Z\s\.]+?)(?:\s*,?\s*(?:MBBS|MD|Pathologist))",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            entities.append(ForensicEntity("EXAMINING_DOCTOR", m.group(1).strip(),
                                           confidence=0.75, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_injury_entities(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    injury_keywords = [
        "lacerat", "contusion", "abrasion", "fracture", "wound",
        "bruise", "ecchymosis", "hematoma", "incised", "puncture",
        "gunshot", "burn", "ligature", "strangulation",
    ]
    pattern = r"(?:Injury\s*(?:No\.?\s*)?\d*\s*[:\-\.]\s*)(.*?)(?=Injury\s*(?:No\.?\s*)?\d+|External|Internal|Opinion|\Z)"
    for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
        desc = m.group(1).strip()
        if len(desc) > 5 and any(kw in desc.lower() for kw in injury_keywords):
            entities.append(ForensicEntity("INJURY", desc[:500],
                                           confidence=0.75, source_start=m.start(), source_end=m.end()))

    # Also catch numbered injury lists
    for m in re.finditer(
        r"(\d+)\.\s*((?:Lacerated|Incised|Contusion|Abrasion|Fracture|Bruise|Wound).*?)(?=\d+\.\s*(?:Lacerated|Incised|Contusion)|$)",
        text, re.IGNORECASE | re.DOTALL,
    ):
        entities.append(ForensicEntity("INJURY", m.group(2).strip()[:500],
                                       confidence=0.7, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_tox_entities(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    substances = [
        "ethanol", "alcohol", "opiate", "opioid", "cannabis", "thc",
        "barbiturate", "benzodiazepine", "amphetamine", "cocaine",
        "organophosph", "cyanide", "arsenic", "mercury", "lead",
        "aluminium phosphide", "oleander", "dhatura", "strychnine",
    ]
    for sub in substances:
        for m in re.finditer(
            rf"({sub}\w*\s*[:\-]?\s*(?:positive|negative|detected|not\s*detected|trace|[\d\.]+\s*\w+))",
            text, re.IGNORECASE,
        ):
            entities.append(ForensicEntity("TOXICOLOGY_FINDING", m.group(1).strip(),
                                           confidence=0.75, source_start=m.start(), source_end=m.end()))
    return entities


def _extract_anatomical(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    terms = {
        "skull": "cranium", "brain": "cerebrum", "heart": "cardiac",
        "liver": "hepatic", "lung": "pulmonary", "kidney": "renal",
        "spleen": "splenic", "stomach": "gastric", "intestine": "intestinal",
        "pancreas": "pancreatic", "trachea": "tracheal", "esophagus": "esophageal",
        "aorta": "aortic", "femur": "femoral", "sternum": "sternal",
        "vertebra": "vertebral", "pelvis": "pelvic", "scapula": "scapular",
        "hyoid": "hyoid", "thyroid": "thyroid",
    }
    for term, adj in terms.items():
        for m in re.finditer(rf"\b{term}\b", text, re.IGNORECASE):
            entities.append(ForensicEntity("ANATOMICAL_REFERENCE", m.group().strip(), term,
                                           confidence=0.9, source_start=m.start(), source_end=m.end()))
    return entities[:50]  # Cap to avoid noise


def _extract_organ_findings(text: str) -> list[ForensicEntity]:
    entities: list[ForensicEntity] = []
    organs = [
        "brain", "heart", "lungs?", "liver", "kidneys?", "spleen",
        "stomach", "intestines?", "pancreas", "uterus", "bladder",
    ]
    for organ in organs:
        for m in re.finditer(
            rf"({organ}\s*[:\-]\s*.*?)(?:\n|$)",
            text, re.IGNORECASE,
        ):
            finding = m.group(1).strip()
            if len(finding) > 10:
                entities.append(ForensicEntity("ORGAN_FINDING", finding[:300],
                                               confidence=0.7, source_start=m.start(), source_end=m.end()))
    return entities


def _enrich_from_structured(
    result: ForensicEntitySet,
    fields: dict[str, Any],
) -> None:
    """Enrich entity set from pre-extracted structured fields."""
    if fields.get("case_number") and not result.case_identifier:
        result.case_identifier.append(
            ForensicEntity("CASE_IDENTIFIER", str(fields["case_number"]), confidence=0.85)
        )
    if fields.get("cause_of_death") and not result.cause_of_death:
        result.cause_of_death.append(
            ForensicEntity("CAUSE_OF_DEATH", str(fields["cause_of_death"]), confidence=0.8)
        )
    if fields.get("manner_of_death") and not result.manner_of_death:
        result.manner_of_death.append(
            ForensicEntity("MANNER_OF_DEATH", str(fields["manner_of_death"]), confidence=0.8)
        )
    injuries = fields.get("injuries", [])
    if isinstance(injuries, list):
        for inj in injuries:
            if isinstance(inj, dict) and inj.get("description"):
                result.injuries.append(
                    ForensicEntity("INJURY", str(inj["description"])[:500], confidence=0.75)
                )
