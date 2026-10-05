"""MOIRA - minimal causal cuts over decision histories.

Research question: what is the minimal historical evidence required to flip
a present decision?
"""
from .core.transitions import Transition, History
from .core.oracle import Decision, DecisionOracle
from .core.cuts import find_minimal_cuts, CutAnalysis, CausalCut
from .core.seal import SealedReport, seal_payload
from .report import seal_analysis, summary_text, to_json

__all__ = [
    "Transition", "History", "Decision", "DecisionOracle",
    "find_minimal_cuts", "CutAnalysis", "CausalCut",
    "SealedReport", "seal_payload",
    "seal_analysis", "summary_text", "to_json",
]

__version__ = "0.1.0"
