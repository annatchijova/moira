"""
moira/oracles/hypothesis.py
===========================
Reference oracle: hypothesis competition under VIGIA's selection rule.

Ported from vigia/abduction/vigia_counter_fact.py's selection invariant:

    sort_key = (cost, -coverage, len(required), hypothesis_id)

Each hypothesis claims a set of required signals and pays a base Ockham cost.
The observed signal set is the union over the transitions that survived the
intervention; each unobserved required signal adds its penalty to the cost.
The winner is the hypothesis with the lexicographically smallest sort key.

`used` is reported honestly: the positions of transitions that contributed at
least one signal required by the WINNING hypothesis — the causal support of
the verdict, not every transition that happened to be present.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import FrozenSet, Sequence, Tuple

from ..core.oracle import Decision
from ..core.transitions import Transition

MAX_HYPOTHESES: int = 256


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id:     str
    verdict:           str                    # verdict label if this wins
    required_signals:  FrozenSet[str]
    base_cost:         Fraction = Fraction(0)
    missing_penalty:   Fraction = Fraction(1) # cost per unobserved required signal

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id must be non-empty")
        if not self.required_signals:
            raise ValueError(
                f"{self.hypothesis_id}: required_signals must be non-empty "
                "(a hypothesis that requires nothing always wins trivially)"
            )
        if self.base_cost < 0 or self.missing_penalty < 0:
            raise ValueError("costs must be non-negative")


class HypothesisOracle:
    """Deterministic decision = argmin over hypotheses of the VIGIA sort key."""

    def __init__(self, hypotheses: Sequence[Hypothesis]) -> None:
        hyps = tuple(hypotheses)
        if not hyps:
            raise ValueError("at least one hypothesis is required")
        if len(hyps) > MAX_HYPOTHESES:
            raise ValueError(f"cap is {MAX_HYPOTHESES} hypotheses")
        ids = [h.hypothesis_id for h in hyps]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate hypothesis_id")
        self._hypotheses: Tuple[Hypothesis, ...] = hyps

    def decide(self, history: Sequence[Transition]) -> Decision:
        observed: FrozenSet[str] = frozenset().union(
            *(t.signals for t in history)
        ) if history else frozenset()

        def sort_key(h: Hypothesis):
            covered = len(h.required_signals & observed)
            missing = len(h.required_signals) - covered
            cost = h.base_cost + h.missing_penalty * missing
            coverage = Fraction(covered, len(h.required_signals))
            return (cost, -coverage, len(h.required_signals), h.hypothesis_id)

        winner = min(self._hypotheses, key=sort_key)
        covered = len(winner.required_signals & observed)
        cost = (winner.base_cost
                + winner.missing_penalty * (len(winner.required_signals) - covered))

        # The aggregation consumed every signal-bearing transition: removing a
        # silent transition cannot change the outcome, so they are excluded.
        used = frozenset(i for i, t in enumerate(history) if t.signals)
        return Decision(
            token=f"winner:{winner.hypothesis_id}",
            verdict=winner.verdict,
            score=cost,
            used=used,
        )
