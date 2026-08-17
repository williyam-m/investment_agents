"""
investment_agents.analysis
==========================

Analysis utilities for the investment committee debate system.

Public exports
--------------
DivergenceScorer
    Scores how much analyst agents disagree after each debate round,
    combining recommendation variance, semantic divergence, and conflict
    detection into a single composite score.

ConflictResolver
    Decides how to handle detected conflicts — whether to flag-and-continue,
    spawn a tiebreaker, or flag the committee as divided.

ConvergenceDetector
    Identifies topics/themes where agents are converging (close numeric
    scores *and* semantically similar key arguments).
"""

from investment_agents.analysis.conflict import (
    ConflictResolution,
    ConflictResolutionAction,
    ConflictResolver,
)
from investment_agents.analysis.convergence import ConvergenceDetector
from investment_agents.analysis.divergence import DivergenceScorer

__all__ = [
    "DivergenceScorer",
    "ConflictResolver",
    "ConflictResolution",
    "ConflictResolutionAction",
    "ConvergenceDetector",
]
