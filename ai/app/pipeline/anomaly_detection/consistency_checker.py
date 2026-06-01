"""
Atopsy — Consistency Checker (Layer 8).

Cross-entity consistency validation across correlation
clusters, entity graphs, and TOD estimates.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.pipeline.correlation.schemas import CorrelationGraph
from app.pipeline.structuring.schemas import ForensicEntityGraph
from app.pipeline.tod_estimation.schemas import TODEstimationResult
from app.pipeline.anomaly_detection.schemas import (
    AnomalyAuditEntry,
    AnomalyFinding,
    FindingCategory,
    FindingSeverity,
    FindingType,
)

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """
    Cross-entity consistency validation.

    Validates:
    - Entity cluster consistency
    - TOD estimate consistency with supporting evidence
    - Evidence group coherence
    - Confidence distribution anomalies
    """

    def __init__(self) -> None:
        self._audit: list[AnomalyAuditEntry] = []

    @property
    def audit_entries(self) -> list[AnomalyAuditEntry]:
        return list(self._audit)

    def check(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
        correlation_graph: CorrelationGraph | None = None,
        tod_result: TODEstimationResult | None = None,
    ) -> list[AnomalyFinding]:
        """
        Run consistency checks.

        Args:
            entity_graphs: Entity graphs from Layer 4.
            correlation_graph: Correlation graph from Layer 5.
            tod_result: TOD estimation result from Layer 7.

        Returns:
            List of inconsistency findings.
        """
        self._audit.clear()
        findings: list[AnomalyFinding] = []

        # 1. Cross-document entity count consistency
        findings.extend(
            self._check_entity_count_consistency(entity_graphs)
        )

        # 2. Cluster confidence consistency
        if correlation_graph:
            findings.extend(
                self._check_cluster_confidence(correlation_graph)
            )

        # 3. TOD consistency
        if tod_result:
            findings.extend(
                self._check_tod_consistency(tod_result)
            )

        # 4. Evidence group coherence
        if correlation_graph:
            findings.extend(
                self._check_evidence_group_coherence(correlation_graph)
            )

        self._audit.append(
            AnomalyAuditEntry(
                stage="consistency_checking",
                action="check_complete",
                finding_ids=[f.finding_id for f in findings],
                detail=(
                    f"Consistency check produced {len(findings)} findings"
                ),
            )
        )

        return findings

    def _check_entity_count_consistency(
        self,
        entity_graphs: list[tuple[str, ForensicEntityGraph]],
    ) -> list[AnomalyFinding]:
        """Flag documents with unusually low entity counts."""
        findings: list[AnomalyFinding] = []

        if len(entity_graphs) < 2:
            return findings

        counts = [
            (eid, graph.metrics.total_entities)
            for eid, graph in entity_graphs
        ]

        if not counts:
            return findings

        avg_count = sum(c for _, c in counts) / len(counts)

        for eid, count in counts:
            if count == 0:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.EVIDENCE_INTEGRITY,
                        severity=FindingSeverity.HIGH,
                        title="Empty entity graph",
                        description=(
                            f"Evidence file {eid} produced no "
                            f"structured entities"
                        ),
                        affected_evidence_ids=[eid],
                        rule_id="EMPTY_GRAPH",
                        confidence=0.95,
                        recommendation=(
                            "Document may be unreadable, corrupted, "
                            "or not a forensic document"
                        ),
                    )
                )
            elif avg_count > 0 and count < avg_count * 0.2:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.ANOMALY,
                        category=FindingCategory.EVIDENCE_INTEGRITY,
                        severity=FindingSeverity.MEDIUM,
                        title="Sparse entity graph",
                        description=(
                            f"Evidence file {eid} has {count} entities "
                            f"vs average {avg_count:.0f}"
                        ),
                        affected_evidence_ids=[eid],
                        rule_id="SPARSE_GRAPH",
                        confidence=0.7,
                        recommendation=(
                            "Document may have poor OCR quality or "
                            "limited forensic content"
                        ),
                    )
                )

        return findings

    def _check_cluster_confidence(
        self,
        correlation_graph: CorrelationGraph,
    ) -> list[AnomalyFinding]:
        """Flag clusters with very low confidence."""
        findings: list[AnomalyFinding] = []

        for cluster in correlation_graph.entity_clusters:
            if cluster.confidence < 0.3 and len(cluster.members) > 1:
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.INCONSISTENCY,
                        category=FindingCategory.EVIDENCE_INTEGRITY,
                        severity=FindingSeverity.MEDIUM,
                        title=(
                            f"Low confidence cluster: "
                            f"{cluster.entity_type}"
                        ),
                        description=(
                            f"Entity cluster '{cluster.canonical_label}' "
                            f"has confidence {cluster.confidence:.2f} "
                            f"with {len(cluster.members)} members"
                        ),
                        affected_entity_ids=[
                            m.entity_id for m in cluster.members
                        ],
                        affected_evidence_ids=cluster.evidence_file_ids,
                        rule_id="LOW_CLUSTER_CONFIDENCE",
                        confidence=0.75,
                        recommendation=(
                            "Cluster members may not represent the "
                            "same real-world entity"
                        ),
                    )
                )

        return findings

    def _check_tod_consistency(
        self,
        tod_result: TODEstimationResult,
    ) -> list[AnomalyFinding]:
        """Check TOD estimation for internal consistency issues."""
        findings: list[AnomalyFinding] = []

        # Flag high conflict penalty
        if tod_result.confidence_scores.conflict_penalty > 0.2:
            findings.append(
                AnomalyFinding(
                    finding_id=str(uuid.uuid4()),
                    finding_type=FindingType.INCONSISTENCY,
                    category=FindingCategory.TOD_ESTIMATION,
                    severity=FindingSeverity.HIGH,
                    title="High TOD conflict penalty",
                    description=(
                        f"TOD estimation has significant conflicts "
                        f"(penalty: "
                        f"{tod_result.confidence_scores.conflict_penalty:.3f})"
                    ),
                    rule_id="TOD_HIGH_CONFLICT",
                    confidence=0.85,
                    recommendation=(
                        "Multiple forensic signals disagree on TOD; "
                        "review supporting evidence"
                    ),
                )
            )

        # Flag very wide TOD window
        window = tod_result.estimated_window
        if window.window_hours and window.window_hours > 48:
            findings.append(
                AnomalyFinding(
                    finding_id=str(uuid.uuid4()),
                    finding_type=FindingType.ANOMALY,
                    category=FindingCategory.TOD_ESTIMATION,
                    severity=FindingSeverity.MEDIUM,
                    title="Very wide TOD window",
                    description=(
                        f"Estimated TOD window spans "
                        f"{window.window_hours:.1f} hours"
                    ),
                    rule_id="TOD_WIDE_WINDOW",
                    confidence=0.8,
                    recommendation=(
                        "Insufficient precise forensic signals; "
                        "additional evidence may narrow the window"
                    ),
                )
            )

        # Flag no candidates
        if not tod_result.tod_candidates:
            findings.append(
                AnomalyFinding(
                    finding_id=str(uuid.uuid4()),
                    finding_type=FindingType.MISSING_DATA,
                    category=FindingCategory.TOD_ESTIMATION,
                    severity=FindingSeverity.HIGH,
                    title="No TOD candidates generated",
                    description=(
                        "TOD estimation produced no candidates; "
                        "insufficient forensic signals"
                    ),
                    rule_id="TOD_NO_CANDIDATES",
                    confidence=0.95,
                    recommendation=(
                        "Review evidence for TOD-relevant information "
                        "such as PMI, rigor, lividity, or witness data"
                    ),
                )
            )

        return findings

    def _check_evidence_group_coherence(
        self,
        correlation_graph: CorrelationGraph,
    ) -> list[AnomalyFinding]:
        """Check evidence groups for completeness."""
        findings: list[AnomalyFinding] = []

        for group in correlation_graph.evidence_groups:
            doc_types = {m.document_type for m in group.members}

            # A complete forensic case should have at minimum an autopsy
            if (
                len(group.members) > 1
                and "autopsy_report" not in doc_types
            ):
                findings.append(
                    AnomalyFinding(
                        finding_id=str(uuid.uuid4()),
                        finding_type=FindingType.MISSING_DATA,
                        category=FindingCategory.EVIDENCE_INTEGRITY,
                        severity=FindingSeverity.MEDIUM,
                        title=(
                            f"Missing autopsy report in evidence group"
                        ),
                        description=(
                            f"Evidence group '{group.case_identifier}' "
                            f"has {len(group.members)} documents but "
                            f"no autopsy report"
                        ),
                        affected_evidence_ids=[
                            m.evidence_file_id for m in group.members
                        ],
                        rule_id="MISSING_AUTOPSY_IN_GROUP",
                        confidence=0.7,
                        recommendation=(
                            "Case may be incomplete; autopsy report "
                            "should be uploaded if available"
                        ),
                    )
                )

        return findings
