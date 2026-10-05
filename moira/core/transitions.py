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
from typing import FrozenSet, Sequence, Tuple

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
