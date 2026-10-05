"""
moira/core/seal.py
==================
SHA-256 sealing over canonical v2 bytes.

A sealed MOIRA report is tamper-evident: the digest covers the canonical form
of every analytic claim (baseline, cuts, coverage). Wall-clock timestamps and
other run metadata live OUTSIDE the sealed payload, so two identical analyses
seal identically — which is precisely what makes the determinism check
meaningful.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .canonicalize import CANONICALIZE_VERSION, canonicalize


def seal_payload(payload: Any) -> str:
    """SHA-256 over the canonical-v2 JSON encoding of payload."""
    canon = canonicalize(payload)
    raw = json.dumps(canon, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SealedReport:
    """An analytic result plus its tamper-evident seal.

    sealed_payload: canonicalized content the digest covers.
    seal:           SHA-256 hex digest of the payload.
    meta:           unsealed run metadata (timestamp, tool version). Never
                    inside the seal — provenance, not payload.
    """
    sealed_payload: Any
    seal:           str
    meta:           dict

    def to_dict(self) -> dict:
        return {
            "canonicalize_version": CANONICALIZE_VERSION,
            "seal": self.seal,
            "payload": self.sealed_payload,
            "meta": self.meta,
        }
