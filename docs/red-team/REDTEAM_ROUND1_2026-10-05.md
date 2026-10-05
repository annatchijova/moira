# Security Audit — MOIRA v0.1.0
## Red Team Round 1

**Date:** 2026-10-05  **Method:** Abductive Engineering (A–D–I) + Red-Team Auditing
**Scope:** `moira/core/*` (transitions, oracle, cuts, canonicalize, seal),
`moira/oracles/hypothesis.py`, `moira/report.py`, `moira/lineage.py`,
`tests/`, `examples/`. Not in scope: `lineage.py` internals beyond the port
(it is VIGIA code carried over, audited there), packaging, CLI surface.
**Base:** `main` @ `9dab09a` (pre-fix state audited; fixes verified and noted
per finding)  **Python:** 3.12.3
**Reproducible evidence:** induction scripts are inlined per finding; the
regression tests referenced by ID are in `tests/`.

## Threat model

- Attacker CAN: supply the input `history` (transitions, signals, labels,
  order), supply or configure the oracle, and present a sealed report to a
  third party against an input of their choosing.
- Attacker CANNOT: modify MOIRA's code, modify a payload after sealing
  without detection, or make a deterministic oracle nondeterministic without
  violating the oracle contract.
- Out of scope as "game over": an attacker who controls the oracle itself
  controls the decisions; MOIRA's guarantee reduces to faithful search.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Executive summary

| ID | Severity | Level | Module | Finding | Disposition |
|----|----------|-------|--------|---------|-------------|
| RT1-F1 | Medium | CONFIRMED | canonicalize | Dict keys not canonicalized: `{1:x}` and `{"1":x}` seal identically | FIXED |
| RT1-F2 | Medium | CONFIRMED | canonicalize | `set`/`frozenset` fallback `str()` is hash-order dependent — latent cross-process seal instability | FIXED |
| RT1-F3 | Low | CONFIRMED | cuts | `tested_singletons` recorded positions the oracle never evaluated | FIXED |
| RT1-F4 | Low | CONFIRMED | canonicalize | Mixed-type dict keys crash `sorted()` (TypeError) | FIXED (via F1) |
| RT1-F5 | Medium | CONFIRMED | report | Sealed payload bound to no input — seal proved self-consistency only | FIXED |
| RT1-F6 | Cosmetic | CONFIRMED | cuts | `tids` sorted lexicographically ("T10" < "T2") | FIXED |
| RT1-F7 | — | CODE FACT | cuts | Oracle exception mid-search discards all partial results | DOCUMENTED (fail-loud by design) |
| RT1-F8 | Low | CONFIRMED | tests | Cross-process test replaced `os.environ`, assumed cwd | FIXED |
| RT1-F9 | — | THREAT-MODEL | oracle.py | Nondeterministic oracle produces clean-looking garbage cuts | DOCUMENTED (contract requirement) |

## Findings

### RT1-F1 — Dict keys bypass canonicalization → type collision in sealed space

**Severity:** Medium  **Epistemic level:** CONFIRMED BY INDUCTION  **Bucket:** vuln (semantic integrity)

- **Abduction:** the v2 schema canonicalizes dict *values* recursively but
  leaves *keys* raw. If so, `json.dumps` coerces non-str keys, and an int
  key `1` and a str key `"1"` must collide — exactly the class v2 was built
  to close for scalars.
- **Deduction (stated before running):** `seal_payload({1:"x"}) ==
  seal_payload({"1":"x"})`.
- **Induction:** ran; seals were **identical** (`True`). CONFIRMED.
- **Causal chain:** `canonicalize` returns `{k: canon(v)}` with raw `k` →
  `json.dumps` coerces int key to `"1"` → identical bytes → identical digest.
- **Fix:** keys are now canonicalized through the same scalar encoding
  (always strings → total sort, no crash); `{1:x}` → `{"1:int": "s:x"}` vs
  `{"1":x}` → `{"s:1": "s:x"}`. Post-fix induction: seals differ. Regression:
  `test_dict_key_types_do_not_collide`.
- **Note:** inherited verbatim from VIGIA's v2 encoder; the same defect is
  live there. Worth an upstream patch.

### RT1-F2 — `set`/`frozenset` fallback leaks hash-order into the seal

**Severity:** Medium (latent — no current payload contains a set)  **Level:** CONFIRMED BY INDUCTION  **Bucket:** vuln (determinism)

- **Abduction:** the fallback `str(obj)` on a frozenset embeds Python's
  hash-randomized iteration order in the canonical form — the exact
  `PYTHONHASHSEED` leak the determinism test exists to catch, hiding in a
  fallback nobody typed yet.
- **Deduction:** two processes with `PYTHONHASHSEED=1` vs `2` print different
  canonical forms for the same frozenset.
- **Induction:** observed —
  `s:frozenset({'beta','delta','gamma','alpha'})` vs
  `s:frozenset({'delta','gamma','alpha','beta'})`. CONFIRMED.
- **Fix:** sets canonicalize to a list sorted by each element's canonical
  JSON — a total, hash-independent order. Post-fix: identical output under
  both seeds. Regression: `test_frozenset_stable_form`.

### RT1-F3 — `tested_singletons` claimed tests that never ran

**Severity:** Low (reporting accuracy, not correctness of cuts)  **Level:** CONFIRMED BY INDUCTION  **Bucket:** vuln (honest-degradation violation)

