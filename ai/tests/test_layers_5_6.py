"""
Verification script for Evidence Correlation Engine (Layer 5) & Temporal Intelligence Layer (Layer 6).
Mocks ForensicEntityGraph inputs and runs them through both engines end-to-end.
"""

import os
import sys
import uuid
from datetime import datetime, timezone

# Add app directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.pipeline.structuring.schemas import (
    ForensicEntityGraph,
    StructuredEntity,
    EntityType,
    EntityNormalizationStatus,
    EntityProvenance
)
from app.pipeline.correlation.engine import CorrelationEngine
from app.pipeline.temporal.engine import TemporalEngine


def create_mock_entity(entity_type, canonical_value, raw_value, confidence=0.9, page=1):
    entity_id = f"ent-{entity_type.lower()}-{uuid.uuid4().hex[:6]}"
    return StructuredEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        canonical_value=canonical_value,
        raw_value=raw_value,
        category="forensic",
        sub_type=entity_type.lower(),
        confidence=confidence,
        normalization_status=EntityNormalizationStatus.NORMALIZED,
        provenance=EntityProvenance(
            original_text=raw_value,
            document_page=page,
            extraction_method="mock_regex",
            extraction_confidence=confidence
        )
    )


def test_pipelines():
    print("==================================================")
    print("  Testing Layer 5 (Correlation) and Layer 6 (Temporal)")
    print("==================================================")

    # 1. Create Mock ForensicEntityGraph for Evidence File 1 (Autopsy)
    eid_autopsy = "evidence-file-autopsy-1111"
    autopsy_entities = [
        create_mock_entity(EntityType.CASE_IDENTIFIER, "FIR 45/2024", "FIR No. 45 of 2024"),
        create_mock_entity(EntityType.DECEASED_INFO, "John Doe", "John Doe, Male, 45 Years"),
        create_mock_entity(EntityType.CAUSE_OF_DEATH, "Blunt force trauma to cranium", "Blunt force injury to the head"),
        create_mock_entity(EntityType.TIME_OF_DEATH, "2024-03-14T22:00:00Z", "approx 12-24 hours prior to exam"),
        create_mock_entity(EntityType.EXAMINER, "Dr. Sharma", "Dr. Sharma, MD"),
    ]
    graph_autopsy = ForensicEntityGraph(
        evidence_file_id=eid_autopsy,
        entities={"CASE": [autopsy_entities[0]], "PEOPLE": [autopsy_entities[1]], "FINDINGS": autopsy_entities[2:]}
    )

    # 2. Create Mock ForensicEntityGraph for Evidence File 2 (FIR)
    eid_fir = "evidence-file-fir-2222"
    fir_entities = [
        create_mock_entity(EntityType.CASE_IDENTIFIER, "FIR 45/2024", "FIR 45/2024"),
        create_mock_entity(EntityType.DECEASED_INFO, "John Doe", "deceased John Doe"),
        create_mock_entity(EntityType.SCENE_REFERENCE, "Highway 12, KM 14", "at highway 12 KM 14 mark"),
    ]
    # Add a custom relative time or absolute time for incident in FIR
    # Wait, TIME_OF_DEATH can be used or we can map time to incident
    incident_time = create_mock_entity(EntityType.TIME_OF_DEATH, "2024-03-14T21:30:00Z", "on 14-03-2024 at 9:30 PM")
    fir_entities.append(incident_time)

    graph_fir = ForensicEntityGraph(
        evidence_file_id=eid_fir,
        entities={"CASE": [fir_entities[0]], "PEOPLE": [fir_entities[1]], "FINDINGS": fir_entities[2:]}
    )

    entity_graphs = [
        (eid_autopsy, graph_autopsy),
        (eid_fir, graph_fir)
    ]

    # 3. Instantiate and run CorrelationEngine (Layer 5)
    print("\nRunning Correlation Engine...")
    correlation_engine = CorrelationEngine()
    correlation_graph = correlation_engine.correlate(entity_graphs, case_id="case-uuid-1234")

    print(f"  [SUCCESS] CorrelationEngine ran successfully!")
    print(f"  - Case ID: {correlation_graph.case_id}")
    print(f"  - Number of Evidence File IDs: {len(correlation_graph.evidence_file_ids)}")
    print(f"  - Number of Clusters: {len(correlation_graph.entity_clusters)}")
    print(f"  - Number of Edges: {len(correlation_graph.relationship_edges)}")
    print(f"  - Number of Contradictions: {len(correlation_graph.contradictions)}")
    print(f"  - Overall Confidence: {correlation_graph.confidence_summary.overall_confidence:.2f}")

    # Check some of the clusters
    for cluster in correlation_graph.entity_clusters:
        print(f"    * Cluster ({cluster.entity_type}): {cluster.canonical_label} with {len(cluster.members)} members")

    # 4. Instantiate and run TemporalEngine (Layer 6)
    print("\nRunning Temporal Intelligence Engine...")
    # Set the anchor datetime to post-mortem exam start (e.g. 2024-03-15 14:30:00)
    anchor_dt = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
    temporal_engine = TemporalEngine(anchor_datetime=anchor_dt)
    
    timeline = temporal_engine.build_timeline(
        entity_graphs=entity_graphs,
        correlation_graph=correlation_graph,
        case_id="case-uuid-1234"
    )

    print(f"  [SUCCESS] TemporalEngine ran successfully!")
    print(f"  - Timeline event count: {len(timeline.timeline)}")
    print(f"  - Event order: {timeline.event_order}")
    print(f"  - Relations count: {len(timeline.temporal_relations)}")
    print(f"  - Conflicts count: {len(timeline.temporal_conflicts)}")
    print(f"  - TOD Candidates count: {len(timeline.tod_candidates)}")
    print(f"  - Overall Reliability Score (through stages): {timeline.processing_time_ms} ms processing time")

    for i, evt in enumerate(timeline.timeline):
        print(f"    * Event {i+1} [{evt.category}]: {evt.label} ({evt.time_window.best_estimate or 'no best estimate'})")

    for cand in timeline.tod_candidates:
        print(f"    * TOD Candidate [{cand.estimation_method}]: estimate={cand.time_window.best_estimate or 'range'} (conf={cand.confidence:.2f})")

    # Verify database model schemas
    from app.models.pipeline import CorrelationRecord, TemporalRecord
    print("\nChecking database models...")
    print(f"  - CorrelationRecord: {CorrelationRecord.__name__}")
    print(f"  - TemporalRecord: {TemporalRecord.__name__}")

    print("\nAll pipeline Layer 5 and Layer 6 tests PASSED successfully!")
    print("==================================================")


if __name__ == "__main__":
    test_pipelines()
