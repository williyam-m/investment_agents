"""
ConflictResolver — decides how to handle detected conflicts.

After the DivergenceScorer identifies ConflictPoints, this module
decides what action the orchestrator should take:
  - FLAG_AND_CONTINUE  → soft conflict, keep debating normally
  - SPAWN_TIEBREAKER   → hard / factual conflict with enough token budget
  - FLAG_AS_DIVIDED    → hard / factual conflict with insufficient budget
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

import structlog

from investment_agents.models.divergence import ConflictPoint, ConflictSeverity

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------


class ConflictResolutionAction(str, Enum):
    """The action the orchestrator should take in response to a conflict."""

    FLAG_AND_CONTINUE = "flag_and_continue"
    """Soft conflict — note it and continue normal debate."""

    SPAWN_TIEBREAKER = "spawn_tiebreaker"
    """Hard or factual conflict with sufficient token budget — spawn a
    tiebreaker agent to adjudicate."""

    FLAG_AS_DIVIDED = "flag_as_divided"
    """Hard or factual conflict without sufficient token budget — record the
    division and do not attempt to resolve."""


# ---------------------------------------------------------------------------
# Resolution result model
# ---------------------------------------------------------------------------


@dataclass
class ConflictResolution:
    """
    The outcome of resolving a single :class:`~investment_agents.models.divergence.ConflictPoint`.

    Attributes
    ----------
    action:
        What the orchestrator should do.
    conflict:
        The original :class:`ConflictPoint` that triggered this resolution.
    notes:
        Human-readable rationale for the chosen action.
    """

    action: ConflictResolutionAction
    conflict: ConflictPoint
    notes: str = field(default="")

    def __str__(self) -> str:
        return (
            f"ConflictResolution(action={self.action.value}, "
            f"conflict_id={self.conflict.conflict_id}, "
            f"severity={self.conflict.severity.value})"
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class ConflictResolver:
    """
    Resolves detected :class:`ConflictPoint` objects into actionable
    :class:`ConflictResolution` directives.

    The resolver does **not** spawn tiebreaker agents itself — it produces
    the decision; the orchestrator is responsible for acting on it.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        conflict: ConflictPoint,
        remaining_tokens: int,
        tiebreaker_min_budget: int,
    ) -> ConflictResolution:
        """
        Decide how to handle a single conflict.

        Parameters
        ----------
        conflict:
            The detected conflict to resolve.
        remaining_tokens:
            How many tokens remain in the overall debate budget.
        tiebreaker_min_budget:
            Minimum tokens required to spawn a tiebreaker agent call.

        Returns
        -------
        ConflictResolution
        """
        log = logger.bind(
            conflict_id=conflict.conflict_id,
            severity=conflict.severity.value,
            agent_a=conflict.agent_a,
            agent_b=conflict.agent_b,
            score_gap=conflict.score_gap,
            remaining_tokens=remaining_tokens,
            tiebreaker_min_budget=tiebreaker_min_budget,
        )

        has_budget = remaining_tokens >= tiebreaker_min_budget

        # ----------------------------------------------------------------
        # Decision tree
        # ----------------------------------------------------------------
        if conflict.severity == ConflictSeverity.SOFT:
            action = ConflictResolutionAction.FLAG_AND_CONTINUE
            notes = (
                f"Soft conflict between {conflict.agent_a} and {conflict.agent_b} "
                f"(score gap={conflict.score_gap:.2f}). "
                "Flagging and continuing debate — agents may converge naturally."
            )

        elif conflict.severity == ConflictSeverity.HARD:
            if has_budget:
                action = ConflictResolutionAction.SPAWN_TIEBREAKER
                notes = (
                    f"Hard conflict between {conflict.agent_a} and {conflict.agent_b} "
                    f"(score gap={conflict.score_gap:.2f}). "
                    f"Sufficient budget ({remaining_tokens} ≥ {tiebreaker_min_budget}): "
                    "spawning tiebreaker agent."
                )
            else:
                action = ConflictResolutionAction.FLAG_AS_DIVIDED
                notes = (
                    f"Hard conflict between {conflict.agent_a} and {conflict.agent_b} "
                    f"(score gap={conflict.score_gap:.2f}). "
                    f"Insufficient budget ({remaining_tokens} < {tiebreaker_min_budget}): "
                    "flagging committee as divided."
                )

        elif conflict.severity == ConflictSeverity.FACTUAL:
            if has_budget:
                action = ConflictResolutionAction.SPAWN_TIEBREAKER
                notes = (
                    f"Factual conflict between {conflict.agent_a} and {conflict.agent_b}. "
                    f"Sufficient budget ({remaining_tokens} ≥ {tiebreaker_min_budget}): "
                    "spawning tiebreaker to arbitrate factual disagreement."
                )
            else:
                action = ConflictResolutionAction.FLAG_AS_DIVIDED
                notes = (
                    f"Factual conflict between {conflict.agent_a} and {conflict.agent_b}. "
                    f"Insufficient budget ({remaining_tokens} < {tiebreaker_min_budget}): "
                    "flagging as divided — factual dispute unresolved."
                )

        else:
            # Unknown severity — be conservative
            action = ConflictResolutionAction.FLAG_AND_CONTINUE
            notes = (
                f"Unknown conflict severity '{conflict.severity}' between "
                f"{conflict.agent_a} and {conflict.agent_b}. Defaulting to flag-and-continue."
            )
            log.warning("conflict_resolver.unknown_severity", severity=str(conflict.severity))

        resolution = ConflictResolution(
            action=action,
            conflict=conflict,
            notes=notes,
        )

        log.info(
            "conflict_resolver.resolved",
            action=action.value,
            has_budget=has_budget,
        )
        return resolution

    def resolve_all(
        self,
        conflicts: List[ConflictPoint],
        remaining_tokens: int,
        tiebreaker_min_budget: int,
    ) -> List[ConflictResolution]:
        """
        Resolve every conflict in *conflicts* and return a list of
        :class:`ConflictResolution` objects in the same order.

        Parameters
        ----------
        conflicts:
            All :class:`ConflictPoint` objects to resolve.
        remaining_tokens:
            Remaining token budget (shared across all resolutions; note that
            tiebreaker spawns may consume from this pool — the caller is
            responsible for updating the budget after acting on results).
        tiebreaker_min_budget:
            Minimum tokens required per tiebreaker agent call.

        Returns
        -------
        list[ConflictResolution]
        """
        if not conflicts:
            logger.debug("conflict_resolver.no_conflicts")
            return []

        log = logger.bind(
            n_conflicts=len(conflicts),
            remaining_tokens=remaining_tokens,
        )
        log.info("conflict_resolver.resolve_all_start")

        resolutions: List[ConflictResolution] = []
        for conflict in conflicts:
            resolution = self.resolve(
                conflict=conflict,
                remaining_tokens=remaining_tokens,
                tiebreaker_min_budget=tiebreaker_min_budget,
            )
            resolutions.append(resolution)

        tiebreakers = sum(
            1 for r in resolutions
            if r.action == ConflictResolutionAction.SPAWN_TIEBREAKER
        )
        divided = sum(
            1 for r in resolutions
            if r.action == ConflictResolutionAction.FLAG_AS_DIVIDED
        )
        continued = sum(
            1 for r in resolutions
            if r.action == ConflictResolutionAction.FLAG_AND_CONTINUE
        )

        log.info(
            "conflict_resolver.resolve_all_complete",
            tiebreakers=tiebreakers,
            flagged_divided=divided,
            flag_and_continue=continued,
        )
        return resolutions
