"""Unit tests for budget engine."""
import asyncio
import pytest
from investment_agents.budget.tracker import TokenBudgetTracker, BudgetExhaustedError
from investment_agents.budget.policy import DebateMode, ExploreExploitPolicy
from investment_agents.models.divergence import DivergenceReport

# --- TokenBudgetTracker ---
def test_initial_state():
    t = TokenBudgetTracker(total_budget=10000, reserved_for_synthesis=2000)
    assert t.get_total_used() == 0
    assert t.get_remaining() == 10000
    assert t.get_available() == 8000
    assert not t.is_exhausted()

def test_record_usage():
    t = TokenBudgetTracker(total_budget=10000, reserved_for_synthesis=2000)
    asyncio.run(t.record_usage("value_investor", 1, 500))
    assert t.get_total_used() == 500
    assert t.get_remaining() == 9500
    assert t.get_used("value_investor") == 500

def test_budget_exhausted_error():
    t = TokenBudgetTracker(total_budget=1000, reserved_for_synthesis=100)
    with pytest.raises(BudgetExhaustedError):
        asyncio.run(t.record_usage("agent", 1, 950))  # 950 > available (900)

def test_multiple_agents():
    t = TokenBudgetTracker(total_budget=10000, reserved_for_synthesis=1000)
    asyncio.run(t.record_usage("agent_a", 1, 1000))
    asyncio.run(t.record_usage("agent_b", 1, 2000))
    assert t.get_total_used() == 3000
    assert t.get_used("agent_a") == 1000
    assert t.get_used("agent_b") == 2000
    assert t.get_remaining() == 7000

def test_get_report():
    t = TokenBudgetTracker(total_budget=5000, reserved_for_synthesis=500)
    asyncio.run(t.record_usage("value_investor", 1, 300))
    asyncio.run(t.record_usage("risk_analyst", 1, 200))
    report = t.get_report()
    assert "total_budget" in report
    assert "total_used" in report
    assert report["total_used"] == 500

# --- ExploreExploitPolicy ---
def make_divergence_report(score: float, has_hard: bool = False) -> DivergenceReport:
    return DivergenceReport(
        round_number=1,
        overall_score=score,
        recommendation_variance=score,
        semantic_divergence=score,
        conflict_penalty=0.25 if has_hard else 0.0,
        has_hard_conflicts=has_hard,
    )

def test_policy_synthesize_on_max_rounds():
    policy = ExploreExploitPolicy()
    report = make_divergence_report(0.6)
    mode, reason = policy.decide(report, round_number=3, max_rounds=3, remaining_tokens=10000, min_synthesis_tokens=1500)
    assert mode == DebateMode.SYNTHESIZE
    assert "rounds" in reason.lower() or "max" in reason.lower()

def test_policy_synthesize_on_low_budget():
    policy = ExploreExploitPolicy()
    report = make_divergence_report(0.6)
    mode, reason = policy.decide(report, round_number=1, max_rounds=5, remaining_tokens=500, min_synthesis_tokens=1500)
    assert mode == DebateMode.SYNTHESIZE

def test_policy_explore_on_high_divergence():
    policy = ExploreExploitPolicy(explore_threshold=0.55)
    report = make_divergence_report(0.7)
    mode, reason = policy.decide(report, round_number=1, max_rounds=5, remaining_tokens=10000, min_synthesis_tokens=1500)
    assert mode == DebateMode.EXPLORE

def test_policy_exploit_on_low_divergence():
    policy = ExploreExploitPolicy(exploit_threshold=0.30)
    report = make_divergence_report(0.2)
    mode, reason = policy.decide(report, round_number=1, max_rounds=5, remaining_tokens=10000, min_synthesis_tokens=1500)
    assert mode == DebateMode.EXPLOIT
