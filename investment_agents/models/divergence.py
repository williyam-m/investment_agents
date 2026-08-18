"""
Divergence and conflict detection data models.
Used by the DivergenceScorer to assess how much agents disagree.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ConflictSeverity(str, Enum):
    SOFT = "soft"       # Disagreement but not opposing conclusions
    HARD = "hard"       # Directly opposing recommendations (BUY vs SELL)
    FACTUAL = "factual" # Agents make contradictory factual claims


class ConflictPoint(BaseModel):
    """A detected conflict between two agents."""

    conflict_id: str
    agent_a: str  # agent_type
    agent_b: str  # agent_type
    severity: ConflictSeverity
    description: str = Field(..., description="What specifically they disagree on")
    agent_a_position: str
    agent_b_position: str
    score_gap: float = Field(..., ge=0.0, le=2.0, description="|score_a - score_b|")
    resolved: bool = False
    resolution_notes: Optional[str] = None
    detected_at_round: int = Field(..., ge=1)


class ConvergenceSignal(BaseModel):
    """A signal that agents are converging on a specific point."""

    topic: str = Field(..., description="What topic/aspect they are converging on")
    converging_agents: List[str]  # agent_types
    avg_score: float
    score_std_dev: float
    round_number: int


class DivergenceReport(BaseModel):
    """
    Full divergence analysis after a debate round.
    Drives the explore-exploit routing decision.
    """

    round_number: int
    overall_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="0=full consensus, 1=max disagreement"
    )

    # Component scores
    recommendation_variance: float = Field(
        ..., ge=0.0, le=1.0,
        description="Normalized std dev of numeric recommendation scores (40% weight)"
    )
    semantic_divergence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Mean pairwise embedding distance of key arguments (35% weight)"
    )
    conflict_penalty: float = Field(
        ..., ge=0.0, le=1.0,
        description="Penalty from detected hard conflicts (25% weight)"
    )

    # Conflict data
    conflicts: List[ConflictPoint] = Field(default_factory=list)
    has_hard_conflicts: bool = False

    # Convergence data
    converging_topics: List[ConvergenceSignal] = Field(default_factory=list)

    # For exploit mode — ranked list of most distinctive agents
    exploit_worthy_agents: List[str] = Field(
        default_factory=list,
        description="Agent types ranked by how distinctive their position is (most → least)",
    )

    # Score breakdown per agent
    agent_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="numeric_score per agent_type this round",
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_high_divergence(self) -> bool:
        from investment_agents.config.settings import get_settings
        return self.overall_score > get_settings().explore_threshold

    @property
    def is_converging(self) -> bool:
        from investment_agents.config.settings import get_settings
        return self.overall_score < get_settings().exploit_threshold

    @property
    def is_transition(self) -> bool:
        from investment_agents.config.settings import get_settings
        s = get_settings()
        return s.exploit_threshold <= self.overall_score <= s.explore_threshold
