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
from .transitions import (Edit, History, Transition, apply_edits, remove,
                          validate_history)

# Hard caps. C(n, k) oracle calls for k cuts; the defaults keep the worst
# case bounded at ~44k calls for n=256, k=3 — but MAX_ORACLE_CALLS trips
# first and reports partial coverage.
DEFAULT_MAX_CUT_SIZE: int = 3
MAX_CUT_SIZE_HARD_CAP: int = 8
MAX_ORACLE_CALLS: int = 50_000
# Replacements widen the branching factor: per position, 1 removal +
# up to this many candidate mutations.
MAX_MUTATIONS_PER_POSITION: int = 16


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


@dataclass(frozen=True)
class MinimalIntervention:
    """A minimal set of edits (removals and/or replacements) whose
    application flips the decision.

    Minimality is over the edit set itself: no proper subset of `edits`
    flips. Two different actions on the same position (e.g. remove T17 vs
    replace T17 with X) are distinct minimal interventions — both are
    legitimate counterfactual explanations."""
    edits:       FrozenSet[Edit]
    positions:   FrozenSet[int]
    alternative: Decision

    @property
    def size(self) -> int:
        return len(self.edits)

    def describe(self, history: Sequence[Transition]) -> Tuple[str, ...]:
        """Human-readable actions, e.g. ("remove T17", "replace T23 ->
        'policy doc absent'"). Positions are named by the ORIGINAL tid."""
        parts = []
        for e in sorted(self.edits, key=lambda x: history[x.position].seq):
            tid = history[e.position].tid
            if e.action == "remove":
                parts.append(f"remove {tid}")
            else:
                label = e.replacement.label or str(e.replacement.signals)
                parts.append(f"replace {tid} with '{label}'")
        return tuple(parts)


@dataclass(frozen=True)
class InterventionAnalysis:
    """Result of a minimal-intervention search (removals + replacements)."""
    baseline:           Decision
    history_len:        int
    depended_on:        Optional[int]
    interventions:      Tuple[MinimalIntervention, ...]
    critical_positions: FrozenSet[int]
    coverage:           Coverage


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
                alt = decide_guarded(remove(hist, candidate))
                if size == 1:
                    # Record only after the oracle actually ran: on budget
                    # exhaustion a position must not be reported as tested.
                    tested_singletons.add(combo[0])
                if baseline.flips(alt):
                    minimal.append(CausalCut(
                        positions=candidate,
                        # Numeric seq order, not lexicographic: "T2" before
                        # "T17", not after "T10".
                        tids=tuple(hist[i].tid
                                   for i in sorted(combo,
                                                   key=lambda i: hist[i].seq)),
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


def find_minimal_interventions(
    oracle: DecisionOracle,
    history: Sequence[Transition],
    max_size: int = DEFAULT_MAX_CUT_SIZE,
    mutagen=None,
    oracle_budget: int = MAX_ORACLE_CALLS,
) -> InterventionAnalysis:
    """Find every minimal intervention of size <= max_size.

    Interventions combine `do(T_i = empty)` removals with `do(T_i = T'_i)`
    replacements drawn from `mutagen(t)` — a callable returning candidate
    substitute transitions for each position (default: none, i.e. removals
    only). A candidate is a set of Edit objects, at most one per position;
    minimality is inclusion over edit sets, and a superset of a known minimal
    intervention is pruned for the same reason as in the removal-only search.

    The branching factor is positions x (1 + len(mutagen(t))), so mutations
    are capped at MAX_MUTATIONS_PER_POSITION and the same oracle budget and
    honest-coverage rules apply.
    """
    hist: History = validate_history(history)
    if not (1 <= max_size <= MAX_CUT_SIZE_HARD_CAP):
        raise ValueError(
            f"max_size must be in [1, {MAX_CUT_SIZE_HARD_CAP}], "
            f"got {max_size}"
        )
    if oracle_budget < 1:
        raise ValueError("oracle_budget must be >= 1")

    # Per-position action menus, computed once.
    menus: List[List[Edit]] = []
    for i, t in enumerate(hist):
        acts = [Edit(position=i, action="remove")]
        if mutagen is not None:
            mutations = list(mutagen(t))[:MAX_MUTATIONS_PER_POSITION]
            acts += [Edit(position=i, action="replace", replacement=m)
                     for m in mutations]
        menus.append(acts)

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
    minimal: List[MinimalIntervention] = []
    minimal_sets: List[FrozenSet[Edit]] = []
    complete_sizes = 0

    for size in range(1, min(max_size, n) + 1):
        try:
            for combo in itertools.combinations(range(n), size):
                for choice in itertools.product(*(menus[i] for i in combo)):
                    candidate = frozenset(choice)
                    if any(m <= candidate for m in minimal_sets):
                        continue
                    alt = decide_guarded(apply_edits(hist, candidate))
                    if baseline.flips(alt):
                        minimal.append(MinimalIntervention(
                            edits=candidate,
                            positions=frozenset(e.position for e in choice),
                            alternative=alt,
                        ))
                        minimal_sets.append(candidate)
            complete_sizes = size
        except OracleBudgetExhausted:
            break

    elapsed = Fraction(time.monotonic() - started).limit_denominator(10**9)
    minimal.sort(key=lambda iv: (iv.size, tuple(sorted(iv.positions))))
    critical = frozenset().union(*(iv.positions for iv in minimal)) \
        if minimal else frozenset()
    exhaustive = complete_sizes == min(max_size, n)

    return InterventionAnalysis(
        baseline=baseline,
        history_len=n,
        depended_on=len(baseline.used) if baseline.used else None,
        interventions=tuple(minimal),
        critical_positions=critical,
        coverage=Coverage(
            max_cut_size=max_size,
            complete_sizes=complete_sizes,
            oracle_calls=calls,
            exhaustive=exhaustive,
            elapsed_seconds=elapsed,
        ),
    )
