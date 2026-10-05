"""Tests for the VIGIA bundle bridge (BandCountOracle, L-036 port)."""
from __future__ import annotations

import unittest

from moira.bridge.vigia_bundle import (BandCountOracle, _to_frac,
                                     analyze_bundle, history_from_bundle)
from moira.report import summary_text


def sig(i, z_num, z_den=1, source="sift_syslog", artifact=None,
        derived=False):
    s = {
        "artifact_id": artifact or f"a{i:02d}",
        "source": source,
        "evidence_type": "memory_process",
        "description": f"signal {i}",
        "z_score": {"__fraction__": True, "num": z_num, "den": z_den},
        "confidence": {"__fraction__": True, "num": 1, "den": 2},
    }
    if derived:
        s["metadata"] = {"signal_class": "derived"}
    return s


def bundle(signals):
    return {
        "case_id": "TEST-001",
        "pipeline_results": {
            "signals": signals,
            "abduction": {"best_hypothesis": "MALICIOUS_INTENT_DETECTED"},
        },
    }


class TestHelpers(unittest.TestCase):

    def test_to_frac(self):
        self.assertEqual(str(_to_frac({"__fraction__": True,
                                       "num": 46, "den": 125})), "46/125")
        self.assertEqual(str(_to_frac("401/4000")), "401/4000")
        self.assertEqual(str(_to_frac(0.5)), "1/2")
        self.assertEqual(str(_to_frac("nan")), "0")

    def test_derived_excluded(self):
        hist = history_from_bundle(bundle([sig(0, 9), sig(1, 9,
                                                        derived=True)]))
        self.assertEqual(len(hist), 1)


class TestBandCount(unittest.TestCase):

    def test_two_critical_is_malice(self):
        hist = history_from_bundle(bundle([sig(0, 9), sig(1, 4)]))
        r = analyze_bundle(bundle([sig(0, 9), sig(1, 4)]))
        self.assertEqual(r.oracle_verdict, "MALICIOUS_INTENT_DETECTED")
        self.assertTrue(r.reproduces_recorded)
        self.assertIsNotNone(r.analysis.baseline.used)
        # each critical signal is a singleton cut
        self.assertEqual(len(r.analysis.cuts), 2)
        self.assertTrue(all(c.size == 1 for c in r.analysis.cuts))

    def test_one_critical_intent(self):
        r = analyze_bundle(bundle([sig(0, 9), sig(1, 1)]))
        self.assertEqual(r.oracle_verdict, "INTENT_DETECTED")

    def test_high_band_needs_two(self):
        r = analyze_bundle(bundle([sig(0, 5, 2)]))   # z=2.5 -> high
        self.assertEqual(r.oracle_verdict, "UNDETERMINED")
        r2 = analyze_bundle(bundle([sig(0, 5, 2), sig(1, 11, 4)]))
        self.assertEqual(r2.oracle_verdict, "SUSPICION_DETECTED")

    def test_mismatch_is_surfaced(self):
        # Bundle records MALICE but the gate sees zero criticals: the flag
        # must say the oracle did NOT reproduce the recorded verdict.
        r = analyze_bundle(bundle([sig(0, 1)]))
        self.assertEqual(r.oracle_verdict, "UNDETERMINED")
        self.assertFalse(r.reproduces_recorded)

    def test_no_recorded_verdict(self):
        b = bundle([sig(0, 9), sig(1, 9)])
        del b["pipeline_results"]["abduction"]["best_hypothesis"]
        r = analyze_bundle(b)
        self.assertIsNone(r.reproduces_recorded)

    def test_summary_over_bundle(self):
        r = analyze_bundle(bundle([sig(0, 9), sig(1, 9), sig(2, 1)]))
        text = summary_text(r.analysis)
        self.assertIn("MALICIOUS_INTENT_DETECTED", text)
        self.assertIn("{T0}", text)


if __name__ == "__main__":
    unittest.main()
