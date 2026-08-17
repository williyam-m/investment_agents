"""Tests for conflict resolution."""
import pytest
from investment_agents.analysis.conflict import ConflictResolutionAction, ConflictResolver
from investment_agents.models.divergence import ConflictPoint, ConflictSeverity

def make_conflict(severity: ConflictSeverity, gap: float = 1.5) -> ConflictPoint:
    return ConflictPoint(
        conflict_id=f"test_{severity.value}",
        agent_a="value_investor",
        agent_b="risk_analyst",
        severity=severity,
        description="Test conflict",
        agent_a_position="BUY",
        agent_b_position="SELL",
        score_gap=gap,
        detected_at_round=1,
    )

def test_soft_conflict_flag_and_continue():
    resolver = ConflictResolver()
    conflict = make_conflict(ConflictSeverity.SOFT, gap=0.7)
    result = resolver.resolve(conflict, remaining_tokens=5000, tiebreaker_min_budget=1000)
    assert result.action == ConflictResolutionAction.FLAG_AND_CONTINUE

def test_hard_conflict_spawn_tiebreaker_with_budget():
    resolver = ConflictResolver()
    conflict = make_conflict(ConflictSeverity.HARD, gap=2.0)
    result = resolver.resolve(conflict, remaining_tokens=5000, tiebreaker_min_budget=1000)
    assert result.action == ConflictResolutionAction.SPAWN_TIEBREAKER

def test_hard_conflict_flag_divided_no_budget():
    resolver = ConflictResolver()
    conflict = make_conflict(ConflictSeverity.HARD, gap=2.0)
    result = resolver.resolve(conflict, remaining_tokens=500, tiebreaker_min_budget=1000)
    assert result.action == ConflictResolutionAction.FLAG_AS_DIVIDED

def test_resolve_all_mixed():
    resolver = ConflictResolver()
    conflicts = [
        make_conflict(ConflictSeverity.SOFT, gap=0.6),
        make_conflict(ConflictSeverity.HARD, gap=1.8),
    ]
    results = resolver.resolve_all(conflicts, remaining_tokens=5000, tiebreaker_min_budget=1000)
    assert len(results) == 2
    actions = {r.action for r in results}
    assert ConflictResolutionAction.FLAG_AND_CONTINUE in actions
    assert ConflictResolutionAction.SPAWN_TIEBREAKER in actions
