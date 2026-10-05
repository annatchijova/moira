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


if __name__ == "__main__":
    unittest.main()
