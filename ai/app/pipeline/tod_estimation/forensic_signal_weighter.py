"""
Atopsy — Forensic Signal Weighter (Layer 7).

Assigns reliability weights to forensic signals based on
signal type, precision, source confidence, and corroboration.
"""

from __future__ import annotations

import logging
from typing import Any

from app.pipeline.tod_estimation.schemas import (
    ForensicSignal,
    SignalConfidenceLevel,
    SignalType,
    TODAuditEntry,
    TODPrecision,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Base reliability weights by signal type
# ─────────────────────────────────────────────

_BASE_WEIGHTS: dict[SignalType, float] = {
    SignalType.DIRECT_EXAMINER: 0.95,
    SignalType.PMI_STATEMENT: 0.85,
    SignalType.BODY_COOLING: 0.80,
    SignalType.RIGOR_MORTIS: 0.70,
    SignalType.LIVIDITY: 0.70,
    SignalType.LAST_SEEN_ALIVE: 0.65,
    SignalType.WITNESS_TIMELINE: 0.60,
    SignalType.DISCOVERY_TIME: 0.60,
    SignalType.TOXICOLOGY: 0.55,
    SignalType.MEDICAL_EVIDENCE: 0.55,
    SignalType.DECOMPOSITION: 0.50,
    SignalType.SCENE_EVIDENCE: 0.45,
    SignalType.ENVIRONMENTAL: 0.40,
}

# Confidence level multipliers
_CONFIDENCE_LEVEL_MULT: dict[SignalConfidenceLevel, float] = {
    SignalConfidenceLevel.OBSERVED: 1.0,
    SignalConfidenceLevel.INFERRED: 0.85,
    SignalConfidenceLevel.ESTIMATED: 0.70,
    SignalConfidenceLevel.SPECULATIVE: 0.50,
}

# Precision multipliers
_PRECISION_MULT: dict[TODPrecision, float] = {
    TODPrecision.EXACT: 1.0,
    TODPrecision.APPROXIMATE: 0.90,
    TODPrecision.RANGE: 0.85,
    TODPrecision.RELATIVE: 0.70,
    TODPrecision.INFERRED: 0.60,
    TODPrecision.UNKNOWN: 0.50,
}


class ForensicSignalWeighter:
    """
    Assigns reliability weights to forensic signals.

    Weight = base_weight × confidence_level_mult × precision_mult
             × source_confidence × corroboration_bonus

    Higher weight = more reliable signal for TOD estimation.
    """

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def weight_signals(
        self,
        signals: list[ForensicSignal],
    ) -> list[ForensicSignal]:
        """
        Assign weights to all signals.

        Args:
            signals: Forensic signals to weight.

        Returns:
            Signals with populated weight fields.
        """
        self._audit.clear()

        # Count signals per type for corroboration
        type_counts: dict[SignalType, int] = {}
        for signal in signals:
            type_counts[signal.signal_type] = (
                type_counts.get(signal.signal_type, 0) + 1
            )

        for signal in signals:
            weight = self._compute_weight(signal, type_counts)
            signal.weight = round(weight, 4)

        self._audit.append(
            TODAuditEntry(
                stage="signal_weighting",
                action="weights_assigned",
                signal_ids=[s.signal_id for s in signals],
                detail=(
                    f"Weighted {len(signals)} signals across "
                    f"{len(type_counts)} types"
                ),
            )
        )

        return signals

    def _compute_weight(
        self,
        signal: ForensicSignal,
        type_counts: dict[SignalType, int],
    ) -> float:
        """Compute final weight for a single signal."""
        # Base weight
        base = _BASE_WEIGHTS.get(signal.signal_type, 0.40)

        # Confidence level multiplier
        conf_mult = _CONFIDENCE_LEVEL_MULT.get(
            signal.confidence_level, 0.50
        )

        # Precision multiplier
        prec_mult = _PRECISION_MULT.get(
            signal.tod_window.precision, 0.50
        )

        # Source confidence (from entity extraction)
        source_conf = max(signal.confidence, 0.1)

        # Corroboration bonus: multiple signals of same type
        count = type_counts.get(signal.signal_type, 1)
        corr_bonus = 1.0 + min(0.2, (count - 1) * 0.05)

        # Window quality penalty: very wide windows less reliable
        window_penalty = 1.0
        if signal.tod_window.window_hours is not None:
            if signal.tod_window.window_hours > 48:
                window_penalty = 0.7
            elif signal.tod_window.window_hours > 24:
                window_penalty = 0.85

        weight = (
            base
            * conf_mult
            * prec_mult
            * source_conf
            * corr_bonus
            * window_penalty
        )

        return min(1.0, max(0.0, weight))
