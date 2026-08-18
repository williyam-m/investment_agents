"""
Debate API routes.

Endpoints
---------
POST   /debates                  — Run a debate synchronously and return the full DebateTrace.
GET    /debates/{debate_id}      — Retrieve a stored DebateTrace by ID.
GET    /debates/{debate_id}/stream — SSE stream; replays stored stream_events from a completed
                                    trace, or runs a fresh debate via the orchestrator streaming
                                    interface if the debate is not yet stored.
GET    /debates                  — List recent debates (completed + pending).
DELETE /debates/{debate_id}      — Delete a debate trace by ID.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from investment_agents.models.debate import DebateRequest, DebateTrace
from investment_agents.models.streaming import StreamEvent, StreamEventType
from investment_agents.orchestrator.graph import DebateOrchestrator
from investment_agents.storage.repository import DebateRepository

router = APIRouter(tags=["debates"])
logger = structlog.get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)


# ── Dependency providers ───────────────────────────────────────────────────

def get_repo(request: Request) -> DebateRepository:
    """Return the DebateRepository from app lifespan state."""
    return request.app.state.repo


def get_orchestrator(request: Request) -> DebateOrchestrator:
    """Return the DebateOrchestrator from app lifespan state."""
    return request.app.state.orchestrator


# ── POST /debates ──────────────────────────────────────────────────────────

@router.post(
    "/debates",
    summary="Start a debate",
    status_code=200,
)
@limiter.limit("5/minute")
async def start_debate(
    request: Request,
    body: DebateRequest,
    repo: DebateRepository = Depends(get_repo),
    orchestrator: DebateOrchestrator = Depends(get_orchestrator),
) -> JSONResponse:
    """
    Run a full investment committee debate synchronously and return the
    complete DebateTrace as JSON.

    The debate_id is auto-generated if not supplied in the request body.
    The completed trace is persisted so it can be retrieved later via
    GET /debates/{debate_id}.

    Rate limited to 5 requests per minute per IP.
    """
    debate_id = body.debate_id  # always set by Pydantic validator

    logger.info(
        "debate.start",
        debate_id=debate_id,
        thesis=body.thesis[:80],
    )

    # Mark pending so /stream can return early 404 messages if polled before
    # the debate finishes.
    repo.create_pending(debate_id, body.thesis)
    repo.save_request(debate_id, body)

    try:
        trace: DebateTrace = await orchestrator.run(body)
    except Exception as exc:
        repo.mark_failed(debate_id, str(exc))
        logger.error("debate.run_failed", debate_id=debate_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Debate execution failed: {exc}") from exc

    # Persist the completed trace
    repo.save(trace)

    logger.info(
        "debate.complete",
        debate_id=debate_id,
        status=trace.status,
        rounds=trace.total_rounds_completed,
    )

    return JSONResponse(content=json.loads(trace.model_dump_json()))


# ── GET /debates/{debate_id}/stream ───────────────────────────────────────

@router.get(
    "/debates/{debate_id}/stream",
    summary="Stream debate events via SSE",
)
async def stream_debate(
    debate_id: str,
    repo: DebateRepository = Depends(get_repo),
    orchestrator: DebateOrchestrator = Depends(get_orchestrator),
) -> EventSourceResponse:
    """
    Server-Sent Events endpoint.

    Behaviour
    ---------
    * If the debate is **already complete** in the repository, all stored
      ``stream_events`` are replayed immediately in order (useful for
      re-connecting clients or front-end demos).
    * If the debate is **not yet stored** but exists as a pending entry (i.e.
      a request object was saved via POST), the orchestrator's
      ``run_streaming`` method is invoked and events are forwarded live.
    * If neither condition holds a 404 error event is emitted and the stream
      closes.
    """
    async def event_generator() -> AsyncIterator[dict]:
        # ── Case 1: debate already completed — replay stored events ──────
        completed_trace = repo.get(debate_id)
        if completed_trace is not None:
            stored_events = getattr(completed_trace, "stream_events", None) or []
            if stored_events:
                for ev_dict in stored_events:
                    try:
                        event = StreamEvent.model_validate(ev_dict)
                        yield event.to_sse_dict()
                    except Exception as exc:
                        logger.warning("stream.event_replay_failed", error=str(exc))
                        yield {
                            "event": ev_dict.get("type", "unknown"),
                            "data": json.dumps(ev_dict),
                        }
            else:
                # Trace exists but no stored stream events — emit a synthetic
                # debate_complete event so the client knows it finished.
                synthetic = StreamEvent(
                    type=StreamEventType.DEBATE_COMPLETE,
                    debate_id=debate_id,
                    data={
                        "debate_id": debate_id,
                        "status": completed_trace.status,
                        "total_rounds": completed_trace.total_rounds_completed,
                        "has_memo": completed_trace.committee_memo is not None,
                    },
                )
                yield synthetic.to_sse_dict()
            return  # done replaying

        # ── Case 2: pending debate — run streaming live ───────────────────
        req = repo.get_request(debate_id)
        if req is not None:
            try:
                async for event in orchestrator.run_streaming(req, repository=repo):
                    yield event.to_sse_dict()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error("stream.run_failed", debate_id=debate_id, error=str(exc))
                error_event = StreamEvent.error(
                    debate_id=debate_id,
                    code="STREAM_ERROR",
                    message=str(exc),
                )
                yield error_event.to_sse_dict()
            return

        # ── Case 3: debate not found ──────────────────────────────────────
        error_event = StreamEvent.error(
            debate_id=debate_id,
            code="NOT_FOUND",
            message=f"Debate {debate_id} not found. "
                    "Start a debate first via POST /api/v1/debates.",
        )
        yield error_event.to_sse_dict()

    return EventSourceResponse(event_generator())


# ── GET /debates/{debate_id} ───────────────────────────────────────────────

@router.get(
    "/debates/{debate_id}",
    summary="Get a completed debate trace",
)
async def get_debate(
    debate_id: str,
    repo: DebateRepository = Depends(get_repo),
) -> JSONResponse:
    """
    Retrieve a stored DebateTrace by its ID.

    Returns 404 if the debate does not exist or is still pending.
    Returns 202 with status information if the debate failed.
    """
    trace = repo.get(debate_id)
    if trace is None:
        # Check if it's pending or failed
        pending = repo.get_pending_status(debate_id)
        if pending:
            return JSONResponse(
                status_code=202,
                content={
                    "debate_id": debate_id,
                    "status": pending.get("status", "pending"),
                    "message": "Debate is still in progress or failed.",
                    "error": pending.get("error"),
                },
            )
        raise HTTPException(status_code=404, detail=f"Debate '{debate_id}' not found.")

    return JSONResponse(content=json.loads(trace.model_dump_json()))


# ── GET /debates ───────────────────────────────────────────────────────────

@router.get(
    "/debates",
    summary="List recent debates",
)
async def list_debates(
    limit: int = 50,
    repo: DebateRepository = Depends(get_repo),
) -> list:
    """
    Return the most recent debates (completed + pending), newest first.
    Each entry is a summary dict, not the full trace.
    """
    return repo.list_recent(limit=limit)


# ── DELETE /debates/{debate_id} ────────────────────────────────────────────

@router.delete(
    "/debates/{debate_id}",
    summary="Delete a debate trace",
    status_code=200,
)
async def delete_debate(
    debate_id: str,
    repo: DebateRepository = Depends(get_repo),
) -> JSONResponse:
    """
    Delete a debate trace (completed or pending) by its ID.
    Also removes the persisted JSON file from disk.
    Returns 404 if not found.
    """
    deleted = repo.delete(debate_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Debate '{debate_id}' not found.")

    logger.info("debate.deleted", debate_id=debate_id)
    return JSONResponse(content={"debate_id": debate_id, "deleted": True})
