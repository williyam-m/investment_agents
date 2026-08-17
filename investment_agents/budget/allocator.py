"""
BudgetAllocator — allocates tokens across agents per round
based on explore/exploit mode and divergence report.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import structlog

from investment_agents.config.settings import Settings, get_settings
from investment_agents.models.divergence import DivergenceReport

logger = structlog.get_logger(__name__)

# Minimum tokens any single agent must receive
MIN_AGENT_TOKENS = 400

# Number of core analyst agents
ANALYST_AGENT_COUNT = 5


class BudgetAllocator:
    """
    Allocates the per-round token budget across agent types.

    Explore mode: equal split across all agents.
    Exploit mode: weight by distinctiveness (exploit_worthy_agents from DivergenceReport).
    """

    def __init__(
        self,
        agent_types: List[str],
        settings: Optional[Settings] = None,
    ) -> None:
        self.agent_types = agent_types
        self.settings = settings or get_settings()

    def allocate_round(
        self,
        available_tokens: int,
        round_number: int,
        mode: str,
        divergence_report: Optional[DivergenceReport] = None,
    ) -> Dict[str, int]:
        """
        Compute token allocations for each agent for a single round.

        Args:
            available_tokens: Total tokens available for this round (already excluding synthesis reserve).
            round_number: Current round number (1-indexed).
            mode: "explore" | "exploit" | "transition"
            divergence_report: Last round's DivergenceReport (None on round 1).

        Returns:
            dict mapping agent_type -> token allocation
        """
        n = len(self.agent_types)
        if n == 0:
            return {}

        if mode in ("explore", None):
            allocations = self._equal_split(available_tokens, n)
        else:
            # exploit / transition
            allocations = self._weighted_split(available_tokens, divergence_report)

        log_allocs = {agent: allocs for agent, allocs in zip(self.agent_types, allocations)}
        logger.info(
            "budget_allocator.allocated",
            round_number=round_number,
            mode=mode,
            available_tokens=available_tokens,
            allocations=log_allocs,
        )
        return log_allocs

    def _equal_split(self, available: int, n: int) -> List[int]:
        """Split available tokens equally, ensuring minimum per agent."""
        base = available // n
        base = max(base, MIN_AGENT_TOKENS)
        # Distribute remainder to first agents
        remainder = available - base * n
        allocations = []
        for i in range(n):
            extra = 1 if i < remainder else 0
            allocations.append(max(MIN_AGENT_TOKENS, base + extra))
        return allocations

    def _weighted_split(
        self, available: int, divergence_report: Optional[DivergenceReport]
    ) -> List[int]:
        """
        Weight allocation by agent distinctiveness in exploit mode.
        Most distinctive agents get proportionally more tokens.
        """
        n = len(self.agent_types)

        if divergence_report is None or not divergence_report.exploit_worthy_agents:
            return self._equal_split(available, n)

        # Build weight map: most distinctive = highest weight
        exploit_order = divergence_report.exploit_worthy_agents
        max_rank = len(exploit_order)

        # Agents ranked higher get more tokens
        weights: Dict[str, float] = {}
        for agent in self.agent_types:
            if agent in exploit_order:
                rank = exploit_order.index(agent)  # 0 = most distinctive
                # Weight decays from max_rank down to 1
                weights[agent] = float(max_rank - rank)
            else:
                weights[agent] = 1.0  # minimum weight

        total_weight = sum(weights.values())

        allocations = []
        for agent in self.agent_types:
            share = weights[agent] / total_weight
            allocated = max(MIN_AGENT_TOKENS, int(available * share))
            allocations.append(allocated)

        # Trim to available if we over-allocated due to minimums
        total_allocated = sum(allocations)
        if total_allocated > available:
            # Scale down proportionally, keeping minimums
            scale = available / total_allocated
            allocations = [max(MIN_AGENT_TOKENS, int(a * scale)) for a in allocations]

        return allocations
