"""
Synthesis data models — final committee memo output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from investment_agents.models.agent_output import AgentType, Recommendation


class ReasoningStep(BaseModel):
    """A traceable reasoning step in the synthesis process."""

    step: str = Field(..., description="E.g. 'weighted_votes', 'conflict_resolution'")
    description: str
    input_summary: str
    output_summary: str


class DissentingView(BaseModel):
    """A dissenting view that did not make it into the majority recommendation."""

    agent_type: AgentType
    recommendation: Recommendation
    conviction: float
    key_argument: str
    why_not_adopted: str = Field(..., description="Why synthesis chose not to follow this view")


class CommitteeMemo(BaseModel):
    """
    Final investment committee memo — the synthesis agent's structured output.
    This is the deliverable: a production-quality investment recommendation
    with full reasoning trace.
    """

    # Verdict
    final_recommendation: Recommendation
    conviction: float = Field(
        ..., ge=0.0, le=1.0,
        description="Committee's overall conviction in the recommendation"
    )
    vote_breakdown: dict = Field(
        default_factory=dict,
        description="How many agents supported each recommendation: {'buy': 3, 'sell': 1, ...}"
    )

    # The memo body (structured, not free-form)
    executive_summary: str = Field(
        ..., max_length=600,
        description="2-3 sentence executive summary for a portfolio manager"
    )
    key_thesis: str = Field(
        ..., max_length=500,
        description="The core investment thesis the committee evaluated"
    )
    bull_case: str = Field(
        ..., max_length=500,
        description="The strongest bull case arguments that emerged from debate"
    )
    bear_case: str = Field(
        ..., max_length=500,
        description="The strongest bear case arguments that emerged from debate"
    )
    key_risks: List[str] = Field(
        ..., min_length=1, max_length=5,
        description="Top 1-5 risks identified by the committee"
    )
    catalysts_to_watch: List[str] = Field(
        default_factory=list,
        description="Key catalysts that could change the recommendation"
    )

    # Debate dynamics
    debate_was_contentious: bool = Field(
        default=False,
        description="True if there were hard conflicts or committee was divided"
    )
    committee_divided: bool = Field(
        default=False,
        description="True if the committee could not reach clear consensus"
    )
    dissenting_views: List[DissentingView] = Field(
        default_factory=list,
        description="Views that didn't make it into the majority recommendation"
    )

    # Reasoning trace
    reasoning_trace: List[ReasoningStep] = Field(
        default_factory=list,
        description="Step-by-step reasoning the synthesis agent followed"
    )

    # Metadata
    total_rounds: int
    total_tokens_used: int
    model_used: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    synthesis_quality: str = Field(
        default="full",
        description="full | partial | degraded (based on available data)"
    )
