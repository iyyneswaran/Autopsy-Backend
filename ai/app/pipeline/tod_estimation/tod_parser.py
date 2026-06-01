"""
Atopsy — TOD Parser (Layer 7).

Extracts TOD-relevant forensic signals from ForensicEntityGraph
entities. Identifies PMI statements, body cooling references,
rigor/lividity descriptions, witness timelines, toxicology
findings, and other forensic indicators.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from app.pipeline.structuring.schemas import (
    EntityType,
    ForensicEntityGraph,
    StructuredEntity,
)
from app.pipeline.temporal.schemas import ForensicTimeline, TODCandidate
from app.pipeline.tod_estimation.schemas import (
    ForensicSignal,
    SignalConfidenceLevel,
    SignalType,
    TODAuditEntry,
    TODProvenanceEntry,
    TODWindow,
    TODPrecision,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Entity-type to signal-type mapping
# ─────────────────────────────────────────────

_ENTITY_SIGNAL_MAP: dict[str, SignalType] = {
    "TIME_OF_DEATH": SignalType.DIRECT_EXAMINER,
    "CAUSE_OF_DEATH": SignalType.MEDICAL_EVIDENCE,
    "MANNER_OF_DEATH": SignalType.MEDICAL_EVIDENCE,
    "TOXICOLOGY_FINDING": SignalType.TOXICOLOGY,
    "INJURY": SignalType.MEDICAL_EVIDENCE,
    "SCENE_REFERENCE": SignalType.SCENE_EVIDENCE,
    "ORGAN_FINDING": SignalType.MEDICAL_EVIDENCE,
    "EXTERNAL_EXAMINATION": SignalType.MEDICAL_EVIDENCE,
    "INTERNAL_EXAMINATION": SignalType.MEDICAL_EVIDENCE,
    "DECEASED_INFO": SignalType.WITNESS_TIMELINE,
}


# ─────────────────────────────────────────────
# Keyword-based signal reclassification
# ─────────────────────────────────────────────

_PMI_KEYWORDS = re.compile(
    r"post[\s\-]?mortem\s+interval|pmi|hours?\s+(before|prior|after)\s+"
    r"(examination|autopsy|post[\s\-]?mortem)",
    re.IGNORECASE,
)

_COOLING_KEYWORDS = re.compile(
    r"body\s+temperature|cooling|algor\s+mortis|rectal\s+temp|"
    r"body\s+heat|cold\s+to\s+touch|warm\s+to\s+touch",
    re.IGNORECASE,
)

_RIGOR_KEYWORDS = re.compile(
    r"rigor\s+mortis|rigidity|stiffness|rigor\s+(present|absent|"
    r"partial|complete|fully\s+developed|passing\s+off|resolved)",
    re.IGNORECASE,
)

_LIVIDITY_KEYWORDS = re.compile(
    r"lividity|livor\s+mortis|hypostasis|post[\s\-]?mortem\s+staining|"
    r"lividity\s+(fixed|unfixed|present|absent)",
    re.IGNORECASE,
)

_DECOMPOSITION_KEYWORDS = re.compile(
    r"decompos|putrefaction|bloating|marbling|skin\s+slip|"
    r"greenish\s+discoloration|maggot|insect\s+activity",
    re.IGNORECASE,
)

_LAST_SEEN_KEYWORDS = re.compile(
    r"last\s+seen\s+alive|seen\s+alive|alive\s+at|"
    r"last\s+(known|confirmed)\s+alive",
    re.IGNORECASE,
)

_DISCOVERY_KEYWORDS = re.compile(
    r"discovered|found\s+(dead|body|deceased)|body\s+found|"
    r"discovery\s+of\s+body",
    re.IGNORECASE,
)

_ENVIRONMENTAL_KEYWORDS = re.compile(
    r"ambient\s+temp|room\s+temp|outdoor\s+temp|weather|"
    r"temperature\s+of\s+(room|environment|surroundings)|"
    r"air\s+conditioning|cold\s+storage|refrigerat",
    re.IGNORECASE,
)


class TODParser:
    """
    Extracts forensic signals relevant to TOD estimation
    from structured entity graphs and timeline data.
    """

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def extract_signals(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        forensic_timeline: ForensicTimeline | None = None,
    ) -> list[ForensicSignal]:
        """
        Extract all TOD-relevant forensic signals.

        Args:
            entity_graphs: List of (evidence_file_id, ForensicEntityGraph).
            forensic_timeline: Optional Layer 6 timeline with existing
                               TOD candidates and events.

        Returns:
            List of ForensicSignal objects.
        """
        self._audit.clear()
        signals: list[ForensicSignal] = []

        # 1. Extract from entity graphs
        for evidence_id, graph in entity_graphs:
            graph_signals = self._extract_from_graph(evidence_id, graph)
            signals.extend(graph_signals)

        # 2. Extract from existing timeline TOD candidates
        if forensic_timeline and forensic_timeline.tod_candidates:
            timeline_signals = self._extract_from_timeline(
                forensic_timeline
            )
            signals.extend(timeline_signals)

        self._audit.append(
            TODAuditEntry(
                stage="signal_extraction",
                action="extraction_complete",
                signal_ids=[s.signal_id for s in signals],
                detail=(
                    f"Extracted {len(signals)} signals from "
                    f"{len(entity_graphs)} entity graphs"
                ),
            )
        )

        logger.info(
            "TOD parser extracted %d signals from %d graphs",
            len(signals),
            len(entity_graphs),
        )

        return signals

    def _extract_from_graph(
        self,
        evidence_file_id: str,
        graph: ForensicEntityGraph,
    ) -> list[ForensicSignal]:
        """Extract signals from a single entity graph."""
        signals: list[ForensicSignal] = []

        for entity_type_key, entities in graph.entities.items():
            for entity in entities:
                signal = self._entity_to_signal(
                    evidence_file_id, entity, entity_type_key
                )
                if signal:
                    signals.append(signal)

        return signals

    def _entity_to_signal(
        self,
        evidence_file_id: str,
        entity: StructuredEntity,
        entity_type_key: str,
    ) -> ForensicSignal | None:
        """Convert a single entity to a forensic signal if relevant."""
        text = (entity.canonical_value or entity.raw_value or "").strip()
        if not text:
            return None

        # Determine signal type via keyword reclassification
        signal_type = self._classify_signal_type(text, entity_type_key)

        # Only keep signals that are TOD-relevant
        if signal_type is None:
            return None

        confidence_level = (
            SignalConfidenceLevel.OBSERVED
            if entity.normalization_status.value in ("NORMALIZED", "VALIDATED")
            else SignalConfidenceLevel.INFERRED
        )

        return ForensicSignal(
            signal_id=str(uuid.uuid4()),
            signal_type=signal_type,
            confidence_level=confidence_level,
            raw_text=entity.raw_value or text,
            normalized_value=text,
            confidence=entity.confidence,
            weight=0.0,  # Set later by weighter
            evidence_file_id=evidence_file_id,
            entity_id=entity.entity_id,
            entity_type=entity_type_key,
            provenance=TODProvenanceEntry(
                evidence_file_id=evidence_file_id,
                entity_id=entity.entity_id,
                entity_type=entity_type_key,
                raw_text=entity.raw_value or "",
                canonical_value=text,
                confidence=entity.confidence,
                extraction_method=(
                    entity.provenance.extraction_method
                    if entity.provenance
                    else ""
                ),
                page=(
                    entity.provenance.document_page
                    if entity.provenance
                    else None
                ),
            ),
        )

    def _classify_signal_type(
        self, text: str, entity_type_key: str
    ) -> SignalType | None:
        """
        Classify signal type using keyword analysis.

        Keyword-based reclassification overrides the default
        entity-type mapping when a more specific signal type
        is detected.
        """
        # Keyword-based reclassification (highest priority)
        if _PMI_KEYWORDS.search(text):
            return SignalType.PMI_STATEMENT
        if _COOLING_KEYWORDS.search(text):
            return SignalType.BODY_COOLING
        if _RIGOR_KEYWORDS.search(text):
            return SignalType.RIGOR_MORTIS
        if _LIVIDITY_KEYWORDS.search(text):
            return SignalType.LIVIDITY
        if _DECOMPOSITION_KEYWORDS.search(text):
            return SignalType.DECOMPOSITION
        if _LAST_SEEN_KEYWORDS.search(text):
            return SignalType.LAST_SEEN_ALIVE
        if _DISCOVERY_KEYWORDS.search(text):
            return SignalType.DISCOVERY_TIME
        if _ENVIRONMENTAL_KEYWORDS.search(text):
            return SignalType.ENVIRONMENTAL

        # Entity-type default mapping
        return _ENTITY_SIGNAL_MAP.get(entity_type_key)

    def _extract_from_timeline(
        self,
        timeline: ForensicTimeline,
    ) -> list[ForensicSignal]:
        """Extract signals from Layer 6 TOD candidates."""
        signals: list[ForensicSignal] = []

        for candidate in timeline.tod_candidates:
            tw = candidate.time_window
            signal = ForensicSignal(
                signal_id=str(uuid.uuid4()),
                signal_type=self._method_to_signal_type(
                    candidate.estimation_method
                ),
                confidence_level=SignalConfidenceLevel.ESTIMATED,
                raw_text=candidate.rationale or "",
                normalized_value=candidate.estimation_method,
                tod_window=TODWindow(
                    earliest=tw.earliest,
                    latest=tw.latest,
                    best_estimate=tw.best_estimate,
                    confidence=tw.confidence,
                    precision=TODPrecision(tw.precision.value)
                    if tw.precision
                    else TODPrecision.UNKNOWN,
                ),
                confidence=candidate.confidence,
                evidence_file_id=(
                    candidate.source_evidence_ids[0]
                    if candidate.source_evidence_ids
                    else ""
                ),
                entity_id=candidate.candidate_id,
                entity_type="TOD_CANDIDATE_L6",
                metadata={"layer6_candidate_id": candidate.candidate_id},
            )
            signals.append(signal)

        if signals:
            self._audit.append(
                TODAuditEntry(
                    stage="signal_extraction",
                    action="timeline_candidates_imported",
                    signal_ids=[s.signal_id for s in signals],
                    detail=(
                        f"Imported {len(signals)} candidates from "
                        f"Layer 6 timeline"
                    ),
                )
            )

        return signals

    @staticmethod
    def _method_to_signal_type(method: str) -> SignalType:
        """Map Layer 6 estimation method to signal type."""
        method_lower = (method or "").lower()
        if "pmi" in method_lower:
            return SignalType.PMI_STATEMENT
        if "last_seen" in method_lower:
            return SignalType.LAST_SEEN_ALIVE
        if "direct" in method_lower or "examiner" in method_lower:
            return SignalType.DIRECT_EXAMINER
        return SignalType.MEDICAL_EVIDENCE
