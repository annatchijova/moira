"""Determinism: identical inputs must seal identically, across runs."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from fractions import Fraction

from moira.core.cuts import find_minimal_cuts
from moira.core.transitions import Transition
from moira.oracles.hypothesis import Hypothesis, HypothesisOracle
from moira.report import payload_of, seal_analysis, seal_payload


def _fixture():
    oracle = HypothesisOracle([
        Hypothesis("H_win", "W", frozenset({"A", "B"})),
        Hypothesis("H_chal", "C", frozenset({"C"}), base_cost=Fraction(3, 2)),
    ])
    hist = tuple(
        Transition(seq=i, kind="obs",
                   signals=frozenset(s), label=f"step {i}")
        for i, s in enumerate([{"A"}, {"B"}, {"C"}, {"n1"}, {"n2"}])
    )
    return oracle, hist


class TestDeterminism(unittest.TestCase):

    def test_same_input_same_seal(self):
        oracle, hist = _fixture()
        a = find_minimal_cuts(oracle, hist)
        b = find_minimal_cuts(oracle, hist)
        self.assertEqual(payload_of(a, hist), payload_of(b, hist))
        self.assertEqual(
            seal_analysis(a, hist).seal,
            seal_analysis(b, hist).seal,
        )

    def test_seal_binds_history(self):
        oracle, hist = _fixture()
        a = find_minimal_cuts(oracle, hist)
        other = tuple(Transition(seq=t.seq, kind=t.kind,
                                 signals=frozenset({"different"}),
                                 label=t.label) for t in hist)
        # Same analysis object, different history -> different seal.
        self.assertNotEqual(
            seal_analysis(a, hist).seal,
            seal_analysis(a, other).seal,
        )
        # Omitting history is visible, not hidden.
        self.assertIsNone(
            seal_analysis(a).sealed_payload["history_fingerprint"])

    def test_timestamp_outside_seal(self):
        oracle, hist = _fixture()
        a = find_minimal_cuts(oracle, hist)
        r1 = seal_analysis(a, hist)
        r2 = seal_analysis(a, hist)
        self.assertEqual(r1.seal, r2.seal)
        # meta carries provenance but is not part of the sealed payload
        self.assertNotIn("generated_at", r1.sealed_payload)
        self.assertIn("generated_at", r1.meta)

    def test_seal_stable_across_processes(self):
        # PYTHONHASHSEED randomization is the classic leak: sets/dicts must
        # never reach the seal unnormalized. A subprocess with a different
        # hash seed must produce the identical seal.
        oracle, hist = _fixture()
        expected = seal_payload(
            payload_of(find_minimal_cuts(oracle, hist), hist))
        code = (
            "import sys; sys.path.insert(0, '.');"
            "from fractions import Fraction;"
            "from moira.core.cuts import find_minimal_cuts;"
            "from moira.core.transitions import Transition;"
            "from moira.oracles.hypothesis import Hypothesis, HypothesisOracle;"
            "from moira.report import payload_of, seal_payload;"
            "o=HypothesisOracle([Hypothesis('H_win','W',frozenset({'A','B'})),"
            "Hypothesis('H_chal','C',frozenset({'C'}),base_cost=Fraction(3,2))]);"
            "h=tuple(Transition(seq=i,kind='obs',signals=frozenset(s),"
            "label='step '+str(i))"
            " for i,s in enumerate([{'A'},{'B'},{'C'},{'n1'},{'n2'}]));"
            "print(seal_payload(payload_of(find_minimal_cuts(o,h),h)))"
        )
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = "12345"
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, check=True,
            env=env,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(out.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
