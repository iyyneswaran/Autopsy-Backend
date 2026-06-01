"""
Atopsy — Anomaly Rules (Layer 8).

Rule-based anomaly detection for missing data, impossible values,
suspicious OCR artifacts, duplicate evidence with divergent values,
and unreasonable numeric values.
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
    AnomalyFinding,
    AnomalyProvenanceEntry,
    FindingCategory,
    FindingSeverity,
    FindingType,
    AnomalyAuditEntry,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Required entity types for a complete forensic report
# ─────────────────────────────────────────────

_REQUIRED_ENTITY_TYPES: dict[str, FindingSeverity] = {
    "CAUSE_OF_DEATH": FindingSeverity.HIGH,
    "MANNER_OF_DEATH": FindingSeverity.HIGH,
    "DECEASED_INFO": FindingSeverity.HIGH,
    "CASE_IDENTIFIER": FindingSeverity.MEDIUM,
    "INJURY": FindingSeverity.MEDIUM,
    "EXAMINER": FindingSeverity.LOW,
}

# OCR artifact patterns
_OCR_ARTIFACT_PATTERNS = [
    re.compile(r"[^\x00-\x7F]{3,}"),  # 3+ non-ASCII chars in a row
    re.compile(r"[|!1l]{5,}"),  # Common OCR confusion chars
    re.compile(r"\b[A-Z]{10,}\b"),  # Very long uppercase word
    re.compile(r"[\x00-\x1F]"),  # Control characters
    re.compile(r"(.)\1{4,}"),  # 5+ repeated characters
]

# Unreasonable numeric ranges
_NUMERIC_RULES: list[
    tuple[str, str, re.Pattern[str], float, float, str]
] = [
    (
        "DECEASED_INFO",
        "age",
        re.compile(r"(\d+)\s*(years?|yrs?|y\.?o\.?)", re.IGNORECASE),
        0.0,
        150.0,
        "Unreasonable age value",
    ),
    (
        "DECEASED_INFO",
        "weight",
        re.compile(r"(\d+(?:\.\d+)?)\s*(kg|kilograms?)", re.IGNORECASE),
        0.5,
        500.0,
        "Unreasonable weight value",
    ),
    (
        "TOXICOLOGY_FINDING",
        "concentration",
        re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|ng|ug)/(ml|dl|l)", re.IGNORECASE),
        0.0,
        100000.0,
        "Suspicious toxicology concentration",
    ),
]


class AnomalyRules:
    """
    Rule-based anomaly detection for forensic evidence.

    Detects:
    - Missing required entity types
    - Suspicious OCR/extraction artifacts
    - Unreasonable numeric values
    - Low-confidence entities
    - Empty or placeholder values
    """

    # Confidence threshold below which entities are flagged
    LOW_CONFIDENCE_THRESHOLD = 0.25

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def detect(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[AnomalyFinding]:
        """
        Detect anomalies across entity graphs.

        Args:
            entity_graphs: (evidence_file_id, ForensicEntityGraph) pairs.

        Returns:
            List of anomaly findings.
        """
        self._audit.clear()
        findings: list[AnomalyFinding] = []

        for evidence_id, graph in entity_graphs:
            # Missing required fields
            findings.extend(
                self._check_missing_fields(evidence_id, graph)
            )

            # OCR artifacts
            findings.extend(
                self._check_ocr_artifacts(evidence_id, graph)
            )

            # Unreasonable numeric values
            findings.extend(
                self._check_numeric_values(evidence_id, graph)
            )

            # Low-confidence entities
            findings.extend(
                self._check_low_confidence(evidence_id, graph)
            )

            # Empty/placeholder values
            findings.extend(
                self._check_empty_values(evidence_id, graph)
            )

        self._audit.append(
            AnomalyAuditEntry(
                stage="anomaly_detection",
                action="detection_complete",
                finding_ids=[f.finding_id for f in findings],
                detail=(
                    f"Detected {len(findings)} anomalies across "
                    f"{len(entity_graphs)} graphs"
                ),
            )
        )

        return findings

    def _check_missing_fields(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Check for missing required entity types."""
        findings: list[AnomalyFinding] = []
        present_types = set(graph.entities.keys())

        for req_type, severity in _REQUIRED_ENTITY_TYPES.items():
            if req_type not in present_types or not graph.entities[req_type]:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.MISSING_DATA,
                        category=FindingCategory.EVIDENCE_INTEGRITY,
                        severity=severity,
                        title=f"Missing {req_type}",
                        description=(
                            f"Required entity type '{req_type}' is absent "
                            f"from evidence file {evidence_id}"
                        ),
                        affected_evidence_ids=[evidence_id],
                        rule_id=f"MISSING_{req_type}",
                        confidence=0.9,
                        recommendation=(
                            f"Review source document for {req_type} "
                            f"information; may indicate OCR failure or "
                            f"incomplete document"
                        ),
                    )
                )

        return findings

    def _check_ocr_artifacts(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Check for suspicious OCR artifacts in entity values."""
        findings: list[AnomalyFinding] = []

        for entity_type_key, entities in graph.entities.items():
            for entity in entities:
                text = entity.raw_value or entity.canonical_value or ""
                for pattern in _OCR_ARTIFACT_PATTERNS:
                    if pattern.search(text):
                        findings.append(
                            AnomalyFinding(
                                finding_id=str(uuid.uuid4()),
                                finding_type=FindingType.OCR_ARTIFACT,
                                category=FindingCategory.OCR_QUALITY,
                                severity=FindingSeverity.LOW,
                                title=(
                                    f"Suspicious OCR artifact in "
                                    f"{entity_type_key}"
                                ),
                                description=(
                                    f"Entity value contains suspicious "
                                    f"patterns that may indicate OCR "
                                    f"errors: '{text[:100]}'"
                                ),
                                affected_entity_ids=[entity.entity_id],
                                affected_evidence_ids=[evidence_id],
                                rule_id="OCR_ARTIFACT",
                                confidence=0.7,
                                recommendation=(
                                    "Re-examine source document; "
                                    "value may need manual correction"
                                ),
                            )
                        )
                        break  # One finding per entity

        return findings

    def _check_numeric_values(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Check for unreasonable numeric values."""
        findings: list[AnomalyFinding] = []

        for (
            entity_type,
            field,
            pattern,
            min_val,
            max_val,
            msg,
        ) in _NUMERIC_RULES:
            for entity in graph.entities.get(entity_type, []):
                text = (
                    entity.canonical_value
                    or entity.raw_value
                    or ""
                )
                match = pattern.search(text)
                if match:
                    try:
                        value = float(match.group(1))
                        if value < min_val or value > max_val:
                            findings.append(
                                AnomalyFinding(
                                    finding_id=str(uuid.uuid4()),
                                    finding_type=FindingType.ANOMALY,
                                    category=FindingCategory.MEDICAL,
                                    severity=FindingSeverity.MEDIUM,
                                    title=msg,
                                    description=(
                                        f"{msg}: {value} "
                                        f"(expected {min_val}-{max_val})"
                                    ),
                                    affected_entity_ids=[entity.entity_id],
                                    affected_evidence_ids=[evidence_id],
                                    rule_id=f"NUMERIC_{entity_type}_{field.upper()}",
                                    confidence=0.85,
                                    recommendation=(
                                        "Verify value against source "
                                        "document; may be OCR error or "
                                        "unit mismatch"
                                    ),
                                )
                            )
                    except (ValueError, TypeError):
                        continue

        return findings

    def _check_low_confidence(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Flag entities with very low extraction confidence."""
        findings: list[AnomalyFinding] = []

        for entity_type_key, entities in graph.entities.items():
            for entity in entities:
                if entity.confidence < self.LOW_CONFIDENCE_THRESHOLD:
                    findings.append(
                        AnomalyFinding(
                            finding_id=str(uuid.uuid4()),
                            finding_type=FindingType.ANOMALY,
                            category=FindingCategory.OCR_QUALITY,
                            severity=FindingSeverity.LOW,
                            title=(
                                f"Low confidence entity: "
                                f"{entity_type_key}"
                            ),
                            description=(
                                f"Entity '{entity.canonical_value or entity.raw_value}' "
                                f"has confidence {entity.confidence:.2f} "
                                f"(threshold: {self.LOW_CONFIDENCE_THRESHOLD})"
                            ),
                            affected_entity_ids=[entity.entity_id],
                            affected_evidence_ids=[evidence_id],
                            rule_id="LOW_CONFIDENCE",
                            confidence=entity.confidence,
                            recommendation=(
                                "Low-confidence extraction; verify "
                                "against source document"
                            ),
                        )
                    )

        return findings

    def _check_empty_values(
        self,
        evidence_id: str,
        graph: ForensicEntityGraph,
    ) -> list[AnomalyFinding]:
        """Flag entities with empty or placeholder values."""
        findings: list[AnomalyFinding] = []
        placeholder_patterns = re.compile(
            r"^(n/?a|unknown|not\s+available|not\s+specified|"
            r"pending|tbd|to\s+be\s+determined|\?\?+|---+)$",
            re.IGNORECASE,
        )

        for entity_type_key, entities in graph.entities.items():
            for entity in entities:
                val = (
                    entity.canonical_value or entity.raw_value or ""
                ).strip()
                if not val or placeholder_patterns.match(val):
                    findings.append(
                        AnomalyFinding(
                            finding_id=str(uuid.uuid4()),
                            finding_type=FindingType.MISSING_DATA,
                            category=FindingCategory.EVIDENCE_INTEGRITY,
                            severity=FindingSeverity.LOW,
                            title=(
                                f"Empty/placeholder value: "
                                f"{entity_type_key}"
                            ),
                            description=(
                                f"Entity has empty or placeholder "
                                f"value: '{val or '(empty)'}'"
                            ),
                            affected_entity_ids=[entity.entity_id],
                            affected_evidence_ids=[evidence_id],
                            rule_id="EMPTY_PLACEHOLDER",
                            confidence=0.9,
                            recommendation=(
                                "Data may be missing from source or "
                                "not extractable"
                            ),
                        )
                    )

        return findings
