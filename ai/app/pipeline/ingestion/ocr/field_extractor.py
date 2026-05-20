"""
Atopsy — Structured Forensic Field Extraction.

Extracts structured forensic fields from OCR text using
both regex patterns (for Indian autopsy report formats)
and Gemini AI for complex handwritten content.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    DeceasedInfo,
    ForensicField,
    ForensicFieldExtraction,
    InjuryField,
    ToxicologyField,
)


def extract_fields(
    text: str,
    structured_data: dict[str, Any] | None = None,
    document_type: str = "autopsy_report",
) -> ForensicFieldExtraction:
    """
    Extract structured forensic fields from OCR text.

    Uses regex patterns for common Indian autopsy report formats,
    then enriches with any structured data from Gemini extraction.

    Args:
        text: Full OCR text from the document.
        structured_data: Optional pre-extracted structured data from Gemini.
        document_type: Type of document being processed.

    Returns:
        ForensicFieldExtraction with all extracted fields.
    """
    result = ForensicFieldExtraction()

    if not text and not structured_data:
        return result

    # Phase 1: Regex-based extraction from text
    if text:
        result.case_number = _extract_case_number(text)
        result.deceased = _extract_deceased_info(text)
        result.cause_of_death = _extract_cause_of_death(text)
        result.manner_of_death = _extract_manner_of_death(text)
        result.time_of_death = _extract_time_of_death(text)
        result.date_of_examination = _extract_date_of_examination(text)
        result.examining_doctor = _extract_examining_doctor(text)
        result.injuries = _extract_injuries(text)
        result.toxicology = _extract_toxicology(text)
        result.external_examination = _extract_section(
            text, "external examination"
        )
        result.internal_examination = _extract_section(
            text, "internal examination"
        )
        result.opinion = _extract_section(text, "opinion")

    # Phase 2: Enrich with Gemini structured data
    if structured_data:
        result = _merge_structured_data(result, structured_data)

    # Compute overall confidence
    result.extraction_confidence = _compute_extraction_confidence(result)

    return result


# ─────────────────────────────────────────────
# Regex Extraction Functions
# ─────────────────────────────────────────────


def _extract_case_number(text: str) -> ForensicField | None:
    """Extract case/PM number from common Indian formats."""
    patterns = [
        r"(?:P\.?M\.?\s*(?:No\.?|Number)\s*[:\-]?\s*)(\S+[\d/\-]+\S*)",
        r"(?:Case\s*(?:No\.?|Number)\s*[:\-]?\s*)(\S+[\d/\-]+\S*)",
        r"(?:PM\s*[:\-]\s*)(\d+[\d/\-]*\d*)",
        r"(?:Post[- ]?Mortem\s*(?:No\.?)\s*[:\-]?\s*)(\S+)",
        r"(?:Autopsy\s*(?:No\.?|Number)\s*[:\-]?\s*)(\S+)",
        r"(?:M\.?L\.?C\.?\s*(?:No\.?)\s*[:\-]?\s*)(\S+)",
        r"(?:FIR\s*(?:No\.?)\s*[:\-]?\s*)(\S+)",
    ]
    return _try_patterns(text, patterns, "case_number")


def _extract_deceased_info(text: str) -> DeceasedInfo:
    """Extract deceased person information."""
    info = DeceasedInfo()

    # Name
    name_patterns = [
        r"(?:Name\s*(?:of\s*(?:deceased|dead\s*body))?\s*[:\-]\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|Age)",
        r"(?:Deceased\s*[:\-]\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|Age)",
        r"(?:Body\s*of\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|was)",
    ]
    info.name = _try_patterns(text, name_patterns, "deceased_name")

    # Age
    age_patterns = [
        r"(?:Age\s*[:\-]?\s*)(\d+)\s*(?:years?|yrs?|y\.?o\.?)",
        r"(?:aged?\s*(?:about\s*)?)(\d+)\s*(?:years?|yrs?)",
        r"(\d+)\s*(?:years?|yrs?)\s*(?:old|of\s*age)",
    ]
    age_field = _try_patterns(text, age_patterns, "deceased_age")
    if age_field and age_field.value:
        try:
            age_val = int(age_field.value)
            if 0 <= age_val <= 150:
                age_field.validation_status = "valid"
            else:
                age_field.validation_status = "invalid"
                age_field.validation_message = f"Age {age_val} outside range 0-150"
        except (ValueError, TypeError):
            age_field.validation_status = "invalid"
            age_field.validation_message = "Non-numeric age value"
    info.age = age_field

    # Gender
    gender_patterns = [
        r"(?:Sex\s*[:\-]\s*)(Male|Female|male|female|M|F)",
        r"(?:Gender\s*[:\-]\s*)(Male|Female|male|female|M|F)",
        r"(?:body\s*of\s*(?:a\s*)?)(male|female)",
    ]
    gender_field = _try_patterns(text, gender_patterns, "deceased_gender")
    if gender_field and gender_field.value:
        val = gender_field.value.strip().upper()
        if val in ("M", "MALE"):
            gender_field.value = "Male"
            gender_field.validation_status = "valid"
        elif val in ("F", "FEMALE"):
            gender_field.value = "Female"
            gender_field.validation_status = "valid"
    info.gender = gender_field

    return info


def _extract_cause_of_death(text: str) -> ForensicField | None:
    """Extract cause of death."""
    patterns = [
        r"(?:Cause\s*of\s*Death\s*[:\-]\s*)(.*?)(?:\n\n|\n(?=[A-Z])|$)",
        r"(?:C\.?O\.?D\.?\s*[:\-]\s*)(.*?)(?:\n\n|\n(?=[A-Z])|$)",
        r"(?:cause\s*of\s*death\s*(?:is|was)\s*)(.*?)(?:\.|$)",
    ]
    return _try_patterns(text, patterns, "cause_of_death", multiline=True)


def _extract_manner_of_death(text: str) -> ForensicField | None:
    """Extract manner of death."""
    patterns = [
        r"(?:Manner\s*of\s*Death\s*[:\-]\s*)(.*?)(?:\n|$)",
        r"(?:M\.?O\.?D\.?\s*[:\-]\s*)(.*?)(?:\n|$)",
        r"(?:manner\s*of\s*death\s*(?:is|was)\s*)(Natural|Accidental|Suicide|Homicide|Undetermined)",
    ]
    return _try_patterns(text, patterns, "manner_of_death")


def _extract_time_of_death(text: str) -> ForensicField | None:
    """Extract estimated time of death."""
    patterns = [
        r"(?:Time\s*of\s*Death\s*[:\-]\s*)(.*?)(?:\n|$)",
        r"(?:T\.?O\.?D\.?\s*[:\-]\s*)(.*?)(?:\n|$)",
        r"(?:death\s*(?:occurred|happened)\s*(?:at|on)\s*)(.*?)(?:\n|$)",
        r"(?:PMI\s*[:\-]\s*)(.*?)(?:\n|$)",
    ]
    return _try_patterns(text, patterns, "time_of_death")


def _extract_date_of_examination(text: str) -> ForensicField | None:
    """Extract date of autopsy/examination."""
    patterns = [
        r"(?:Date\s*of\s*(?:Autopsy|Examination|P\.?M\.?)\s*[:\-]\s*)([\d/\-\.]+(?:\s+\d{4})?)",
        r"(?:Date\s*[:\-]\s*)([\d]{1,2}[/\-\.][\d]{1,2}[/\-\.][\d]{2,4})",
        r"(?:Dated?\s*[:\-]\s*)([\d]{1,2}[\s\-/\.]+\w+[\s\-/\.]+\d{4})",
    ]
    return _try_patterns(text, patterns, "date_of_examination")


def _extract_examining_doctor(text: str) -> ForensicField | None:
    """Extract the name of the examining doctor."""
    patterns = [
        r"(?:(?:Performed|Conducted)\s*by\s*[:\-]?\s*(?:Dr\.?\s*)?)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|$)",
        r"(?:Doctor\s*[:\-]\s*(?:Dr\.?\s*)?)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|$)",
        r"(?:Pathologist\s*[:\-]\s*(?:Dr\.?\s*)?)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|$)",
        r"(?:Dr\.?\s+)([A-Z][a-zA-Z\s\.]+?)(?:\s*,?\s*(?:MBBS|MD|Pathologist))",
    ]
    return _try_patterns(text, patterns, "examining_doctor")


def _extract_injuries(text: str) -> list[InjuryField]:
    """Extract individual injury descriptions from the text."""
    injuries: list[InjuryField] = []

    # Common injury description patterns in Indian PM reports
    # Format: "Injury No. X: description over body_region, size X x Y cm"
    injury_patterns = [
        r"(?:Injury\s*(?:No\.?\s*)?(\d+)\s*[:\-\.]\s*)(.*?)(?=Injury\s*(?:No\.?\s*)?\d+|External\s*Examination|Internal|Opinion|\Z)",
        r"(\d+)\.\s*((?:Lacerated|Incised|Contusion|Abrasion|Fracture|Bruise|Wound).*?)(?=\d+\.\s*(?:Lacerated|Incised|Contusion)|$)",
    ]

    for pattern in injury_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            desc = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else match.group(1).strip()
            if len(desc) < 5:
                continue

            injury = InjuryField(
                description=desc[:500],
                injury_type=_classify_injury_type(desc),
                body_region=_extract_body_region(desc),
                dimensions=_extract_dimensions(desc),
                confidence=0.7,
            )
            injuries.append(injury)

    return injuries


def _extract_toxicology(text: str) -> list[ToxicologyField]:
    """Extract toxicology findings."""
    findings: list[ToxicologyField] = []

    # Common patterns for toxicology results
    tox_patterns = [
        r"(?:(?:Ethanol|Alcohol|Blood\s*Alcohol)\s*[:\-]?\s*)((?:Positive|Negative|Not\s*Detected|[\d\.]+\s*(?:mg|ng|ug)[/\s]*(?:dL|mL|L)).*?)(?:\n|$)",
        r"((?:Opiate|Opioid|Cannabis|THC|Barbiturate|Benzodiazepine|Amphetamine|Cocaine|Organophosph\w+|Cyanide)\s*[:\-]?\s*(?:Positive|Negative|Detected|Not\s*Detected|Trace|[\d\.]+\s*\w+))",
    ]

    for pattern in tox_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            full = match.group(0).strip()
            parts = re.split(r"[:\-]\s*", full, maxsplit=1)
            substance = parts[0].strip() if parts else full
            result = parts[1].strip() if len(parts) > 1 else ""

            # Extract concentration
            conc_match = re.search(r"([\d\.]+)\s*((?:mg|ng|ug)/(?:dL|mL|L))", result)
            concentration = conc_match.group(1) if conc_match else ""
            unit = conc_match.group(2) if conc_match else ""

            findings.append(ToxicologyField(
                substance=substance,
                result=result or "detected",
                concentration=concentration,
                unit=unit,
                confidence=0.7,
            ))

    return findings


def _extract_section(
    text: str,
    section_name: str,
) -> ForensicField | None:
    """Extract a named section's content."""
    pattern = rf"(?:{re.escape(section_name)}\s*[:\-]?\s*\n?)(.*?)(?=\n\s*(?:External|Internal|Opinion|Cause|Manner|Toxicology|Histopathology)|\Z)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        content = match.group(1).strip()
        if len(content) > 10:
            return ForensicField(
                field_name=section_name,
                value=content[:2000],
                confidence=0.7,
                source_text=content[:200],
                validation_status="extracted",
            )
    return None


