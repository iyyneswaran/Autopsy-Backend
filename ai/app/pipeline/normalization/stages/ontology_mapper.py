"""
Atopsy — Ontology Mapping Engine.

Maps forensic entities to standard ontologies:
  - ICD-10 codes for injuries and causes of death
  - Anatomical hierarchy for body regions
  - Drug classification categories
"""

from __future__ import annotations

from typing import Any

from app.core.logger import logger


class OntologyMapping:
    """A single ontology mapping result."""

    __slots__ = (
        "source_term", "ontology_code", "ontology_name",
        "ontology_system", "confidence", "is_exact_match",
    )

    def __init__(
        self,
        source_term: str,
        ontology_code: str,
        ontology_name: str,
        ontology_system: str = "ICD-10",
        confidence: float = 0.8,
        is_exact_match: bool = False,
    ) -> None:
        self.source_term = source_term
        self.ontology_code = ontology_code
        self.ontology_name = ontology_name
        self.ontology_system = ontology_system
        self.confidence = confidence
        self.is_exact_match = is_exact_match

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_term": self.source_term,
            "ontology_code": self.ontology_code,
            "ontology_name": self.ontology_name,
            "ontology_system": self.ontology_system,
            "confidence": self.confidence,
            "is_exact_match": self.is_exact_match,
        }


# ─────────────────────────────────────────────
# ICD-10 Mappings — Injuries
# ─────────────────────────────────────────────

ICD10_INJURIES: dict[str, tuple[str, str]] = {
    # Head injuries
    "head injury": ("S09.90", "Unspecified injury of head"),
    "craniocerebral injury": ("S06.9", "Intracranial injury, unspecified"),
    "skull fracture": ("S02.9", "Fracture of skull, unspecified"),
    "cranial fracture": ("S02.9", "Fracture of skull, unspecified"),
    "subdural hematoma": ("S06.5", "Traumatic subdural hemorrhage"),
    "epidural hematoma": ("S06.4", "Epidural hemorrhage"),
    "subarachnoid hemorrhage": ("S06.6", "Traumatic subarachnoid hemorrhage"),
    "intracerebral hemorrhage": ("S06.3", "Focal traumatic brain injury"),
    "brain contusion": ("S06.3", "Focal traumatic brain injury"),
    "concussion": ("S06.0", "Concussion"),
    "traumatic brain injury": ("S06.9", "Intracranial injury, unspecified"),
    "facial fracture": ("S02.9", "Fracture of facial bones"),
    "mandible fracture": ("S02.6", "Fracture of mandible"),
    "nasal fracture": ("S02.2", "Fracture of nasal bones"),
    # Neck
    "neck injury": ("S19.9", "Unspecified injury of neck"),
    "cervical spine fracture": ("S12.9", "Fracture of cervical vertebra"),
    "hyoid fracture": ("S12.8", "Fracture of other cervical vertebra"),
    "strangulation": ("T71.1", "Asphyxiation due to strangulation"),
    "ligature strangulation": ("T71.1", "Asphyxiation due to strangulation"),
    "hanging": ("T71.0", "Asphyxiation due to hanging"),
    # Thorax
    "rib fracture": ("S22.3", "Fracture of rib"),
    "rib fractures": ("S22.4", "Multiple fractures of ribs"),
    "sternal fracture": ("S22.2", "Fracture of sternum"),
    "hemothorax": ("S27.1", "Traumatic hemothorax"),
    "pneumothorax": ("S27.0", "Traumatic pneumothorax"),
    "cardiac contusion": ("S26.0", "Injury of heart"),
    "lung contusion": ("S27.3", "Contusion of lung"),
    "flail chest": ("S22.5", "Flail chest"),
    # Abdomen
    "liver laceration": ("S36.1", "Injury of liver"),
    "splenic rupture": ("S36.0", "Injury of spleen"),
    "kidney injury": ("S37.0", "Injury of kidney"),
    "intestinal perforation": ("S36.4", "Injury of small intestine"),
    "mesenteric tear": ("S35.2", "Injury of mesenteric vessels"),
    # Extremities
    "femur fracture": ("S72.9", "Fracture of femur, unspecified"),
    "tibia fracture": ("S82.2", "Fracture of shaft of tibia"),
    "humerus fracture": ("S42.3", "Fracture of shaft of humerus"),
    "radius fracture": ("S52.5", "Fracture of lower end of radius"),
    "pelvic fracture": ("S32.8", "Fracture of pelvis"),
    "vertebral fracture": ("S32.0", "Fracture of lumbar vertebra"),
    # Soft tissue
    "laceration": ("T14.1", "Open wound of unspecified body region"),
    "contusion": ("T14.0", "Superficial injury of unspecified body region"),
    "abrasion": ("T14.0", "Superficial injury of unspecified body region"),
    "incised wound": ("T14.1", "Open wound of unspecified body region"),
    "puncture wound": ("T14.1", "Open wound of unspecified body region"),
    "gunshot wound": ("T14.1", "Open wound by firearm"),
    "stab wound": ("T14.1", "Open wound by sharp object"),
    "burn": ("T30.0", "Burn of unspecified body region"),
    "thermal burn": ("T30.0", "Burn of unspecified body region"),
    "chemical burn": ("T30.4", "Corrosion of unspecified body region"),
    "electrical burn": ("T75.4", "Effects of electric current"),
    "periorbital ecchymosis": ("S00.1", "Contusion of eyelid"),
    "defense wound": ("T14.1", "Defense wound of upper extremity"),
    "ligature mark": ("T71", "Asphyxiation due to ligature"),
}