- **Deduction:** with `oracle_budget=1` (baseline consumes the only call),
  `tested_singletons` should be empty — but the code added the position
  *before* `decide_guarded` could raise.
- **Induction:** `oracle_calls=1`, `tested_singletons={0}` — position 0 was
  reported tested although the oracle never saw its removal. CONFIRMED.
- **Why it matters:** this set exists to support coverage claims. An
  overcount is exactly the false-PASS shape §5.3 forbids.
- **Fix:** record after the oracle call returns. Regression:
  `test_tested_singletons_only_counts_ran`.

### RT1-F4 — Mixed-type dict keys crash the canonicalizer

**Severity:** Low  **Level:** CONFIRMED BY INDUCTION  **Bucket:** vuln (availability of the sealing path)

- **Deduction:** `canonicalize({1:"a","b":"c"})` raises TypeError —
  `sorted()` cannot compare `str` to `int`.
- **Induction:** `'<' not supported between instances of 'str' and 'int'`.
  CONFIRMED. Fixed by F1's canonical keys (uniformly strings). Regression:
  `test_mixed_type_dict_keys`.

### RT1-F5 — The seal bound to nothing (Round 3 — trust boundary)

**Severity:** Medium  **Level:** CONFIRMED BY INDUCTION  **Bucket:** architectural / trust-boundary gap

- **Abduction:** `payload_of` sealed the *claims* (baseline, cuts, coverage)
  but not the *subject* — no commitment to the history analyzed nor to the
  oracle that produced it. A seal over self-referential claims proves "these
  bytes didn't change", not "this analysis ran over that history".
- **Deduction:** `seal_analysis(analysis).seal` is identical whether the
  report is presented against history H or a different history H'.
- **Induction:** trivially true pre-fix — the history was not an input to
  the payload. CONFIRMED by inspection + post-fix divergence test.
- **Fix:** payload now carries `history_fingerprint` (SHA-256 over the
  canonicalized transitions) and `oracle_id`. Omitting history records
  `null` — visible, not hidden. Regression: `test_seal_binds_history`.
- **Residual honesty:** `oracle_id` is caller-attested, not a code
  fingerprint. MOIRA cannot prove which oracle ran; it can only bind what
  the caller declares. That boundary is stated, not sold.

### RT1-F6 — `tids` ordering lexicographic

**Severity:** Cosmetic  **Level:** CODE FACT  **Bucket:** hygiene
`tuple(sorted(hist[i].tid))` yields `["T10","T17","T2"]`. Fixed to numeric
seq order.

### RT1-F7 — Oracle exception mid-search loses all partial results

**Level:** CODE FACT  **Bucket:** design decision, documented
A non-budget exception from `oracle.decide()` propagates and discards the
entire analysis. Deliberate: silently continuing past an oracle failure
would emit partial results that look complete — the worse failure. Recorded
as a known constraint; a `strict=False` continuation mode is a candidate
feature, not a fix.

### RT1-F8 — Cross-process determinism test was itself fragile

**Severity:** Low  **Level:** CONFIRMED  **Bucket:** test hygiene
Replaced `os.environ` wholesale (dropping `HOME`, venv vars) and assumed
`cwd="."`. Fixed: env merged, cwd anchored to repo root via `__file__`.
The test then caught a real mismatch — the fixture's `label` field was absent
in the subprocess reproduction — which is the mechanism working as intended.

### RT1-F9 — Nondeterministic oracle → clean-looking garbage

**Level:** THREAT-MODEL ASSUMPTION (not a vuln)
Every guarantee inherits the oracle contract: `decide()` deterministic.
A nondeterministic oracle does not produce a detectable failure — it produces
cuts that look measured but are noise. Stated in `oracle.py`'s contract and
here; detection (re-run baseline, compare seals) is a candidate feature.

## Discarded (non-exploitable) vectors

| Vector | Result | Why it failed |
|--------|--------|---------------|
| Superset pruning unsound — a skipped superset might still be minimal | FALSIFIED | A candidate is skipped only when a recorded *flipping* set is a proper subset of it, which by definition makes it non-minimal. Recording only minimal flips suffices: any non-minimal flip contains a minimal one found at a smaller size, and enumeration is in increasing size order. Backed by `test_minimality_pruning` / `test_overlapping_pair_cuts`. |
| Float leaks into sealed payload | FALSIFIED | `elapsed_seconds` is excluded from `payload_of`; scores serialize as `str(Fraction)`. `test_timestamp_outside_seal` + payload inspection. |
| Combinatorial DoS via crafted history | FALSIFIED as defect | `MAX_HISTORY_LEN=256`, `MAX_CUT_SIZE_HARD_CAP=8`, `oracle_budget`; exhaustion returns honest partial coverage (`test_budget_exhaustion_is_honest`). |
| History `seq` collision across removals | FALSIFIED | `remove()` indexes by position; `seq` is a stable label. Duplicate `seq` rejected at the boundary. |

## Recommendations (recorded, out of scope of this change)

- Port the F1/F4 dict-key fix upstream to VIGIA's `canonicalize.py` (the
  collision is live there; verify against its v1-compatibility constraints
  first — v2 semantics change for dict-keyed payloads).
- Consider `strict=False` continuation mode for oracle failures (F7).
- Consider baseline re-run check to detect nondeterministic oracles (F9).
- `depended_on` conflates "oracle doesn't track" with "decision used zero
  positions" (empty `used` → `None`); a tri-state sentinel would disambiguate.
