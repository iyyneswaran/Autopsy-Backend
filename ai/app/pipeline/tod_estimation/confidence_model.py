"""
Atopsy — TOD Confidence Model (Layer 7).

Computes per-candidate and overall confidence scores
for the TOD estimation result.
"""

from __future__ import annotations

import logging

from app.pipeline.tod_estimation.schemas import (
    ForensicSignal,
    SignalConflict,
    SignalType,
    TODAuditEntry,
    TODCandidateV2,
    TODConfidenceScores,
)

logger = logging.getLogger(__name__)


# Expected signal types for a complete forensic estimation
_EXPECTED_SIGNAL_TYPES: set[SignalType] = {
    SignalType.DIRECT_EXAMINER,
    SignalType.PMI_STATEMENT,
    SignalType.RIGOR_MORTIS,
    SignalType.LIVIDITY,
    SignalType.LAST_SEEN_ALIVE,
}


class ConfidenceModel:
    """
    Computes confidence scores for the TOD estimation.

    Formula:
        candidate_confidence = Σ(weight × confidence) / Σ(weight) - conflict_penalty
        overall = primary_conf × 0.7 + corroboration_bonus × 0.3 - penalties
    """

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def compute(
        self,
        candidates: list[TODCandidateV2],
        signals: list[ForensicSignal],
        conflicts: list[SignalConflict],
    ) -> TODConfidenceScores:
        """
        Compute all confidence scores.

        Args:
            candidates: Ranked TOD candidates.
            signals: All forensic signals.
            conflicts: Detected signal conflicts.

        Returns:
            TODConfidenceScores with all metrics.
        """
        self._audit.clear()

        # Primary candidate confidence
        primary = next(
            (c for c in candidates if c.is_primary), None
        )
        primary_conf = primary.confidence if primary else 0.0

        # Corroboration bonus: how many independent signal types agree
        present_types = {s.signal_type for s in signals if s.weight > 0}
        agreeing_types = len(
            present_types & _EXPECTED_SIGNAL_TYPES
        )
        max_types = len(_EXPECTED_SIGNAL_TYPES)
        corroboration_bonus = min(
            0.3, (agreeing_types / max(max_types, 1)) * 0.3
        )

        # Conflict penalty
        conflict_penalty = min(0.4, len(conflicts) * 0.08)

        # Missing signal penalty: expected signals absent
        missing_types = _EXPECTED_SIGNAL_TYPES - present_types
        missing_penalty = min(0.2, len(missing_types) * 0.04)

        # Signal agreement: fraction of signals supporting primary
        supporting = 0
        conflicting = 0
        for signal in signals:
            if primary and signal.signal_id in primary.supporting_signals:
                supporting += 1
            elif primary and signal.signal_id in primary.conflicting_signals:
                conflicting += 1

        total = len(signals) or 1
        agreement = supporting / total

        # Overall confidence
        overall = max(
            0.0,
            min(
                1.0,
                (primary_conf * 0.7)
                + (corroboration_bonus)
                - conflict_penalty
                - missing_penalty,
            ),
        )

        scores = TODConfidenceScores(
            overall_confidence=round(overall, 3),
            primary_candidate_confidence=round(primary_conf, 3),
            signal_agreement_score=round(agreement, 3),
            corroboration_bonus=round(corroboration_bonus, 3),
            conflict_penalty=round(conflict_penalty, 3),
            missing_signal_penalty=round(missing_penalty, 3),
            total_signals=len(signals),
            supporting_signal_count=supporting,
            conflicting_signal_count=conflicting,
        )

        self._audit.append(
            TODAuditEntry(
                stage="confidence_scoring",
                action="scores_computed",
                detail=(
                    f"Overall confidence: {overall:.3f}, "
                    f"primary: {primary_conf:.3f}, "
                    f"agreement: {agreement:.3f}, "
                    f"conflicts: {len(conflicts)}, "
                    f"missing types: {len(missing_types)}"
                ),
                confidence=overall,
            )
        )

        return scores