# ─────────────────────────────────────────────
# ICD-10 Mappings — Causes of Death
# ─────────────────────────────────────────────

ICD10_CAUSES_OF_DEATH: dict[str, tuple[str, str]] = {
    "myocardial infarction": ("I21.9", "Acute myocardial infarction, unspecified"),
    "coronary artery disease": ("I25.1", "Atherosclerotic heart disease"),
    "pulmonary embolism": ("I26.9", "Pulmonary embolism without acute cor pulmonale"),
    "cerebrovascular accident": ("I64", "Stroke, not specified"),
    "hypertension": ("I10", "Essential hypertension"),
    "pneumonia": ("J18.9", "Pneumonia, unspecified organism"),
    "septicemia": ("A41.9", "Sepsis, unspecified organism"),
    "asphyxia": ("T71.9", "Asphyxiation, unspecified"),
    "drowning": ("T75.1", "Drowning and nonfatal submersion"),
    "poisoning": ("T65.9", "Toxic effect of unspecified substance"),
    "organophosphate poisoning": ("T60.0", "Toxic effect of organophosphorus insecticides"),
    "cyanide poisoning": ("T65.0", "Toxic effect of cyanides"),
    "aluminum phosphide poisoning": ("T57.1", "Toxic effect of phosphorus"),
    "alcohol poisoning": ("T51.0", "Toxic effect of ethanol"),
    "opiate overdose": ("T40.2", "Poisoning by other opioids"),
    "blunt force trauma": ("T14.9", "Injury, unspecified"),
    "sharp force trauma": ("T14.1", "Open wound, unspecified"),
    "hemorrhagic shock": ("R57.1", "Hypovolemic shock"),
    "multiple injuries": ("T07", "Multiple injuries, unspecified"),
    "electrocution": ("T75.4", "Effects of electric current"),
    "burns": ("T30", "Burns, unspecified"),
    "heat stroke": ("T67.0", "Heatstroke and sunstroke"),
    "hypothermia": ("T68", "Hypothermia"),
    "starvation": ("T73.0", "Starvation"),
    "natural disease": ("R99", "Other ill-defined causes of mortality"),
}

# ─────────────────────────────────────────────
# Anatomical Hierarchy
# ─────────────────────────────────────────────

