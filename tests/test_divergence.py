"""Unit tests for divergence scoring."""
import pytest
from investment_agents.analysis.divergence import DivergenceScorer
from investment_agents.models.agent_output import AgentType, AnalystOutput, Evidence, Recommendation

def make_output(agent_type: AgentType, rec: Recommendation, score: float, argument: str) -> AnalystOutput:
    return AnalystOutput(
        agent_id=f"{agent_type.value}_r1",
        agent_type=agent_type,
        round_number=1,
        recommendation=rec,
        conviction_score=0.8,
        numeric_score=score,
        thesis_agreement="Test",
        key_argument=argument,
        supporting_evidence=[Evidence(claim="test", source_type="qualitative", confidence=0.7, supports_thesis=True)],
    )

def test_consensus_outputs_low_divergence():
    """When all agents agree, divergence should be low."""
    outputs = [
        make_output(AgentType.VALUE_INVESTOR, Recommendation.BUY, 0.7, "Strong value"),
        make_output(AgentType.MOMENTUM_TRADER, Recommendation.BUY, 0.6, "Good momentum"),
        make_output(AgentType.RISK_ANALYST, Recommendation.BUY, 0.5, "Manageable risk"),
    ]
    scorer = DivergenceScorer()
    report = scorer.score(outputs, round_number=1)
    assert report.overall_score < 0.6
    assert not report.has_hard_conflicts

def test_divided_outputs_high_divergence():
    """When agents strongly disagree, divergence should be high."""
    outputs = [
        make_output(AgentType.VALUE_INVESTOR, Recommendation.STRONG_BUY, 1.0, "Deep value buy"),
        make_output(AgentType.RISK_ANALYST, Recommendation.STRONG_SELL, -1.0, "Catastrophic risk"),
    ]
    scorer = DivergenceScorer()
    report = scorer.score(outputs, round_number=1)
    assert report.has_hard_conflicts
    assert len(report.conflicts) >= 1
    assert report.conflicts[0].score_gap >= 1.5

def test_exploit_worthy_agents_ordering():
    """Agents furthest from mean should be first in exploit_worthy_agents."""
    outputs = [
        make_output(AgentType.VALUE_INVESTOR, Recommendation.STRONG_BUY, 1.0, "Buy strongly"),
        make_output(AgentType.MOMENTUM_TRADER, Recommendation.HOLD, 0.0, "Neutral"),
        make_output(AgentType.RISK_ANALYST, Recommendation.STRONG_SELL, -1.0, "Sell strongly"),
    ]
    scorer = DivergenceScorer()
    report = scorer.score(outputs, round_number=1)
    # value_investor and risk_analyst should be first (most distinctive)
    assert "value_investor" in report.exploit_worthy_agents[:2]
    assert "risk_analyst" in report.exploit_worthy_agents[:2]

def test_agent_scores_populated():
    outputs = [
        make_output(AgentType.VALUE_INVESTOR, Recommendation.BUY, 0.8, "Value case"),
        make_output(AgentType.CONTRARIAN, Recommendation.SELL, -0.5, "Counter case"),
    ]
    scorer = DivergenceScorer()
    report = scorer.score(outputs, round_number=1)
    assert "value_investor" in report.agent_scores
    assert "contrarian" in report.agent_scores
    assert report.agent_scores["value_investor"] == 0.8
    assert report.agent_scores["contrarian"] == -0.5
