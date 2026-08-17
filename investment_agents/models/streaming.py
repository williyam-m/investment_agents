"""
Streaming event models for SSE (Server-Sent Events).
Every significant orchestrator action produces a StreamEvent that is sent
to connected React clients in real time.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class DebateMode(str, Enum):
    EXPLORE = "explore"
    EXPLOIT = "exploit"
    SYNTHESIS = "synthesis"
    COMPLETE = "complete"


class StreamEventType(str, Enum):
    # Debate lifecycle
    DEBATE_STARTED = "debate_started"
    DEBATE_COMPLETE = "debate_complete"
    ERROR = "error"

    # Round lifecycle
    ROUND_STARTED = "round_started"
    ROUND_COMPLETE = "round_complete"

    # Agent events
    AGENT_THINKING = "agent_thinking"       # streaming token chunk
    AGENT_OUTPUT = "agent_output"           # completed AnalystOutput

    # Budget
    BUDGET_UPDATE = "budget_update"

    # Intelligence events
    DIVERGENCE_SCORED = "divergence_scored"
    MODE_CHANGED = "mode_changed"
    CONFLICT_DETECTED = "conflict_detected"
    CONVERGENCE_SIGNAL = "convergence_signal"
    TIEBREAKER_SPAWNED = "tiebreaker_spawned"

    # Synthesis
    SYNTHESIS_STARTED = "synthesis_started"
    SYNTHESIS_COMPLETE = "synthesis_complete"


class StreamEvent(BaseModel):
    """A single SSE event. Serialized as JSON in the event data field."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: StreamEventType
    data: Dict[str, Any]
    debate_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_sse_dict(self) -> Dict[str, str]:
        """Convert to the format expected by sse-starlette."""
        return {
            "id": self.id,
            "event": self.type.value,
            "data": self.model_dump_json(exclude={"type"}),
        }

    @classmethod
    def debate_started(
        cls, debate_id: str, thesis: str, total_budget: int, max_rounds: int, model: str
    ) -> "StreamEvent":
        return cls(
            type=StreamEventType.DEBATE_STARTED,
            debate_id=debate_id,
            data={
                "debate_id": debate_id,
                "thesis": thesis,
                "total_budget": total_budget,
                "max_rounds": max_rounds,
                "model": model,
            },
        )

    @classmethod
    def round_started(
        cls,
        debate_id: str,
        round_number: int,
        mode: DebateMode,
        allocations: Dict[str, int],
    ) -> "StreamEvent":
        return cls(
            type=StreamEventType.ROUND_STARTED,
            debate_id=debate_id,
            data={
                "round_number": round_number,
                "mode": mode.value,
                "allocations": allocations,
            },
        )

    @classmethod
    def agent_thinking(
        cls, debate_id: str, agent_type: str, token_chunk: str, round_number: int
    ) -> "StreamEvent":
        return cls(
            type=StreamEventType.AGENT_THINKING,
            debate_id=debate_id,
            data={
                "agent_type": agent_type,
                "token_chunk": token_chunk,
                "round_number": round_number,
            },
        )

    @classmethod
    def budget_update(
        cls, debate_id: str, used: int, remaining: int, by_agent: Dict[str, int]
    ) -> "StreamEvent":
        return cls(
            type=StreamEventType.BUDGET_UPDATE,
            debate_id=debate_id,
            data={"used": used, "remaining": remaining, "by_agent": by_agent},
        )

    @classmethod
    def mode_changed(
        cls, debate_id: str, from_mode: str, to_mode: str, reason: str, divergence_score: float
    ) -> "StreamEvent":
        return cls(
            type=StreamEventType.MODE_CHANGED,
            debate_id=debate_id,
            data={
                "from": from_mode,
                "to": to_mode,
                "reason": reason,
                "divergence_score": divergence_score,
            },
        )

    @classmethod
    def error(cls, debate_id: str, code: str, message: str) -> "StreamEvent":
        return cls(
            type=StreamEventType.ERROR,
            debate_id=debate_id,
            data={"code": code, "message": message},
        )