ANATOMICAL_HIERARCHY: dict[str, dict[str, str]] = {
    "head": {"body_system": "musculoskeletal", "region": "head", "parent": "axial"},
    "skull": {"body_system": "musculoskeletal", "region": "head", "parent": "head"},
    "brain": {"body_system": "nervous", "region": "head", "parent": "cranial_cavity"},
    "face": {"body_system": "musculoskeletal", "region": "head", "parent": "head"},
    "neck": {"body_system": "musculoskeletal", "region": "neck", "parent": "axial"},
    "trachea": {"body_system": "respiratory", "region": "neck", "parent": "airway"},
    "larynx": {"body_system": "respiratory", "region": "neck", "parent": "airway"},
    "hyoid": {"body_system": "musculoskeletal", "region": "neck", "parent": "neck"},
    "thorax": {"body_system": "musculoskeletal", "region": "thorax", "parent": "axial"},
    "heart": {"body_system": "cardiovascular", "region": "thorax", "parent": "mediastinum"},
    "lungs": {"body_system": "respiratory", "region": "thorax", "parent": "thoracic_cavity"},
    "sternum": {"body_system": "musculoskeletal", "region": "thorax", "parent": "thorax"},
    "ribs": {"body_system": "musculoskeletal", "region": "thorax", "parent": "thorax"},
    "abdomen": {"body_system": "musculoskeletal", "region": "abdomen", "parent": "axial"},
    "liver": {"body_system": "digestive", "region": "abdomen", "parent": "abdominal_cavity"},
    "spleen": {"body_system": "lymphatic", "region": "abdomen", "parent": "abdominal_cavity"},
    "kidney": {"body_system": "urinary", "region": "abdomen", "parent": "retroperitoneal"},
    "stomach": {"body_system": "digestive", "region": "abdomen", "parent": "abdominal_cavity"},
    "intestine": {"body_system": "digestive", "region": "abdomen", "parent": "abdominal_cavity"},
    "pancreas": {"body_system": "digestive", "region": "abdomen", "parent": "retroperitoneal"},
    "aorta": {"body_system": "cardiovascular", "region": "thorax", "parent": "great_vessels"},
    "pelvis": {"body_system": "musculoskeletal", "region": "pelvis", "parent": "axial"},
    "uterus": {"body_system": "reproductive", "region": "pelvis", "parent": "pelvic_cavity"},
    "femur": {"body_system": "musculoskeletal", "region": "lower_extremity", "parent": "thigh"},
    "tibia": {"body_system": "musculoskeletal", "region": "lower_extremity", "parent": "leg"},
    "humerus": {"body_system": "musculoskeletal", "region": "upper_extremity", "parent": "arm"},
    "spine": {"body_system": "musculoskeletal", "region": "back", "parent": "axial"},
}

# ─────────────────────────────────────────────
# Drug Classification
# ─────────────────────────────────────────────

DRUG_CLASSIFICATION: dict[str, dict[str, str]] = {
    "ethanol": {"class": "depressant", "schedule": "unscheduled", "category": "alcohol"},
    "morphine": {"class": "opioid", "schedule": "Schedule II", "category": "analgesic"},
    "diacetylmorphine": {"class": "opioid", "schedule": "Schedule I", "category": "narcotic"},
    "cocaine": {"class": "stimulant", "schedule": "Schedule II", "category": "local_anesthetic"},
    "methamphetamine": {"class": "stimulant", "schedule": "Schedule II", "category": "amphetamine"},
    "cannabis": {"class": "cannabinoid", "schedule": "Schedule I", "category": "hallucinogen"},
    "diazepam": {"class": "benzodiazepine", "schedule": "Schedule IV", "category": "anxiolytic"},
    "alprazolam": {"class": "benzodiazepine", "schedule": "Schedule IV", "category": "anxiolytic"},
    "phenobarbital": {"class": "barbiturate", "schedule": "Schedule IV", "category": "anticonvulsant"},
    "fentanyl": {"class": "opioid", "schedule": "Schedule II", "category": "analgesic"},
    "organophosphate": {"class": "cholinesterase_inhibitor", "schedule": "pesticide", "category": "insecticide"},
    "aluminum_phosphide": {"class": "fumigant", "schedule": "pesticide", "category": "rodenticide"},
    "cyanide": {"class": "metabolic_poison", "schedule": "restricted", "category": "industrial_chemical"},
    "strychnine": {"class": "convulsant", "schedule": "restricted", "category": "rodenticide"},
    "paraquat": {"class": "herbicide", "schedule": "pesticide", "category": "herbicide"},
}


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────


