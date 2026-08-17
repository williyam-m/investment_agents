"""
Debate request, trace, and round data models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from investment_agents.models.agent_output import AnalystOutput
from investment_agents.models.budget import BudgetSummary
from investment_agents.models.divergence import ConflictPoint, DivergenceReport
from investment_agents.models.synthesis import CommitteeMemo


class InvestmentContext(BaseModel):
    """Optional structured context about the investment being debated."""

    ticker: Optional[str] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    current_price: Optional[float] = None
    market_cap_bn: Optional[float] = None
    supporting_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary financial data: P/E, revenue growth, etc.",
    )
    relevant_documents: List[str] = Field(
        default_factory=list,
        description="Text snippets or document references for agents to use",
    )


class ModelConfig(BaseModel):
    """LLM model configuration for the debate."""

    model: str = Field(default="ollama/llama2:7b", description="LiteLLM model string")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens_per_call: int = Field(
        default=1000,
        description="Max tokens per individual LLM call (not total budget)",
    )
    ollama_base_url: str = Field(default="http://localhost:11434")


class DebateRequest(BaseModel):
    """Input to start a debate session."""

    thesis: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="The investment thesis to be debated",
    )
    investment_context: InvestmentContext = Field(default_factory=InvestmentContext)
    total_budget: int = Field(
        default=40000,
        gt=0,
        description="Total token budget for the entire debate",
    )
    max_rounds: int = Field(default=3, ge=1, le=5)
    model_config_: ModelConfig = Field(
        default_factory=ModelConfig,
        alias="model_config",
    )
    debate_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Optional: provide a custom ID, otherwise auto-generated",
    )

    model_config = {"populate_by_name": True}


class RoutingDecision(BaseModel):
    """The orchestrator's decision about what happens after a round."""

    after_round: int
    decision: str  # explore | exploit | synthesize | tiebreaker
    reason: str
    divergence_score: float
    previous_mode: Optional[str] = None
    new_mode: Optional[str] = None


class RoundTrace(BaseModel):
    """Complete trace of a single debate round."""

    round_number: int
    mode: str  # explore | exploit
    budget_allocated: Dict[str, int]  # agent_type → tokens
    budget_used: Dict[str, int]       # agent_type → tokens actually used
    agent_outputs: List[AnalystOutput]
    divergence_report: Optional[DivergenceReport] = None
    routing_decision: Optional[RoutingDecision] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class DebateTrace(BaseModel):
    """
    The complete, immutable record of a debate session.
    This is what gets saved to the database and returned by the API.
    """

    debate_id: str
    thesis: str
    investment_context: InvestmentContext
    model_used: str

    # Rounds
    rounds: List[RoundTrace] = Field(default_factory=list)
    total_rounds_completed: int = 0

    # Conflicts
    conflicts: List[ConflictPoint] = Field(default_factory=list)
    tiebreaker_outputs: List[AnalystOutput] = Field(default_factory=list)

    # Final output
    committee_memo: Optional[CommitteeMemo] = None

    # Budget
    budget_summary: Optional[BudgetSummary] = None

    # Metadata
    status: str = Field(
        default="pending",
        description="pending | running | complete | failed",
    )
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    def all_agent_outputs(self) -> List[AnalystOutput]:
        """Flatten all agent outputs across all rounds."""
        outputs = []
        for r in self.rounds:
            outputs.extend(r.agent_outputs)
        outputs.extend(self.tiebreaker_outputs)
        return outputs
