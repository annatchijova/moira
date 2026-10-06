"""
moira/bridge/vigia_bundle.py
============================
Bridge: run MOIRA's minimal-cut search over a VIGIA sealed bundle.

Mapping:
- Each pipeline signal in `pipeline_results.signals` becomes a Transition
  carrying tokens: `id:<artifact_id>`, `src:<source>`, `type:<evidence_type>`,
  and a z-band token `z:critical` | `z:high` | `z:low` derived from the
  signal's z_score (exact Fraction, never a float).
- `BandCountOracle` reconstructs VIGIA's deterministic signal-count gate
  (vigia_agent.py, L-036): among primary signals,
    n_critical >= 2              -> MALICIOUS_INTENT_DETECTED (conclusive)
    n_critical >= 1              -> INTENT_DETECTED
    n_high (2 < |z| <= 3) >= 2   -> SUSPICION_DETECTED
    otherwise                    -> UNDETERMINED
  Derived signals (metadata.signal_class == "derived") and unanalyzed
  artifacts are excluded, mirroring _is_primary_signal.

Honest scope: the gate above is only part of VIGIA's abduction — the recorded
verdict may come from the reasoner layer. `analyze_bundle` therefore reports
`reproduces_recorded`: whether the oracle's baseline matches the bundle's
`abduction.best_hypothesis`. A mismatch is surfaced, not hidden — it means
the recorded verdict was produced by a layer this oracle does not model, and
the cuts apply to the gate, not to that verdict.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from ..core.cuts import CutAnalysis, find_minimal_cuts
from ..core.oracle import Decision
from ..core.transitions import History, Transition

MAX_SIGNALS_PER_BUNDLE: int = 256


def _try_frac(value: Any) -> Optional[Fraction]:
    """Strict parse of a VIGIA numeric; None when unparseable (RT2-F4:
    malformed must be distinguishable from a measured 0)."""
    try:
        if isinstance(value, dict) and value.get("__fraction__"):
            return Fraction(int(value.get("num", 0)),
                            max(int(value.get("den", 1)), 1))
        if isinstance(value, Fraction):
            return value
        if isinstance(value, bool):
            return Fraction(int(value), 1)
        if isinstance(value, int):
            return Fraction(value, 1)
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                return None
            return Fraction(str(value))
        if isinstance(value, str):
            s = value.strip()
            if s.lower() in ("", "nan", "inf", "-inf", "+inf",
                             "infinity", "-infinity"):
                return None
            return Fraction(s)
    except (ValueError, ZeroDivisionError, TypeError):
        return None
    return None


def _to_frac(value: Any) -> Fraction:
    """Parse a VIGIA numeric: tagged {__fraction__}, int, float, or "n/d" str.
    Deterministic; never produces a float. Mirrors vigia_agent._to_frac.
    Unparseable input maps to 0 — callers needing to distinguish malformed
    from measured-zero should use _try_frac."""
    parsed = _try_frac(value)
    return parsed if parsed is not None else Fraction(0, 1)


def _is_primary(signal: Dict[str, Any]) -> bool:
    """Port of vigia_agent._is_primary_signal: no metadata -> primary."""
    meta = signal.get("metadata") if isinstance(signal, dict) else None
    if not isinstance(meta, dict):
        return True
    return meta.get("signal_class") != "derived" and not meta.get("unanalyzed")


def _z_band(z: Fraction) -> str:
    a = abs(z)
    if a > 3:
        return "z:critical"
    if a > 2:
        return "z:high"
    return "z:low"


def history_from_bundle(bundle: Dict[str, Any]) -> History:
    """Reconstruct the transition history from a sealed bundle's signals."""
    signals = (bundle.get("pipeline_results") or {}).get("signals") or []
    if len(signals) > MAX_SIGNALS_PER_BUNDLE:
        raise ValueError(
            f"bundle carries {len(signals)} signals; cap is "
            f"{MAX_SIGNALS_PER_BUNDLE}")
    hist = []
    for i, s in enumerate(signals):
        if not isinstance(s, dict):
            # RT2-F5: a malformed entry must not vanish silently — a dropped
            # signal changes the denominator of the gate.
            raise ValueError(
                f"signals[{i}] is not a dict "
                f"({type(s).__name__}) — malformed bundle")
        if not _is_primary(s):
            continue   # derived/unanalyzed signals are not evidence (N4/F5)
        # RT2-F4: distinguish absent/unparseable z_score from a measured
        # low value. Numerically identical to z:low (counts toward neither
        # critical nor high) but observable in the history.
        if "z_score" not in s:
            z_tok = "z:absent"
        else:
            z = _try_frac(s["z_score"])
            z_tok = "z:malformed" if z is None else _z_band(z)
        toks = {
            f"id:{s.get('artifact_id', f'sig_{i}')}",
            f"src:{s.get('source', s.get('tool', 'unknown'))}",
            f"type:{s.get('evidence_type', 'unknown')}",
            z_tok,
        }
        hist.append(Transition(
            seq=i, kind=str(s.get("evidence_type", "signal")),
            signals=frozenset(toks),
            label=str(s.get("description", ""))[:120],
        ))
    return tuple(hist)


