"""Unit tests for Pydantic models."""
import pytest
from investment_agents.models.agent_output import AgentType, AnalystOutput, Evidence, Recommendation
from investment_agents.models.debate import DebateRequest, InvestmentContext
from investment_agents.models.streaming import StreamEvent, StreamEventType

def make_evidence():
    return Evidence(claim="Test claim", source_type="qualitative", confidence=0.8, supports_thesis=True)

def make_output(score: float = 0.5, rec: str = "buy") -> AnalystOutput:
    return AnalystOutput(
        agent_id="test_agent_r1",
        agent_type=AgentType.VALUE_INVESTOR,
        round_number=1,
        recommendation=Recommendation(rec),
        conviction_score=0.7,
        numeric_score=score,
        thesis_agreement="Agree",
        key_argument="Test argument",
        supporting_evidence=[make_evidence()],
    )

def test_analyst_output_validation():
    out = make_output()
    assert out.numeric_score == 0.5
    assert out.recommendation == Recommendation.BUY

def test_analyst_output_clamps_invalid_score():
    # numeric_score > 1.0 is clamped to 1.0 (production-safe behaviour)
    out = make_output(score=2.0)
    assert out.numeric_score == 1.0

def test_analyst_output_clamps_negative_score():
    # numeric_score < -1.0 is clamped to -1.0
    out = make_output(score=-5.0)
    assert out.numeric_score == -1.0

def test_debate_request_auto_id():
    req = DebateRequest(thesis="Is Apple a good investment at current valuations?")
    assert req.debate_id is not None
    assert len(req.debate_id) > 0

def test_debate_request_defaults():
    req = DebateRequest(thesis="Is Apple a good investment at current valuations?")
    assert req.total_budget == 40000
    assert req.max_rounds == 3

def test_stream_event_debate_started():
    event = StreamEvent.debate_started("abc123", "Test thesis", 40000, 3, "ollama/llama2")
    assert event.type == StreamEventType.DEBATE_STARTED
    assert event.debate_id == "abc123"
    sse = event.to_sse_dict()
    assert "event" in sse
    assert "data" in sse

def test_recommendation_enum_values():
    assert Recommendation.STRONG_BUY.value == "strong_buy"
    assert Recommendation.STRONG_SELL.value == "strong_sell"
    assert Recommendation.HOLD.value == "hold"
