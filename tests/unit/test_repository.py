"""
Unit tests for DebateRepository.
Covers: save/get, path-traversal protection, delete, list_recent, pending/failed states.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from investment_agents.storage.repository import DebateRepository, _validate_debate_id
from investment_agents.models.debate import DebateTrace, InvestmentContext


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_trace(debate_id: str = "11111111-1111-1111-1111-111111111111") -> DebateTrace:
    return DebateTrace(
        debate_id=debate_id,
        thesis="Is Apple a buy?",
        investment_context=InvestmentContext(),
        model_used="ollama/llama2:7b",
        status="complete",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_rounds_completed=2,
    )


# ── UUID validation ────────────────────────────────────────────────────────

def test_validate_debate_id_valid():
    _validate_debate_id("11111111-1111-1111-1111-111111111111")  # should not raise


def test_validate_debate_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        _validate_debate_id("../../etc/passwd")


def test_validate_debate_id_rejects_empty():
    with pytest.raises(ValueError):
        _validate_debate_id("")


def test_validate_debate_id_rejects_non_uuid():
    with pytest.raises(ValueError):
        _validate_debate_id("not-a-valid-uuid-at-all")


# ── Save and get ───────────────────────────────────────────────────────────

def test_save_and_get(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    trace = _make_trace()
    repo.save(trace)

    result = repo.get(trace.debate_id)
    assert result is not None
    assert result.debate_id == trace.debate_id
    assert result.thesis == trace.thesis


def test_get_returns_none_for_unknown_id(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    assert repo.get("11111111-1111-1111-1111-111111111111") is None


def test_save_persists_json_to_disk(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    trace = _make_trace()
    repo.save(trace)

    json_file = tmp_path / f"{trace.debate_id}.json"
    assert json_file.exists()


# ── Path traversal protection ──────────────────────────────────────────────

def test_path_traversal_blocked_on_save(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    trace = _make_trace(debate_id="../../etc/malicious")
    # _persist_trace should log a warning and not write the file
    repo._persist_trace(trace)  # should not raise, just warn
    assert not (tmp_path / "../../etc/malicious.json").exists()


# ── Pending / failed states ────────────────────────────────────────────────

def test_create_pending_and_retrieve(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    debate_id = "22222222-2222-2222-2222-222222222222"
    repo.create_pending(debate_id, "Is TSLA a buy?")

    status = repo.get_pending_status(debate_id)
    assert status is not None
    assert status["status"] == "pending"
    assert status["thesis"] == "Is TSLA a buy?"


def test_mark_failed(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    debate_id = "33333333-3333-3333-3333-333333333333"
    repo.create_pending(debate_id, "Is NVDA a buy?")
    repo.mark_failed(debate_id, "LLM timeout")

    status = repo.get_pending_status(debate_id)
    assert status["status"] == "failed"
    assert status["error"] == "LLM timeout"


def test_save_removes_from_pending(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    trace = _make_trace()
    repo.create_pending(trace.debate_id, trace.thesis)
    assert repo.get_pending_status(trace.debate_id) is not None

    repo.save(trace)
    assert repo.get_pending_status(trace.debate_id) is None


# ── Delete ─────────────────────────────────────────────────────────────────

def test_delete_existing_trace(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    trace = _make_trace()
    repo.save(trace)
    assert repo.get(trace.debate_id) is not None

    deleted = repo.delete(trace.debate_id)
    assert deleted is True
    assert repo.get(trace.debate_id) is None


def test_delete_nonexistent_returns_false(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    deleted = repo.delete("11111111-1111-1111-1111-111111111111")
    assert deleted is False


# ── List recent ────────────────────────────────────────────────────────────

def test_list_recent_returns_completed(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    trace = _make_trace()
    repo.save(trace)

    recent = repo.list_recent(limit=10)
    ids = [r["debate_id"] for r in recent]
    assert trace.debate_id in ids


def test_list_recent_includes_pending(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    debate_id = "44444444-4444-4444-4444-444444444444"
    repo.create_pending(debate_id, "Pending debate")

    recent = repo.list_recent(limit=10)
    ids = [r["debate_id"] for r in recent]
    assert debate_id in ids


def test_list_recent_respects_limit(tmp_path: Path):
    repo = DebateRepository(persist_dir=tmp_path)
    for i in range(5):
        uid = f"5555555{i}-5555-5555-5555-555555555555"
        repo.create_pending(uid, f"Debate {i}")

    recent = repo.list_recent(limit=3)
    assert len(recent) <= 3
