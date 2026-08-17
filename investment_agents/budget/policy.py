"""
ExploreExploitPolicy — decides whether to explore, exploit, or synthesize
based on the divergence score and budget/round constraints.
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple

import structlog

from investment_agents.models.divergence import DivergenceReport

logger = structlog.get_logger(__name__)


class DebateMode(str, Enum):
    EXPLORE = "explore"
    EXPLOIT = "exploit"
    TRANSITION = "transition"  # Between explore and exploit thresholds
    SYNTHESIZE = "synthesize"


class ExploreExploitPolicy:
    """
    Decides the debate mode after each round based on:
    - Divergence score from DivergenceScorer
    - Remaining token budget
    - Current round vs max rounds

    Thresholds:
        divergence > explore_threshold  → EXPLORE (agents still disagree widely)
        divergence < exploit_threshold  → EXPLOIT (deep-dive the most distinctive views)
        otherwise                       → TRANSITION (moderate disagreement)

    Override conditions (always checked first):
        remaining_tokens < min_synthesis_tokens  → SYNTHESIZE
        round_number >= max_rounds               → SYNTHESIZE
    """

    def __init__(
        self,
        explore_threshold: float = 0.55,
        exploit_threshold: float = 0.30,
    ) -> None:
        if explore_threshold <= exploit_threshold:
            raise ValueError("explore_threshold must be greater than exploit_threshold")
        self.explore_threshold = explore_threshold
        self.exploit_threshold = exploit_threshold

    def decide(
        self,
        divergence_report: DivergenceReport,
        round_number: int,
        max_rounds: int,
        remaining_tokens: int,
        min_synthesis_tokens: int,
    ) -> Tuple[DebateMode, str]:
        """
        Determine the next debate mode.

        Returns:
            (DebateMode, reason_string)
        """
        score = divergence_report.overall_score

        # --- Hard stops: always synthesize ---
        if remaining_tokens < min_synthesis_tokens:
            reason = (
                f"Budget nearly exhausted: {remaining_tokens} tokens remaining "
                f"< {min_synthesis_tokens} minimum for synthesis."
            )
            logger.info("policy.synthesize", trigger="budget_exhausted", remaining=remaining_tokens)
            return DebateMode.SYNTHESIZE, reason

        if round_number >= max_rounds:
            reason = (
                f"Maximum rounds reached: round {round_number} of {max_rounds}."
            )
            logger.info("policy.synthesize", trigger="max_rounds", round=round_number)
            return DebateMode.SYNTHESIZE, reason

        # --- Score-based routing ---
        if score > self.explore_threshold:
            reason = (
                f"High divergence ({score:.3f} > {self.explore_threshold}): "
                f"agents still disagree widely — continuing to EXPLORE."
            )
            logger.info("policy.explore", divergence_score=score, threshold=self.explore_threshold)
            return DebateMode.EXPLORE, reason

        if score < self.exploit_threshold:
            reason = (
                f"Low divergence ({score:.3f} < {self.exploit_threshold}): "
                f"converging — switching to EXPLOIT mode to deepen key positions."
            )
            logger.info("policy.exploit", divergence_score=score, threshold=self.exploit_threshold)
            return DebateMode.EXPLOIT, reason

        # --- Transition zone ---
        reason = (
            f"Moderate divergence ({score:.3f}): in transition zone "
            f"[{self.exploit_threshold}, {self.explore_threshold}] — using EXPLOIT allocation."
        )
        logger.info("policy.transition", divergence_score=score)
        return DebateMode.TRANSITION, reason