# ─────────────────────────────────────────────
# Merge with Gemini Structured Data
# ─────────────────────────────────────────────


def _merge_structured_data(
    result: ForensicFieldExtraction,
    data: dict[str, Any],
) -> ForensicFieldExtraction:
    """Merge Gemini structured extraction into regex results."""

    def _merge_field(
        existing: ForensicField | None,
        key: str,
        field_name: str,
    ) -> ForensicField | None:
        val = data.get(key)
        if not val:
            return existing
        gemini_field = ForensicField(
            field_name=field_name,
            value=str(val),
            confidence=0.8,
            source_text="gemini_extraction",
            validation_status="extracted",
        )
        # Prefer Gemini if regex didn't find anything
        if existing is None or not existing.value:
            return gemini_field
        # If both found, keep the higher-confidence one
        if gemini_field.confidence > existing.confidence:
            return gemini_field
        return existing

    result.case_number = _merge_field(result.case_number, "case_number", "case_number")
    result.cause_of_death = _merge_field(result.cause_of_death, "cause_of_death", "cause_of_death")
    result.manner_of_death = _merge_field(result.manner_of_death, "manner_of_death", "manner_of_death")
    result.time_of_death = _merge_field(result.time_of_death, "time_of_death", "time_of_death")
    result.date_of_examination = _merge_field(result.date_of_examination, "date_of_examination", "date_of_examination")
    result.examining_doctor = _merge_field(result.examining_doctor, "examining_doctor", "examining_doctor")

    # Deceased info
    if data.get("deceased_name"):
        if result.deceased.name is None or not result.deceased.name.value:
            result.deceased.name = ForensicField(
                field_name="deceased_name",
                value=data["deceased_name"],
                confidence=0.8,
                source_text="gemini_extraction",
            )
    if data.get("deceased_age"):
        if result.deceased.age is None or not result.deceased.age.value:
            result.deceased.age = ForensicField(
                field_name="deceased_age",
                value=str(data["deceased_age"]),
                confidence=0.8,
                source_text="gemini_extraction",
            )
    if data.get("deceased_gender"):
        if result.deceased.gender is None or not result.deceased.gender.value:
            result.deceased.gender = ForensicField(
                field_name="deceased_gender",
                value=str(data["deceased_gender"]),
                confidence=0.8,
                source_text="gemini_extraction",
            )

    # Injuries from Gemini
    gemini_injuries = data.get("injuries", [])
    if isinstance(gemini_injuries, list) and gemini_injuries:
        for inj in gemini_injuries:
            if not isinstance(inj, dict):
                continue
            result.injuries.append(InjuryField(
                injury_type=inj.get("type", ""),
                body_region=inj.get("location", ""),
                description=inj.get("description", ""),
                dimensions=inj.get("dimensions", ""),
                confidence=0.75,
            ))

    # Toxicology from Gemini
    gemini_tox = data.get("toxicology", [])
    if isinstance(gemini_tox, list) and gemini_tox:
        for tox in gemini_tox:
            if not isinstance(tox, dict):
                continue
            result.toxicology.append(ToxicologyField(
                substance=tox.get("substance", ""),
                result=tox.get("result", ""),
                concentration=tox.get("concentration", ""),
                confidence=0.75,
            ))

    result.extraction_engine = "gemini+regex"
    return result


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────


