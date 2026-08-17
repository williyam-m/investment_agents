"""
DebateRepository
================
In-memory store with optional JSON file persistence.

Thread-safe via ``threading.Lock`` (compatible with FastAPI's default
single-threaded async event loop + background tasks model).

For production, swap the in-memory dicts with a SQLAlchemy/PostgreSQL
or Redis-backed implementation behind the same interface.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from investment_agents.models.debate import DebateRequest, DebateTrace

logger = structlog.get_logger(__name__)


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
        self._lock = threading.Lock()

        self._persist_dir: Path = persist_dir or Path("data/debates")
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._load_from_disk()

    # ── Write operations ───────────────────────────────────────────────────

    def create_pending(self, debate_id: str, thesis: str) -> None:
        """Register a new debate as pending before the orchestrator runs."""
        with self._lock:
            self._pending[debate_id] = {
                "thesis": thesis,
                "status": "pending",
                "started_at": datetime.utcnow().isoformat(),
                "error": None,
            }

    def save_request(self, debate_id: str, request: DebateRequest) -> None:
        """
        Persist the original DebateRequest so the SSE stream endpoint can
        re-run the debate if the trace is not yet complete.
        """
        with self._lock:
            self._requests[debate_id] = request
            # Also attach to pending metadata for convenience
            if debate_id in self._pending:
                self._pending[debate_id]["has_request"] = True

    def save(self, trace: DebateTrace) -> None:
        """Persist a completed DebateTrace and remove from pending."""
        with self._lock:
            self._traces[trace.debate_id] = trace
            self._pending.pop(trace.debate_id, None)
            self._requests.pop(trace.debate_id, None)
            self._persist_trace(trace)
        logger.info("repository.saved", debate_id=trace.debate_id, status=trace.status)

    def mark_failed(self, debate_id: str, error: str) -> None:
        """Mark a pending debate as failed."""
        with self._lock:
            if debate_id in self._pending:
                self._pending[debate_id]["status"] = "failed"
                self._pending[debate_id]["error"] = error
                self._pending[debate_id]["failed_at"] = datetime.utcnow().isoformat()
        logger.warning("repository.marked_failed", debate_id=debate_id, error=error)

    # ── Read operations ────────────────────────────────────────────────────

    def get(self, debate_id: str) -> Optional[DebateTrace]:
        """Return a completed DebateTrace, or None if not found / still pending."""
        with self._lock:
            return self._traces.get(debate_id)

    def get_request(self, debate_id: str) -> Optional[DebateRequest]:
        """Return the stored DebateRequest for a pending debate."""
        with self._lock:
            return self._requests.get(debate_id)

    def get_pending_status(self, debate_id: str) -> Optional[dict]:
        """Return pending metadata dict, or None if debate is not pending."""
        with self._lock:
            return self._pending.get(debate_id)

    def list_recent(self, limit: int = 20) -> List[dict]:
        """
        Return a summary list of recent debates, newest first.
        Includes both completed traces and in-flight / failed pending entries.
        """
        with self._lock:
            # Completed traces
            completed = sorted(
                self._traces.values(),
                key=lambda t: t.started_at,
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
            path = self._persist_dir / f"{trace.debate_id}.json"
            path.write_text(trace.model_dump_json(indent=2))
            logger.debug("repository.persisted", path=str(path))
        except Exception as exc:
            logger.warning("repository.persist_failed", debate_id=trace.debate_id, error=str(exc))

    def _load_from_disk(self) -> None:
        """Load all previously persisted traces from disk at startup."""
        loaded = 0
        errors = 0
        try:
            for json_file in self._persist_dir.glob("*.json"):
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
