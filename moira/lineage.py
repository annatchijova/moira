"""
moira/lineage.py
================
Hypothesis genealogy during an abductive cycle — ported from
vigia/abduction/hypothesis_lineage.py.

Records not only the winning hypothesis but the "map of alternatives":
near-misses within 20% cost of the winner, pivot signals whose presence or
absence would change the verdict, and an investigation roadmap.

Invariants (inherited):
- HypothesisNode is a frozen dataclass
- All costs are Fraction — no float in the decision path
- audit_hash is deterministic from the full trace
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import List, Optional


@dataclass(frozen=True)
class HypothesisNode:
    hypothesis_id:      str
    hypothesis_name:    str
    verdict:            str           # NOISE | MALICE | ABSTAIN | ...
    iteration:          int
    cost_ockham:        Fraction
    cost_adversarial:   Fraction
    cost_final:         Fraction
    signals_covered:    frozenset
    signals_ignored:    frozenset
    parent_id:          Optional[str] = None
    elimination_reason: Optional[str] = None


@dataclass(frozen=True)
class PivotSignal:
    """Signal whose presence or absence would change the verdict."""
    signal_name:     str
    current_state:   str        # "present" | "absent" | "unknown"
    if_found:        str        # verdict if the signal were found
    if_not_found:    str        # verdict if absence were confirmed
    confidence_delta: Fraction  # how much the confidence would shift


@dataclass
class LineageReport:
    winner:                HypothesisNode
    verdict_stability:     Fraction
    near_misses:           List[HypothesisNode]
    pivot_signals:         List[PivotSignal]
    investigation_roadmap: List[str]
    audit_hash:            str


class HypothesisLineageTracker:
    """Records the full abductive cycle for audit traceability."""

    def __init__(self) -> None:
        self._nodes: List[HypothesisNode] = []

    def record(
        self,
        hypothesis_id:    str,
        hypothesis_name:  str,
        verdict:          str,
        iteration:        int,
        cost_ockham:      Fraction,
        cost_adversarial: Fraction,
        cost_final:       Fraction,
        signals_covered:  frozenset,
        signals_ignored:  frozenset,
        parent_id:          Optional[str] = None,
        elimination_reason: Optional[str] = None,
    ) -> None:
        """Record one hypothesis evaluation in the tree."""
        self._nodes.append(HypothesisNode(
            hypothesis_id=hypothesis_id,
            hypothesis_name=hypothesis_name,
            verdict=verdict,
            iteration=iteration,
            cost_ockham=cost_ockham,
            cost_adversarial=cost_adversarial,
            cost_final=cost_final,
            signals_covered=signals_covered,
            signals_ignored=signals_ignored,
            parent_id=parent_id,
            elimination_reason=elimination_reason,
        ))

    def finalize(self, winner_id: str) -> LineageReport:
        """Close the cycle and produce the lineage report."""
        if not self._nodes:
            raise ValueError("No hypotheses have been recorded")

        winner_nodes = [n for n in self._nodes if n.hypothesis_id == winner_id]
        if not winner_nodes:
            raise ValueError(f"Winning hypothesis not found: {winner_id}")
        winner = winner_nodes[-1]  # last version if there were iterations

        # Near misses: within 20% of the winner's final cost
        threshold = Fraction(1, 5)
        near_misses = [
            n for n in self._nodes
            if n.hypothesis_id != winner_id
            and n.cost_final > Fraction(0)
            and abs(n.cost_final - winner.cost_final)
                / max(winner.cost_final, Fraction(1, 100)) <= threshold
        ]
        near_misses.sort(key=lambda n: abs(n.cost_final - winner.cost_final))

        # Verdict stability: share of iterations where the winner was leading
        winner_iterations = sum(
            1 for n in self._nodes if n.hypothesis_id == winner_id
        )
        total_iterations = len(set(n.iteration for n in self._nodes))
        verdict_stability = (
            Fraction(winner_iterations, total_iterations)
            if total_iterations > 0 else Fraction(1)
        )

        pivot_signals = _compute_pivot_signals(winner, self._nodes)
        roadmap = _build_roadmap(winner, near_misses, pivot_signals)
        audit_hash = _compute_lineage_hash(self._nodes, winner_id)

        return LineageReport(
            winner=winner,
            verdict_stability=verdict_stability,
            near_misses=near_misses,
            pivot_signals=pivot_signals,
            investigation_roadmap=roadmap,
            audit_hash=audit_hash,
        )


def _compute_pivot_signals(
    winner: HypothesisNode,
    all_nodes: List[HypothesisNode],
) -> List[PivotSignal]:
    """Signals ignored by the winner that an alternative covered — the
    evidence whose collection could change the verdict."""
    pivots: List[PivotSignal] = []
    for signal in winner.signals_ignored:
        covering = [
            n for n in all_nodes
            if n.hypothesis_id != winner.hypothesis_id
            and signal in n.signals_covered
        ]
        if not covering:
            continue
        best_alt = min(covering, key=lambda n: n.cost_final)
        cost_delta = best_alt.cost_final - winner.cost_final
        pivots.append(PivotSignal(
            signal_name=signal,
            current_state="absent",
            if_found=best_alt.verdict,
            if_not_found=winner.verdict,
            confidence_delta=min(abs(cost_delta), Fraction(1)),
        ))
    pivots.sort(key=lambda p: p.confidence_delta, reverse=True)
    return pivots[:5]


def _build_roadmap(
    winner: HypothesisNode,
    near_misses: List[HypothesisNode],
    pivot_signals: List[PivotSignal],
) -> List[str]:
    roadmap: List[str] = [
        f"Winning hypothesis: {winner.hypothesis_name} "
        f"(verdict={winner.verdict}, cost={winner.cost_final})"
    ]
    if near_misses:
        roadmap.append(
            f"{len(near_misses)} near-miss hypothesis/hypotheses "
            f"within 20% cost margin:"
        )
        for nm in near_misses[:3]:
            roadmap.append(
                f"  -> {nm.hypothesis_name} (verdict={nm.verdict}, "
                f"cost={nm.cost_final}, "
                f"delta={abs(nm.cost_final - winner.cost_final)})"
            )
    if pivot_signals:
        roadmap.append("Pivot signals — verify these to increase certainty:")
        for ps in pivot_signals:
            roadmap.append(
                f"  -> '{ps.signal_name}': "
                f"if found -> {ps.if_found}, "
                f"if confirmed absent -> {ps.if_not_found} "
                f"(confidence delta: {int(ps.confidence_delta * 100)}%)"
            )
    if winner.signals_ignored:
        roadmap.append(
            f"Signals not explained by winning hypothesis "
            f"({len(winner.signals_ignored)}):"
        )
        for sig in sorted(winner.signals_ignored)[:5]:
            roadmap.append(f"  -> {sig}")
    return roadmap


def _compute_lineage_hash(nodes: List[HypothesisNode], winner_id: str) -> str:
    content = json.dumps(
        {
            "winner_id": winner_id,
            "nodes": [
                {
                    "id":      n.hypothesis_id,
                    "verdict": n.verdict,
                    "cost":    str(n.cost_final),
                    "iter":    n.iteration,
                }
                for n in nodes
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()