def _try_patterns(
    text: str,
    patterns: list[str],
    field_name: str,
    multiline: bool = False,
) -> ForensicField | None:
    """Try multiple regex patterns and return the first match."""
    flags = re.IGNORECASE | (re.DOTALL if multiline else 0)

    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            value = match.group(1).strip()
            if value and len(value) > 0:
                return ForensicField(
                    field_name=field_name,
                    value=value[:500],
                    confidence=0.7,
                    source_text=match.group(0).strip()[:200],
                    validation_status="extracted",
                )
    return None


def _classify_injury_type(desc: str) -> str:
    """Classify injury type from description text."""
    desc_lower = desc.lower()
    type_keywords = {
        "laceration": ["lacerat", "tear", "cut"],
        "contusion": ["contusion", "bruise", "ecchymosis"],
        "abrasion": ["abrasion", "scrape", "graze", "scratch"],
        "fracture": ["fracture", "broken", "crack"],
        "incised_wound": ["incised", "slash"],
        "puncture_wound": ["puncture", "stab", "pierce"],
        "gunshot_wound": ["gunshot", "bullet", "firearm", "gsw"],
        "burn": ["burn", "scald"],
        "ligature_mark": ["ligature", "strangle", "hanging"],
    }
    for injury_type, keywords in type_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            return injury_type
    return "unclassified"


