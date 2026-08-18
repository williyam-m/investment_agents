"""
Integration tests for the Debate API.
Covers: health endpoint, POST /debates, GET /debates/{id}, DELETE /debates/{id}.
All LLM calls are mocked so no real model is required.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from investment_agents.api.app import app
from investment_agents.models.debate import DebateTrace, InvestmentContext
from investment_agents.models.synthesis import CommitteeMemo
from investment_agents.models.agent_output import AgentType, Recommendation
from investment_agents.storage.repository import DebateRepository
from investment_agents.orchestrator.graph import DebateOrchestrator


# ── Helpers ────────────────────────────────────────────────────────────────

VALID_DEBATE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _make_complete_trace() -> DebateTrace:
    memo = CommitteeMemo(
        final_recommendation=Recommendation.BUY,
        conviction=0.75,
        vote_breakdown={"buy": 3, "sell": 1, "hold": 1},
        executive_summary="Committee recommends BUY with moderate conviction.",
        key_thesis="Strong FCF generation supports current valuation.",
        bull_case="Growing addressable market and margin expansion.",
        bear_case="Macro headwinds and elevated interest rates.",
        key_risks=["Competition", "Regulation"],
        catalysts_to_watch=["Q3 earnings", "New product launch"],
        debate_was_contentious=True,
        committee_divided=False,
        dissenting_views=[],
        reasoning_trace=[],
        total_rounds=2,
        total_tokens_used=8000,
        model_used="test-model",
        synthesis_quality="full",
    )
    return DebateTrace(
        debate_id=VALID_DEBATE_ID,
        thesis="Is Apple a buy?",
        investment_context=InvestmentContext(),
        model_used="test-model",
        status="complete",
        total_rounds_completed=2,
        committee_memo=memo,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_repo() -> DebateRepository:
    repo = MagicMock(spec=DebateRepository)
    repo.get.return_value = None
    repo.get_pending_status.return_value = None
    repo.get_request.return_value = None
    repo.create_pending.return_value = None
    repo.save_request.return_value = None
    repo.save.return_value = None
    repo.mark_failed.return_value = None
    repo.list_recent.return_value = []
    repo.delete.return_value = True
    return repo


@pytest.fixture
def mock_orchestrator() -> DebateOrchestrator:
    orch = AsyncMock(spec=DebateOrchestrator)
    orch.run = AsyncMock(return_value=_make_complete_trace())
    return orch


@pytest.fixture
def client(mock_repo, mock_orchestrator) -> TestClient:
    """TestClient with mocked repo and orchestrator injected via app.state."""
    app.state.repo = mock_repo
    app.state.orchestrator = mock_orchestrator
    return TestClient(app, raise_server_exceptions=False)


# ── Health ─────────────────────────────────────────────────────────────────

def test_health_endpoint(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


# ── POST /debates ──────────────────────────────────────────────────────────

def test_post_debates_returns_200(client: TestClient, mock_orchestrator):
    resp = client.post(
        "/api/v1/debates",
        json={"thesis": "Is Apple a buy at current valuations?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "debate_id" in data
    assert "status" in data


def test_post_debates_calls_orchestrator(client: TestClient, mock_orchestrator):
    client.post(
        "/api/v1/debates",
        json={"thesis": "Is Microsoft overvalued given slowing cloud growth?"},
    )
    mock_orchestrator.run.assert_called_once()


def test_post_debates_saves_trace(client: TestClient, mock_repo):
    client.post(
        "/api/v1/debates",
        json={"thesis": "Is NVIDIA a long-term hold despite high P/E?"},
    )
    mock_repo.save.assert_called_once()


def test_post_debates_rejects_short_thesis(client: TestClient):
    resp = client.post("/api/v1/debates", json={"thesis": "Buy?"})
    assert resp.status_code == 422


def test_post_debates_propagates_orchestrator_error(client: TestClient, mock_orchestrator, mock_repo):
    mock_orchestrator.run.side_effect = RuntimeError("LLM connection failed")
    resp = client.post(
        "/api/v1/debates",
        json={"thesis": "Is Tesla worth buying after recent pullback?"},
    )
    assert resp.status_code == 500
    mock_repo.mark_failed.assert_called_once()


# ── GET /debates/{id} ──────────────────────────────────────────────────────

def test_get_debate_returns_completed_trace(client: TestClient, mock_repo):
    trace = _make_complete_trace()
    mock_repo.get.return_value = trace

    resp = client.get(f"/api/v1/debates/{VALID_DEBATE_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["debate_id"] == VALID_DEBATE_ID
    assert data["status"] == "complete"


def test_get_debate_returns_404_for_unknown(client: TestClient, mock_repo):
    mock_repo.get.return_value = None
    mock_repo.get_pending_status.return_value = None

    resp = client.get(f"/api/v1/debates/{VALID_DEBATE_ID}")
    assert resp.status_code == 404


def test_get_debate_returns_202_for_pending(client: TestClient, mock_repo):
    mock_repo.get.return_value = None
    mock_repo.get_pending_status.return_value = {
        "status": "pending",
        "thesis": "Is AAPL a buy?",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    resp = client.get(f"/api/v1/debates/{VALID_DEBATE_ID}")
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"


# ── GET /debates ───────────────────────────────────────────────────────────

def test_list_debates_returns_list(client: TestClient, mock_repo):
    mock_repo.list_recent.return_value = [
        {
            "debate_id": VALID_DEBATE_ID,
            "thesis": "Is AAPL a buy?",
            "status": "complete",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "rounds": 2,
            "has_memo": True,
        }
    ]
    resp = client.get("/api/v1/debates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


# ── DELETE /debates/{id} ───────────────────────────────────────────────────

def test_delete_debate_returns_200(client: TestClient, mock_repo):
    mock_repo.delete.return_value = True
    resp = client.delete(f"/api/v1/debates/{VALID_DEBATE_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True


def test_delete_debate_returns_404_if_not_found(client: TestClient, mock_repo):
    mock_repo.delete.return_value = False
    resp = client.delete(f"/api/v1/debates/{VALID_DEBATE_ID}")
    assert resp.status_code == 404
