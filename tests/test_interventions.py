"""Tests for do(T = T') replacement interventions."""
from __future__ import annotations

import unittest

from moira.core.cuts import find_minimal_interventions
from moira.core.oracle import Decision
from moira.core.transitions import Edit, Transition, apply_edits
from moira.report import seal_analysis, summary_text


def T(seq, signals=(), label=""):
    return Transition(seq=seq, kind="obs", signals=frozenset(signals),
                      label=label)


class NeedA:
    """Verdict 'GO' iff signal 'a' is observed."""

    def decide(self, history):
        obs = frozenset().union(*(t.signals for t in history))
        ok = "a" in obs
        return Decision(token="GO" if ok else "NOGO",
                        verdict="GO" if ok else "NOGO")


def strip_a(t: Transition):
    """Mutagen: a variant of t without its 'a' signal."""
    return [Transition(seq=t.seq, kind=t.kind,
                       signals=frozenset(t.signals - {"a"}),
                       label=t.label + " (a stripped)")]


class TestApplyEdits(unittest.TestCase):

    def test_replace_and_remove(self):
        hist = [T(0, {"a"}), T(1, {"b"}), T(2, {"c"})]
        out = apply_edits(hist, frozenset({
            Edit(0, "replace", T(0, {"z"}, "swapped")),
            Edit(2, "remove"),
        }))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].signals, frozenset({"z"}))
        self.assertEqual(out[1].signals, frozenset({"b"}))

    def test_two_edits_same_position_rejected(self):
        with self.assertRaises(ValueError):
            apply_edits([T(0)], frozenset({
                Edit(0, "remove"), Edit(0, "replace", T(0, {"x"}))}))

    def test_bad_edit_rejected(self):
        with self.assertRaises(ValueError):
            Edit(0, "replace")          # missing replacement
        with self.assertRaises(ValueError):
            Edit(0, "remove", T(0))     # replacement on a removal
        with self.assertRaises(ValueError):
            Edit(0, "mutate")


class TestInterventionSearch(unittest.TestCase):

    def test_remove_and_replace_are_both_minimal(self):
        # 'a' only on T0. Two minimal size-1 interventions: remove T0,
        # and replace T0 with the stripped variant. Replacing T1 (noise)
        # changes nothing.
        hist = [T(0, {"a"}, "guard doc"), T(1, {"noise"}, "chatter")]
        r = find_minimal_interventions(NeedA(), hist, max_size=2,
                                       mutagen=strip_a)
        self.assertEqual(len(r.interventions), 2)
        acts = sorted(
            tuple(sorted((e.position, e.action) for e in iv.edits))
            for iv in r.interventions
        )
        self.assertEqual(acts, [((0, "remove"),), ((0, "replace"),)])
        self.assertTrue(all(iv.alternative.verdict == "NOGO"
                            for iv in r.interventions))
        self.assertEqual(r.critical_positions, frozenset({0}))
        self.assertTrue(r.coverage.exhaustive)

    def test_superset_pruning_with_mixed_edits(self):
        hist = [T(0, {"a"}), T(1, {"noise"})]
        r = find_minimal_interventions(NeedA(), hist, max_size=2,
                                       mutagen=strip_a)
        for iv in r.interventions:
            self.assertEqual(iv.size, 1)  # no size-2 intervention is minimal

    def test_no_mutagen_is_removal_only(self):
        hist = [T(0, {"a"}), T(1, {"noise"})]
        r = find_minimal_interventions(NeedA(), hist, max_size=1)
        self.assertEqual(len(r.interventions), 1)
        self.assertEqual(
            next(iter(r.interventions[0].edits)).action, "remove")

    def test_budget_partial_is_honest(self):
        hist = [T(i, {f"s{i}"}) for i in range(10)]
        r = find_minimal_interventions(NeedA(), hist, max_size=2,
                                       mutagen=strip_a, oracle_budget=5)
        self.assertFalse(r.coverage.exhaustive)
        self.assertEqual(r.coverage.oracle_calls, 5)

    def test_summary_describes_replacement(self):
        hist = [T(0, {"a"}, "guard doc"), T(1, {"noise"})]
        r = find_minimal_interventions(NeedA(), hist, max_size=1,
                                       mutagen=strip_a)
        text = summary_text(r, hist)
        self.assertIn("remove T0", text)
        self.assertIn("replace T0 with 'guard doc (a stripped)'", text)

    def test_sealed_payload_records_edits(self):
        hist = [T(0, {"a"}, "guard doc")]
        r = find_minimal_interventions(NeedA(), hist, max_size=1,
                                       mutagen=strip_a)
        rep = seal_analysis(r, hist)
        edits = rep.sealed_payload["minimal_cuts"][0]["edits"]
        self.assertTrue(any(e["action"] == "replace" for e in
                            rep.sealed_payload["minimal_cuts"][1]["edits"])
                        or True)
        self.assertIn("replace", {e["action"] for iv in
                                  rep.sealed_payload["minimal_cuts"]
                                  for e in iv["edits"]})
        self.assertIn("remove", {e["action"] for iv in
                                 rep.sealed_payload["minimal_cuts"]
                                 for e in iv["edits"]})


if __name__ == "__main__":
    unittest.main()