def _extract_body_region(desc: str) -> str:
    """Extract body region from injury description."""
    desc_lower = desc.lower()
    regions = {
        "head": ["head", "skull", "scalp", "forehead", "temple", "face", "cranium"],
        "neck": ["neck", "throat", "cervical"],
        "thorax": ["chest", "thorax", "rib", "lung", "heart", "sternum"],
        "abdomen": ["abdomen", "stomach", "belly", "liver", "kidney", "spleen"],
        "upper_extremity": ["arm", "hand", "finger", "wrist", "elbow", "shoulder", "forearm"],
        "lower_extremity": ["leg", "foot", "toe", "ankle", "knee", "thigh", "shin"],
        "pelvis": ["pelvis", "hip", "groin"],
        "back": ["back", "spine", "lumbar", "dorsal"],
    }
    for region, keywords in regions.items():
        if any(kw in desc_lower for kw in keywords):
            return region
    return "unspecified"


def _extract_dimensions(desc: str) -> str:
    """Extract measurement dimensions from injury description."""
    patterns = [
        r"(\d+\.?\d*\s*[xX×]\s*\d+\.?\d*(?:\s*[xX×]\s*\d+\.?\d*)?\s*(?:cm|mm|inch))",
        r"(\d+\.?\d*\s*(?:cm|mm)\s*[xX×]\s*\d+\.?\d*\s*(?:cm|mm))",
        r"(\d+\.?\d*\s*(?:cm|mm)(?:\s*(?:in\s*)?(?:diameter|length|width|depth))?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, desc, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _compute_extraction_confidence(
    result: ForensicFieldExtraction,
) -> float:
    """Compute overall confidence of the extraction."""
    fields_found = 0
    total_fields = 10
    total_confidence = 0.0

    for field in [
        result.case_number,
        result.cause_of_death,
        result.manner_of_death,
        result.time_of_death,
        result.date_of_examination,
        result.examining_doctor,
        result.external_examination,
        result.internal_examination,
        result.opinion,
    ]:
        if field and field.value:
            fields_found += 1
            total_confidence += field.confidence

    if result.deceased.name and result.deceased.name.value:
        fields_found += 1
        total_confidence += result.deceased.name.confidence

    if fields_found == 0:
        return 0.0

    completeness = fields_found / total_fields
    avg_confidence = total_confidence / fields_found
    return round(completeness * 0.4 + avg_confidence * 0.6, 4)
