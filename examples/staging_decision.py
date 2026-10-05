"""
examples/staging_decision.py
============================
The running example: an agent answered "staging is mandatory". MOIRA answers
the follow-up — what would it take to change that answer?

Scenario: a 14-step agent session. Two transitions carried the decisive
evidence (T17 observed the deploy guard, T23 observed the written policy);
the rest are context. A competing hypothesis ("staging is optional") loses by
a margin of one missing signal, so removing either T17 or T23 alone is not
enough — removing both flips the decision.

Run:  python3 examples/staging_decision.py
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moira.core.cuts import find_minimal_cuts
from moira.core.transitions import Transition
from moira.oracles.hypothesis import Hypothesis, HypothesisOracle
from moira.report import seal_analysis, summary_text, to_json


def build_case():
    oracle = HypothesisOracle([
        Hypothesis(
            hypothesis_id="H_STAGING_MANDATORY",
            verdict="staging is mandatory",
            required_signals=frozenset({"deploy_guard_seen", "policy_seen"}),
        ),
        Hypothesis(
            hypothesis_id="H_STAGING_OPTIONAL",
            verdict="staging is optional",
            required_signals=frozenset({"fastlane_seen"}),
            base_cost=Fraction(3, 2),  # Ockham penalty: the lazy reading
        ),
    ])

    steps = [
        (0,  "read issue tracker",        {"issue_opened"}),
        (3,  "list repo files",           {"repo_listed"}),
        (5,  "open CI config",            {"ci_config_seen"}),
        (8,  "grep deploy scripts",       {"deploy_script_seen"}),
        (11, "read contributing guide",   {"contrib_seen"}),
        (14, "check branch protection",   {"branch_protection_seen"}),
        (17, "open deploy guard",         {"deploy_guard_seen"}),
        (19, "read README badge",         {"badge_seen"}),
        (23, "open staging policy doc",   {"policy_seen"}),
        (25, "list environments",         {"envs_seen"}),
        (28, "check secrets store",       {"secrets_seen"}),
        (30, "open fastlane doc",         {"fastlane_seen"}),
        (33, "check rollback playbook",   {"rollback_seen"}),
        (36, "read oncall notes",         {"oncall_seen"}),
    ]
    history = tuple(
        Transition(seq=seq, kind="observation",
                   signals=frozenset(sig), label=label)
        for seq, label, sig in steps
    )
    return oracle, history


def main() -> int:
    oracle, history = build_case()
    analysis = find_minimal_cuts(oracle, history, max_cut_size=3)
    report = seal_analysis(analysis, history,
                           oracle_id="HypothesisOracle/vigia-sort-key")

    print("=" * 64)
    print("MOIRA — minimal causal cuts")
    print("=" * 64)
    print(summary_text(analysis, history))
    print()
    print(f"oracle calls: {analysis.coverage.oracle_calls} | "
          f"exhaustive to size {analysis.coverage.complete_sizes} | "
          f"elapsed: {float(analysis.coverage.elapsed_seconds):.3f}s")
    print(f"seal: {report.seal}")
    print()
    print(to_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
