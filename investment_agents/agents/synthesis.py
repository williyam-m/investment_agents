"""
Synthesis agent — investment committee chair.
Reads the full debate and produces a CommitteeMemo as the final deliverable.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AnalystOutput, Recommendation
from investment_agents.models.divergence import ConflictPoint
from investment_agents.models.synthesis import CommitteeMemo, DissentingView, ReasoningStep

logger = structlog.get_logger(__name__)

_MAX_JSON_RETRIES = 2

SCHEMA = """{
  "final_recommendation": "strong_buy|buy|hold|sell|strong_sell",
  "conviction": 0.0-1.0,
  "vote_breakdown": {"buy": N, "sell": N, "hold": N},
  "executive_summary": "2-3 sentence summary for a portfolio manager (max 600 chars)",
  "key_thesis": "core investment thesis the committee evaluated (max 500 chars)",
  "bull_case": "strongest bull arguments from the debate (max 500 chars)",
  "bear_case": "strongest bear arguments from the debate (max 500 chars)",
  "key_risks": ["risk1", "risk2", "risk3"],
  "catalysts_to_watch": ["catalyst1", "catalyst2"],
  "debate_was_contentious": false,
  "committee_divided": false,
  "dissenting_views": [
    {
      "agent_type": "agent_type_string",
      "recommendation": "buy|sell|hold|...",
      "conviction": 0.0-1.0,
      "key_argument": "max 300 chars",
      "why_not_adopted": "max 300 chars"
    }
  ],
  "reasoning_trace": [
    {
      "step": "step_name",
      "description": "what this step does",
      "input_summary": "what went in",
      "output_summary": "what came out"
    }
  ]
}"""

SYSTEM = """You are the investment committee chair.
Synthesize all analyst arguments into a final committee memo.
Weight arguments by evidence quality and conviction.
Acknowledge dissent. Be honest about uncertainty.
Always respond with valid JSON only."""


class SynthesisAgent(BaseAnalystAgent):
    """
    Investment committee chair: synthesizes all debate outputs into a final CommitteeMemo.

    This agent has a distinct interface from the other analyst agents:
    instead of `analyze()` it exposes `analyze_debate()` which takes the
    full list of AnalystOutputs and ConflictPoints and returns a CommitteeMemo.
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.SYNTHESIS

    @property
    def system_prompt(self) -> str:
        return SYSTEM

    @property
    def json_schema_description(self) -> str:
        return SCHEMA

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    async def analyze_debate(
        self,
        thesis: str,
        all_outputs: List[AnalystOutput],
        conflicts: List[ConflictPoint],
        debate_id: str,
        token_allocation: int,
        total_rounds: int = 0,
    ) -> CommitteeMemo:
        """
        Synthesize the full debate into a CommitteeMemo.

        Parameters
        ----------
        thesis          : The original investment thesis.
        all_outputs     : Every AnalystOutput produced across all rounds.
        conflicts       : Detected conflict points from the divergence scorer.
        debate_id       : Unique identifier for this debate run.
        token_allocation: Max tokens to spend on this call.
        total_rounds    : Total rounds completed in this debate.

        Returns
        -------
        CommitteeMemo   : Production-quality investment recommendation with full trace.
        """
        self._total_rounds = total_rounds  # stored so _parse_memo can use it
        log = logger.bind(agent_id="synthesis", debate_id=debate_id)

        debate_context = self._format_debate_context(thesis, all_outputs, conflicts)
        user_msg = (
            "You have reviewed the full investment committee debate above.\n"
            "Produce the final committee memo as a JSON object matching this schema:\n"
            f"{self.json_schema_description}"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": debate_context + "\n\n" + user_msg},
        ]

        total_tokens = 0
        raw_text = ""

        for attempt in range(_MAX_JSON_RETRIES + 1):
            try:
                raw_text, total_tokens = await self.llm.complete(
                    messages,
                    agent_id="synthesis",
                    debate_id=debate_id,
                    round_number=0,
                    max_tokens=min(token_allocation, 2000),
                    temperature=0.5,
                )
                data = self.llm.extract_json(raw_text)
                memo = self._parse_memo(data, total_tokens, self.llm.model, total_rounds=total_rounds)
                log.info(
                    "synthesis.complete",
                    recommendation=memo.final_recommendation,
                    conviction=memo.conviction,
                    tokens=total_tokens,
                )
                return memo
            except Exception as exc:
                log.warning("synthesis.parse_failed", attempt=attempt, error=str(exc))
                if attempt < _MAX_JSON_RETRIES:
                    messages.append({"role": "assistant", "content": raw_text})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your response was not valid JSON. Error: {exc}\n"
                                f"Please respond with ONLY a valid JSON object matching:\n"
                                f"{self.json_schema_description}"
                            ),
                        }
                    )
                else:
                    log.error("synthesis.all_retries_exhausted", debate_id=debate_id)

        return self._fallback_memo(all_outputs, total_tokens)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_memo(
        self, data: Dict[str, Any], total_tokens: int, model: str, total_rounds: int = 0
    ) -> CommitteeMemo:
        """Parse raw LLM JSON dict into a validated CommitteeMemo."""
        # Recommendation
        rec_str = str(data.get("final_recommendation", "hold")).lower().strip()
        rec_map = {r.value: r for r in Recommendation}
        final_rec = rec_map.get(rec_str, Recommendation.HOLD)

        # Conviction
        conviction = self._safe_float(data.get("conviction", 0.5), lo=0.0, hi=1.0)

        # Vote breakdown
        raw_votes = data.get("vote_breakdown", {})
        vote_breakdown = {str(k): int(v) for k, v in raw_votes.items()} if isinstance(raw_votes, dict) else {}

        # Text fields
        executive_summary = self._safe_str(data.get("executive_summary", ""), max_len=600)
        key_thesis = self._safe_str(data.get("key_thesis", ""), max_len=500)
        bull_case = self._safe_str(data.get("bull_case", ""), max_len=500)
        bear_case = self._safe_str(data.get("bear_case", ""), max_len=500)

        # Lists
        key_risks = [str(r)[:200] for r in (data.get("key_risks") or [])[:5]]
        if not key_risks:
            key_risks = ["Insufficient data to assess risks"]
        catalysts = [str(c)[:200] for c in (data.get("catalysts_to_watch") or [])[:5]]

        # Debate dynamics
        debate_contentious = bool(data.get("debate_was_contentious", False))
        committee_divided = bool(data.get("committee_divided", False))

        # Dissenting views
        dissenting_views: List[DissentingView] = []
        for dv in data.get("dissenting_views") or []:
            try:
                agent_type_str = str(dv.get("agent_type", "value_investor")).lower()
                agent_type_map = {a.value: a for a in AgentType}
                agent_t = agent_type_map.get(agent_type_str, AgentType.VALUE_INVESTOR)

                dv_rec_str = str(dv.get("recommendation", "hold")).lower().strip()
                dv_rec = rec_map.get(dv_rec_str, Recommendation.HOLD)

                dissenting_views.append(
                    DissentingView(
                        agent_type=agent_t,
                        recommendation=dv_rec,
                        conviction=self._safe_float(dv.get("conviction", 0.5), lo=0.0, hi=1.0),
                        key_argument=self._safe_str(dv.get("key_argument", ""), max_len=300),
                        why_not_adopted=self._safe_str(dv.get("why_not_adopted", ""), max_len=300),
                    )
                )
            except Exception:
                pass

        # Reasoning trace
        reasoning_trace: List[ReasoningStep] = []
        for step in data.get("reasoning_trace") or []:
            try:
                reasoning_trace.append(
                    ReasoningStep(
                        step=self._safe_str(step.get("step", ""), max_len=100),
                        description=self._safe_str(step.get("description", ""), max_len=300),
                        input_summary=self._safe_str(step.get("input_summary", ""), max_len=300),
                        output_summary=self._safe_str(step.get("output_summary", ""), max_len=300),
                    )
                )
            except Exception:
                pass

        # Derive total rounds from data we have
        return CommitteeMemo(
            final_recommendation=final_rec,
            conviction=conviction,
            vote_breakdown=vote_breakdown,
            executive_summary=executive_summary,
            key_thesis=key_thesis,
            bull_case=bull_case,
            bear_case=bear_case,
            key_risks=key_risks,
            catalysts_to_watch=catalysts,
            debate_was_contentious=debate_contentious,
            committee_divided=committee_divided,
            dissenting_views=dissenting_views,
            reasoning_trace=reasoning_trace,
            total_rounds=int(data.get("total_rounds", 0)),
            total_tokens_used=total_tokens,
            model_used=model,
            synthesis_quality="full",
        )

    # ------------------------------------------------------------------
    # _parse_output: required by BaseAnalystAgent but not used here.
    # SynthesisAgent exposes analyze_debate() instead of analyze().
    # ------------------------------------------------------------------

    def _parse_output(
        self,
        data: Dict[str, Any],
        round_number: int,
        tokens_used: int,
        tokens_allocated: int,
    ) -> AnalystOutput:  # pragma: no cover
        raise NotImplementedError(
            "SynthesisAgent does not use _parse_output. Use analyze_debate() instead."
        )

    # ------------------------------------------------------------------
    # Context formatters
    # ------------------------------------------------------------------

    def _format_debate_context(
        self,
        thesis: str,
        all_outputs: List[AnalystOutput],
        conflicts: List[ConflictPoint],
    ) -> str:
        """Build the full debate context string sent to the LLM."""
        lines: List[str] = [f"=== Investment Thesis ===\n{thesis}\n"]

        # Group outputs by round for readability
        rounds: Dict[int, List[AnalystOutput]] = {}
        for out in all_outputs:
            rounds.setdefault(out.round_number, []).append(out)

        for rn in sorted(rounds):
            lines.append(f"\n=== Round {rn} ===")
            for out in rounds[rn]:
                lines.append(
                    f"[{out.agent_type.value.upper()}] "
                    f"Rec: {out.recommendation.value} "
                    f"(score {out.numeric_score:+.2f}, conviction {out.conviction_score:.2f})\n"
                    f"Key argument: {out.key_argument}\n"
                    f"Thesis stance: {out.thesis_agreement}"
                )
                if out.response_to_agents:
                    for resp in out.response_to_agents:
                        lines.append(
                            f"  → Response to {resp.responding_to_agent}: "
                            f"agreement={resp.agreement_level:+.1f} | {resp.rebuttal}"
                        )

        # Conflicts
        if conflicts:
            lines.append("\n=== Detected Conflicts ===")
            for c in conflicts:
                lines.append(
                    f"[{c.severity.value.upper()}] {c.agent_a} vs {c.agent_b} "
                    f"(score gap {c.score_gap:.2f}): {c.description}\n"
                    f"  {c.agent_a}: {c.agent_a_position}\n"
                    f"  {c.agent_b}: {c.agent_b_position}"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback_memo(
        self, all_outputs: List[AnalystOutput], total_tokens: int
    ) -> CommitteeMemo:
        """Return a degraded memo when synthesis fails after all retries."""
        logger.error("synthesis.fallback_memo_produced")

        if all_outputs:
            avg_score = sum(o.numeric_score for o in all_outputs) / len(all_outputs)
            rec = (
                Recommendation.BUY if avg_score > 0.2
                else Recommendation.SELL if avg_score < -0.2
                else Recommendation.HOLD
            )
            max_round = max(o.round_number for o in all_outputs)
        else:
            rec = Recommendation.HOLD
            max_round = 0

        return CommitteeMemo(
            final_recommendation=rec,
            conviction=0.1,
            vote_breakdown={},
            executive_summary=(
                "Synthesis agent failed to produce structured output. "
                "Recommendation derived from raw agent score average. "
                "Manual review required."
            ),
            key_thesis="Not available — synthesis failure.",
            bull_case="Not available.",
            bear_case="Not available.",
            key_risks=["Synthesis failure — treat this recommendation with extreme caution."],
            catalysts_to_watch=[],
            debate_was_contentious=True,
            committee_divided=True,
            dissenting_views=[],
            reasoning_trace=[],
            total_rounds=max_round,
            total_tokens_used=total_tokens,
            model_used=self.llm.model,
            synthesis_quality="degraded",
        )
