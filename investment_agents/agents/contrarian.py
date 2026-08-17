"""Contrarian analyst agent."""
from __future__ import annotations

from typing import Any, Dict, List

import structlog

from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AgentResponse, AnalystOutput

logger = structlog.get_logger(__name__)

SCHEMA = """{
  "recommendation": "sell",
  "conviction_score": 0.7,
  "numeric_score": -0.5,
  "thesis_agreement": "Consensus is too optimistic — contrarian signals flash caution",
  "key_argument": "When everyone agrees on a trade, it is usually crowded and near its peak",
  "supporting_evidence": [
    {"claim": "Analyst buy ratings at 92% — extreme crowding", "source_type": "qualitative", "confidence": 0.75, "supports_thesis": false}
  ],
  "agent_specific_analysis": {
    "contrarian_signal": "Extreme bullish sentiment",
    "crowding_level": "high",
    "historical_analogy": "Similar to 2021 growth bubble"
  },
  "response_to_agents": [
    {"responding_to_agent": "momentum_trader", "agreement_level": -0.6, "rebuttal": "Momentum chasers are the last ones in before the reversal", "concession": null}
  ],
  "position_changed": false,
  "position_change_reason": null
}"""

SYSTEM = """You are a contrarian analyst. Your job is to steelman the opposing view — if most agents are bullish, find the strongest bear case. If bearish, find the bull case.
Challenge consensus assumptions. Use second-order thinking.
Blind spot: sometimes contrarian for its own sake.

IMPORTANT: You MUST respond with ONLY a valid JSON object. No explanation text before or after the JSON. Start your response with { and end with }."""


class ContrarianAgent(BaseAnalystAgent):
    """Contrarian analyst: challenges consensus, steelmans opposing views, second-order thinking."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CONTRARIAN

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
                        responding_to_agent=r.get("responding_to_agent", "contrarian"),
                        agreement_level=self._safe_float(
                            r.get("agreement_level", 0), lo=-1.0, hi=1.0
                        ),
                        rebuttal=self._safe_str(r.get("rebuttal", ""), max_len=400),
                        concession=r.get("concession"),
                    )
                )
            except Exception:
                pass

        return AnalystOutput(
            agent_id=f"contrarian_r{round_number}",
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
            agent_specific_analysis=data.get("agent_specific_analysis", {}),
            response_to_agents=responses or None,
            position_changed=bool(data.get("position_changed", False)),
            position_change_reason=data.get("position_change_reason"),
            tokens_used=tokens_used,
            tokens_allocated=tokens_allocated,
        )
