"""Tiebreaker agent — called when analysts reach irreconcilable conflict."""
from __future__ import annotations

from typing import Any, Dict, List

import structlog

from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AgentResponse, AnalystOutput

logger = structlog.get_logger(__name__)

SCHEMA = """{
  "recommendation": "buy",
  "conviction_score": 0.6,
  "numeric_score": 0.3,
  "thesis_agreement": "After weighing both sides, slight edge to the bull case",
  "key_argument": "The value case is more grounded in fundamentals than the bear case",
  "supporting_evidence": [
    {"claim": "Discounted cash flow shows 20% upside", "source_type": "financial_metric", "confidence": 0.7, "supports_thesis": true}
  ],
  "agent_specific_analysis": {
    "adjudication_basis": "Fundamental analysis outweighs momentum concerns",
    "confidence_in_adjudication": 0.6
  },
  "response_to_agents": [
    {"responding_to_agent": "risk_analyst", "agreement_level": 0.4, "rebuttal": "Risk concerns are noted but the bull case has stronger evidence quality", "concession": null}
  ],
  "position_changed": false,
  "position_change_reason": null
}"""

SYSTEM = """You are an objective arbitrator called in when analysts have irreconcilable conflict.
Review both positions fairly and determine which argument is stronger based on evidence quality, logical consistency, and risk-adjusted reasoning.

IMPORTANT: You MUST respond with ONLY a valid JSON object. No explanation text before or after the JSON. Start your response with { and end with }."""


class TiebreakerAgent(BaseAnalystAgent):
    """Tiebreaker arbitrator: resolves hard conflicts between analysts with impartial reasoning."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.TIEBREAKER

    @property
    def system_prompt(self) -> str:
        return SYSTEM

    @property
    def json_schema_description(self) -> str:
        return SCHEMA

    def _parse_output(
        self,
        data: Dict[str, Any],
        round_number: int,
        tokens_used: int,
        tokens_allocated: int,
    ) -> AnalystOutput:
        responses: List[AgentResponse] = []
        for r in data.get("response_to_agents") or []:
            try:
                responses.append(
                    AgentResponse(
                        responding_to_agent=r.get("responding_to_agent", "tiebreaker"),
                        agreement_level=self._safe_float(
                            r.get("agreement_level", 0), lo=-1.0, hi=1.0
                        ),
                        rebuttal=self._safe_str(r.get("rebuttal", ""), max_len=400),
                        concession=r.get("concession"),
                    )
                )
            except Exception:
                pass

        # Extract tiebreaker-specific fields and validate resolution_confidence
        agent_specific = data.get("agent_specific_analysis", {})
        if isinstance(agent_specific, dict):
            raw_conf = agent_specific.get("resolution_confidence")
            if raw_conf is not None:
                agent_specific["resolution_confidence"] = self._safe_float(
                    raw_conf, lo=0.0, hi=1.0
                )

        return AnalystOutput(
            agent_id=f"tiebreaker_r{round_number}",
            agent_type=self.agent_type,
            round_number=round_number,
            recommendation=self._rec_from_str(data.get("recommendation", "hold")),
            conviction_score=self._safe_float(
                data.get("conviction_score", 0.5), lo=0.0, hi=1.0
            ),
            numeric_score=self._safe_float(data.get("numeric_score", 0.0)),
            thesis_agreement=self._safe_str(data.get("thesis_agreement", ""), max_len=400),
            key_argument=self._safe_str(data.get("key_argument", ""), max_len=600),
            supporting_evidence=self._parse_evidence(data.get("supporting_evidence", [])),
            agent_specific_analysis=agent_specific,
            response_to_agents=responses or None,
            position_changed=bool(data.get("position_changed", False)),
            position_change_reason=data.get("position_change_reason"),
            tokens_used=tokens_used,
            tokens_allocated=tokens_allocated,
        )
