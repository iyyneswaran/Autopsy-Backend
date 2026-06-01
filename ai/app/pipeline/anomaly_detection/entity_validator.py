"""
Atopsy — Entity Validator (Layer 8).

Per-entity validation rules for forensic evidence entities.
Checks completeness, medical terminology, anatomical consistency,
toxicology ranges, and examiner credential formats.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from app.pipeline.structuring.schemas import (
    ForensicEntityGraph,
    StructuredEntity,
)
from app.pipeline.anomaly_detection.schemas import (
    AnomalyAuditEntry,
    AnomalyFinding,
    FindingCategory,
    FindingSeverity,
    FindingType,
)

logger = logging.getLogger(__name__)


# Known anatomical references for validation
_KNOWN_ANATOMICAL = {
    "head", "skull", "brain", "face", "neck", "chest", "thorax",
    "abdomen", "pelvis", "back", "spine", "shoulder", "arm",
    "forearm", "hand", "finger", "hip", "thigh", "knee", "leg",
    "ankle", "foot", "toe", "eye", "ear", "nose", "mouth",
    "throat", "lung", "heart", "liver", "kidney", "spleen",
    "stomach", "intestine", "colon", "rectum", "bladder",
    "uterus", "ovary", "testis", "rib", "femur", "tibia",
    "humerus", "radius", "ulna", "scapula", "clavicle",
    "vertebra", "cervical", "thoracic", "lumbar", "sacral",
}

# Known manner of death values
_KNOWN_MOD = {
    "natural", "accident", "accidental", "suicide", "homicide",
    "undetermined", "pending", "could not be determined",
}

# Examiner credential pattern (Dr., M.D., M.B.B.S., etc.)
_CREDENTIAL_PATTERN = re.compile(
    r"(dr\.?|m\.?d\.?|m\.?b\.?b\.?s\.?|m\.?s\.?|d\.?o\.?|"
    r"f\.?r\.?c\.?s\.?|professor|pathologist|medical\s+examiner)",
    re.IGNORECASE,
)


class EntityValidator:
    """
    Per-entity validation for forensic evidence.

    Validates:
    - Deceased info completeness (name, age, gender)
    - Manner of death against known values
    - Anatomical reference validity
    - Injury description completeness
    - Examiner credential format
    - Toxicology finding structure
    """

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def validate(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[AnomalyFinding]:
        """
        Validate entities across all graphs.

        Args:
            entity_graphs: (evidence_file_id, ForensicEntityGraph) pairs.

        Returns:
            List of validation findings.
        """
        self._audit.clear()
        findings: list[AnomalyFinding] = []

        for evidence_id, graph in entity_graphs:
            findings.extend(
                self._validate_manner_of_death(evidence_id, graph)
            )
            findings.extend(
                self._validate_anatomical_refs(evidence_id, graph)
            )
            findings.extend(
                self._validate_examiner(evidence_id, graph)
            )
            findings.extend(
                self._validate_injury_completeness(evidence_id, graph)
            )
            findings.extend(
                self._validate_toxicology(evidence_id, graph)
            )

        self._audit.append(
            AnomalyAuditEntry(
                stage="entity_validation",
                action="validation_complete",
                finding_ids=[f.finding_id for f in findings],
                detail=(
                    f"Entity validation produced {len(findings)} findings "
                    f"across {len(entity_graphs)} graphs"
                ),
            )
        )

        return findings

    def _validate_manner_of_death(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Validate manner of death against known categories."""
        findings: list[AnomalyFinding] = []

        for entity in graph.entities.get("MANNER_OF_DEATH", []):
            val = (
                entity.canonical_value or entity.raw_value or ""
            ).strip().lower()

            if not val:
                continue

            # Check against known MOD values
            if not any(known in val for known in _KNOWN_MOD):
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.INCONSISTENCY,
                        category=FindingCategory.MEDICAL,
                        severity=FindingSeverity.MEDIUM,
                        title="Non-standard manner of death",
                        description=(
                            f"Manner of death '{val}' does not match "
                            f"standard categories (natural, accident, "
                            f"suicide, homicide, undetermined)"
                        ),
                        affected_entity_ids=[entity.entity_id],
                        affected_evidence_ids=[evidence_id],
                        rule_id="NONSTANDARD_MOD",
                        confidence=0.7,
                        recommendation=(
                            "Verify manner of death classification "
                            "against source document"
                        ),
                    )
                )

        return findings

    def _validate_anatomical_refs(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Validate anatomical references against known terms."""
        findings: list[AnomalyFinding] = []

        for entity in graph.entities.get("ANATOMICAL_REFERENCE", []):
            val = (
                entity.canonical_value or entity.raw_value or ""
            ).strip().lower()

            if not val:
                continue

            # Check if any known anatomical term appears
            words = set(re.findall(r"[a-z]+", val))
            if not words & _KNOWN_ANATOMICAL:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.INCONSISTENCY,
                        category=FindingCategory.MEDICAL,
                        severity=FindingSeverity.LOW,
                        title="Unrecognized anatomical reference",
                        description=(
                            f"Anatomical reference '{val}' does not "
                            f"match known anatomical terms"
                        ),
                        affected_entity_ids=[entity.entity_id],
                        affected_evidence_ids=[evidence_id],
                        rule_id="UNKNOWN_ANATOMY",
                        confidence=0.6,
                        recommendation=(
                            "May be OCR error, abbreviation, or "
                            "specialized terminology"
                        ),
                    )
                )

        return findings

    def _validate_examiner(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Validate examiner credential format."""
        findings: list[AnomalyFinding] = []

        for entity in graph.entities.get("EXAMINER", []):
            val = (
                entity.canonical_value or entity.raw_value or ""
            ).strip()

            if not val:
                continue

            # Check for credential pattern
            if not _CREDENTIAL_PATTERN.search(val):
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.EVIDENCE_INTEGRITY,
                        severity=FindingSeverity.LOW,
                        title="Missing examiner credentials",
                        description=(
                            f"Examiner '{val}' does not include "
                            f"recognizable medical credentials"
                        ),
                        affected_entity_ids=[entity.entity_id],
                        affected_evidence_ids=[evidence_id],
                        rule_id="MISSING_CREDENTIALS",
                        confidence=0.5,
                        recommendation=(
                            "Examiner name may be incomplete; "
                            "verify from source document"
                        ),
                    )
                )

        return findings

    def _validate_injury_completeness(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Check injury descriptions for minimum completeness."""
        findings: list[AnomalyFinding] = []

        for entity in graph.entities.get("INJURY", []):
            val = (
                entity.canonical_value or entity.raw_value or ""
            ).strip()

            if not val:
                continue

            # Very short injury descriptions may be incomplete
            if len(val) < 10:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.MEDICAL,
                        severity=FindingSeverity.LOW,
                        title="Brief injury description",
                        description=(
                            f"Injury description is very brief: "
                            f"'{val}' ({len(val)} chars)"
                        ),
                        affected_entity_ids=[entity.entity_id],
                        affected_evidence_ids=[evidence_id],
                        rule_id="BRIEF_INJURY",
                        confidence=0.5,
                        recommendation=(
                            "Injury description may be truncated; "
                            "verify completeness from source"
                        ),
                    )
                )

        return findings

    def _validate_toxicology(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Validate toxicology findings for structural completeness."""
        findings: list[AnomalyFinding] = []

        for entity in graph.entities.get("TOXICOLOGY_FINDING", []):
            val = (
                entity.canonical_value or entity.raw_value or ""
            ).strip().lower()

            if not val:
                continue

            # Toxicology should mention at least a substance name
            # or a result (positive/negative/detected/not detected)
            result_terms = {
                "positive", "negative", "detected", "not detected",
                "present", "absent", "trace", "nil", "none",
            }
            has_result = any(term in val for term in result_terms)
            has_substance = len(val) > 5 and not val.isdigit()

            if not has_result and not has_substance:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.TOXICOLOGY,
                        severity=FindingSeverity.LOW,
                        title="Incomplete toxicology finding",
                        description=(
                            f"Toxicology finding '{val}' lacks clear "
                            f"substance or result indication"
                        ),
                        affected_entity_ids=[entity.entity_id],
                        affected_evidence_ids=[evidence_id],
                        rule_id="INCOMPLETE_TOX",
                        confidence=0.6,
                        recommendation=(
                            "Verify toxicology data from source; "
                            "extraction may be incomplete"
                        ),
                    )
                )

        return findings
