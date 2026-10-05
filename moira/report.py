"""
moira/report.py
===============
The counterfactual report — "what would it take to change this answer?"

Turns a CutAnalysis into (a) a sealed, machine-verifiable payload and
(b) a human-readable summary of the decision's causal fragility:

    Current decision depends causally on 14 historical transitions.
    Only 2 are decision-critical.
    Removing either alone is insufficient.
    Removing {T17, T23} changes the decision to 'staging_optional'.
    All other tested removals preserve it.

Every claim in the text is backed by the sealed payload: the sentences are a
narration of measured removals, not an interpretation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from typing import List, Optional, Sequence

from .core.cuts import CutAnalysis
from .core.seal import SealedReport, seal_payload
from .core.transitions import History

SCHEMA_VERSION: str = "moira.report/1"


def _cut_dict(cut) -> dict:
    return {
        "positions": sorted(cut.positions),
        "tids": list(cut.tids),
        "alternative_verdict": cut.alternative.verdict,
        "alternative_token": cut.alternative.token,
        "alternative_score": (
            str(cut.alternative.score)
            if cut.alternative.score is not None else None
        ),
    }


def _transition_dict(t) -> dict:
    return {
        "seq": t.seq, "kind": t.kind,
        "signals": sorted(t.signals), "label": t.label,
    }


def history_fingerprint(history) -> str:
    """SHA-256 over the canonical form of the full history. Binds a sealed
    report to the exact input the analysis ran over (RT1-F5): without it a
    seal proves self-consistency only — the same payload can be presented
    against a different history."""
    return seal_payload([_transition_dict(t) for t in history])


def payload_of(
    analysis: CutAnalysis,
    history: Optional[History] = None,
    oracle_id: Optional[str] = None,
) -> dict:
    """The canonical, sealable content of an analysis. No timestamps — the
    seal must be reproducible across runs of identical inputs."""
    return {
        "schema": SCHEMA_VERSION,
        "history_fingerprint": (
            history_fingerprint(history) if history is not None else None
        ),
        "oracle_id": oracle_id,
        "baseline": {
            "token": analysis.baseline.token,
            "verdict": analysis.baseline.verdict,
            "score": (str(analysis.baseline.score)
                      if analysis.baseline.score is not None else None),
        },
        "history_len": analysis.history_len,
        "depended_on": analysis.depended_on,
        "minimal_cuts": [_cut_dict(c) for c in analysis.cuts],
        "critical_positions": sorted(analysis.critical_positions),
        "coverage": {
            "max_cut_size": analysis.coverage.max_cut_size,
            "complete_sizes": analysis.coverage.complete_sizes,
            "oracle_calls": analysis.coverage.oracle_calls,
            "exhaustive": analysis.coverage.exhaustive,
        },
    }


def seal_analysis(
    analysis: CutAnalysis,
    history: Optional[History] = None,
    oracle_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> SealedReport:
    """Seal the analysis. meta is stored OUTSIDE the seal (provenance).

    Pass `history` to bind the seal to the exact input analyzed; omit it and
    the payload records history_fingerprint=null — visible, not hidden.
    """
    m = {"generated_at": datetime.now(timezone.utc).isoformat()}
    if meta:
        m.update(meta)
    payload = payload_of(analysis, history, oracle_id)
    return SealedReport(sealed_payload=payload, seal=seal_payload(payload),
                        meta=m)


def summary_lines(analysis: CutAnalysis, history: Optional[History] = None) -> List[str]:
    """Human-readable counterfactual summary. Every line states a measured
    fact from the analysis; no line speculates."""
    base = analysis.baseline
    cuts = analysis.cuts
    cov = analysis.coverage

    if analysis.depended_on is not None:
        dep = (f"Current decision depends causally on "
               f"{analysis.depended_on} historical transitions.")
    else:
        dep = (f"Current decision was tested against "
               f"{analysis.history_len} historical transitions "
               f"(oracle does not report dependency tracking).")

    lines = [
        f"Decision under test: '{base.verdict}'.",
        dep,
        f"Decision-critical transitions: {len(analysis.critical_positions)} "
        f"of {analysis.history_len}.",
    ]

    singletons = [c for c in cuts if c.size == 1]
    if not cuts:
        bound = cov.complete_sizes
        lines.append(
            f"No removal of up to {bound} transition(s) changes the decision."
        )
        if not cov.exhaustive:
            lines.append(
                f"WARNING: search bounded at size {cov.max_cut_size}; "
                f"larger cuts were not exhaustively tested."
            )
        return lines

    if not singletons:
        smallest = min(c.size for c in cuts)
        lines.append(
            f"Removing any single tested transition is insufficient; "
            f"the smallest decisive cut has size {smallest}."
        )
    for c in cuts:
        members = "{" + ", ".join(c.tids) + "}"
        lines.append(
            f"Removing {members} changes the decision to "
            f"'{c.alternative.verdict}'."
        )
    if cov.exhaustive:
        lines.append("All other tested removals preserve it.")
    else:
        lines.append(
            f"Coverage note: removals of size <= {cov.complete_sizes} were "
            f"fully tested; the search stopped before exhausting size "
            f"{cov.max_cut_size} ({cov.oracle_calls} oracle calls)."
        )
    return lines


def summary_text(analysis: CutAnalysis, history: Optional[History] = None) -> str:
    return "\n".join(summary_lines(analysis, history))


def to_json(report: SealedReport, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent, sort_keys=True,
                      ensure_ascii=False)
