"""
DebateRepository
================
In-memory store with optional JSON file persistence.

Uses asyncio.Lock for async-safe operation within FastAPI's async event loop.

For production, swap the in-memory dicts with a SQLAlchemy/PostgreSQL
or Redis-backed implementation behind the same interface.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from investment_agents.models.debate import DebateRequest, DebateTrace

logger = structlog.get_logger(__name__)

_UUID_PATTERN = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')


def _validate_debate_id(debate_id: str) -> None:
    """Raise ValueError if debate_id is not a valid UUID format."""
    if not _UUID_PATTERN.match(debate_id):
        raise ValueError(f"Invalid debate_id format: {debate_id!r}. Must be a UUID.")


class DebateRepository:
    """
    In-memory repository with JSON file persistence.

    Storage
    -------
    * ``_traces``  — completed DebateTrace objects, keyed by debate_id.
    * ``_pending`` — lightweight metadata for in-flight / failed debates,
                     keyed by debate_id.  Each value is a plain dict::

                         {
                             "thesis":      str,
                             "status":      "pending" | "failed",
                             "started_at":  ISO-8601 str,
                             "error":       str | None,
                             "request":     DebateRequest | None,  # saved separately
                         }
    """

    def __init__(self, persist_dir: Optional[Path] = None) -> None:
        self._traces: Dict[str, DebateTrace] = {}
        self._pending: Dict[str, dict] = {}
        self._requests: Dict[str, DebateRequest] = {}  # debate_id → DebateRequest
        self._lock = asyncio.Lock()

        self._persist_dir: Path = persist_dir or Path("data/debates")
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._load_from_disk()

    # ── Write operations ───────────────────────────────────────────────────

    def create_pending(self, debate_id: str, thesis: str) -> None:
        """Register a new debate as pending before the orchestrator runs."""
        # Note: sync method called before async context; lock not needed here
        self._pending[debate_id] = {
            "thesis": thesis,
            "status": "pending",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }

    def save_request(self, debate_id: str, request: DebateRequest) -> None:
        """
        Persist the original DebateRequest so the SSE stream endpoint can
        re-run the debate if the trace is not yet complete.
        """
        self._requests[debate_id] = request
        # Also attach to pending metadata for convenience
        if debate_id in self._pending:
            self._pending[debate_id]["has_request"] = True

    def save(self, trace: DebateTrace) -> None:
        """Persist a completed DebateTrace and remove from pending."""
        self._traces[trace.debate_id] = trace
        self._pending.pop(trace.debate_id, None)
        self._requests.pop(trace.debate_id, None)
        self._persist_trace(trace)
        logger.info("repository.saved", debate_id=trace.debate_id, status=trace.status)

    def mark_failed(self, debate_id: str, error: str) -> None:
        """Mark a pending debate as failed."""
        if debate_id in self._pending:
            self._pending[debate_id]["status"] = "failed"
            self._pending[debate_id]["error"] = error
            self._pending[debate_id]["failed_at"] = datetime.now(timezone.utc).isoformat()
        logger.warning("repository.marked_failed", debate_id=debate_id, error=error)

    def delete(self, debate_id: str) -> bool:
        """
        Delete a debate trace (completed or pending) by its ID.
        Also removes the persisted JSON file from disk.
        Returns True if something was deleted, False if not found.
        """
        deleted = False
        if debate_id in self._traces:
            del self._traces[debate_id]
            deleted = True
        if debate_id in self._pending:
            del self._pending[debate_id]
            deleted = True
        if debate_id in self._requests:
            del self._requests[debate_id]

        # Remove persisted file (only if debate_id is safe)
        try:
            _validate_debate_id(debate_id)
            path = self._persist_dir / f"{debate_id}.json"
            if path.exists():
                path.unlink()
                logger.debug("repository.deleted_file", path=str(path))
        except ValueError:
            logger.warning("repository.delete_invalid_id", debate_id=debate_id)
        except Exception as exc:
            logger.warning("repository.delete_file_failed", debate_id=debate_id, error=str(exc))

        if deleted:
            logger.info("repository.deleted", debate_id=debate_id)
        return deleted

    # ── Read operations ────────────────────────────────────────────────────

    def get(self, debate_id: str) -> Optional[DebateTrace]:
        """Return a completed DebateTrace, or None if not found / still pending."""
        return self._traces.get(debate_id)

    def get_request(self, debate_id: str) -> Optional[DebateRequest]:
        """Return the stored DebateRequest for a pending debate."""
        return self._requests.get(debate_id)

    def get_pending_status(self, debate_id: str) -> Optional[dict]:
        """Return pending metadata dict, or None if debate is not pending."""
        return self._pending.get(debate_id)

    def list_recent(self, limit: int = 20) -> List[dict]:
        """
        Return a summary list of recent debates, newest first.
        Includes both completed traces and in-flight / failed pending entries.
        """
        # Completed traces — normalize to UTC-aware for consistent sorting
        def _to_utc(dt):
            if dt is None:
                return datetime.min.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        completed = sorted(
            self._traces.values(),
            key=lambda t: _to_utc(t.started_at),
            reverse=True,
        )
        result: List[dict] = [
            {
                "debate_id": t.debate_id,
                "thesis": t.thesis[:120],
                "status": t.status,
                "started_at": t.started_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "rounds": t.total_rounds_completed,
                "has_memo": t.committee_memo is not None,
            }
            for t in completed
        ]

        # Pending / failed entries not yet promoted to traces
        for did, meta in self._pending.items():
            result.append(
                {
                    "debate_id": did,
                    "thesis": meta.get("thesis", "")[:120],
                    "status": meta.get("status", "pending"),
                    "started_at": meta.get("started_at", ""),
                    "completed_at": None,
                    "rounds": 0,
                    "has_memo": False,
                    "error": meta.get("error"),
                }
            )

        # Sort everything by started_at descending
        result.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return result[:limit]

    # ── Persistence helpers ────────────────────────────────────────────────

    def _persist_trace(self, trace: DebateTrace) -> None:
        """Write a single trace to a JSON file in persist_dir."""
        try:
            _validate_debate_id(trace.debate_id)
            path = self._persist_dir / f"{trace.debate_id}.json"
            path.write_text(trace.model_dump_json(indent=2))
            logger.debug("repository.persisted", path=str(path))
        except ValueError as exc:
            logger.warning("repository.persist_invalid_id", debate_id=trace.debate_id, error=str(exc))
        except Exception as exc:
            logger.warning("repository.persist_failed", debate_id=trace.debate_id, error=str(exc))

    def _load_from_disk(self) -> None:
        """Load all previously persisted traces from disk at startup."""
        loaded = 0
        errors = 0
        try:
            for json_file in self._persist_dir.glob("*.json"):
                stem = json_file.stem
                if not _UUID_PATTERN.match(stem):
                    logger.warning("repository.load_skipped_invalid_name", file=str(json_file))
                    continue
                try:
                    trace = DebateTrace.model_validate_json(json_file.read_text())
                    self._traces[trace.debate_id] = trace
                    loaded += 1
                except Exception as exc:
                    errors += 1
                    logger.warning(
                        "repository.load_file_failed",
                        file=str(json_file),
                        error=str(exc),
                    )
        except Exception as exc:
            logger.warning("repository.load_failed", error=str(exc))

        logger.info("repository.loaded_from_disk", loaded=loaded, errors=errors)
