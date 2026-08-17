"""Conditional edge routing functions for LangGraph."""
from __future__ import annotations

import structlog

from investment_agents.config.settings import get_settings
from investment_agents.orchestrator.state import DebateState

logger = structlog.get_logger(__name__)


def route_after_divergence(state: DebateState) -> str:
    """
    After scoring divergence: decide what happens next.

    Examines remaining token budget, round number cap, and hard conflict flags
    to decide the next graph node.

    Returns: "tiebreaker" | "next_round" | "synthesize"
    """
    settings = get_settings()
    budget_report = state.get("budget_report", {})
    remaining = (
        budget_report.get("token_budget", {}).get("remaining", 0)
        if isinstance(budget_report, dict)
        else 0
    )

    # Budget exhausted — must synthesize immediately
    if remaining < settings.min_synthesis_tokens:
        logger.info("routing.budget_exhausted", remaining=remaining)
        return "synthesize"

    # Max rounds reached — synthesize regardless of divergence
    if state["round_number"] >= state["max_rounds"]:
        logger.info("routing.max_rounds_reached", round=state["round_number"])
        return "synthesize"

    # Check for hard conflicts that warrant a tiebreaker
    div_report = state.get("divergence_report")
    if div_report and isinstance(div_report, dict):
        has_hard = div_report.get("has_hard_conflicts", False)
        if has_hard and remaining >= settings.tiebreaker_min_budget:
            logger.info("routing.tiebreaker_needed")
            return "tiebreaker"

    return "next_round"


def route_after_tiebreaker(state: DebateState) -> str:
    """
    After tiebreaker: always go to next round or synthesize.

    Returns: "next_round" | "synthesize"
    """
    settings = get_settings()
    budget_report = state.get("budget_report", {})
    remaining = (
        budget_report.get("token_budget", {}).get("remaining", 0)
        if isinstance(budget_report, dict)
        else 0
    )

    if remaining < settings.min_synthesis_tokens or state["round_number"] >= state["max_rounds"]:
        return "synthesize"

    return "next_round"
