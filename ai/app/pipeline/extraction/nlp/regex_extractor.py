"""
Atopsy — Rule-Based Forensic NLP Extractor.

Deterministic regex-based extraction for Indian medico-legal documents.
Produces ExtractedSpan objects with character-level source spans for
every match. Supports autopsy reports, post-mortem notes, FIRs,
toxicology reports, and handwriting-heavy scanned records.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger
from app.pipeline.extraction.nlp.base import BaseExtractor
from app.pipeline.extraction.schemas import ExtractedSpan, SourceSpan


class RegexExtractor(BaseExtractor):
    """
    Rule-based forensic NLP extractor using regex patterns.

    Extracts 12+ entity types from Indian medico-legal documents
    with full source-span provenance for every match.
    """

    extractor_id = "regex_forensic_v1"
    supported_entity_types = [
        "CASE_IDENTIFIER", "DECEASED_NAME", "DECEASED_AGE",
        "DECEASED_GENDER", "CAUSE_OF_DEATH", "MANNER_OF_DEATH",
        "TIME_OF_DEATH", "EXAMINING_DOCTOR", "INJURY",
        "TOXICOLOGY_FINDING", "ANATOMICAL_REFERENCE", "ORGAN_FINDING",
    ]

    def extract(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[ExtractedSpan]:
        """Extract all supported entity types from text."""
        if not text or len(text.strip()) < 5:
            return []

        spans: list[ExtractedSpan] = []
        spans.extend(self._extract_case_ids(text))
        spans.extend(self._extract_deceased_name(text))
        spans.extend(self._extract_deceased_age(text))
        spans.extend(self._extract_deceased_gender(text))
        spans.extend(self._extract_cause_of_death(text))
        spans.extend(self._extract_manner_of_death(text))
        spans.extend(self._extract_time_of_death(text))
        spans.extend(self._extract_examining_doctor(text))
        spans.extend(self._extract_injuries(text))
        spans.extend(self._extract_toxicology(text))
        spans.extend(self._extract_anatomical_refs(text))
        spans.extend(self._extract_organ_findings(text))
        for label, category in [('Date of examination', 'EXAMINATION'), ('Last seen alive', 'LAST_SEEN_ALIVE'),
            ('Discovery time', 'DISCOVERY'), ('CCTV event', 'WITNESS_OBSERVATION'), ('Witness observation', 'WITNESS_OBSERVATION'),
            ('Scene observation', 'SCENE_INVESTIGATION'), ('Collection time', 'TOXICOLOGY_COLLECTION')]:
            for match in re.finditer(rf'{label}\s*[:\-]\s*([^\n]+)', text, re.IGNORECASE):
                spans.append(self._make_span('SCENE_REFERENCE', match.group(1).strip(), match, .75,
                    metadata={'sub_type': category, 'event_category': category}))

        logger.debug(
            f"RegexExtractor: extracted {len(spans)} spans from "
            f"{len(text)} chars"
        )
        return spans

    # ─────────────────────────────────────────
    # Case Identifiers
    # ─────────────────────────────────────────

    def _extract_case_ids(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        patterns = [
            (r"(?:P\.?M\.?\s*No\.?\s*[:\-]?\s*)(\S+[\d/\-]+\S*)", "PM_NUMBER", 0.85),
            (r"(?:Case\s*No\.?\s*[:\-]?\s*)(\S+[\d/\-]+\S*)", "CASE_NUMBER", 0.85),
            (r"(?:M\.?L\.?C\.?\s*No\.?\s*[:\-]?\s*)(\S+)", "MLC_NUMBER", 0.80),
            (r"(?:FIR\s*No\.?\s*[:\-]?\s*)(\S+)", "FIR_NUMBER", 0.80),
            (r"(?:Inquest\s*No\.?\s*[:\-]?\s*)(\S+[\d/\-]+\S*)", "INQUEST_NUMBER", 0.75),
        ]
        for pattern, sub_type, conf in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                spans.append(self._make_span(
                    entity_type="CASE_IDENTIFIER",
                    value=m.group(1).strip(),
                    match=m,
                    confidence=conf,
                    metadata={"sub_type": sub_type},
                ))
        return spans

    # ─────────────────────────────────────────
    # Deceased Information
    # ─────────────────────────────────────────

    def _extract_deceased_name(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        patterns = [
            r"(?:Name\s*(?:of\s*(?:deceased|dead\s*body))?\s*[:\-]\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|Age)",
            r"(?:Deceased\s*[:\-]\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|Age|Sex)",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                val = m.group(1).strip()
                if len(val) > 2:
                    spans.append(self._make_span(
                        "DECEASED_NAME", val, m, 0.75,
                        metadata={"sub_type": "DECEASED_NAME"},
                    ))
        return spans

    def _extract_deceased_age(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        for m in re.finditer(
            r"(?:Age\s*[:\-]?\s*)(\d+)\s*(?:years?|yrs?|Y)",
            text, re.IGNORECASE,
        ):
            spans.append(self._make_span(
                "DECEASED_AGE", m.group(1).strip(), m, 0.80,
                metadata={"sub_type": "DECEASED_AGE"},
            ))
        return spans

    def _extract_deceased_gender(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        for m in re.finditer(
            r"(?:Sex|Gender)\s*[:\-]\s*(Male|Female|M|F)\b",
            text, re.IGNORECASE,
        ):
            raw = m.group(1).strip().upper()
            normalized = "Male" if raw in ("M", "MALE") else "Female"
            spans.append(self._make_span(
                "DECEASED_GENDER", normalized, m, 0.90,
                metadata={"sub_type": "DECEASED_GENDER", "raw_value": m.group(1).strip()},
            ))
        return spans

    # ─────────────────────────────────────────
    # Cause / Manner / Time of Death
    # ─────────────────────────────────────────

    def _extract_cause_of_death(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        for m in re.finditer(
            r"(?:Cause\s*of\s*Death|C\.?O\.?D\.?)\s*[:\-]\s*(.*?)(?:\n\n|\n(?=[A-Z])|\.\s*\n|$)",
            text, re.IGNORECASE | re.DOTALL,
        ):
            val = m.group(1).strip()
            if len(val) > 3:
                spans.append(self._make_span(
                    "CAUSE_OF_DEATH", val[:500], m, 0.80,
                ))
        return spans

    def _extract_manner_of_death(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        for m in re.finditer(
            r"(?:Manner\s*of\s*Death|M\.?O\.?D\.?)\s*[:\-]\s*(.*?)(?:\n|$)",
            text, re.IGNORECASE,
        ):
            spans.append(self._make_span(
                "MANNER_OF_DEATH", m.group(1).strip(), m, 0.80,
            ))
        return spans

    def _extract_time_of_death(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        for m in re.finditer(
            r"(?:Time\s*of\s*Death|T\.?O\.?D\.?|PMI|Post[\s\-]?Mortem\s*Interval)\s*[:\-]\s*(.*?)(?:\n|$)",
            text, re.IGNORECASE,
        ):
            spans.append(self._make_span(
                "TIME_OF_DEATH", m.group(1).strip(), m, 0.70,
            ))
        return spans

    # ─────────────────────────────────────────
    # Examining Doctor
    # ─────────────────────────────────────────

    def _extract_examining_doctor(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        patterns = [
            r"(?:(?:Performed|Conducted)\s*by\s*[:\-]?\s*(?:Dr\.?\s*)?)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|$)",
            r"(?:Dr\.?\s+)([A-Z][a-zA-Z\s\.]+?)(?:\s*,?\s*(?:MBBS|MD|Pathologist|Forensic))",
            r"(?:Examining\s*(?:Officer|Doctor)\s*[:\-]\s*)([A-Z][a-zA-Z\s\.]+?)(?:\n|,|$)",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                spans.append(self._make_span(
                    "EXAMINING_DOCTOR", m.group(1).strip(), m, 0.75,
                ))
        return spans

    # ─────────────────────────────────────────
    # Injuries
    # ─────────────────────────────────────────

    def _extract_injuries(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        injury_kw = [
            "lacerat", "contusion", "abrasion", "fracture", "wound",
            "bruise", "ecchymosis", "hematoma", "incised", "puncture",
            "gunshot", "burn", "ligature", "strangulation",
        ]

        # Numbered injury lists: "Injury No. 1:" or "1."
        pattern = (
            r"(?:Injury\s*(?:No\.?\s*)?\d*\s*[:\-\.]\s*)"
            r"([^\n]+)"
        )
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            desc = m.group(1).strip()
            if len(desc) > 5 and any(kw in desc.lower() for kw in injury_kw):
                spans.append(self._make_span(
                    "INJURY", desc[:500], m, 0.75,
                ))

        # Also catch standalone numbered injury lists
        for m in re.finditer(
            r"(\d+)\.\s*((?:Lacerated|Incised|Contusion|Abrasion|Fracture|Bruise|Wound).*?)(?=\d+\.\s*(?:Lacerated|Incised|Contusion)|$)",
            text, re.IGNORECASE | re.DOTALL,
        ):
            spans.append(self._make_span(
                "INJURY", m.group(2).strip()[:500], m, 0.70,
            ))
        return spans

    # ─────────────────────────────────────────
    # Toxicology
    # ─────────────────────────────────────────

    def _extract_toxicology(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        substances = [
            "ethanol", "alcohol", "opiate", "opioid", "cannabis", "thc",
            "barbiturate", "benzodiazepine", "amphetamine", "cocaine",
            "organophosph", "cyanide", "arsenic", "mercury", "lead",
            "aluminium phosphide", "aluminum phosphide", "oleander",
            "dhatura", "strychnine", "morphine",
        ]
        for sub in substances:
            for m in re.finditer(
                rf"({sub}\w*\s*[:\-]?\s*(?:positive|negative|detected|not\s*detected|trace|[\d\.]+\s*(?:[a-zµμ]+(?:\s*/\s*[a-zµμ]+)?|%)))",
                text, re.IGNORECASE,
            ):
                spans.append(self._make_span(
                    "TOXICOLOGY_FINDING", m.group(1).strip(), m, 0.75,
                ))
        return spans

    # ─────────────────────────────────────────
    # Anatomical References
    # ─────────────────────────────────────────

    _ANATOMICAL_TERMS: dict[str, str] = {
        "skull": "cranium", "brain": "cerebrum", "heart": "cardiac",
        "liver": "hepatic", "lung": "pulmonary", "kidney": "renal",
        "spleen": "splenic", "stomach": "gastric", "intestine": "intestinal",
        "pancreas": "pancreatic", "trachea": "tracheal", "esophagus": "esophageal",
        "aorta": "aortic", "femur": "femoral", "sternum": "sternal",
        "vertebra": "vertebral", "pelvis": "pelvic", "scapula": "scapular",
        "hyoid": "hyoid", "thyroid": "thyroid",
    }

    def _extract_anatomical_refs(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
        for term in self._ANATOMICAL_TERMS:
            for m in re.finditer(rf"\b{term}\b", text, re.IGNORECASE):
                spans.append(self._make_span(
                    "ANATOMICAL_REFERENCE", term, m, 0.90,
                ))
        return spans[:50]  # Cap to avoid noise

    # ─────────────────────────────────────────
    # Organ Findings
    # ─────────────────────────────────────────

    def _extract_organ_findings(self, text: str) -> list[ExtractedSpan]:
        spans: list[ExtractedSpan] = []
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
                    spans.append(self._make_span(
                        "ORGAN_FINDING", finding[:300], m, 0.70,
                    ))
        return spans

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _make_span(
        self,
        entity_type: str,
        value: str,
        match: re.Match,  # type: ignore[type-arg]
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractedSpan:
        """Create an ExtractedSpan from a regex match."""
        return ExtractedSpan(
            entity_type=entity_type,
            value=value,
            source_span=SourceSpan(
                start_char=match.start(),
                end_char=match.end(),
                raw_text=match.group(0),
            ),
            confidence=confidence,
            extractor_id=self.extractor_id,
            extraction_method="rule_based",
            metadata=metadata or {},
        )
