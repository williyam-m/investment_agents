"""
Agent output data models.
Every analyst agent produces a strictly-typed, Pydantic-validated output.
No free text flows between system components.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentType(str, Enum):
    VALUE_INVESTOR = "value_investor"
    MOMENTUM_TRADER = "momentum_trader"
    RISK_ANALYST = "risk_analyst"
    MACRO_ECONOMIST = "macro_economist"
    CONTRARIAN = "contrarian"
    TIEBREAKER = "tiebreaker"
    SYNTHESIS = "synthesis"


class Recommendation(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    INSUFFICIENT_DATA = "insufficient_data"


# Map recommendations to numeric scores for divergence math
RECOMMENDATION_SCORES: Dict[Recommendation, float] = {
    Recommendation.STRONG_BUY: 1.0,
    Recommendation.BUY: 0.5,
    Recommendation.HOLD: 0.0,
    Recommendation.SELL: -0.5,
    Recommendation.STRONG_SELL: -1.0,
    Recommendation.INSUFFICIENT_DATA: 0.0,
}


class Evidence(BaseModel):
    """A single piece of supporting evidence cited by an agent."""

    claim: str = Field(..., description="The specific factual claim or data point")
    source_type: str = Field(
        ..., description="Type: financial_metric | macro_data | technical | qualitative"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Agent confidence in this evidence (0-1)"
    )
    supports_thesis: bool = Field(
        ..., description="True if this evidence supports the investment thesis"
    )


class AgentResponse(BaseModel):
    """An agent's direct response to another agent's argument (cross-agent dialogue)."""

    responding_to_agent: AgentType
    agreement_level: float = Field(
        ..., ge=-1.0, le=1.0, description="-1.0 strong disagree, +1.0 strong agree"
    )
    rebuttal: str = Field(..., description="Direct, specific response to the other agent's argument")
    concession: Optional[str] = Field(
        None, description="Any point the agent concedes to the other agent"
    )


class AnalystOutput(BaseModel):
    """
    Fully-structured output from a single analyst agent in a single round.
    This is the atomic unit of the debate — every agent call produces one of these.
    """

    # Identity
    agent_id: str = Field(..., description="Unique identifier e.g. 'value_investor_r1'")
    agent_type: AgentType
    round_number: int = Field(..., ge=1)

    # Core verdict
    recommendation: Recommendation
    conviction_score: float = Field(
        ..., ge=0.0, le=1.0, description="How confident the agent is in their recommendation"
    )
    numeric_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Numeric representation: -1.0 (strong sell) to +1.0 (strong buy)",
    )

    # Primary reasoning (structured, not free-form)
    thesis_agreement: str = Field(
        ...,
        max_length=400,
        description="Concise statement: does agent agree/disagree with main thesis and why",
    )
    key_argument: str = Field(
        ...,
        max_length=600,
        description="The single most important argument this agent makes this round",
    )
    supporting_evidence: List[Evidence] = Field(
        ..., min_length=1, max_length=5, description="1-5 pieces of supporting evidence"
    )

    # Agent-type-specific analysis fields (flexible dict, validated by agent)
    agent_specific_analysis: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific metrics: DCF data, momentum scores, risk scenarios, etc.",
    )

    # Cross-agent dialogue (round > 1)
    response_to_agents: Optional[List[AgentResponse]] = Field(
        None, description="Direct responses to other agents' arguments (only in round 2+)"
    )
    position_changed: bool = Field(
        default=False,
        description="Did this agent meaningfully update their position from last round?",
    )
    position_change_reason: Optional[str] = Field(
        None, description="Why the position changed (if position_changed is True)"
    )

    # Budget tracking
    tokens_used: int = Field(default=0, ge=0)
    tokens_allocated: int = Field(default=0, ge=0)

    # Metadata
    model_used: str = Field(default="", description="LiteLLM model string used for this call")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_llm_response: Optional[str] = Field(
        None, description="Raw LLM text before parsing (for debugging)", exclude=True
    )

    @field_validator("numeric_score", mode="before")
    @classmethod
    def clamp_numeric_score(cls, v: float) -> float:
        return max(-1.0, min(1.0, float(v)))

    @field_validator("conviction_score", mode="before")
    @classmethod
    def clamp_conviction(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    def budget_utilization(self) -> float:
        """Ratio of tokens used vs allocated. >1.0 means over budget."""
        if self.tokens_allocated == 0:
            return 0.0
        return self.tokens_used / self.tokens_allocated

    class Config:
        use_enum_values = False
