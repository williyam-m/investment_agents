"""
Token budget tracker for multi-agent debate sessions.
Thread-safe, in-memory, async-friendly.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict, List

import structlog

logger = structlog.get_logger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when a token recording attempt would exceed the available budget."""

    def __init__(self, agent_id: str, requested: int, available: int) -> None:
        self.agent_id = agent_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Budget exhausted: agent '{agent_id}' requested {requested} tokens "
            f"but only {available} are available."
        )


class TokenBudgetTracker:
    """
    Thread-safe, in-memory token budget tracker for a single debate session.

    Tracks total token consumption across multiple agents and rounds.
    Enforces a hard ceiling on spending and reserves a configurable amount
    for the final synthesis step.
    """

    def __init__(self, total_budget: int, reserved_for_synthesis: int = 2000) -> None:
        if total_budget <= 0:
            raise ValueError("total_budget must be positive")
        if reserved_for_synthesis < 0:
            raise ValueError("reserved_for_synthesis must be non-negative")

        self._total_budget = total_budget
        self._reserved_for_synthesis = reserved_for_synthesis
        self._used_by_agent: Dict[str, int] = defaultdict(int)
        self._usage_log: List[Dict] = []  # {agent_id, round_number, tokens}
        self._lock = asyncio.Lock()

        logger.info(
            "budget_tracker.init",
            total_budget=total_budget,
            reserved_for_synthesis=reserved_for_synthesis,
        )

    async def record_usage(self, agent_id: str, round_number: int, tokens: int) -> None:
        """
        Record token usage for an agent in a specific round.
        Raises BudgetExhaustedError if the recording would exceed available budget.
        """
        if tokens < 0:
            raise ValueError("tokens must be non-negative")

        async with self._lock:
            available = self._total_budget - sum(self._used_by_agent.values()) - self._reserved_for_synthesis
            if tokens > available:
                raise BudgetExhaustedError(agent_id, tokens, available)

            self._used_by_agent[agent_id] += tokens
            self._usage_log.append({
                "agent_id": agent_id,
                "round_number": round_number,
                "tokens": tokens,
            })

            logger.debug(
                "budget_tracker.recorded",
                agent_id=agent_id,
                round_number=round_number,
                tokens=tokens,
                total_used=sum(self._used_by_agent.values()),
                remaining=self.get_remaining(),
            )

    def get_used(self, agent_id: str) -> int:
        """Return total tokens used by a specific agent."""
        return self._used_by_agent.get(agent_id, 0)

    def get_total_used(self) -> int:
        """Return total tokens used across all agents."""
        return sum(self._used_by_agent.values())

    def get_remaining(self) -> int:
        """Return remaining budget (including reserved)."""
        return self._total_budget - self.get_total_used()

    def get_available(self) -> int:
        """Return available budget for agent use (excluding reserved synthesis tokens)."""
        return max(0, self.get_remaining() - self._reserved_for_synthesis)

    def is_exhausted(self) -> bool:
        """Return True if available budget is 0 or less."""
        return self.get_available() <= 0

    def get_report(self) -> dict:
        """Return a full breakdown of token usage."""
        total_used = self.get_total_used()
        return {
            "total_budget": self._total_budget,
            "total_used": total_used,
            "remaining": self.get_remaining(),
            "available": self.get_available(),
            "reserved_for_synthesis": self._reserved_for_synthesis,
            "is_exhausted": self.is_exhausted(),
            "usage_by_agent": dict(self._used_by_agent),
            "usage_log": list(self._usage_log),
        }
