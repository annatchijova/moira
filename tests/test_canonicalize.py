"""Tests for canonical v2 serialization — the type-collision guarantees."""
from __future__ import annotations

import unittest
from fractions import Fraction

from moira.core.canonicalize import CANONICALIZE_VERSION, canonicalize
from moira.core.seal import seal_payload


class TestCanonicalize(unittest.TestCase):

    def test_version(self):
        self.assertEqual(CANONICALIZE_VERSION, "2")

    def test_type_tags_are_distinct(self):
        # The collisions v2 exists to close: 1, "1", 1.0, True, "true", None
        forms = {canonicalize(v) for v in
                 [1, "1", 1.0, True, "true", None, "null"]}
        self.assertEqual(len(forms), 7)

    def test_bool_before_int(self):
        self.assertEqual(canonicalize(True), "true")
        self.assertEqual(canonicalize(1), "1:int")

    def test_fraction(self):
        self.assertEqual(canonicalize(Fraction(1, 2)), "1/2:frac")

    def test_string_normalization(self):
        self.assertEqual(canonicalize("a\r\nb"), canonicalize("a\nb"))
        self.assertEqual(canonicalize("café"), canonicalize("café"))

    def test_signed_zero(self):
        self.assertEqual(canonicalize(-0.0), canonicalize(0.0))

    def test_dict_key_order(self):
        a = canonicalize({"b": 1, "a": 2})
        b = canonicalize({"a": 2, "b": 1})
        self.assertEqual(a, b)

    def test_seal_determinism(self):
        payload = {"x": [1, "s", Fraction(3, 7)], "y": {"k": True}}
        self.assertEqual(seal_payload(payload), seal_payload(payload))

    # RT1-F1 regression: dict keys are canonicalized — distinct source types
    # must not collide in sealed space.
    def test_dict_key_types_do_not_collide(self):
        self.assertNotEqual(seal_payload({1: "x"}), seal_payload({"1": "x"}))
        self.assertNotEqual(seal_payload({True: "x"}),
                            seal_payload({"true": "x"}))

    # RT1-F4 regression: mixed-type dict keys must not crash the sort.
    def test_mixed_type_dict_keys(self):
        canon = canonicalize({1: "a", "b": "c"})
        self.assertEqual(set(canon.keys()), {"1:int", "s:b"})

    # RT1-F2 regression: set/frozenset canonical form must be hash-order
    # independent (str(set) is not).
    def test_frozenset_stable_form(self):
        a = canonicalize(frozenset({"x", "y", "z"}))
        b = canonicalize({"z", "x", "y"})
        self.assertEqual(a, b)
        self.assertEqual(a, sorted(a))


if __name__ == "__main__":
    unittest.main()
