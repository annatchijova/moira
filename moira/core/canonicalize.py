"""
moira/core/canonicalize.py
==========================
Single source of truth for canonical serialization in MOIRA.

Ported in lockstep from vigia/core/canonicalize.py (schema v2). The v1 legacy
schema is not carried over: MOIRA has no historical bundles to verify, so it
emits v2 only.

INVARIANT: every value that is sealed (SHA-256) must be serialized through
this module. Divergent ad-hoc encoders are how one logical input gets two
hashes.

Schema v2:
  bool     -> "true" / "false"          (checked BEFORE int: bool subclasses int)
  int      -> "N:int"
  float    -> "N.NNNNNNNN" (8 fixed decimals), "nan", "inf", "-inf"
  str      -> "s:" + NFC(CRLF/CR -> LF)  (unambiguous prefix + normalization)
  None     -> "null"
  Fraction -> "num/den:frac"
  dict     -> keys sorted, values recursive
  list     -> elements recursive

Signed zero: -0.0 is normalized via `obj + 0.0` so both zeros canonicalize
to "0.00000000".

CANONICALIZE_VERSION = "2"
"""
from __future__ import annotations

import unicodedata
from fractions import Fraction
from typing import Any

CANONICALIZE_VERSION: str = "2"

# Unambiguous prefix for strings — prevents "true"/"1:int"/"null" from
# colliding with a scalar's tag. Any prefix works as long as no scalar
# encoding can produce it; "s:" cannot.
_V2_STR_PREFIX: str = "s:"


def _v2_norm_str(s: str) -> str:
    """Normalize a string for v2 hashing: line endings CRLF/CR -> LF, then
    NFC. Closes the "one logical string -> two hashes" instability
    (NFC/NFD, CRLF/LF)."""
    return unicodedata.normalize("NFC", s.replace("\r\n", "\n").replace("\r", "\n"))


def _canonicalize_v2(obj: Any) -> Any:
    """
    Canonical form under schema v2 — the only schema MOIRA emits.

    - bool/int/float/None   scalar tags, identical to VIGIA v2 bit-for-bit
    - str                   "s:" + NFC(CRLF/CR -> LF)
    - Fraction              "num/den:frac"
    - dict                  keys sorted, values recursive
    - list/tuple            elements recursive
    - fallback              "s:" + NFC(str(obj)) — never raw, avoids collision
    """
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return f"{obj}:int"
    if isinstance(obj, float):
        if obj != obj:
            return "nan"
        if obj == float("inf"):
            return "inf"
        if obj == float("-inf"):
            return "-inf"
        return f"{obj + 0.0:.8f}"  # +0.0 maps -0.0 -> 0.0
    if isinstance(obj, str):
        return _V2_STR_PREFIX + _v2_norm_str(obj)
    if obj is None:
        return "null"
    if isinstance(obj, Fraction):
        return f"{obj.numerator}/{obj.denominator}:frac"
    if isinstance(obj, dict):
        return {k: _canonicalize_v2(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonicalize_v2(v) for v in obj]
    return _V2_STR_PREFIX + _v2_norm_str(str(obj))


def canonicalize(obj: Any) -> Any:
    """Canonical form of obj under the current schema version."""
    return _canonicalize_v2(obj)
