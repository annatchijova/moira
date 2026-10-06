# Security Audit — MOIRA v0.1.0
## Red Team Round 2

**Date:** 2026-10-05  **Method:** Abductive Engineering (A–D–I) + Red-Team Auditing
**Scope:** the deltas since RT1 — `find_minimal_interventions` /
`Edit` / `apply_edits` (do(T = T')), `moira/bridge/vigia_bundle.py`,
intervention support in `report.py`, `Coverage` extensions. RT1 findings
are not re-audited.
**Base:** `main` @ `c756947` (pre-fix state audited; fixes verified per finding)
**Python:** 3.12.3

## Threat model

- Attacker CAN: supply the history, the mutagen, the oracle, and a VIGIA
  bundle file to the bridge; present a sealed report to a third party.
- Attacker CANNOT: modify MOIRA's code or a sealed payload without
  detection.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Executive summary

| ID | Severity | Level | Module | Finding | Disposition |
|----|----------|-------|--------|---------|-------------|
| RT2-F1 | Medium | CONFIRMED | transitions | Out-of-range `Edit.position` silently no-ops — ghost edit counted as applied | FIXED |
| RT2-F2 | Medium | CONFIRMED | cuts | Mutagen output truncated at 16/position with no record — coverage claim spanned an untested menu | FIXED |
| RT2-F3 | Low | CONFIRMED | report | Interventions serialized under `minimal_cuts` key without `tids` — sealed shape ambiguity | FIXED |
| RT2-F4 | Low | CONFIRMED | bridge | Malformed/absent `z_score` silently became `z:low` — corrupted evidence indistinguishable from measured-weak | FIXED |
| RT2-F5 | Low | CONFIRMED | bridge | Non-dict signal entries silently dropped — denominator of the gate changed with no trace | FIXED |
| RT2-F6 | Cosmetic | CODE FACT | cuts | `describe()` used `str(frozenset)` — hash-order-dependent narrative text (unsealed only) | FIXED |
| RT2-F7 | Low | CONFIRMED | canonicalize | MOIRA's encoder stamped "2" while implementing strict-superset semantics of VIGIA v2 — false lockstep claim | FIXED (stamped "3") |
| RT2-F8 | — | THREAT-MODEL | cuts | Nondeterministic mutagen produces unstable menus — same contract class as RT1-F9 | DOCUMENTED |
| RT2-F9 | — | CODE FACT | bridge | Bridge models the L-036 gate only; reasoner-layer verdicts are not reproducible by design | DOCUMENTED (flagged via reproduces_recorded) |

## Findings

### RT2-F1 — Out-of-range edit positions silently ignored

**Severity:** Medium  **Level:** CONFIRMED BY INDUCTION  **Bucket:** vuln (boundary validation)

- **Abduction:** `apply_edits` maps edits by `by_pos.get(i)` while iterating
  history positions — a position beyond the history never matches and the
  edit evaporates, yet the caller's edit set records it as applied.
- **Deduction:** `apply_edits([T0], {Edit(5,"remove")})` returns the full
  tuple unchanged with no error.
- **Induction:** observed `len(out) == 1`. CONFIRMED. The searcher can never
  produce this (positions come from `combinations(range(n))`), but
  `apply_edits` is public API — a caller-built edit set could carry ghost
  edits that a sealed intervention would describe as applied.
- **Fix:** positions are validated `0 <= p < len(history)` — ValueError at
  the boundary. Regression: `test_out_of_range_edit_rejected`.

### RT2-F2 — Mutation menu truncation invisible to coverage

**Severity:** Medium  **Level:** CONFIRMED BY INDUCTION  **Bucket:** vuln (honest-degradation)

- **Abduction:** `mutations[:MAX_MUTATIONS_PER_POSITION]` silently caps the
  per-position menu; `Coverage` then reports `exhaustive=True` over a
  search space the caller never fully specified — the truncation existed
  nowhere in the sealed payload.
- **Deduction:** mutagen returning 20 mutations → `oracle_calls` reflects
  16, and no field records the 4 dropped.
- **Induction:** `mutations_offered`/`mutations_truncated` were absent from
  `Coverage` entirely. CONFIRMED.
- **Fix:** `Coverage` gains `mutations_offered` and `mutations_truncated`
  (null in the removal-only path — absent feature, not false claim). Both
  sealed in the payload. Regression: `test_mutation_truncation_is_recorded`.

### RT2-F3 — Intervention results serialized under the wrong key

**Severity:** Low  **Level:** CONFIRMED BY INDUCTION  **Bucket:** schema integrity

- The sealed payload emitted interventions under `minimal_cuts`, but
  intervention entries carry `edits` and no `tids` — a consumer reading the
  documented cut shape would fail on missing fields, inside a seal that
  claims schema `moira.report/1`.
- **Fix:** payload now carries `result_kind`
  (`minimal_cuts` | `minimal_interventions`) with the matching key;
  `SCHEMA_VERSION` bumped to `moira.report/2` since the shape changed.
  Regression: `test_sealed_payload_records_edits`.

### RT2-F4 — Malformed `z_score` downgraded silently to `z:low`

**Severity:** Low  **Level:** CONFIRMED BY INDUCTION  **Bucket:** honest degradation

- **Deduction:** `_to_frac("garbage")`, `_to_frac(None)`, `_to_frac({})` all
  return `Fraction(0)` — corrupted evidence becomes numerically weakest
  evidence, indistinguishable in the history from a real 0.
- **Induction:** observed `0` for all three. CONFIRMED.
- **Fix:** `_try_frac` strict parser; history now emits `z:absent` (key
  missing) and `z:malformed` (present but unparseable) tokens —
  numerically identical to `z:low` (counts toward neither band) but
  observable and individually cuttable. Regression:
  `test_malformed_and_absent_z_are_visible`.

### RT2-F5 — Non-dict signals dropped without trace

**Severity:** Low  **Level:** CONFIRMED BY INDUCTION  **Bucket:** boundary validation

- `history_from_bundle` skipped non-dict entries via `continue` — a
  bundle with 3 malformed signals produced a 1-transition history, and the
  gate's denominator silently shrank.
- **Induction:** `[dict, "x", 42, None]` → `len(hist) == 1`. CONFIRMED.
- **Fix:** `ValueError` naming the index and type — malformed bundle,
  loud. Regression: `test_non_dict_signal_fails_closed`.

### RT2-F6 — `describe()` narrative used `str(frozenset)`

**Severity:** Cosmetic (unsealed text only)  **Level:** CODE FACT
Label-less replacements rendered `str(e.replacement.signals)` — hash-order
dependent text in the human summary. Fixed: sorted join. The sealed payload
was never affected (signals are sorted there).

### RT2-F7 — Canonicalizer stamped "2" while implementing superset semantics

**Severity:** Low  **Level:** CONFIRMED (follows from RT1-F1/F2 fixes)
The RT1 fixes gave MOIRA's encoder canonical dict keys and set ordering —
a strict superset of VIGIA v2, byte-identical on v2-legal payloads but
divergent beyond them. Stamping `CANONICALIZE_VERSION = "2"` claimed a
lockstep that no longer exists. Now stamped `"3"` with a version note.
A consumer comparing seals across the two encoders must read the version.

### RT2-F8 — Nondeterministic mutagen

**Level:** THREAT-MODEL ASSUMPTION (same class as RT1-F9)
A mutagen that returns different mutation sets per call yields unstable
menus; the analysis is still faithfully searched but reports an unstable
result. Contract documented; detection is a candidate feature (re-run and
compare `mutations_offered`).

### RT2-F9 — The bridge models the gate, not the reasoner

**Level:** CODE FACT, by design
Real bundles can carry verdicts the L-036 gate cannot reproduce (the
reasoner layer produced them). Verified on can018/031/038 — all flag
`reproduces_recorded=False`. Not a defect; the flag is the honest claim.
Recorded so a future reader doesn't mistake gate-level cuts for
verdict-level cuts.

## Discarded (non-exploitable) vectors

| Vector | Result | Why it failed |
|--------|--------|---------------|
| Edit-superset pruning skips a minimal intervention | FALSIFIED | Same argument as RT1: a candidate is skipped only when a recorded flipping *edit set* is its proper subset — non-minimal by definition. Replacements don't change this: `remove T17` and `replace T17->X` are distinct edits, so `{remove T17} ⊆ {remove T17, replace T23->Y}` prunes correctly while `{replace T17->X, remove T1}` is not a superset of `{remove T17}` and is correctly still tested. |
| Replacement of a transition with an identical one counted as a cut | FALSIFIED | `apply_edits` with an identical replacement yields the same history — the baseline token cannot flip. Harmless wasted call, bounded by the menu cap. |
| Two actions on the same position in one candidate | FALSIFIED | `product(*(menus[i] for i in combo))` picks exactly one edit per chosen position; `apply_edits` validates uniqueness anyway. |
| Mutagen returning non-Transition mutations | FALSIFIED | `Edit.__post_init__` rejects a `replace` without a `Transition` — fail-closed at menu construction. |

## Recommendations (recorded, out of scope)

- `strict=False` continuation for oracle/mutagen exceptions (same class as
  RT1's F7 note).
- Baseline/menu re-run checks for nondeterministic oracle + mutagen (F8).
- Weighted minimality and MARCO-style seed enumeration remain roadmap.
