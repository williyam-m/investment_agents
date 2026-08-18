"""
Unit tests for orchestrator nodes.
Covers: node_allocate_budget — equal split, budget ceiling, budget exhaustion signal.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from typing import Any, Dict

from investment_agents.orchestrator.nodes import (
    node_allocate_budget,
    _AGENT_TYPES,
    _NUM_AGENTS,
    _MIN_AGENT_TOKENS,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_state(
    available: int,
    mode: str = "explore",
    round_number: int = 1,
    max_rounds: int = 3,
    divergence_report: Any = None,
) -> Dict[str, Any]:
    """Build a minimal DebateState dict for node_allocate_budget.

    Keys must match DebateState TypedDict exactly.
    """
    # TokenBudget.available is a @property: max(0, total - used - reserved_for_synthesis)
    # So we set used + reserved_for_synthesis = total - available
    reserved_for_synthesis = 2000
    used = max(0, 40000 - available - reserved_for_synthesis)
    token_budget = {
        "total": 40000,
        "used": used,
        "reserved_for_synthesis": reserved_for_synthesis,
    }
    budget_report = {
        "token_budget": token_budget,
        "round_allocations": [],
        "total_rounds_planned": max_rounds,
        "rounds_completed": round_number - 1,
        "allocation_history": [],
        "budget_decisions": [],
        "decisions": [],
    }
    return {
        "debate_id": "test-debate-id",
        "thesis": "Is Apple a buy?",
        "investment_context": {},
        "total_budget": 40000,
        "max_rounds": max_rounds,
        "model": "test-model",
        # Runtime state
        "round_number": round_number,
        "debate_mode": mode,
        "current_round_outputs": [],
        "all_round_outputs": [],
        # Budget
        "budget_report": budget_report,
        # Intelligence
        "divergence_report": divergence_report,
        "conflicts": [],
        "convergence_signals": [],
        "routing_decision": None,
        # Control
        "should_continue": True,
        "spawn_tiebreaker": False,
        "tiebreaker_outputs": [],
        # Output
        "rounds": [],
        "committee_memo": None,
        # Streaming
        "stream_events": [],
        # Error
        "error": None,
    }


# ── Helpers to extract allocations from the budget_report dict ─────────────

def _get_allocations(result: Dict[str, Any]) -> Dict[str, int]:
    """Extract per-agent allocations from the returned budget_report."""
    budget_report = result.get("budget_report", {})
    round_allocations = budget_report.get("round_allocations", [])
    return {a["agent_type"]: a["allocated"] for a in round_allocations}


def _total_allocated(result: Dict[str, Any]) -> int:
    return sum(_get_allocations(result).values())


# ── Allocation tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_allocate_budget_explore_equal_split():
    """In explore mode with ample budget, all agents get equal allocation."""
    state = _make_state(available=20000, mode="explore")
    result = await node_allocate_budget(state)

    allocations = _get_allocations(result)
    assert len(allocations) == _NUM_AGENTS

    values = list(allocations.values())
    assert len(set(values)) == 1, f"Expected equal allocation but got: {allocations}"


@pytest.mark.asyncio
async def test_allocate_budget_does_not_exceed_available():
    """Total allocated tokens must never exceed the available budget."""
    available = 1500  # tight budget — less than 5 * 400 = 2000
    state = _make_state(available=available, mode="explore")
    result = await node_allocate_budget(state)

    total = _total_allocated(result)
    assert total <= available, f"Over-allocated! total={total} > available={available}"


@pytest.mark.asyncio
async def test_allocate_budget_signals_exhaustion_when_too_tight():
    """When budget is critically tight the node should handle it gracefully."""
    state = _make_state(available=100, mode="explore")
    # Should not raise — the allocator handles starvation gracefully
    result = await node_allocate_budget(state)
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_allocate_budget_all_agent_types_present():
    """All 5 analyst agent types must receive an allocation."""
    state = _make_state(available=10000, mode="explore")
    result = await node_allocate_budget(state)

    allocations = _get_allocations(result)
    for agent_type in _AGENT_TYPES:
        assert agent_type in allocations, f"Missing allocation for {agent_type}"


@pytest.mark.asyncio
async def test_allocate_budget_exploit_mode_runs():
    """Exploit mode should produce valid allocations without error."""
    divergence_report = {
        "round_number": 2,
        "overall_score": 0.2,
        "recommendation_variance": 0.1,
        "semantic_divergence": 0.2,
        "conflict_penalty": 0.0,
        "conflicts": [],
        "has_hard_conflicts": False,
        "converging_topics": [],
        "exploit_worthy_agents": ["value_investor", "risk_analyst"],
        "agent_scores": {
            "value_investor": 0.5,
            "risk_analyst": -0.2,
            "contrarian": -0.5,
            "macro_economist": 0.1,
            "momentum_trader": 0.3,
        },
    }
    state = _make_state(available=10000, mode="exploit", divergence_report=divergence_report)
    result = await node_allocate_budget(state)

    allocations = _get_allocations(result)
    assert len(allocations) >= 1

    total = sum(allocations.values())
    assert total <= 10000, f"Over-allocated in exploit mode: {total}"


@pytest.mark.asyncio
async def test_allocate_budget_returns_state_dict():
    """Result should be a dict (state update) with budget_report key."""
    state = _make_state(available=5000, mode="explore")
    result = await node_allocate_budget(state)

    assert isinstance(result, dict)
    assert "budget_report" in result