class BandCountOracle:
    """Deterministic reconstruction of VIGIA's L-036 signal-count gate.

    decide() counts primary transitions per z-band and applies the tiered
    rule. `used` = positions of signal-bearing transitions (the gate reads
    every primary signal)."""

    ORACLE_ID = "vigia.l036.band-count/v1"

    def decide(self, history: Sequence[Transition]) -> Decision:
        n_crit = sum(1 for t in history if "z:critical" in t.signals)
        n_high = sum(1 for t in history if "z:high" in t.signals)
        n = max(len(history), 1)
        if n_crit >= 2:
            v, score, concl = "MALICIOUS_INTENT_DETECTED", Fraction(n_crit, n), True
        elif n_crit >= 1:
            v, score, concl = "INTENT_DETECTED", Fraction(n_crit, n), True
        elif n_high >= 2:
            v, score, concl = "SUSPICION_DETECTED", Fraction(n_high, n), False
        else:
            v, score, concl = "UNDETERMINED", Fraction(0, n), False
        return Decision(
            token=f"{v}|conclusive={concl}",
            verdict=v, score=score,
            used=frozenset(i for i, t in enumerate(history) if t.signals),
        )


@dataclass(frozen=True)
class BundleAnalysis:
    """MOIRA result plus the verdict-reproduction honesty flag."""
    analysis:            CutAnalysis
    recorded_verdict:    Optional[str]
    oracle_verdict:      str
    reproduces_recorded: Optional[bool]  # None when bundle records none
    case_id:             Optional[str]


def analyze_bundle(bundle: Union[str, Path, Dict[str, Any]],
                   max_cut_size: int = 3,
                   oracle_budget: int = 50_000) -> BundleAnalysis:
    """Load a VIGIA bundle (path or dict), rebuild its signal history, and
    run the minimal-cut search under the band-count gate."""
    if isinstance(bundle, (str, Path)):
        bundle = json.loads(Path(bundle).read_text())
    hist = history_from_bundle(bundle)
    analysis = find_minimal_cuts(BandCountOracle(), hist,
                                 max_cut_size=max_cut_size,
                                 oracle_budget=oracle_budget)
    recorded = ((bundle.get("pipeline_results") or {}).get("abduction") or {}) \
        .get("best_hypothesis")
    oracle_v = analysis.baseline.verdict
    return BundleAnalysis(
        analysis=analysis,
        recorded_verdict=recorded,
        oracle_verdict=oracle_v,
        reproduces_recorded=(oracle_v == recorded
                             if recorded is not None else None),
        case_id=bundle.get("case_id"),
    )
