"""
moira/core/cuts.py
==================
Minimal causal cut search — MOIRA's core.

Research question: what is the minimal historical evidence required to flip
a present decision?

Given a history H = (T_0 ... T_n) and a deterministic oracle with baseline
decision D = decide(H), a *cut* is a set S of positions such that
decide(H \\ S) != D. A cut is *minimal* when no proper subset of it is also
a cut — every element is load-bearing.

Correctness note: the flip predicate is NOT monotone under removal (removing
more transitions can flip the verdict back), so this is not a simple hitting-
set problem. Minimality is still well-defined under set inclusion, and one
pruning is always valid: a strict superset of a known cut can never itself be
minimal. Enumerating candidate sets in increasing size order and recording
every minimal cut found makes the "no proper subset flips" check exact for
all sizes within the bound.

Honest degradation: the search is combinatorial. If MAX_ORACLE_CALLS is
exhausted, the result states exactly which cut sizes were fully explored
(`coverage.complete_sizes`) instead of implying exhaustive coverage.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from .oracle import Decision, DecisionOracle
from .transitions import History, Transition, remove, validate_history

# Hard caps. C(n, k) oracle calls for k cuts; the defaults keep the worst
# case bounded at ~44k calls for n=256, k=3 — but MAX_ORACLE_CALLS trips
# first and reports partial coverage.
DEFAULT_MAX_CUT_SIZE: int = 3
MAX_CUT_SIZE_HARD_CAP: int = 8
MAX_ORACLE_CALLS: int = 50_000


@dataclass(frozen=True)
class CausalCut:
    """One minimal set of positions whose removal flips the decision."""
    positions:   FrozenSet[int]          # indices into the input history
    tids:        Tuple[str, ...]         # {"T17", "T23"} — for reporting
    alternative: Decision                # the decision under do(T_S = empty)

    @property
    def size(self) -> int:
        return len(self.positions)


@dataclass(frozen=True)
class Coverage:
    """Exactly what was tested — the honest claim about completeness."""
    max_cut_size:     int                # requested bound
    complete_sizes:   int                # all sizes 1..k fully explored
    oracle_calls:     int
    exhaustive:       bool               # every subset up to bound was tested
    elapsed_seconds:  Fraction


@dataclass(frozen=True)
class CutAnalysis:
    """Full result of a minimal-cut search over one history."""
    baseline:          Decision
    history_len:       int
    depended_on:       Optional[int]     # len(baseline.used) or None if untracked
    cuts:              Tuple[CausalCut, ...]   # sorted by (size, positions)
    critical_positions: FrozenSet[int]   # union of all minimal cuts
    tested_singletons: FrozenSet[int]    # positions whose solo removal was tested
    coverage:          Coverage


class OracleBudgetExhausted(Exception):
    """Internal control flow: the oracle-call budget ran out mid-search."""


def find_minimal_cuts(
    oracle: DecisionOracle,
    history: Sequence[Transition],
    max_cut_size: int = DEFAULT_MAX_CUT_SIZE,
    oracle_budget: int = MAX_ORACLE_CALLS,
) -> CutAnalysis:
    """Find every minimal cut of size <= max_cut_size.

    Raises ValueError on a malformed history or out-of-range bound.
    Never raises for budget exhaustion — partial results are returned with
    coverage.exhaustive=False and complete_sizes stating what was proven.
    """
    hist: History = validate_history(history)
    if not (1 <= max_cut_size <= MAX_CUT_SIZE_HARD_CAP):
        raise ValueError(
            f"max_cut_size must be in [1, {MAX_CUT_SIZE_HARD_CAP}], "
            f"got {max_cut_size}"
        )
    if oracle_budget < 1:
        raise ValueError("oracle_budget must be >= 1")

    calls = 0
    started = time.monotonic()

    def decide_guarded(h: History) -> Decision:
        nonlocal calls
        if calls >= oracle_budget:
            raise OracleBudgetExhausted
        calls += 1
        return oracle.decide(h)

    n = len(hist)
    baseline = decide_guarded(hist)
    minimal: List[CausalCut] = []
    minimal_sets: List[FrozenSet[int]] = []
    tested_singletons: set[int] = set()
    complete_sizes = 0

    for size in range(1, min(max_cut_size, n) + 1):
        try:
            for combo in itertools.combinations(range(n), size):
                candidate = frozenset(combo)
                # A strict superset of a known minimal cut cannot be minimal.
                if any(m <= candidate for m in minimal_sets):
                    continue
                if size == 1:
                    tested_singletons.add(combo[0])
                alt = decide_guarded(remove(hist, candidate))
                if baseline.flips(alt):
                    minimal.append(CausalCut(
                        positions=candidate,
                        tids=tuple(sorted(hist[i].tid for i in combo)),
                        alternative=alt,
                    ))
                    minimal_sets.append(candidate)
            complete_sizes = size
        except OracleBudgetExhausted:
            break

    elapsed = Fraction(time.monotonic() - started).limit_denominator(10**9)
    minimal.sort(key=lambda c: (c.size, tuple(sorted(c.positions))))
    critical = frozenset().union(*minimal_sets) if minimal_sets else frozenset()
    exhaustive = complete_sizes == min(max_cut_size, n)

    return CutAnalysis(
        baseline=baseline,
        history_len=n,
        depended_on=len(baseline.used) if baseline.used else None,
        cuts=tuple(minimal),
        critical_positions=critical,
        tested_singletons=frozenset(tested_singletons),
        coverage=Coverage(
            max_cut_size=max_cut_size,
            complete_sizes=complete_sizes,
            oracle_calls=calls,
            exhaustive=exhaustive,
            elapsed_seconds=elapsed,
        ),
    )