def map_to_ontology(
    entities: list[dict[str, Any]],
) -> list[OntologyMapping]:
    """
    Map forensic entities to ontology codes.

    Args:
        entities: List of entity dicts with 'entity_type' and 'normalized_value'.

    Returns:
        List of OntologyMapping results.
    """
    mappings: list[OntologyMapping] = []

    for entity in entities:
        entity_type = entity.get("entity_type", "")
        value = entity.get("normalized_value", entity.get("raw_value", ""))

        if not value:
            continue

        value_lower = value.lower().strip()

        # Injury → ICD-10
        if entity_type in ("INJURY", "CAUSE_OF_DEATH"):
            icd = _find_icd10(value_lower, entity_type)
            if icd:
                mappings.append(icd)

        # Anatomical → hierarchy
        if entity_type == "ANATOMICAL_REFERENCE":
            anat = _find_anatomical(value_lower)
            if anat:
                mappings.append(anat)

        # Toxicology → drug classification
        if entity_type == "TOXICOLOGY_FINDING":
            drug = _find_drug_class(value_lower)
            if drug:
                mappings.append(drug)

    return mappings


def map_injury_to_icd10(injury_desc: str) -> OntologyMapping | None:
    """Map a single injury description to ICD-10."""
    return _find_icd10(injury_desc.lower().strip(), "INJURY")


def map_cod_to_icd10(cause: str) -> OntologyMapping | None:
    """Map a cause of death to ICD-10."""
    return _find_icd10(cause.lower().strip(), "CAUSE_OF_DEATH")


def get_anatomical_hierarchy(term: str) -> dict[str, str] | None:
    """Get the anatomical hierarchy for a body term."""
    return ANATOMICAL_HIERARCHY.get(term.lower().strip())


# ─────────────────────────────────────────────
# Internal Lookup
# ─────────────────────────────────────────────


def _find_icd10(value: str, entity_type: str) -> OntologyMapping | None:
    """Find ICD-10 mapping for an injury or cause of death."""
    lookup = (
        ICD10_CAUSES_OF_DEATH if entity_type == "CAUSE_OF_DEATH"
        else ICD10_INJURIES
    )

    # Exact match
    if value in lookup:
        code, name = lookup[value]
        return OntologyMapping(
            source_term=value,
            ontology_code=code,
            ontology_name=name,
            ontology_system="ICD-10",
            confidence=0.95,
            is_exact_match=True,
        )

    # Partial match (check if value contains any key)
    best_match: tuple[str, str, str, int] | None = None
    for key, (code, name) in lookup.items():
        if key in value or value in key:
            match_len = len(key)
            if best_match is None or match_len > best_match[3]:
                best_match = (key, code, name, match_len)

    if best_match:
        return OntologyMapping(
            source_term=value,
            ontology_code=best_match[1],
            ontology_name=best_match[2],
            ontology_system="ICD-10",
            confidence=0.7,
            is_exact_match=False,
        )

    return None


def _find_anatomical(value: str) -> OntologyMapping | None:
    """Find anatomical hierarchy mapping."""
    if value in ANATOMICAL_HIERARCHY:
        hier = ANATOMICAL_HIERARCHY[value]
        return OntologyMapping(
            source_term=value,
            ontology_code=f"ANAT:{hier['body_system']}.{hier['region']}",
            ontology_name=f"{hier['body_system']} > {hier['region']} > {value}",
            ontology_system="ANATOMICAL_HIERARCHY",
            confidence=0.9,
            is_exact_match=True,
        )
    return None


def _find_drug_class(value: str) -> OntologyMapping | None:
    """Find drug classification mapping."""
    if value in DRUG_CLASSIFICATION:
        info = DRUG_CLASSIFICATION[value]
        return OntologyMapping(
            source_term=value,
            ontology_code=f"DRUG:{info['class']}.{info['category']}",
            ontology_name=f"{info['class']} ({info['category']}) - {info['schedule']}",
            ontology_system="DRUG_CLASSIFICATION",
            confidence=0.85,
            is_exact_match=True,
        )
    return None
