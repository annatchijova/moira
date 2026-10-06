# AGENTS.md — MOIRA engineering contract

Repo language: English (code, comments, commits, docs). No emojis.

## Invariants

- **No floats in the decision path.** Scores and costs are `Fraction`.
  Floats may appear only in display formatting, never in a sealed value.
- **One canonical encoder.** Everything sealed goes through
  `moira/core/canonicalize.py` (currently schema "3" — a strict superset of
  VIGIA v2). Do not add a second encoder, and do not change semantics
  without bumping `CANONICALIZE_VERSION`.
- **Seal covers payload only.** Timestamps and run metadata go in `meta`,
  outside the seal. Identical inputs must produce identical seals.
- **Honest coverage.** If the cut search cannot exhaust the bound, report
  `exhaustive=False` and `complete_sizes`. Never imply full coverage.
- **MOIRA does not interpret verdicts.** The flip criterion is the decision
  token; nothing else.

## Verification

```bash
python3 -m unittest discover -s tests
python3 examples/staging_decision.py
```

## Git

- Forward-only operations. No rebase, squash, or force-push in agent
  sessions.
