"""Risk Analyst agent."""
from __future__ import annotations

from typing import Any, Dict, List

import structlog

from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AgentResponse, AnalystOutput

logger = structlog.get_logger(__name__)

SCHEMA = """{
  "recommendation": "hold",
  "conviction_score": 0.6,
  "numeric_score": -0.2,
  "thesis_agreement": "Thesis has merit but underestimates tail risks",
  "key_argument": "Regulatory risk and leverage create downside scenario",
  "supporting_evidence": [
    {"claim": "Debt/equity ratio is high at 2.5x", "source_type": "financial_metric", "confidence": 0.9, "supports_thesis": false}
  ],
  "agent_specific_analysis": {
    "max_drawdown_scenario": "35% decline in bear case",
    "key_risk_factor": "Regulatory scrutiny",
    "risk_reward_ratio": "1:2"
  },
  "response_to_agents": [
    {"responding_to_agent": "momentum_trader", "agreement_level": -0.3, "rebuttal": "Momentum ignores the leverage risk that could amplify any downturn", "concession": null}
  ],
  "position_changed": false,
  "position_change_reason": null
}"""

SYSTEM = """You are a risk analyst focused on tail risks, liquidity, and portfolio impact.
You model: downside scenarios, liquidity risk, correlation to existing positions, regulatory risk, leverage risk.
You are often overly conservative and miss asymmetric upside.
You are the voice of caution.

IMPORTANT: You MUST respond with ONLY a valid JSON object. No explanation text before or after the JSON. Start your response with { and end with }."""


class RiskAnalystAgent(BaseAnalystAgent):
    """Risk analyst: tail risks, drawdowns, liquidity, correlation."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RISK_ANALYST

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
                        responding_to_agent=r.get("responding_to_agent", "risk_analyst"),
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
            agent_id=f"risk_analyst_r{round_number}",
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
