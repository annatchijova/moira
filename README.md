# MOIRA — minimal causal cuts over decision histories

> *What is the minimal historical evidence required to flip a present decision?*

MOIRA answers the question every decision system ducks: **what would it take
to change this answer?** Given a deterministic decision oracle and the
ordered history of transitions it consumed, MOIRA searches for the *minimal
causal cuts* — the smallest sets of historical transitions whose absence
(`do(T_S = ∅)`) changes the outcome.

```
Decision under test: 'staging is mandatory'.
Current decision depends causally on 14 historical transitions.
Decision-critical transitions: 2 of 14.
Removing any single tested transition is insufficient; the smallest decisive cut has size 2.
Removing {T17, T23} changes the decision to 'staging is optional'.
All other tested removals preserve it.
```

This is counterfactual explanation *minimization*, not replay: not "here is
what happened", but "here is the smallest change to what happened that
changes what was decided".

## Origin

Ported from VIGÍA (`vigia-intent-analysis`), idea 33 — hypothesis lineage and
counterfactuals — and re-cast from hypothesis-space to history-space. VIGÍA's
counterfactual engine asks *which hypothesis would win if evidence differed*;
MOIRA asks *which history would have produced a different decision*. The
selection rule (`cost, -coverage, len(required)`), the canonical serializer,
the Fraction-only decision path, and the lineage tracker are carried over
near-verbatim; the cut search is new.

## Concepts

- **Transition** — one recorded step in a history (`seq`, `kind`, `signals`,
  `label`). `T17` = the transition with `seq` 17; labels survive removal.
- **Oracle** — anything implementing `decide(history) -> Decision`.
  Deterministic, side-effect free. The decision `token` is the flip
  criterion; MOIRA never interprets verdicts.
- **Cut** — a set of positions whose removal flips the baseline token.
- **Minimal cut** — a cut with no proper subset that also flips. Every member
  is load-bearing.
- **Decision-critical** — a position belonging to at least one minimal cut.

## Correctness and bounds

The flip predicate is not monotone under removal — removing more transitions
can flip the decision back. Minimality is still well-defined under inclusion:
the search enumerates candidate sets in increasing size order and prunes
strict supersets of known cuts (a superset of a cut can never be minimal).

The search is combinatorial — `C(n, ≤k)` oracle calls. Hard caps:

| Bound | Default | Hard cap |
|---|---|---|
| history length | — | 256 transitions |
| cut size | 3 | 8 |
| oracle calls | 50 000 | caller-set |

If the budget is exhausted, the result is not a silent partial: `coverage`
states exactly which cut sizes were fully explored (`complete_sizes`) and
`exhaustive=False`. A bounded result is a WARN, never a silent PASS.

## Determinism and sealing

Inherited invariants from VIGÍA:

- **No floats in the decision path** — scores are `Fraction`.
- **Canonical v2 serialization** — type-tagged (`1`, `"1"`, `1.0`, `True` are
  distinct), key-sorted, `CANONICALIZE_VERSION`-stamped.
- **SHA-256 seal** over the payload; timestamps and run metadata live outside
  the seal, so identical analyses seal identically.
- Verified by test: identical seals across runs and across processes with
  different `PYTHONHASHSEED`.

## Usage

```python
from fractions import Fraction
from moira import Transition, find_minimal_cuts, summary_text
from moira.oracles.hypothesis import Hypothesis, HypothesisOracle

oracle = HypothesisOracle([
    Hypothesis("H_MAND", "staging is mandatory",
               frozenset({"deploy_guard_seen", "policy_seen"})),
    Hypothesis("H_OPT", "staging is optional",
               frozenset({"fastlane_seen"}), base_cost=Fraction(3, 2)),
])
history = (... )  # tuple of Transition

analysis = find_minimal_cuts(oracle, history, max_cut_size=3)
print(summary_text(analysis))
```

Or your own oracle — implement `decide(history) -> Decision` and MOIRA
searches it unchanged. Run the demo:

```bash
python3 examples/staging_decision.py
python3 -m unittest discover -s tests
```

## Layout

```
moira/core/canonicalize.py   canonical v2 serializer (ported, lockstep)
moira/core/transitions.py    Transition / History / do(T_S = ∅)
moira/core/oracle.py         Decision + DecisionOracle protocol
moira/core/cuts.py           minimal causal cut search (the core)
moira/core/seal.py           SHA-256 sealing over canonical bytes
moira/oracles/hypothesis.py  reference oracle, VIGIA sort key
moira/lineage.py             hypothesis lineage: near-misses, pivots, roadmap
moira/report.py              sealed report + human summary
```

## Roadmap

- `do(T_i = T'_i)` replacement interventions, not only removal.
- Weighted minimality (cost-per-transition cuts, not cardinality).
- MARCO-style seed-based enumeration for large histories.
- Bridge: run MOIRA over VIGÍA's sealed bundles (abduction trace as history).

## License

Same terms as the parent project.
