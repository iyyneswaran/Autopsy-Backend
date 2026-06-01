"""
Atopsy — Candidate Ranker (Layer 7).

Ranks TOD candidates by grouping overlapping windows,
scoring by weighted signal support, and selecting the
most plausible hypothesis. Never forces a single point
estimate — always preserves window ranges.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.pipeline.tod_estimation.schemas import (
    ForensicSignal,
    SignalConflict,
    ConflictSeverity,
    TODAuditEntry,
    TODCandidateV2,
    TODPrecision,
    TODProvenanceEntry,
    TODWindow,
)

logger = logging.getLogger(__name__)


class CandidateRanker:
    """
    Ranks and selects TOD candidates from weighted signals.

    Strategy:
    1. Group signals with overlapping TOD windows.
    2. For each group, build a consensus candidate.
    3. Identify conflicts between non-overlapping groups.
    4. Rank candidates by weighted support.
    5. Mark the highest-confidence candidate as primary.
    """

    def __init__(self) -> None:
        self._audit: list[TODAuditEntry] = []

    @property
    def audit_entries(self) -> list[TODAuditEntry]:
        return list(self._audit)

    def rank(
        self,
        signals: list[ForensicSignal],
    ) -> tuple[list[TODCandidateV2], list[SignalConflict]]:
        """
        Rank signals into TOD candidates and detect conflicts.

        Args:
            signals: Weighted forensic signals with TOD windows.

        Returns:
            Tuple of (ranked candidates, detected conflicts).
        """
        self._audit.clear()

        # Filter to signals with usable windows
        usable = [
            s for s in signals
            if (
                s.tod_window.earliest
                or s.tod_window.latest
                or s.tod_window.best_estimate
            )
        ]

        if not usable:
            self._audit.append(
                TODAuditEntry(
                    stage="candidate_ranking",
                    action="no_usable_signals",
                    detail="No signals with TOD windows found",
                )
            )
            return [], []

        # Group overlapping signals
        groups = self._group_overlapping(usable)

        # Build candidates from groups
        candidates: list[TODCandidateV2] = []
        for i, group in enumerate(groups):
            candidate = self._build_candidate(group, i + 1)
            candidates.append(candidate)

        # Detect conflicts between candidates
        conflicts = self._detect_conflicts(candidates, usable)

        # Mark conflicting signals on candidates
        conflict_signal_ids: set[str] = set()
        for conflict in conflicts:
            conflict_signal_ids.add(conflict.signal_a_id)
            conflict_signal_ids.add(conflict.signal_b_id)

        for candidate in candidates:
            candidate.conflicting_signals = [
                sid
                for sid in candidate.supporting_signals
                if sid in conflict_signal_ids
            ]

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        # Assign ranks and mark primary
        for rank, candidate in enumerate(candidates, 1):
            candidate.rank = rank
            candidate.is_primary = rank == 1

        self._audit.append(
            TODAuditEntry(
                stage="candidate_ranking",
                action="ranking_complete",
                detail=(
                    f"Ranked {len(candidates)} candidates from "
                    f"{len(usable)} signals, "
                    f"{len(conflicts)} conflicts detected"
                ),
            )
        )

        return candidates, conflicts

    def _group_overlapping(
        self, signals: list[ForensicSignal]
    ) -> list[list[ForensicSignal]]:
        """Group signals with overlapping TOD windows."""
        if not signals:
            return []

        # Sort by earliest bound (or best_estimate)
        def sort_key(s: ForensicSignal) -> str:
            return (
                s.tod_window.earliest
                or s.tod_window.best_estimate
                or s.tod_window.latest
                or ""
            )

        sorted_signals = sorted(signals, key=sort_key)

        groups: list[list[ForensicSignal]] = [[sorted_signals[0]]]

        for signal in sorted_signals[1:]:
            merged = False
            for group in groups:
                if self._windows_overlap(
                    group[0].tod_window, signal.tod_window
                ):
                    group.append(signal)
                    merged = True
                    break

            if not merged:
                groups.append([signal])

        return groups

    def _windows_overlap(
        self, w1: TODWindow, w2: TODWindow
    ) -> bool:
        """Check if two TOD windows overlap."""
        e1 = w1.earliest or w1.best_estimate
        l1 = w1.latest or w1.best_estimate
        e2 = w2.earliest or w2.best_estimate
        l2 = w2.latest or w2.best_estimate

        if not e1 or not l1 or not e2 or not l2:
            # If we can't determine bounds, assume possible overlap
            return True

        # Windows overlap if neither ends before the other starts
        return not (l1 < e2 or l2 < e1)

    def _build_candidate(
        self,
        group: list[ForensicSignal],
        group_index: int,
    ) -> TODCandidateV2:
        """Build a consensus candidate from a group of signals."""
        # Compute consensus window (intersection of ranges)
        earliest_vals = [
            s.tod_window.earliest
            for s in group
            if s.tod_window.earliest
        ]
        latest_vals = [
            s.tod_window.latest
            for s in group
            if s.tod_window.latest
        ]
        best_vals = [
            s.tod_window.best_estimate
            for s in group
            if s.tod_window.best_estimate
        ]

        # Consensus: latest of all earliest bounds, earliest of all latest
        consensus_earliest = max(earliest_vals) if earliest_vals else None
        consensus_latest = min(latest_vals) if latest_vals else None
        consensus_best = (
            sorted(best_vals)[len(best_vals) // 2]
            if best_vals
            else None
        )

        # Compute window span
        window_hours: float | None = None
        if consensus_earliest and consensus_latest:
            try:
                dt_e = datetime.fromisoformat(consensus_earliest)
                dt_l = datetime.fromisoformat(consensus_latest)
                window_hours = (dt_l - dt_e).total_seconds() / 3600.0
            except (ValueError, TypeError):
                pass

        # Weighted confidence
        total_weight = sum(s.weight for s in group) or 1.0
        weighted_conf = sum(
            s.weight * s.confidence for s in group
        ) / total_weight

        # Determine estimation method from dominant signal type
        type_weights: dict[str, float] = {}
        for s in group:
            st = s.signal_type.value
            type_weights[st] = type_weights.get(st, 0.0) + s.weight
        dominant_method = max(type_weights, key=type_weights.get)  # type: ignore[arg-type]

        # Build provenance entries
        provenance = [
            s.provenance for s in group if s.provenance.entity_id
        ]

        return TODCandidateV2(
            candidate_id=str(uuid.uuid4()),
            tod_window=TODWindow(
                earliest=consensus_earliest,
                latest=consensus_latest,
                best_estimate=consensus_best,
                window_hours=round(window_hours, 2) if window_hours else None,
                confidence=round(weighted_conf, 3),
                precision=TODPrecision.RANGE,
            ),
            estimation_method=f"consensus_{dominant_method.lower()}",
            supporting_signals=[s.signal_id for s in group],
            confidence=round(weighted_conf, 3),
            rationale=(
                f"Consensus from {len(group)} signals "
                f"(dominant: {dominant_method})"
            ),
            provenance_entries=provenance,
            corroboration_count=len(group),
        )

    def _detect_conflicts(
        self,
        candidates: list[TODCandidateV2],
        signals: list[ForensicSignal],
    ) -> list[SignalConflict]:
        """Detect conflicts between non-overlapping candidates."""
        conflicts: list[SignalConflict] = []
        signal_map = {s.signal_id: s for s in signals}

        for i, ca in enumerate(candidates):
            for cb in candidates[i + 1:]:
                if not self._windows_overlap(
                    ca.tod_window, cb.tod_window
                ):
                    # These candidates conflict
                    # Create a conflict for each pair of supporting signals
                    sig_a = (
                        ca.supporting_signals[0]
                        if ca.supporting_signals
                        else ""
                    )
                    sig_b = (
                        cb.supporting_signals[0]
                        if cb.supporting_signals
                        else ""
                    )

                    wa = ca.tod_window
                    wb = cb.tod_window

                    conflicts.append(
                        SignalConflict(
                            conflict_id=str(uuid.uuid4()),
                            signal_a_id=sig_a,
                            signal_b_id=sig_b,
                            conflict_type="NON_OVERLAPPING_WINDOWS",
                            severity=ConflictSeverity.HIGH,
                            description=(
                                f"TOD candidates do not overlap: "
                                f"[{wa.earliest} - {wa.latest}] vs "
                                f"[{wb.earliest} - {wb.latest}]"
                            ),
                            window_a_summary=(
                                f"{wa.earliest or '?'} to {wa.latest or '?'}"
                            ),
                            window_b_summary=(
                                f"{wb.earliest or '?'} to {wb.latest or '?'}"
                            ),
                            resolution_hint=(
                                "Review source evidence for both windows; "
                                "one may contain extraction errors"
                            ),
                        )
                    )

        return conflicts
