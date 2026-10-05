"""Tests for the minimal causal cut search."""
from __future__ import annotations

import unittest
from fractions import Fraction

from moira.core.cuts import find_minimal_cuts
from moira.core.oracle import Decision
from moira.core.transitions import Transition
from moira.oracles.hypothesis import Hypothesis, HypothesisOracle


def T(seq, signals=(), kind="obs", label=""):
    return Transition(seq=seq, kind=kind, signals=frozenset(signals),
                      label=label)


class AndOracle:
    """Verdict 'GO' iff signals a AND b are both observed."""

    def decide(self, history):
        obs = frozenset().union(*(t.signals for t in history))
        ok = {"a", "b"} <= obs
        return Decision(token="GO" if ok else "NOGO",
                        verdict="GO" if ok else "NOGO",
                        score=Fraction(int(ok)),
                        used=frozenset(range(len(history))))


class TestCuts(unittest.TestCase):

    def test_singleton_cuts(self):
        # a from T0, b from T1; removing either alone flips GO -> NOGO
        hist = [T(0, {"a"}), T(1, {"b"}), T(2, {"noise"})]
        r = find_minimal_cuts(AndOracle(), hist)
        self.assertEqual(r.baseline.verdict, "GO")
        self.assertEqual(len(r.cuts), 2)
        self.assertTrue(all(c.size == 1 for c in r.cuts))
        self.assertEqual(r.critical_positions, frozenset({0, 1}))
        self.assertEqual(r.depended_on, 3)
        self.assertTrue(r.coverage.exhaustive)

    def test_pair_cut_only(self):
        # 'a' provided redundantly by T0 and T1: removing one leaves it,
        # removing both flips. Only {0,1} is a minimal cut.
        class SingleSignalOracle:
            def decide(self, history):
                obs = frozenset().union(*(t.signals for t in history))
                ok = "a" in obs
                return Decision(token="GO" if ok else "NOGO",
                                verdict="GO" if ok else "NOGO")
        hist = [T(0, {"a"}), T(1, {"a"}), T(2, {"b"})]
        r = find_minimal_cuts(SingleSignalOracle(), hist)
        self.assertEqual(len(r.cuts), 1)
        self.assertEqual(r.cuts[0].positions, frozenset({0, 1}))
        self.assertEqual(r.cuts[0].tids, ("T0", "T1"))

    def test_no_cuts(self):
        hist = [T(0, {"noise"})]
        r = find_minimal_cuts(AndOracle(), hist)
        self.assertEqual(r.baseline.verdict, "NOGO")
        self.assertEqual(r.cuts, ())
        self.assertTrue(r.coverage.exhaustive)

    def test_minimality_pruning(self):
        # 'a' only on T0: {0} flips alone, so {0,1} flips too but is NOT
        # minimal — it must be pruned as a strict superset of a known cut.
        class SingleSignalOracle:
            def decide(self, history):
                obs = frozenset().union(*(t.signals for t in history))
                ok = "a" in obs
                return Decision(token="GO" if ok else "NOGO",
                                verdict="GO" if ok else "NOGO")
        hist = [T(0, {"a"}), T(1, {"b"})]
        r = find_minimal_cuts(SingleSignalOracle(), hist, max_cut_size=2)
        self.assertEqual({c.positions for c in r.cuts}, {frozenset({0})})

    def test_overlapping_pair_cuts(self):
        # a on {T0,T1}, b on {T1,T2}: baseline GO.
        # No singleton flips (each signal survives). Pairs that flip: {0,1}
        # (kills a) and {1,2} (kills b). {0,2} leaves a via T1 and b via T1.
        hist = [T(0, {"a"}), T(1, {"a", "b"}), T(2, {"b"})]
        r = find_minimal_cuts(AndOracle(), hist, max_cut_size=2)
        self.assertEqual({c.positions for c in r.cuts},
                         {frozenset({0, 1}), frozenset({1, 2})})

    def test_budget_exhaustion_is_honest(self):
        hist = [T(i, {f"s{i}"}) for i in range(30)]
        r = find_minimal_cuts(AndOracle(), hist, max_cut_size=3,
                              oracle_budget=40)
        self.assertFalse(r.coverage.exhaustive)
        self.assertLess(r.coverage.complete_sizes, 3)
        self.assertEqual(r.coverage.oracle_calls, 40)

    def test_tested_singletons_only_counts_ran(self):
        # RT1-F3 regression: a position must not be reported as tested if the
        # oracle never evaluated its removal.
        hist = [T(i, {f"s{i}"}) for i in range(5)]
        r = find_minimal_cuts(AndOracle(), hist, oracle_budget=1)
        self.assertEqual(r.coverage.oracle_calls, 1)   # baseline only
        self.assertEqual(r.tested_singletons, frozenset())

    def test_empty_history(self):
        r = find_minimal_cuts(AndOracle(), [])
        self.assertEqual(r.baseline.verdict, "NOGO")
        self.assertEqual(r.cuts, ())


class TestHypothesisOracle(unittest.TestCase):

    def test_vigia_sort_key(self):
        # Winner needs {A,B}; challenger needs {C} with base_cost 3/2.
        # Baseline: winner cost 0. Remove T0 (A): winner cost 1 < 3/2, stands.
        # Remove {T0,T1}: winner cost 2 > 3/2 -> challenger wins.
        oracle = HypothesisOracle([
            Hypothesis("H_win", "staging is mandatory",
                       frozenset({"A", "B"})),
            Hypothesis("H_chal", "staging is optional",
                       frozenset({"C"}), base_cost=Fraction(3, 2)),
        ])
        hist = [T(0, {"A"}), T(1, {"B"}), T(2, {"C"}), T(3, {"noise"})]
        r = find_minimal_cuts(oracle, hist)
        self.assertEqual(r.baseline.verdict, "staging is mandatory")
        self.assertEqual({c.positions for c in r.cuts},
                         {frozenset({0, 1})})
        self.assertEqual(r.cuts[0].alternative.verdict, "staging is optional")

    def test_duplicate_hypothesis_rejected(self):
        with self.assertRaises(ValueError):
            HypothesisOracle([
                Hypothesis("H", "v", frozenset({"x"})),
                Hypothesis("H", "v", frozenset({"y"})),
            ])


if __name__ == "__main__":
    unittest.main()
