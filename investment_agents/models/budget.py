"""
Budget data models.
Token budget is a first-class primitive — tracked at every LLM call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TokenBudget(BaseModel):
    """Represents the total token budget for a debate session."""

    total: int = Field(..., gt=0, description="Total token budget for the entire debate")
    used: int = Field(default=0, ge=0)
    reserved_for_synthesis: int = Field(
        default=2000, description="Tokens held back for synthesis step"
    )

    @property
    def available(self) -> int:
        return max(0, self.total - self.used - self.reserved_for_synthesis)

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.used)

    @property
    def utilization_pct(self) -> float:
        return (self.used / self.total) * 100 if self.total > 0 else 0.0

    @property
    def is_exhausted(self) -> bool:
        return self.available <= 0


class BudgetAllocation(BaseModel):
    """Per-agent token allocation for a single round."""

    agent_type: str
    allocated: int = Field(..., ge=0)
    used: int = Field(default=0, ge=0)
    round_number: int = Field(..., ge=1)
    mode: str = Field(..., description="explore | exploit")

    @property
    def over_budget(self) -> bool:
        return self.used > self.allocated

    @property
    def efficiency(self) -> float:
        if self.allocated == 0:
            return 0.0
        return min(1.0, self.used / self.allocated)


class BudgetDecision(BaseModel):
    """Records a budget allocation decision made by the orchestrator."""

    round_number: int
    mode: str  # explore | exploit
    total_round_budget: int
    allocations: Dict[str, int]  # agent_type → tokens
    reasoning: str = Field(..., description="Why this allocation was chosen")
    divergence_score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetReport(BaseModel):
    """Live budget tracking object — part of the LangGraph DebateState."""

    token_budget: TokenBudget
    round_allocations: List[BudgetAllocation] = Field(default_factory=list)
    decisions: List[BudgetDecision] = Field(default_factory=list)
    by_agent: Dict[str, int] = Field(
        default_factory=dict, description="Total tokens used per agent type across all rounds"
    )
    by_round: Dict[int, int] = Field(
        default_factory=dict, description="Total tokens used per round"
    )

    def record_usage(self, agent_type: str, round_number: int, tokens: int) -> None:
        self.token_budget.used += tokens
        self.by_agent[agent_type] = self.by_agent.get(agent_type, 0) + tokens
        self.by_round[round_number] = self.by_round.get(round_number, 0) + tokens

    def get_allocation(self, agent_type: str, round_number: int) -> Optional[BudgetAllocation]:
        for alloc in self.round_allocations:
            if alloc.agent_type == agent_type and alloc.round_number == round_number:
                return alloc
        return None

    @property
    def remaining_tokens(self) -> int:
        return self.token_budget.remaining

    @property
    def available_tokens(self) -> int:
        return self.token_budget.available


class BudgetSummary(BaseModel):
    """Final budget summary included in DebateTrace."""

    total_allocated: int
    total_used: int
    by_agent: Dict[str, int]
    by_round: Dict[int, int]
    budget_decisions: List[BudgetDecision]
    efficiency_pct: float = Field(description="total_used / total_allocated * 100")

    @classmethod
    def from_report(cls, report: BudgetReport) -> "BudgetSummary":
        total = report.token_budget.total
        used = report.token_budget.used
        return cls(
            total_allocated=total,
            total_used=used,
            by_agent=report.by_agent,
            by_round=report.by_round,
            budget_decisions=report.decisions,
            efficiency_pct=(used / total * 100) if total > 0 else 0.0,
        )
