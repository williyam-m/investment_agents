"""
DebateGraph — the main LangGraph StateGraph.
Orchestrates the full investment committee debate.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog
from langgraph.graph import StateGraph, END

from investment_agents.models.debate import DebateRequest, DebateTrace, InvestmentContext, RoundTrace
from investment_agents.models.budget import BudgetSummary, BudgetReport, TokenBudget
from investment_agents.models.streaming import StreamEvent, StreamEventType
from investment_agents.orchestrator.edges import route_after_divergence, route_after_tiebreaker
from investment_agents.orchestrator.nodes import (
    node_init,
    node_allocate_budget,
    node_run_agents,
    node_score_divergence,
    node_run_tiebreaker,
    node_synthesize,
    node_prepare_next_round,
)
from investment_agents.orchestrator.state import DebateState

logger = structlog.get_logger(__name__)


def build_debate_graph() -> StateGraph:
    """Build and compile the LangGraph StateGraph for the investment committee debate."""
    graph = StateGraph(DebateState)

    # ── Add nodes ──────────────────────────────────────────────────────────
    graph.add_node("init", node_init)
    graph.add_node("allocate_budget", node_allocate_budget)
    graph.add_node("run_agents", node_run_agents)
    graph.add_node("score_divergence", node_score_divergence)
    graph.add_node("run_tiebreaker", node_run_tiebreaker)
    graph.add_node("synthesize", node_synthesize)
    graph.add_node("prepare_next_round", node_prepare_next_round)

    # ── Linear flow ────────────────────────────────────────────────────────
    graph.set_entry_point("init")
    graph.add_edge("init", "allocate_budget")
    graph.add_edge("allocate_budget", "run_agents")
    graph.add_edge("run_agents", "score_divergence")

    # ── Conditional branching after divergence score ───────────────────────
    graph.add_conditional_edges(
        "score_divergence",
        route_after_divergence,
        {
            "tiebreaker": "run_tiebreaker",
            "next_round": "prepare_next_round",
            "synthesize": "synthesize",
        },
    )

    # ── After tiebreaker ───────────────────────────────────────────────────
    graph.add_conditional_edges(
        "run_tiebreaker",
        route_after_tiebreaker,
        {
            "next_round": "prepare_next_round",
            "synthesize": "synthesize",
        },
    )

    # ── Loop back for next round ───────────────────────────────────────────
    graph.add_edge("prepare_next_round", "allocate_budget")

    # ── Synthesis is terminal ──────────────────────────────────────────────
    graph.add_edge("synthesize", END)

    return graph.compile()


class DebateOrchestrator:
    """High-level interface for running investment committee debates."""

    def __init__(self) -> None:
        self._graph = build_debate_graph()

    def _make_initial_state(self, request: DebateRequest) -> DebateState:
        """Convert DebateRequest to initial DebateState."""
        ctx = request.investment_context.model_dump() if request.investment_context else {}
        model = request.model_config_.model if request.model_config_ else "ollama/llama2:7b"
        return DebateState(
            debate_id=request.debate_id or str(uuid.uuid4()),
            thesis=request.thesis,
            investment_context=ctx,
            total_budget=request.total_budget,
            max_rounds=request.max_rounds,
            model=model,
            round_number=1,
            debate_mode="explore",
            current_round_outputs=[],
            all_round_outputs=[],
            budget_report={},
            divergence_report=None,
            conflicts=[],
            convergence_signals=[],
            routing_decision=None,
            should_continue=True,
            spawn_tiebreaker=False,
            tiebreaker_outputs=[],
            rounds=[],
            committee_memo=None,
            stream_events=[],
            error=None,
        )

    def _state_to_trace(self, state: DebateState, request: DebateRequest) -> DebateTrace:
        """Convert final DebateState to a DebateTrace."""
        from investment_agents.models.synthesis import CommitteeMemo
        from investment_agents.models.divergence import ConflictPoint

        memo = None
        if state.get("committee_memo"):
            try:
                memo = CommitteeMemo.model_validate(state["committee_memo"])
            except Exception as exc:
                logger.warning("state_to_trace.memo_parse_failed", error=str(exc))

        conflicts = []
        for c in (state.get("conflicts") or []):
            try:
                conflicts.append(ConflictPoint.model_validate(c))
            except Exception as exc:
                logger.warning("state_to_trace.conflict_parse_failed", error=str(exc))

        tb_outputs = state.get("tiebreaker_outputs") or []

        budget_report_dict = state.get("budget_report", {})
        budget_summary = None
        if budget_report_dict:
            try:
                br = BudgetReport.model_validate(budget_report_dict)
                budget_summary = BudgetSummary.from_report(br)
            except Exception as exc:
                logger.warning("state_to_trace.budget_report_parse_failed", error=str(exc))

        rounds = []
        for r in (state.get("rounds") or []):
            try:
                rounds.append(RoundTrace.model_validate(r))
            except Exception as exc:
                logger.warning("state_to_trace.round_parse_failed", error=str(exc))

        ctx = request.investment_context if request.investment_context else InvestmentContext()
        model = request.model_config_.model if request.model_config_ else "ollama/llama2:7b"

        stream_events = list(state.get("stream_events") or [])

        return DebateTrace(
            debate_id=state["debate_id"],
            thesis=state["thesis"],
            investment_context=ctx,
            model_used=model,
            rounds=rounds,
            total_rounds_completed=len(rounds),
            conflicts=conflicts,
            tiebreaker_outputs=tb_outputs,
            committee_memo=memo,
            budget_summary=budget_summary,
            stream_events=stream_events,
            status="complete" if memo else "failed",
            completed_at=datetime.now(timezone.utc),
        )

    async def run(self, request: DebateRequest) -> DebateTrace:
        """Run a complete debate and return the full trace."""
        initial = self._make_initial_state(request)
        logger.info(
            "orchestrator.run_start",
            debate_id=initial["debate_id"],
            thesis=request.thesis[:80],
        )

        try:
            final_state = await self._graph.ainvoke(initial)
            trace = self._state_to_trace(final_state, request)
            logger.info(
                "orchestrator.run_complete",
                debate_id=trace.debate_id,
                status=trace.status,
            )
            return trace
        except Exception as e:
            logger.error("orchestrator.run_failed", error=str(e))
            raise

    async def run_streaming(
        self,
        request: DebateRequest,
        repository=None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Run debate and yield StreamEvents as they are produced.

        Optionally accepts a repository to persist the final trace
        once the graph finishes, so SSE replay works on reconnect.
        """
        initial = self._make_initial_state(request)
        seen_event_ids = set()
        final_state: Optional[Dict[str, Any]] = None

        async for chunk in self._graph.astream(initial, stream_mode="updates"):
            for node_name, node_state in chunk.items():
                events = node_state.get("stream_events", [])
                for ev_dict in events:
                    ev_id = ev_dict.get("id", "")
                    if ev_id not in seen_event_ids:
                        seen_event_ids.add(ev_id)
                        try:
                            yield StreamEvent.model_validate(ev_dict)
                        except Exception as exc:
                            logger.warning(
                                "run_streaming.event_parse_failed",
                                error=str(exc),
                            )
            # Track the latest full node state for final state capture
            # (LangGraph "updates" mode returns partial node updates)
            if final_state is None:
                final_state = {}
            for node_name, node_state in chunk.items():
                final_state.update(node_state)

        if repository is not None and final_state is not None:
            try:
                # Merge initial state with final accumulated state
                merged = dict(initial)
                merged.update(final_state)
                trace = self._state_to_trace(merged, request)  # type: ignore[arg-type]
                repository.save(trace)
                logger.info(
                    "run_streaming.trace_persisted",
                    debate_id=request.debate_id,
                )
            except Exception as exc:
                logger.warning(
                    "run_streaming.persist_failed",
                    debate_id=request.debate_id,
                    error=str(exc),
                )
