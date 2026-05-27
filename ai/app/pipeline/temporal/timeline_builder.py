"""
Atopsy — Timeline Builder (Layer 6).

Constructs temporal events from correlated evidence and
builds the ordered forensic timeline.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.pipeline.correlation.schemas import (
    CorrelationGraph,
    EntityCluster,
)
from app.pipeline.structuring.schemas import ForensicEntityGraph, StructuredEntity
from app.pipeline.temporal.schemas import (
    EventCategory,
    ResolutionMethod,
    TemporalAuditEntry,
    TemporalEvent,
    TemporalEventProvenance,
    TemporalExpression,
    TemporalPrecision,
    TimeWindow,
)
from app.pipeline.temporal.temporal_parser import TemporalParser

# ─────────────────────────────────────────────
# Entity type → event category mapping
# ─────────────────────────────────────────────

_ENTITY_TO_CATEGORY: dict[str, EventCategory] = {
    "TIME_OF_DEATH": EventCategory.DEATH,
    "CAUSE_OF_DEATH": EventCategory.DEATH,
    "MANNER_OF_DEATH": EventCategory.DEATH,
    "INJURY": EventCategory.INJURY_INFLICTION,
    "TOXICOLOGY_FINDING": EventCategory.TOXICOLOGY_COLLECTION,
    "EXAMINER": EventCategory.EXAMINATION,
    "SCENE_REFERENCE": EventCategory.SCENE_INVESTIGATION,
    "CASE_IDENTIFIER": EventCategory.REPORT_FILED,
}


def _entity_type_str(entity: StructuredEntity) -> str:
    return (
        entity.entity_type.value
        if hasattr(entity.entity_type, "value")
        else str(entity.entity_type)
    )


class TimelineBuilder:
    """
    Constructs temporal events from entity graphs and correlation data.

    Extracts temporal information from:
    - TIME_OF_DEATH entities
    - Temporal expressions in entity values
    - Document-level timestamps
    - Correlation-linked events across documents
    """

    def __init__(self) -> None:
        self._parser = TemporalParser()
        self._audit: list[TemporalAuditEntry] = []

    @property
    def audit_entries(self) -> list[TemporalAuditEntry]:
        return list(self._audit)

    def build_events(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        correlation_graph: CorrelationGraph | None = None,
    ) -> list[TemporalEvent]:
        """
        Build temporal events from entity graphs.

        Args:
            entity_graphs: List of (evidence_file_id, graph) tuples.
            correlation_graph: Optional correlation data for
                               cross-document event linking.

        Returns:
            List of TemporalEvent objects.
        """
        self._audit.clear()
        events: list[TemporalEvent] = []

        # 1. Extract events from entity graphs
        for efile_id, graph in entity_graphs:
            graph_events = self._extract_from_graph(efile_id, graph)
            events.extend(graph_events)

        # 2. Extract document-level temporal events
        for efile_id, graph in entity_graphs:
            doc_event = self._extract_document_event(efile_id, graph)
            if doc_event:
                events.append(doc_event)

        # 3. Link events via correlation clusters
        if correlation_graph:
            linked = self._link_via_correlation(events, correlation_graph)
            events.extend(linked)

        # Deduplicate by content
        events = self._deduplicate(events)

        self._audit.append(
            TemporalAuditEntry(
                stage="timeline_building",
                action="events_built",
                event_ids=[e.event_id for e in events],
                detail=f"Built {len(events)} temporal events from {len(entity_graphs)} evidence files",
            )
        )

        return events

    def _extract_from_graph(
        self,
        efile_id: str,
        graph: ForensicEntityGraph,
    ) -> list[TemporalEvent]:
        """Extract temporal events from an entity graph."""
        events: list[TemporalEvent] = []

        for etype_key, entity_list in graph.entities.items():
            category = _ENTITY_TO_CATEGORY.get(etype_key)
            if category is None:
                continue

            for entity in entity_list:
                # Parse temporal expressions from entity value
                temporal_exprs = self._parser.parse_text(
                    entity.canonical_value or entity.raw_value,
                    evidence_file_id=efile_id,
                    entity_id=entity.entity_id,
                    page=entity.provenance.document_page,
                )

                # Also parse from raw value if different
                if (
                    entity.raw_value
                    and entity.raw_value != entity.canonical_value
                ):
                    raw_exprs = self._parser.parse_text(
                        entity.raw_value,
                        evidence_file_id=efile_id,
                        entity_id=entity.entity_id,
                        page=entity.provenance.document_page,
                    )
                    # Merge without duplicates
                    seen = {e.raw_text for e in temporal_exprs}
                    for re_ in raw_exprs:
                        if re_.raw_text not in seen:
                            temporal_exprs.append(re_)

                # Build time window from expressions
                time_window = self._best_window(temporal_exprs)

                # Determine if this is observed or inferred
                etype = _entity_type_str(entity)
                is_observed = etype == "TIME_OF_DEATH" or len(temporal_exprs) > 0

                event = TemporalEvent(
                    event_id=str(uuid.uuid4()),
                    label=self._make_label(etype, entity.canonical_value),
                    description=entity.canonical_value or entity.raw_value,
                    category=category,
                    time_window=time_window,
                    temporal_expressions=temporal_exprs,
                    is_observed=is_observed,
                    is_anchor=(etype == "EXAMINER"),
                    provenance=TemporalEventProvenance(
                        evidence_file_id=efile_id,
                        entity_id=entity.entity_id,
                        entity_type=etype,
                        extraction_method=entity.provenance.extraction_method,
                        raw_text=entity.raw_value,
                        page=entity.provenance.document_page,
                    ),
                    confidence=entity.confidence,
                    resolution_method=(
                        ResolutionMethod.DIRECT_PARSE
                        if temporal_exprs
                        else ResolutionMethod.CONTEXT_INFERENCE
                    ),
                )
                events.append(event)

        return events

    def _extract_document_event(
        self,
        efile_id: str,
        graph: ForensicEntityGraph,
    ) -> TemporalEvent | None:
        """
        Create a document-creation event from graph metadata.

        Uses the processing timestamp as a proxy for document date.
        """
        if not graph.processed_at:
            return None

        return TemporalEvent(
            event_id=str(uuid.uuid4()),
            label="Document Processing",
            description=f"Evidence file {efile_id[:8]}... processed",
            category=EventCategory.DOCUMENT_CREATION,
            time_window=TimeWindow(
                earliest=graph.processed_at,
                latest=graph.processed_at,
                best_estimate=graph.processed_at,
                confidence=0.95,
                precision=TemporalPrecision.EXACT,
            ),
            is_observed=True,
            is_anchor=True,
            provenance=TemporalEventProvenance(
                evidence_file_id=efile_id,
            ),
            confidence=0.95,
            resolution_method=ResolutionMethod.DOCUMENT_DATE,
        )

    def _link_via_correlation(
        self,
        existing_events: list[TemporalEvent],
        corr_graph: CorrelationGraph,
    ) -> list[TemporalEvent]:
        """Link temporal events across documents using correlation clusters."""
        # This is a placeholder for cross-document temporal linking
        # In production, this would merge events from the same cluster
        # into unified timeline entries
        return []

    def _best_window(
        self, exprs: list[TemporalExpression]
    ) -> TimeWindow:
        """Select the best time window from a list of expressions."""
        if not exprs:
            return TimeWindow()

        # Prefer the highest-confidence expression
        best = max(exprs, key=lambda e: e.confidence)
        return best.time_window

    def _make_label(self, entity_type: str, value: str) -> str:
        """Create a human-readable event label."""
        labels: dict[str, str] = {
            "TIME_OF_DEATH": "Estimated Time of Death",
            "CAUSE_OF_DEATH": "Cause of Death Determined",
            "MANNER_OF_DEATH": "Manner of Death Classified",
            "INJURY": "Injury Event",
            "TOXICOLOGY_FINDING": "Toxicology Finding",
            "EXAMINER": "Examination Conducted",
            "SCENE_REFERENCE": "Scene Investigation",
            "CASE_IDENTIFIER": "Case Registered",
        }
        label = labels.get(entity_type, entity_type)
        if value and len(value) <= 60:
            label = f"{label}: {value}"
        return label

    def _deduplicate(
        self, events: list[TemporalEvent]
    ) -> list[TemporalEvent]:
        """Deduplicate events with same label and evidence source."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[TemporalEvent] = []
        for evt in events:
            key = (
                evt.provenance.evidence_file_id,
                evt.provenance.entity_type,
                evt.description[:50] if evt.description else "",
            )
            if key not in seen:
                seen.add(key)
                unique.append(evt)
        return unique
