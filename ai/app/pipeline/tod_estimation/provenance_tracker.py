"""
Atopsy — TOD Provenance Tracker (Layer 7).

Builds the provenance map and reasoning trace for the
TOD estimation result. Links every candidate back to
its source entities, evidence files, and raw text.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.pipeline.tod_estimation.schemas import (
    ForensicSignal,
    ReasoningStep,
    SignalConflict,
    TODAuditEntry,
    TODCandidateV2,
    TODConfidenceScores,
    TODProvenanceEntry,
)

logger = logging.getLogger(__name__)


class ProvenanceTracker:
    """
    Builds provenance maps and reasoning traces for TOD results.

    Preserves chain-of-custody:
        entity → signal → window → candidate → hypothesis
    """

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def build_provenance_map(
        self,
        candidates: list[TODCandidateV2],
        signals: list[ForensicSignal],
    ) -> dict[str, list[TODProvenanceEntry]]:
        """
        Build a provenance map indexed by candidate and signal IDs.

        Args:
            candidates: TOD candidates.
            signals: All forensic signals.

        Returns:
            Dict mapping IDs to provenance entries.
        """
        self._audit.clear()
        provenance_map: dict[str, list[TODProvenanceEntry]] = {}

        # Index signals
        signal_map = {s.signal_id: s for s in signals}

        # Map each candidate to its signal provenance
        for candidate in candidates:
            entries: list[TODProvenanceEntry] = []

            for sig_id in candidate.supporting_signals:
                signal = signal_map.get(sig_id)
                if signal and signal.provenance.entity_id:
                    entries.append(signal.provenance)

            if entries:
                provenance_map[candidate.candidate_id] = entries

        # Map each signal to its own provenance
        for signal in signals:
            if signal.provenance.entity_id:
                provenance_map[signal.signal_id] = [signal.provenance]

        self._audit.append(
            TODAuditEntry(
                stage="provenance_tracking",
                action="provenance_map_built",
                detail=(
                    f"Built provenance map with {len(provenance_map)} entries"
                ),
            )
        )

        return provenance_map

    def build_reasoning_trace(
        self,
        signals: list[ForensicSignal],
        candidates: list[TODCandidateV2],
        conflicts: list[SignalConflict],
        confidence_scores: TODConfidenceScores,
    ) -> list[ReasoningStep]:
        """
        Build a human-readable reasoning trace.

        Args:
            signals: All forensic signals.
            candidates: Ranked candidates.
            conflicts: Detected conflicts.
            confidence_scores: Computed scores.

        Returns:
            List of reasoning steps.
        """
        steps: list[ReasoningStep] = []
        idx = 0

        # Step 1: Signal extraction summary
        idx += 1
        type_summary = {}
        for s in signals:
            t = s.signal_type.value
            type_summary[t] = type_summary.get(t, 0) + 1

        steps.append(
            ReasoningStep(
                step_index=idx,
                action="signal_extraction",
                input_signals=[s.signal_id for s in signals],
                output=f"Extracted {len(signals)} forensic signals",
                rationale=(
                    f"Signal types: {type_summary}"
                ),
            )
        )

        # Step 2: Window construction summary
        idx += 1
        windowed = [
            s for s in signals
            if s.tod_window.earliest or s.tod_window.latest
        ]
        steps.append(
            ReasoningStep(
                step_index=idx,
                action="window_construction",
                input_signals=[s.signal_id for s in windowed],
                output=(
                    f"Built {len(windowed)} TOD windows from signals"
                ),
                rationale="Forensic timing rules applied per signal type",
            )
        )

        # Step 3: Candidate formation
        idx += 1
        steps.append(
            ReasoningStep(
                step_index=idx,
                action="candidate_formation",
                output=(
                    f"Formed {len(candidates)} TOD candidates by "
                    f"grouping overlapping windows"
                ),
                rationale=(
                    "Signals with overlapping time windows merged "
                    "into consensus candidates"
                ),
            )
        )

        # Step 4: Conflict detection
        idx += 1
        if conflicts:
            steps.append(
                ReasoningStep(
                    step_index=idx,
                    action="conflict_detection",
                    output=(
                        f"Detected {len(conflicts)} signal conflicts"
                    ),
                    rationale=(
                        "Non-overlapping candidate windows indicate "
                        "conflicting evidence"
                    ),
                    confidence_delta=-confidence_scores.conflict_penalty,
                )
            )
        else:
            steps.append(
                ReasoningStep(
                    step_index=idx,
                    action="conflict_detection",
                    output="No signal conflicts detected",
                    rationale="All candidate windows are compatible",
                )
            )

        # Step 5: Final ranking
        idx += 1
        primary = next(
            (c for c in candidates if c.is_primary), None
        )
        steps.append(
            ReasoningStep(
                step_index=idx,
                action="final_ranking",
                output=(
                    f"Primary candidate: {primary.candidate_id if primary else 'none'} "
                    f"(confidence: {primary.confidence if primary else 0:.3f})"
                ),
                rationale=(
                    f"Overall confidence: "
                    f"{confidence_scores.overall_confidence:.3f}"
                ),
                confidence_delta=0.0,
            )
        )

        return steps
