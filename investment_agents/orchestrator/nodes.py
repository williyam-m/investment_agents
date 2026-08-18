"""Graph nodes — each is a pure async function: state -> state_updates."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from investment_agents.agents.contrarian import ContrarianAgent
from investment_agents.agents.macro_economist import MacroEconomistAgent
from investment_agents.agents.momentum_trader import MomentumTraderAgent
from investment_agents.agents.risk_analyst import RiskAnalystAgent
from investment_agents.agents.synthesis import SynthesisAgent
from investment_agents.agents.tiebreaker import TiebreakerAgent
from investment_agents.agents.value_investor import ValueInvestorAgent
from investment_agents.analysis.convergence import ConvergenceDetector
from investment_agents.analysis.divergence import DivergenceScorer
from investment_agents.budget.allocator import BudgetAllocator
from investment_agents.budget.policy import ExploreExploitPolicy, DebateMode as PolicyDebateMode
from investment_agents.config.settings import get_settings
from investment_agents.llm.client import LLMClient
from investment_agents.models.agent_output import AnalystOutput
from investment_agents.models.budget import (
    BudgetAllocation,
    BudgetDecision,
    BudgetReport,
    TokenBudget,
)
from investment_agents.models.debate import RoundTrace, RoutingDecision
from investment_agents.models.divergence import ConflictPoint, ConflictSeverity, DivergenceReport
from investment_agents.models.streaming import (
    DebateMode as StreamDebateMode,
    StreamEvent,
    StreamEventType,
)
from investment_agents.orchestrator.state import DebateState

logger = structlog.get_logger(__name__)

# Minimum tokens guaranteed per agent per round
_MIN_AGENT_TOKENS: int = 400
# Number of core analyst agents
_NUM_AGENTS: int = 5
# Agent type string → used to index allocations
_AGENT_TYPES = [
    "value_investor",
    "momentum_trader",
    "risk_analyst",
    "macro_economist",
    "contrarian",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_agent_allocation(
    budget_report: dict,
    agent_type: str,
    round_number: int,
) -> int:
    """
    Retrieve per-agent token allocation from the serialised BudgetReport dict.
    Falls back to 600 if not found.
    """
    allocations: List[dict] = budget_report.get("round_allocations", [])
    for alloc in allocations:
        if (
            alloc.get("agent_type") == agent_type
            and alloc.get("round_number") == round_number
        ):
            return int(alloc.get("allocated", 600))
    return 600


def _serialize_event(event: StreamEvent) -> dict:
    """Serialize a StreamEvent for storage inside DebateState."""
    return event.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Node 1 — Initialise debate
# ---------------------------------------------------------------------------

async def node_init(state: DebateState) -> dict:
    """
    Initialise all mutable state fields before the first round.
    Emits DEBATE_STARTED stream event.
    """
    debate_id = state["debate_id"]
    thesis = state["thesis"]
    total_budget = state["total_budget"]
    max_rounds = state["max_rounds"]
    model = state["model"]

    logger.info(
        "node.init",
        debate_id=debate_id,
        thesis=thesis[:80],
        total_budget=total_budget,
        max_rounds=max_rounds,
    )

    # Build the initial BudgetReport
    token_budget = TokenBudget(
        total=total_budget,
        reserved_for_synthesis=2000,
    )
    budget_report = BudgetReport(token_budget=token_budget)

    # Emit DEBATE_STARTED event
    started_event = StreamEvent.debate_started(
        debate_id=debate_id,
        thesis=thesis,
        total_budget=total_budget,
        max_rounds=max_rounds,
        model=model,
    )

    return {
        "round_number": 1,
        "debate_mode": "explore",
        "current_round_outputs": [],
        "all_round_outputs": [],
        "tiebreaker_outputs": [],
        "conflicts": [],
        "convergence_signals": [],
        "rounds": [],
        "stream_events": [_serialize_event(started_event)],
        "should_continue": True,
        "spawn_tiebreaker": False,
        "committee_memo": None,
        "routing_decision": None,
        "divergence_report": None,
        "budget_report": budget_report.model_dump(mode="json"),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Node 2 — Allocate per-agent budget for this round
# ---------------------------------------------------------------------------

async def node_allocate_budget(state: DebateState) -> dict:
    """
    Decide how many tokens each of the 5 core agents receives this round.

    Uses BudgetAllocator for explore/exploit weighted allocation.
    Every agent is guaranteed at least _MIN_AGENT_TOKENS tokens.
    """
    debate_id = state["debate_id"]
    round_number = state["round_number"]
    debate_mode = state["debate_mode"]
    budget_report_dict = state["budget_report"]

    budget_report = BudgetReport.model_validate(budget_report_dict)
    available = budget_report.token_budget.available

    logger.info(
        "node.allocate_budget",
        debate_id=debate_id,
        round=round_number,
        mode=debate_mode,
        available=available,
    )

    settings = get_settings()
    allocator = BudgetAllocator(agent_types=_AGENT_TYPES, settings=settings)

    # Deserialize DivergenceReport if present (for exploit-mode weighting)
    div_report_obj: Optional[DivergenceReport] = None
    div_report_dict = state.get("divergence_report")
    if div_report_dict:
        try:
            div_report_obj = DivergenceReport.model_validate(div_report_dict)
        except Exception as exc:
            logger.warning("node.allocate_budget.divergence_parse_failed", error=str(exc))

    allocations: Dict[str, int] = allocator.allocate_round(
        available_tokens=available,
        round_number=round_number,
        mode=debate_mode,
        divergence_report=div_report_obj,
    )

    total_allocated = sum(allocations.values())
    if total_allocated > available and available > 0:
        if available < _MIN_AGENT_TOKENS * _NUM_AGENTS:
            # Not enough budget to give everyone the minimum — distribute proportionally,
            # never clamping up to _MIN_AGENT_TOKENS (that would exceed budget).
            scale = available / total_allocated
            allocations = {
                agent: max(1, int(tokens * scale))
                for agent, tokens in allocations.items()
            }
        else:
            scale = available / total_allocated
            allocations = {
                agent: max(_MIN_AGENT_TOKENS, int(tokens * scale))
                for agent, tokens in allocations.items()
            }
        # Final hard cap: ensure total never exceeds available
        final_total = sum(allocations.values())
        if final_total > available:
            sorted_agents = sorted(allocations.keys())
            excess = final_total - available
            for agent in sorted_agents:
                if excess <= 0:
                    break
                reduction = min(allocations[agent], excess)
                allocations[agent] -= reduction
                excess -= reduction
        logger.warning(
            "node.allocate_budget.scaled_down",
            original_total=total_allocated,
            available=available,
            scaled_total=sum(allocations.values()),
        )

    # Convert to BudgetAllocation objects and append to the report
    mode_str = debate_mode
    alloc_objects: List[BudgetAllocation] = []
    for agent_type, tokens in allocations.items():
        alloc_obj = BudgetAllocation(
            agent_type=agent_type,
            allocated=tokens,
            used=0,
            round_number=round_number,
            mode=mode_str,
        )
        alloc_objects.append(alloc_obj)
        budget_report.round_allocations.append(alloc_obj)

    # Record the budget decision
    decision = BudgetDecision(
        round_number=round_number,
        mode=mode_str,
        total_round_budget=sum(allocations.values()),
        allocations=allocations,
        reasoning=(
            f"BudgetAllocator {'equal split' if debate_mode == 'explore' else 'exploit-weighted allocation'} "
            f"for round {round_number}. Available: {available} tokens."
        ),
    )
    budget_report.decisions.append(decision)

    # Emit ROUND_STARTED event
    stream_mode = (
        StreamDebateMode.EXPLORE if debate_mode == "explore" else StreamDebateMode.EXPLOIT
    )
    round_started_event = StreamEvent.round_started(
        debate_id=debate_id,
        round_number=round_number,
        mode=stream_mode,
        allocations=allocations,
    )

    existing_events: List[dict] = list(state.get("stream_events", []))
    existing_events.append(_serialize_event(round_started_event))

    logger.info(
        "node.allocate_budget.done",
        debate_id=debate_id,
        round=round_number,
        allocations=allocations,
    )

    return {
        "budget_report": budget_report.model_dump(mode="json"),
        "stream_events": existing_events,
    }


# ---------------------------------------------------------------------------
# Node 3 — Run all 5 analyst agents in parallel
# ---------------------------------------------------------------------------

async def node_run_agents(state: DebateState) -> dict:
    """
    Run all 5 analyst agents in parallel using asyncio.gather.

    Handles failures gracefully — exceptions produce fallback outputs.
    Emits AGENT_OUTPUT and BUDGET_UPDATE stream events.
    """
    debate_id = state["debate_id"]
    round_number = state["round_number"]
    thesis = state["thesis"]
    investment_context = state["investment_context"]
    prior_outputs: List[AnalystOutput] = list(state.get("all_round_outputs", []))
    budget_report_dict = state["budget_report"]
    model = state["model"]

    budget_report = BudgetReport.model_validate(budget_report_dict)
    llm = LLMClient(model=model)

    # Instantiate all 5 agents
    agents = [
        ValueInvestorAgent(llm),
        MomentumTraderAgent(llm),
        RiskAnalystAgent(llm),
        MacroEconomistAgent(llm),
        ContrarianAgent(llm),
    ]

    # Build per-agent token allocations
    agent_token_map: Dict[str, int] = {
        agent.agent_type.value: _get_agent_allocation(
            budget_report_dict, agent.agent_type.value, round_number
        )
        for agent in agents
    }

    logger.info(
        "node.run_agents.start",
        debate_id=debate_id,
        round=round_number,
        allocations=agent_token_map,
    )

    # ── Coroutines for all 5 agents ────────────────────────────────────────
    async def run_agent(agent):
        allocation = agent_token_map.get(agent.agent_type.value, _MIN_AGENT_TOKENS)
        return await agent.analyze(
            thesis=thesis,
            investment_context=investment_context,
            round_number=round_number,
            debate_id=debate_id,
            prior_outputs=prior_outputs,
            token_allocation=allocation,
        )

    results = await asyncio.gather(
        *[run_agent(agent) for agent in agents],
        return_exceptions=True,
    )

    # ── Process results ─────────────────────────────────────────────────────
    outputs: List[AnalystOutput] = []
    new_stream_events: List[dict] = list(state.get("stream_events", []))

    for agent, result in zip(agents, results):
        agent_type_str = agent.agent_type.value
        alloc_tokens = agent_token_map.get(agent_type_str, _MIN_AGENT_TOKENS)

        if isinstance(result, Exception):
            logger.warning(
                "node.run_agents.agent_exception",
                debate_id=debate_id,
                agent=agent_type_str,
                error=str(result),
            )
            output = agent._fallback_output(round_number, alloc_tokens)
        else:
            output = result

        # Record token usage in budget
        budget_report.record_usage(
            agent_type=agent_type_str,
            round_number=round_number,
            tokens=output.tokens_used,
        )

        # Update the corresponding BudgetAllocation.used field
        alloc_obj = budget_report.get_allocation(agent_type_str, round_number)
        if alloc_obj is not None:
            alloc_obj.used = output.tokens_used

        outputs.append(output)

        # Emit AGENT_OUTPUT event
        agent_event = StreamEvent(
            type=StreamEventType.AGENT_OUTPUT,
            debate_id=debate_id,
            data={
                "agent_type": agent_type_str,
                "round_number": round_number,
                "recommendation": output.recommendation.value,
                "numeric_score": output.numeric_score,
                "conviction_score": output.conviction_score,
                "key_argument": output.key_argument,
                "tokens_used": output.tokens_used,
                "tokens_allocated": output.tokens_allocated,
            },
        )
        new_stream_events.append(_serialize_event(agent_event))

    # Emit BUDGET_UPDATE event after all agents
    budget_event = StreamEvent.budget_update(
        debate_id=debate_id,
        used=budget_report.token_budget.used,
        remaining=budget_report.token_budget.remaining,
        by_agent=dict(budget_report.by_agent),
    )
    new_stream_events.append(_serialize_event(budget_event))

    updated_all = list(prior_outputs) + outputs

    logger.info(
        "node.run_agents.done",
        debate_id=debate_id,
        round=round_number,
        agent_count=len(outputs),
        tokens_used=budget_report.token_budget.used,
        tokens_remaining=budget_report.token_budget.remaining,
    )

    return {
        "current_round_outputs": outputs,
        "all_round_outputs": updated_all,
        "budget_report": budget_report.model_dump(mode="json"),
        "stream_events": new_stream_events,
    }


# ---------------------------------------------------------------------------
# Node 4 — Score divergence and detect conflicts / convergence
# ---------------------------------------------------------------------------

async def node_score_divergence(state: DebateState) -> dict:
    """
    Run DivergenceScorer and ConvergenceDetector on the current round outputs.
    Emits DIVERGENCE_SCORED, CONFLICT_DETECTED, and CONVERGENCE_SIGNAL events.
    """
    debate_id = state["debate_id"]
    round_number = state["round_number"]
    current_outputs: List[AnalystOutput] = list(state.get("current_round_outputs", []))
    existing_conflicts: List[dict] = list(state.get("conflicts", []))
    new_stream_events: List[dict] = list(state.get("stream_events", []))

    logger.info(
        "node.score_divergence",
        debate_id=debate_id,
        round=round_number,
        agent_count=len(current_outputs),
    )

    # ── DivergenceScorer ──────────────────────────────────────────────────
    scorer = DivergenceScorer()
    div_report: DivergenceReport = scorer.score(current_outputs, round_number)

    # ── ConvergenceDetector ───────────────────────────────────────────────
    detector = ConvergenceDetector()
    conv_signals = detector.detect(current_outputs, round_number)

    # Attach convergence topics to the report
    div_report.converging_topics = conv_signals

    # ── Merge conflicts ───────────────────────────────────────────────────
    new_conflicts_dicts: List[dict] = [
        c.model_dump(mode="json") for c in div_report.conflicts
    ]
    all_conflicts = existing_conflicts + new_conflicts_dicts

    # ── Convergence signals ───────────────────────────────────────────────
    existing_conv: List[dict] = list(state.get("convergence_signals", []))
    new_conv_dicts: List[dict] = [cs.model_dump(mode="json") for cs in conv_signals]
    all_conv_signals = existing_conv + new_conv_dicts

    # ── Emit DIVERGENCE_SCORED event ──────────────────────────────────────
    div_event = StreamEvent(
        type=StreamEventType.DIVERGENCE_SCORED,
        debate_id=debate_id,
        data={
            "round_number": round_number,
            "overall_score": div_report.overall_score,
            "recommendation_variance": div_report.recommendation_variance,
            "semantic_divergence": div_report.semantic_divergence,
            "conflict_penalty": div_report.conflict_penalty,
            "has_hard_conflicts": div_report.has_hard_conflicts,
            "is_high_divergence": div_report.is_high_divergence,
            "is_converging": div_report.is_converging,
            "exploit_worthy_agents": div_report.exploit_worthy_agents,
        },
    )
    new_stream_events.append(_serialize_event(div_event))

    # ── Emit CONFLICT_DETECTED for each hard conflict ─────────────────────
    for conflict in div_report.conflicts:
        if conflict.severity == ConflictSeverity.HARD:
            conflict_event = StreamEvent(
                type=StreamEventType.CONFLICT_DETECTED,
                debate_id=debate_id,
                data={
                    "conflict_id": conflict.conflict_id,
                    "agent_a": conflict.agent_a,
                    "agent_b": conflict.agent_b,
                    "severity": conflict.severity.value,
                    "score_gap": conflict.score_gap,
                    "description": conflict.description,
                    "round_number": round_number,
                },
            )
            new_stream_events.append(_serialize_event(conflict_event))

    # ── Emit CONVERGENCE_SIGNAL for each convergence signal ───────────────
    for cs in conv_signals:
        conv_event = StreamEvent(
            type=StreamEventType.CONVERGENCE_SIGNAL,
            debate_id=debate_id,
            data={
                "topic": cs.topic,
                "converging_agents": cs.converging_agents,
                "avg_score": cs.avg_score,
                "round_number": cs.round_number,
            },
        )
        new_stream_events.append(_serialize_event(conv_event))

    logger.info(
        "node.score_divergence.done",
        debate_id=debate_id,
        round=round_number,
        overall_score=div_report.overall_score,
        hard_conflicts=len([c for c in div_report.conflicts if c.severity == ConflictSeverity.HARD]),
        convergence_signals=len(conv_signals),
    )

    return {
        "divergence_report": div_report.model_dump(mode="json"),
        "conflicts": all_conflicts,
        "convergence_signals": all_conv_signals,
        "stream_events": new_stream_events,
    }


# ---------------------------------------------------------------------------
# Node 5 — Run tiebreaker agent for hard conflicts
# ---------------------------------------------------------------------------

async def node_run_tiebreaker(state: DebateState) -> dict:
    """
    Spawn a TiebreakerAgent for each hard conflict that hasn't been resolved.
    Deducts from token budget.
    Emits TIEBREAKER_SPAWNED stream event.
    """
    debate_id = state["debate_id"]
    round_number = state["round_number"]
    thesis = state["thesis"]
    investment_context = state["investment_context"]
    model = state["model"]
    budget_report_dict = state["budget_report"]
    conflicts_dicts: List[dict] = list(state.get("conflicts", []))
    all_round_outputs: List[AnalystOutput] = list(state.get("all_round_outputs", []))
    existing_tb_outputs: List[AnalystOutput] = list(state.get("tiebreaker_outputs", []))
    new_stream_events: List[dict] = list(state.get("stream_events", []))

    budget_report = BudgetReport.model_validate(budget_report_dict)
    llm = LLMClient(model=model)
    tiebreaker = TiebreakerAgent(llm)

    settings = get_settings()

    # Find unresolved hard conflicts
    hard_conflicts: List[ConflictPoint] = []
    for c_dict in conflicts_dicts:
        try:
            c = ConflictPoint.model_validate(c_dict)
            if c.severity == ConflictSeverity.HARD and not c.resolved:
                hard_conflicts.append(c)
        except Exception:
            pass

    logger.info(
        "node.run_tiebreaker",
        debate_id=debate_id,
        round=round_number,
        hard_conflicts=len(hard_conflicts),
    )

    tb_outputs: List[AnalystOutput] = []
    updated_conflicts_dicts: List[dict] = list(conflicts_dicts)

    for conflict in hard_conflicts:
        available = budget_report.token_budget.available
        if available < settings.tiebreaker_min_budget:
            logger.warning(
                "node.run_tiebreaker.budget_insufficient",
                available=available,
                required=settings.tiebreaker_min_budget,
            )
            break

        tb_allocation = min(available, settings.tiebreaker_min_budget)

        # Build context that focuses on the conflict
        conflict_context = {
            **investment_context,
            "_conflict_summary": {
                "agent_a": conflict.agent_a,
                "agent_a_position": conflict.agent_a_position,
                "agent_b": conflict.agent_b,
                "agent_b_position": conflict.agent_b_position,
                "score_gap": conflict.score_gap,
                "description": conflict.description,
            },
        }

        try:
            tb_output = await tiebreaker.analyze(
                thesis=thesis,
                investment_context=conflict_context,
                round_number=round_number,
                debate_id=debate_id,
                prior_outputs=all_round_outputs,
                token_allocation=tb_allocation,
            )
        except Exception as exc:
            logger.warning(
                "node.run_tiebreaker.exception",
                debate_id=debate_id,
                error=str(exc),
            )
            tb_output = tiebreaker._fallback_output(round_number, tb_allocation)

        # Record budget usage
        budget_report.record_usage(
            agent_type="tiebreaker",
            round_number=round_number,
            tokens=tb_output.tokens_used,
        )

        tb_outputs.append(tb_output)

        # Mark conflict as resolved in state
        updated: List[dict] = []
        for c_dict in updated_conflicts_dicts:
            if c_dict.get("conflict_id") == conflict.conflict_id:
                c_dict = dict(c_dict)
                c_dict["resolved"] = True
                c_dict["resolution_notes"] = (
                    f"Tiebreaker reached: {tb_output.recommendation.value} "
                    f"(conviction {tb_output.conviction_score:.2f})"
                )
            updated.append(c_dict)
        updated_conflicts_dicts = updated

        # Emit TIEBREAKER_SPAWNED event
        tb_event = StreamEvent(
            type=StreamEventType.TIEBREAKER_SPAWNED,
            debate_id=debate_id,
            data={
                "conflict_id": conflict.conflict_id,
                "agent_a": conflict.agent_a,
                "agent_b": conflict.agent_b,
                "tiebreaker_recommendation": tb_output.recommendation.value,
                "tiebreaker_conviction": tb_output.conviction_score,
                "tokens_used": tb_output.tokens_used,
                "round_number": round_number,
            },
        )
        new_stream_events.append(_serialize_event(tb_event))

    all_tb_outputs = existing_tb_outputs + tb_outputs

    logger.info(
        "node.run_tiebreaker.done",
        debate_id=debate_id,
        tiebreakers_run=len(tb_outputs),
        tokens_remaining=budget_report.token_budget.remaining,
    )

    return {
        "tiebreaker_outputs": all_tb_outputs,
        "conflicts": updated_conflicts_dicts,
        "budget_report": budget_report.model_dump(mode="json"),
        "stream_events": new_stream_events,
        "spawn_tiebreaker": False,
    }


# ---------------------------------------------------------------------------
# Node 6 — Synthesize final committee memo
# ---------------------------------------------------------------------------

async def node_synthesize(state: DebateState) -> dict:
    """
    Run SynthesisAgent to produce the final CommitteeMemo.
    Uses all outputs from all rounds + tiebreaker outputs.
    Emits SYNTHESIS_STARTED and SYNTHESIS_COMPLETE events.
    """
    debate_id = state["debate_id"]
    round_number = state["round_number"]
    thesis = state["thesis"]
    model = state["model"]
    budget_report_dict = state["budget_report"]
    all_round_outputs: List[AnalystOutput] = list(state.get("all_round_outputs", []))
    tiebreaker_outputs: List[AnalystOutput] = list(state.get("tiebreaker_outputs", []))
    conflicts_dicts: List[dict] = list(state.get("conflicts", []))
    current_round_outputs: List[AnalystOutput] = list(state.get("current_round_outputs", []))
    new_stream_events: List[dict] = list(state.get("stream_events", []))

    budget_report = BudgetReport.model_validate(budget_report_dict)

    settings = get_settings()
    synthesis_budget = max(
        settings.min_synthesis_tokens,
        budget_report.token_budget.available,
    )

    logger.info(
        "node.synthesize",
        debate_id=debate_id,
        round=round_number,
        synthesis_budget=synthesis_budget,
        all_outputs=len(all_round_outputs),
    )

    # Emit SYNTHESIS_STARTED event
    synth_start_event = StreamEvent(
        type=StreamEventType.SYNTHESIS_STARTED,
        debate_id=debate_id,
        data={
            "round_number": round_number,
            "total_outputs": len(all_round_outputs),
            "synthesis_budget": synthesis_budget,
        },
    )
    new_stream_events.append(_serialize_event(synth_start_event))

    # Deserialize conflicts
    conflicts: List[ConflictPoint] = []
    for c_dict in conflicts_dicts:
        try:
            conflicts.append(ConflictPoint.model_validate(c_dict))
        except Exception:
            pass

    # Combine all outputs: analyst rounds + tiebreakers
    all_outputs = all_round_outputs + tiebreaker_outputs

    total_rounds_completed = max(
        (o.round_number for o in all_outputs), default=round_number
    )

    # Run SynthesisAgent
    llm = LLMClient(model=model)
    synthesis_agent = SynthesisAgent(llm)

    try:
        memo = await synthesis_agent.analyze_debate(
            thesis=thesis,
            all_outputs=all_outputs,
            conflicts=conflicts,
            debate_id=debate_id,
            token_allocation=synthesis_budget,
            total_rounds=total_rounds_completed,
        )
        # Record synthesis token usage
        budget_report.record_usage(
            agent_type="synthesis",
            round_number=round_number,
            tokens=memo.total_tokens_used,
        )
    except Exception as exc:
        logger.error(
            "node.synthesize.exception",
            debate_id=debate_id,
            error=str(exc),
        )
        # Build a degraded fallback memo
        memo = synthesis_agent._fallback_memo(all_outputs, 0)

    # Build the RoundTrace for the final round (current round outputs)
    # Build allocated and used dicts for this round
    budget_allocated: Dict[str, int] = {}
    budget_used: Dict[str, int] = {}
    for alloc in budget_report.round_allocations:
        if alloc.round_number == round_number:
            budget_allocated[alloc.agent_type] = alloc.allocated
            budget_used[alloc.agent_type] = alloc.used

    div_report_dict = state.get("divergence_report")
    div_report_obj: Optional[DivergenceReport] = None
    if div_report_dict:
        try:
            div_report_obj = DivergenceReport.model_validate(div_report_dict)
        except Exception:
            pass

    round_trace = RoundTrace(
        round_number=round_number,
        mode=state["debate_mode"],
        budget_allocated=budget_allocated,
        budget_used=budget_used,
        agent_outputs=current_round_outputs,
        divergence_report=div_report_obj,
        routing_decision=None,
        completed_at=datetime.now(timezone.utc),
    )

    existing_rounds: List[dict] = list(state.get("rounds", []))
    existing_rounds.append(round_trace.model_dump(mode="json"))

    # Emit SYNTHESIS_COMPLETE event
    synth_complete_event = StreamEvent(
        type=StreamEventType.SYNTHESIS_COMPLETE,
        debate_id=debate_id,
        data={
            "final_recommendation": memo.final_recommendation.value,
            "conviction": memo.conviction,
            "debate_was_contentious": memo.debate_was_contentious,
            "committee_divided": memo.committee_divided,
            "total_tokens_used": memo.total_tokens_used,
            "synthesis_quality": memo.synthesis_quality,
        },
    )
    new_stream_events.append(_serialize_event(synth_complete_event))

    # Emit DEBATE_COMPLETE event
    complete_event = StreamEvent(
        type=StreamEventType.DEBATE_COMPLETE,
        debate_id=debate_id,
        data={
            "debate_id": debate_id,
            "total_rounds": len(existing_rounds),
            "final_recommendation": memo.final_recommendation.value,
            "total_tokens_used": budget_report.token_budget.used,
        },
    )
    new_stream_events.append(_serialize_event(complete_event))

    logger.info(
        "node.synthesize.done",
        debate_id=debate_id,
        recommendation=memo.final_recommendation.value,
        conviction=memo.conviction,
    )

    return {
        "committee_memo": memo.model_dump(mode="json"),
        "should_continue": False,
        "budget_report": budget_report.model_dump(mode="json"),
        "rounds": existing_rounds,
        "stream_events": new_stream_events,
    }


# ---------------------------------------------------------------------------
# Node 7 — Prepare next round
# ---------------------------------------------------------------------------

async def node_prepare_next_round(state: DebateState) -> dict:
    """
    Transition to the next round:
    - Increment round_number
    - Save current round's RoundTrace to rounds list
    - Reset current_round_outputs
    - Update debate_mode from routing_decision (or divergence_report)
    - Emit MODE_CHANGED if mode switches
    """
    debate_id = state["debate_id"]
    round_number = state["round_number"]
    debate_mode = state["debate_mode"]
    current_round_outputs: List[AnalystOutput] = list(state.get("current_round_outputs", []))
    budget_report_dict = state["budget_report"]
    routing_decision_dict = state.get("routing_decision")
    div_report_dict = state.get("divergence_report")
    new_stream_events: List[dict] = list(state.get("stream_events", []))

    settings = get_settings()
    budget_report = BudgetReport.model_validate(budget_report_dict)

    logger.info(
        "node.prepare_next_round",
        debate_id=debate_id,
        current_round=round_number,
    )

    # ── Determine new mode using ExploreExploitPolicy ───────────────
    new_mode = debate_mode  # default: keep current mode
    mode_change_reason = ""
    divergence_score = 0.0
    policy_mode_str = debate_mode

    if div_report_dict:
        try:
            div_report = DivergenceReport.model_validate(div_report_dict)
            divergence_score = div_report.overall_score

            policy = ExploreExploitPolicy(
                explore_threshold=settings.explore_threshold,
                exploit_threshold=settings.exploit_threshold,
            )
            policy_mode, mode_change_reason = policy.decide(
                divergence_report=div_report,
                round_number=round_number,
                max_rounds=state["max_rounds"],
                remaining_tokens=budget_report.token_budget.remaining,
                min_synthesis_tokens=settings.min_synthesis_tokens,
            )

            # Map PolicyDebateMode → string stored in state
            if policy_mode == PolicyDebateMode.EXPLORE:
                policy_mode_str = "explore"
            elif policy_mode in (PolicyDebateMode.EXPLOIT, PolicyDebateMode.TRANSITION):
                policy_mode_str = "exploit"
            # SYNTHESIZE is handled by the edge router; keep current mode in state
            elif policy_mode == PolicyDebateMode.SYNTHESIZE:
                policy_mode_str = debate_mode

            new_mode = policy_mode_str
        except Exception as exc:
            logger.warning("node.prepare_next_round.policy_failed", error=str(exc))

    # Override with explicit routing decision if present
    if routing_decision_dict:
        try:
            rd = RoutingDecision.model_validate(routing_decision_dict)
            if rd.new_mode and rd.new_mode in ("explore", "exploit"):
                new_mode = rd.new_mode
                mode_change_reason = rd.reason
                divergence_score = rd.divergence_score
        except Exception as exc:
            logger.warning("node.prepare_next_round.routing_decision_parse_failed", error=str(exc))

    # Emit MODE_CHANGED event if mode switches
    if new_mode != debate_mode:
        mode_event = StreamEvent.mode_changed(
            debate_id=debate_id,
            from_mode=debate_mode,
            to_mode=new_mode,
            reason=mode_change_reason,
            divergence_score=divergence_score,
        )
        new_stream_events.append(_serialize_event(mode_event))
        logger.info(
            "node.prepare_next_round.mode_change",
            debate_id=debate_id,
            from_mode=debate_mode,
            to_mode=new_mode,
            divergence_score=divergence_score,
        )

    # ── Build RoundTrace for completed round ──────────────────────────────
    budget_allocated: Dict[str, int] = {}
    budget_used: Dict[str, int] = {}
    for alloc in budget_report.round_allocations:
        if alloc.round_number == round_number:
            budget_allocated[alloc.agent_type] = alloc.allocated
            budget_used[alloc.agent_type] = alloc.used

    div_report_obj: Optional[DivergenceReport] = None
    if div_report_dict:
        try:
            div_report_obj = DivergenceReport.model_validate(div_report_dict)
        except Exception:
            pass

    routing_obj: Optional[RoutingDecision] = None
    if routing_decision_dict:
        try:
            routing_obj = RoutingDecision.model_validate(routing_decision_dict)
        except Exception:
            pass

    round_trace = RoundTrace(
        round_number=round_number,
        mode=debate_mode,
        budget_allocated=budget_allocated,
        budget_used=budget_used,
        agent_outputs=current_round_outputs,
        divergence_report=div_report_obj,
        routing_decision=routing_obj,
        completed_at=datetime.now(timezone.utc),
    )

    existing_rounds: List[dict] = list(state.get("rounds", []))
    existing_rounds.append(round_trace.model_dump(mode="json"))

    next_round_number = round_number + 1

    logger.info(
        "node.prepare_next_round.done",
        debate_id=debate_id,
        next_round=next_round_number,
        new_mode=new_mode,
    )

    new_routing_decision = RoutingDecision(
        after_round=round_number,
        decision=new_mode,
        reason=mode_change_reason or f"Continuing in {new_mode} mode.",
        divergence_score=divergence_score,
        previous_mode=debate_mode,
        new_mode=new_mode,
    )

    return {
        "round_number": next_round_number,
        "debate_mode": new_mode,
        "current_round_outputs": [],
        "rounds": existing_rounds,
        "stream_events": new_stream_events,
        # Clear divergence_report — will be re-scored next round
        "divergence_report": None,
        "routing_decision": new_routing_decision.model_dump(mode="json"),
    }
