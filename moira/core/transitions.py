"""
moira/core/transitions.py
=========================
The objects MOIRA reasons about: an ordered history of transitions, and the
intervention primitive `do(T_i = empty)` — removing a set of transitions and
re-running the decision.

A Transition is deliberately minimal: it is any step in a recorded history
that may have contributed evidence (signals) to a decision. The oracle — not
MOIRA — decides how signals aggregate into a verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Sequence, Tuple

# Hard caps — resource exhaustion guards. A history is caller-supplied input;
# the cut search is combinatorial in its length.
MAX_HISTORY_LEN: int = 256
MAX_SIGNALS_PER_TRANSITION: int = 64
MAX_ID_LEN: int = 128


@dataclass(frozen=True)
class Transition:
    """One recorded step in the history a decision was built on.

    seq:      position in the original history (0-based). Stable identity for
              reporting ("T17" = the transition with seq 17); unlike list
              position it survives removals without renumbering confusion.
    kind:     coarse type ("tool_call", "observation", "config", ...). Opaque
              to MOIRA; carried for reporting.
    signals:  evidence contributed by this step. The oracle interprets them.
    label:    human-readable one-liner for the report.
    """
    seq:     int
    kind:    str
    signals: FrozenSet[str] = field(default_factory=frozenset)
    label:   str = ""

    @property
    def tid(self) -> str:
        return f"T{self.seq}"

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError(f"seq must be >= 0, got {self.seq}")
        if len(self.signals) > MAX_SIGNALS_PER_TRANSITION:
            raise ValueError(
                f"transition {self.tid} carries {len(self.signals)} signals; "
                f"cap is {MAX_SIGNALS_PER_TRANSITION}"
            )
        if len(self.label) > MAX_ID_LEN:
            raise ValueError(f"label exceeds {MAX_ID_LEN} chars")
        if len(self.kind) > MAX_ID_LEN:
            raise ValueError(f"kind exceeds {MAX_ID_LEN} chars")


History = Tuple[Transition, ...]


def validate_history(history: Sequence[Transition]) -> History:
    """Boundary validation for a caller-supplied history.

    Raises ValueError at the edge rather than letting a malformed history
    explode deep inside the cut search.
    """
    hist = tuple(history)
    if len(hist) > MAX_HISTORY_LEN:
        raise ValueError(
            f"history has {len(hist)} transitions; cap is {MAX_HISTORY_LEN}"
        )
    seen: set[int] = set()
    for t in hist:
        if not isinstance(t, Transition):
            raise ValueError(f"expected Transition, got {type(t).__name__}")
        if t.seq in seen:
            raise ValueError(f"duplicate seq {t.seq} in history")
        seen.add(t.seq)
    return hist


def remove(history: Sequence[Transition], indices: FrozenSet[int]) -> History:
    """do(T_S = empty): the history with the indexed positions removed.

    `indices` are POSITIONS in `history`, not seq values. The surviving
    transitions keep their original seq — T17 stays T17 wherever it lands.
    """
    return tuple(t for i, t in enumerate(history) if i not in indices)


@dataclass(frozen=True)
class Edit:
    """One atomic intervention on a history position.

    action:      "remove" (do(T_i = empty)) or "replace" (do(T_i = T'_i)).
    replacement: the substitute Transition for action="replace". Its signals
                 are what the oracle sees; its seq is advisory — reporting
                 always names the position by the ORIGINAL transition's tid.
    """
    position:    int
    action:      str
    replacement: Optional["Transition"] = None

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("position must be >= 0")
        if self.action not in ("remove", "replace"):
            raise ValueError(f"action must be 'remove' or 'replace', "
                             f"got {self.action!r}")
        if self.action == "replace" and not isinstance(
                self.replacement, Transition):
            raise ValueError("action='replace' requires a Transition "
                             "replacement")
        if self.action == "remove" and self.replacement is not None:
            raise ValueError("action='remove' takes no replacement")


def apply_edits(history: Sequence[Transition],
                edits: FrozenSet[Edit]) -> History:
    """do(T = T'): apply a set of edits to a history.

    At most one edit per position (enforced by construction in the searcher;
    validated here). Removals drop the position; replacements substitute the
    Transition object wholesale.
    """
    positions = [e.position for e in edits]
    if len(set(positions)) != len(positions):
        raise ValueError("at most one edit per position")
    by_pos = {e.position: e for e in edits}
    out = []
    for i, t in enumerate(history):
        e = by_pos.get(i)
        if e is None:
            out.append(t)
        elif e.action == "replace":
            out.append(e.replacement)
        # "remove" simply omits the position
    return tuple(out)
