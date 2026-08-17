"""DebateState — the single shared state object flowing through the LangGraph graph."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional, Annotated
from typing_extensions import TypedDict
from investment_agents.models.agent_output import AnalystOutput
from investment_agents.models.budget import BudgetReport
from investment_agents.models.debate import DebateRequest, RoundTrace, RoutingDecision
from investment_agents.models.divergence import ConflictPoint, ConvergenceSignal, DivergenceReport
from investment_agents.models.streaming import StreamEvent
from investment_agents.models.synthesis import CommitteeMemo


class DebateState(TypedDict):
    # Input
    debate_id: str
    thesis: str
    investment_context: Dict[str, Any]
    total_budget: int
    max_rounds: int
    model: str

    # Runtime state
    round_number: int
    debate_mode: str  # "explore" | "exploit"
    current_round_outputs: List[AnalystOutput]
    all_round_outputs: List[AnalystOutput]

    # Budget
    budget_report: Dict[str, Any]  # serialized BudgetReport

    # Intelligence
    divergence_report: Optional[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    convergence_signals: List[Dict[str, Any]]
    routing_decision: Optional[Dict[str, Any]]

    # Control
    should_continue: bool
    spawn_tiebreaker: bool
    tiebreaker_outputs: List[AnalystOutput]

    # Output
    rounds: List[Dict[str, Any]]
    committee_memo: Optional[Dict[str, Any]]

    # Streaming
    stream_events: List[Dict[str, Any]]

    # Error
    error: Optional[str]
