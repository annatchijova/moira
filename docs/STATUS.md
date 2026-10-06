# MOIRA — Project Status

**As of:** 2026-10-05, end of session
**HEAD:** `main` (see `git log`)

## What MOIRA is

Minimal causal cuts over decision histories: *what is the minimal
historical evidence required to flip a present decision?* Given a
deterministic oracle and an ordered history of transitions, it finds the
minimal sets of removals (`do(T_i = ∅)`) or edits (`do(T_i = T'_i)`) that
flip the verdict, and seals the result.

Origin: VIGÍA idea 33 (hypothesis lineage + counterfactuals) recast from
hypothesis-space to history-space.

## What exists today

| Piece | Status |
|-------|--------|
| `core/cuts.py` — minimal cut search (removals) | stable, tested |
| `core/cuts.py` — `find_minimal_interventions` (removals + replacements) | stable, tested |
| `core/transitions.py` — Transition/History/Edit/apply_edits | stable, boundary-validated |
| `core/canonicalize.py` — schema "3" (VIGIA v2 superset: canon keys + sets) | stable |
| `core/seal.py` — SHA-256 over canonical bytes, meta outside seal | stable |
| `core/oracle.py` — Decision + DecisionOracle protocol | stable |
| `oracles/hypothesis.py` — HypothesisOracle, VIGIA sort key | reference impl |
| `bridge/vigia_bundle.py` — VIGIA bundle → history + BandCountOracle (L-036 port) | working; models gate only, flags `reproduces_recorded` |
| `lineage.py` — near-misses, pivot signals, roadmap (ported) | ported, lightly used |
| `report.py` — sealed payload (schema moira.report/2) + human summary | stable |

## Audit history

- `docs/red-team/REDTEAM_ROUND1_2026-10-05.md` — 6 confirmed defects fixed
  (dict-key collision, frozenset hash-order leak, singleton overcount,
  unbound seal, tid ordering, test fragility).
- `docs/red-team/REDTEAM_ROUND2_2026-10-05.md` — 5 confirmed defects fixed
  (ghost edits, invisible mutagen truncation, schema ambiguity,
  silent z_score degradation, dropped signals) + version stamp corrected
  to "3".

## Invariants (enforced, tested)

- No floats in the decision path (Fraction only; `elapsed_seconds` is
  excluded from sealed payloads).
- One canonical encoder; seals reproducible across `PYTHONHASHSEED`.
- Fail-closed boundaries: malformed history/bundle/edits raise, never
  silently degrade.
- Honest coverage: `exhaustive=False` + `complete_sizes` + mutation
  truncation counts when the bound isn't fully explored.
- The seal binds `history_fingerprint` + `oracle_id`; timestamps live in
  `meta`, outside the seal.

## Verify

```bash
cd ~/moira
python3 -m unittest discover -s tests   # 49 tests
python3 examples/staging_decision.py
```

## Open work (tomorrow)

- Weighted minimality — cuts by cost per transition, not cardinality.
- MARCO-style seed enumeration for large histories (n > ~60).
- Baseline/menu re-run check to detect nondeterministic oracle/mutagen
  (RT1-F9 / RT2-F8).
- `depended_on` tri-state: "not tracked" vs "used zero positions".
- `strict=False` continuation mode for oracle/mutagen exceptions
  (currently fail-loud by design — decide before implementing).
- lineage.py is ported but not yet wired into any oracle output —
  either integrate (near-misses into the report) or trim.
- vigia-repo: local commit `661ce09f` (fail-closed v2 hardening,
  RT1-F1/F2/F4 port) is committed but NOT pushed — maintainer to decide.
  Restore point tag `pre-session-20261005-2352` exists.

## Notes for the next session

- Read `AGENTS.md` before editing — invariants are enforced there.
- Intervention `describe()` names positions by ORIGINAL `seq` (T17 stays
  T17); `positions` in payloads are indices into the input history.
- `result_kind` discriminates `minimal_cuts` vs `minimal_interventions`
  in the sealed payload (schema `moira.report/2`).
- The bridge is intentionally honest about scope: gate-level cuts are
  not verdict-level cuts; `reproduces_recorded=False` on reasoner-verdict
  bundles is the expected, correct outcome.
