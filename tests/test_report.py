"""Tests for the counterfactual report text and sealing."""
from __future__ import annotations

import unittest
from fractions import Fraction

from moira.core.cuts import find_minimal_cuts
from moira.core.transitions import Transition
from moira.oracles.hypothesis import Hypothesis, HypothesisOracle
from moira.report import seal_analysis, summary_text, to_json


def T(seq, signals=()):
    return Transition(seq=seq, kind="obs", signals=frozenset(signals))


def _staging_case():
    """The canonical example: 'staging is mandatory' held up by {T17,T23}."""
    oracle = HypothesisOracle([
        Hypothesis("H_mand", "staging is mandatory",
                   frozenset({"guard_seen", "policy_seen"})),
        Hypothesis("H_opt", "staging is optional",
                   frozenset({"fastlane_seen"}), base_cost=Fraction(3, 2)),
    ])
    hist = [T(i, {f"noise_{i}"}) for i in range(12)]
    hist[5] = T(17, {"guard_seen"})
    hist[9] = T(23, {"policy_seen"})
    hist.append(T(30, {"fastlane_seen"}))
    return oracle, hist


class TestReport(unittest.TestCase):

    def test_pair_cut_narrative(self):
        oracle, hist = _staging_case()
        a = find_minimal_cuts(oracle, hist)
        text = summary_text(a)
        self.assertIn("'staging is mandatory'", text)
        self.assertIn("Removing any single tested transition is insufficient",
                      text)
        self.assertIn("{T17, T23}", text)
        self.assertIn("'staging is optional'", text)
        self.assertIn("All other tested removals preserve it.", text)
        # 12 noise transitions + fastlane are signal-bearing -> 13 depended
        self.assertEqual(a.depended_on, 13)
        self.assertEqual(len(a.critical_positions), 2)

    def test_no_cut_narrative(self):
        class NeverFlips:
            def decide(self, history):
                from moira.core.oracle import Decision
                return Decision(token="X", verdict="X")
        a = find_minimal_cuts(NeverFlips(), [T(0), T(1)])
        text = summary_text(a)
        self.assertIn("No removal", text)
        self.assertIn("does not report dependency tracking", text)

    def test_sealed_json_shape(self):
        oracle, hist = _staging_case()
        r = seal_analysis(find_minimal_cuts(oracle, hist))
        doc = to_json(r)
        self.assertIn('"seal"', doc)
        self.assertIn('"canonicalize_version": "2"', doc)
        self.assertIn('"exhaustive": true', doc)


if __name__ == "__main__":
    unittest.main()
