"""
moira/core/oracle.py
====================
The decision oracle: the deterministic engine whose verdict MOIRA attacks
with counterfactual removals.

MOIRA is oracle-agnostic. Anything that maps a history to a Decision — a rule
engine, a hypothesis scorer, a policy evaluator — can be searched for minimal
causal cuts, provided:

  1. decide() is deterministic: same history -> bit-identical Decision.
  2. The decision token is the flip criterion. Two histories produce "the
     same decision" iff their tokens are equal; MOIRA does not interpret
     verdicts.

`used` is the oracle's own claim of which history positions it read. When
present, the report can say "depends causally on N transitions" as a measured
fact rather than an inference. When absent (empty frozenset), the report
degrades honestly to "tested N transitions" — MOIRA never claims a dependency
count it did not observe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import FrozenSet, Optional, Protocol, Sequence, runtime_checkable

from .transitions import Transition


@dataclass(frozen=True)
class Decision:
    """A sealed-comparable decision produced by an oracle over a history.

    token:   canonical identity of the outcome — the flip criterion. Equal
             tokens == same decision. Typically "<verdict>" or
             "<verdict>/<rationale>". Must be deterministic.
    verdict: human-readable verdict label for reporting.
    score:   optional scalar associated with the winner (Fraction only —
             never a float in the decision path).
    used:    positions in the input history the decision actually depended
             on, if the oracle tracks them. Empty frozenset = not tracked.
    """
    token:   str
    verdict: str
    score:   Optional[Fraction] = None
    used:    FrozenSet[int] = field(default_factory=frozenset)

    def flips(self, other: "Decision") -> bool:
        return self.token != other.token


@runtime_checkable
class DecisionOracle(Protocol):
    """Protocol every oracle must satisfy.

    Implementations must be deterministic and must not mutate the input
    history. MOIRA calls decide() O(n^k) times; implementers should keep it
    cheap and side-effect free.
    """

    def decide(self, history: Sequence[Transition]) -> Decision:
        ...
