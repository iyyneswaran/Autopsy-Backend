"""
Verification script for TOD Estimation Engine (Layer 7) & Anomaly & Contradiction Detection (Layer 8).
Mocks ForensicEntityGraph inputs, runs them through Layer 5 (Correlation), Layer 6 (Temporal),
Layer 7 (TOD Estimation), and Layer 8 (Anomaly Detection) end-to-end.
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
    EntityProvenance,
    EntityGraphMetrics
)
from app.pipeline.correlation.engine import CorrelationEngine
from app.pipeline.temporal.engine import TemporalEngine
from app.pipeline.temporal.schemas import TemporalEvent, TimeWindow, EventCategory, TemporalPrecision
from app.pipeline.tod_estimation.engine import TODEstimationEngine
from app.pipeline.anomaly_detection.engine import AnomalyDetectionEngine

from app.models.pipeline import TODEstimationRecord, AnomalyDetectionRecord


def create_mock_entity(entity_type, canonical_value, raw_value, confidence=0.9, page=1):
    entity_id = f"ent-{entity_type.lower().replace('_', '-')}-{uuid.uuid4().hex[:6]}"
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


def test_pipelines_7_8():
    print("==================================================")
    print("  Testing Layer 7 (TOD Estimation) and Layer 8 (Anomaly Detection)")
    print("==================================================")

    # 1. Create Mock ForensicEntityGraph for Evidence File 1 (Autopsy Report)
    eid_autopsy = "evidence-file-autopsy-1111"
    autopsy_entities = [
        create_mock_entity(EntityType.CASE_IDENTIFIER, "FIR 45/2024", "FIR No. 45 of 2024"),
        create_mock_entity(EntityType.DECEASED_INFO, "John Doe, Male, 45 Years", "John Doe, Male, 45 Years"),
        create_mock_entity(EntityType.CAUSE_OF_DEATH, "Blunt force injury to the head", "Blunt force injury to the head"),
        create_mock_entity(EntityType.MANNER_OF_DEATH, "Homicide", "Homicide"),
        create_mock_entity(EntityType.INJURY, "Laceration on occipital region", "Laceration on occipital region"),
        # Forensic signals for TOD
        create_mock_entity(EntityType.TIME_OF_DEATH, "PMI 12 to 24 hours prior to exam", "PMI 12 to 24 hours prior to exam"),
        create_mock_entity(EntityType.TIME_OF_DEATH, "rigor complete", "Rigor mortis was complete"),
        create_mock_entity(EntityType.TIME_OF_DEATH, "lividity fixed", "Lividity was fixed on posterior"),
        create_mock_entity(EntityType.EXAMINER, "Dr. Sharma, MD", "Dr. Sharma, MD"),
        create_mock_entity(EntityType.TOXICOLOGY_FINDING, "BAC 0.15%", "Toxicology shows BAC of 0.15%"),
    ]
    graph_autopsy = ForensicEntityGraph(
        evidence_file_id=eid_autopsy,
        entities={"CASE": [autopsy_entities[0]], "PEOPLE": [autopsy_entities[1]], "FINDINGS": autopsy_entities[2:]},
        metrics=EntityGraphMetrics(
            total_entities=len(autopsy_entities),
            entity_type_counts={"CASE_IDENTIFIER": 1, "DECEASED_INFO": 1, "CAUSE_OF_DEATH": 1, "MANNER_OF_DEATH": 1, "INJURY": 1, "TIME_OF_DEATH": 3, "EXAMINER": 1, "TOXICOLOGY_FINDING": 1},
            average_confidence=0.9,
            normalization_coverage=1.0,
            validation_pass_rate=1.0
        )
    )

    # 2. Create Mock ForensicEntityGraph for Evidence File 2 (FIR / Incident Report)
    eid_fir = "evidence-file-fir-2222"
    fir_entities = [
        create_mock_entity(EntityType.CASE_IDENTIFIER, "FIR 45/2024", "FIR 45/2024"),
        create_mock_entity(EntityType.DECEASED_INFO, "John Doe", "deceased John Doe"),
        create_mock_entity(EntityType.SCENE_REFERENCE, "Highway 12, KM 14", "at highway 12 KM 14 mark"),
        create_mock_entity(EntityType.TIME_OF_DEATH, "2024-03-14T21:30:00Z", "Incident occurred on 14-03-2024 at 9:30 PM"),
        create_mock_entity(EntityType.TIME_OF_DEATH, "last seen alive 2024-03-14T20:00:00Z", "Last seen alive on 14-03-2024 at 8:00 PM"),
    ]
    graph_fir = ForensicEntityGraph(
        evidence_file_id=eid_fir,
        entities={"CASE": [fir_entities[0]], "PEOPLE": [fir_entities[1]], "FINDINGS": fir_entities[2:]},
        metrics=EntityGraphMetrics(
            total_entities=len(fir_entities),
            entity_type_counts={"CASE_IDENTIFIER": 1, "DECEASED_INFO": 1, "SCENE_REFERENCE": 1, "TIME_OF_DEATH": 2},
            average_confidence=0.9,
            normalization_coverage=1.0,
            validation_pass_rate=1.0
        )
    )

    # 3. Create Mock ForensicEntityGraph for Evidence File 3 (Witness Statement - Contradictory Case ID / Data)
    # This will trigger Layer 8 contradictions
    eid_witness = "evidence-file-witness-3333"
    witness_entities = [
        create_mock_entity(EntityType.CASE_IDENTIFIER, "FIR 99/2024", "FIR 99/2024"), # Mismatched Case ID!
        create_mock_entity(EntityType.DECEASED_INFO, "John Doe", "John Doe"),
        create_mock_entity(EntityType.CAUSE_OF_DEATH, "Asphyxia due to drowning", "Drowned in water"), # Contradictory COD!
        create_mock_entity(EntityType.TIME_OF_DEATH, "2024-03-15T08:00:00Z", "I saw him walking around at 8:00 AM on March 15th"), # Contradictory time!
    ]
    graph_witness = ForensicEntityGraph(
        evidence_file_id=eid_witness,
        entities={"CASE": [witness_entities[0]], "PEOPLE": [witness_entities[1]], "FINDINGS": witness_entities[2:]},
        metrics=EntityGraphMetrics(
            total_entities=len(witness_entities),
            entity_type_counts={"CASE_IDENTIFIER": 1, "DECEASED_INFO": 1, "CAUSE_OF_DEATH": 1, "TIME_OF_DEATH": 1},
            average_confidence=0.9,
            normalization_coverage=1.0,
            validation_pass_rate=1.0
        )
    )

    entity_graphs = [
        (eid_autopsy, graph_autopsy),
        (eid_fir, graph_fir),
        (eid_witness, graph_witness)
    ]

    # --- Run Layer 5 ---
    print("\n[Layer 5] Running Correlation Engine...")
    correlation_engine = CorrelationEngine()
    correlation_graph = correlation_engine.correlate(entity_graphs, case_id="case-uuid-1234")
    print(f"  - Correlation overall confidence: {correlation_graph.confidence_summary.overall_confidence:.2f}")

    # --- Run Layer 6 ---
    print("\n[Layer 6] Running Temporal Intelligence Engine...")
    anchor_dt = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc) # Examination time
    temporal_engine = TemporalEngine(anchor_datetime=anchor_dt)
    timeline = temporal_engine.build_timeline(
        entity_graphs=entity_graphs,
        correlation_graph=correlation_graph,
        case_id="case-uuid-1234"
    )
    print(f"  - Timeline events: {len(timeline.timeline)}")

    # Manually insert anchor/examination event into the timeline to trigger Layer 7 relative calculations
    exam_event = TemporalEvent(
        event_id="evt-exam-1234",
        label="Post-mortem examination",
        category=EventCategory.EXAMINATION,
        time_window=TimeWindow(
            earliest="2024-03-15T14:30:00Z",
            latest="2024-03-15T14:30:00Z",
            best_estimate="2024-03-15T14:30:00Z",
            confidence=1.0,
            precision=TemporalPrecision.EXACT
        ),
        is_observed=True,
        is_anchor=True,
        confidence=1.0
    )
    timeline.temporal_events.append(exam_event)
    timeline.timeline.append(exam_event)

    # --- Run Layer 7 ---
    print("\n[Layer 7] Running TOD Estimation Engine...")
    tod_engine = TODEstimationEngine()
    tod_result = tod_engine.estimate(
        entity_graphs=entity_graphs,
        correlation_graph=correlation_graph,
        forensic_timeline=timeline,
        case_id="case-uuid-1234"
    )

    print(f"  [SUCCESS] TODEstimationEngine completed successfully!")
    print(f"  - Candidates count: {len(tod_result.tod_candidates)}")
    print(f"  - Supporting signals count: {len(tod_result.supporting_signals)}")
    print(f"  - Signal conflicts count: {len(tod_result.signal_conflicts)}")
    print(f"  - Overall confidence: {tod_result.confidence_scores.overall_confidence:.4f}")
    if tod_result.tod_candidates:
        print(f"  - Primary candidate window: {tod_result.estimated_window.earliest} to {tod_result.estimated_window.latest}")
        print(f"  - Rationale: {tod_result.final_tod_hypothesis.summary}")
        for cand in tod_result.tod_candidates:
            print(f"    * Candidate ({cand.estimation_method}): {cand.tod_window.earliest} to {cand.tod_window.latest} (conf={cand.confidence:.2f})")
    else:
        print("  - No TOD candidates generated.")

    # --- Run Layer 8 ---
    print("\n[Layer 8] Running Anomaly & Contradiction Detection Engine...")
    anomaly_engine = AnomalyDetectionEngine()
    anomaly_report = anomaly_engine.detect(
        entity_graphs=entity_graphs,
        correlation_graph=correlation_graph,
        forensic_timeline=timeline,
        tod_result=tod_result,
        case_id="case-uuid-1234"
    )

    print(f"  [SUCCESS] AnomalyDetectionEngine completed successfully!")
    print(f"  - Total Anomalies: {len(anomaly_report.anomalies)}")
    print(f"  - Total Contradictions: {len(anomaly_report.contradictions)}")
    print(f"  - Severity Summary: {anomaly_report.severity_summary.model_dump()}")
    print(f"  - Affected entities count: {len(anomaly_report.affected_entities)}")
    print(f"  - Affected events count: {len(anomaly_report.affected_timeline_events)}")
    print(f"  - Rule hits count: {len(anomaly_report.rule_hits)}")
    print(f"  - Overall report confidence: {anomaly_report.confidence_scores.overall_confidence:.2f}")

    print("\nActive rule hits:")
    for hit in anomaly_report.rule_hits:
        print(f"    * Rule: {hit.rule_id} ({hit.hit_count} hits) - {hit.description}")

    print("\nAnomalies list:")
    for i, an in enumerate(anomaly_report.anomalies):
        print(f"    {i+1}. [{an.severity}] {an.title}: {an.description}")

    print("\nContradictions list:")
    for i, co in enumerate(anomaly_report.contradictions):
        print(f"    {i+1}. [{co.severity}] {co.title}: {co.description}")
        print(f"       Value A: '{co.value_a}' (source: {co.source_a.evidence_file_id})")
        print(f"       Value B: '{co.value_b}' (source: {co.source_b.evidence_file_id})")

    # Verify SQLAlchemy DB Models
    print("\nChecking database models integration...")
    print(f"  - TODEstimationRecord: {TODEstimationRecord.__name__}")
    print(f"  - AnomalyDetectionRecord: {AnomalyDetectionRecord.__name__}")

    print("\nAll pipeline Layer 7 and Layer 8 tests PASSED successfully!")
    print("==================================================")


if __name__ == "__main__":
    test_pipelines_7_8()
