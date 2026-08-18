# Agents — Investment Committee Debate System

## Overview

The system contains **7 agents**: 5 core analyst agents that participate in every debate round, 1 tiebreaker agent spawned on hard conflicts, and 1 synthesis agent that produces the final CommitteeMemo.

All agents inherit from `BaseAnalystAgent` and communicate exclusively via structured `AnalystOutput` Pydantic models. No free-form text passes between agents.

---

## BaseAnalystAgent

**Location**: `investment_agents/agents/base.py`

The abstract base class provides the complete execution pipeline for every analyst agent. Subclasses only need to define the agent's identity, prompt, and output parsing logic.

### What BaseAnalystAgent Provides

| Method / Property | Type | Description |
|-------------------|------|-------------|
| `agent_type` | abstract property → `AgentType` | Enum identity of the agent |
| `system_prompt` | abstract property → `str` | LLM system prompt defining the agent's persona |
| `json_schema_description` | abstract property → `str` | JSON schema string given to the LLM as output format |
| `_parse_output(data, round_number, tokens_used, tokens_allocated)` | abstract method → `AnalystOutput` | Converts raw JSON dict into `AnalystOutput` |
| `analyze(thesis, investment_context, round_number, debate_id, prior_outputs, token_allocation)` | async → `AnalystOutput` | Complete execution pipeline with retry logic |
| `_fallback_output(round_number, token_allocation)` | → `AnalystOutput` | Returns a safe HOLD response when all LLM retries fail |
| `_format_prior_context(prior_outputs)` | → `str` | Formats prior round outputs as context for round 2+ |
| `_parse_evidence(raw)` | → `List[Evidence]` | Safely parses supporting evidence from LLM JSON |
| `_safe_float(val, default, lo, hi)` | → `float` | Clamps floats to range with fallback |
| `_safe_str(val, default, max_len)` | → `str` | Truncates strings safely |
| `_rec_from_str(val)` | → `Recommendation` | Maps string to Recommendation enum |

### Execution Pipeline (analyze method)

```
analyze(thesis, context, round_number, debate_id, prior_outputs, token_allocation)
  │
  ├── _format_prior_context(prior_outputs)    → context string
  ├── _build_context_message(thesis, context, prior_context)
  ├── _build_user_message(thesis, round_number, prior_outputs)
  │
  └── for attempt in range(MAX_JSON_RETRIES + 1):  # up to 3 tries
        LLMClient.complete(messages, max_tokens=allocation)
        LLMClient.extract_json(raw_text)
        agent._parse_output(data) → AnalystOutput
        [on failure: append correction message and retry]
      [exhausted retries] → _fallback_output()
```

### How to Subclass

```python
from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AnalystOutput

class MyCustomAgent(BaseAnalystAgent):

    @property
    def agent_type(self) -> AgentType:
        return AgentType.MY_CUSTOM  # add to enum first

    @property
    def system_prompt(self) -> str:
        return """You are a [persona description].
        Always respond with valid JSON only."""

    @property
    def json_schema_description(self) -> str:
        return """{
          "recommendation": "strong_buy|buy|hold|sell|strong_sell",
          "conviction_score": 0.0-1.0,
          "numeric_score": -1.0 to 1.0,
          "thesis_agreement": "max 300 chars",
          "key_argument": "max 500 chars",
          "supporting_evidence": [...],
          "agent_specific_analysis": { "custom_field": "..." },
          "response_to_agents": [...],
          "position_changed": false,
          "position_change_reason": null
        }"""

    def _parse_output(
        self,
        data: dict,
        round_number: int,
        tokens_used: int,
        tokens_allocated: int,
    ) -> AnalystOutput:
        return AnalystOutput(
            agent_id=f"my_custom_r{round_number}",
            agent_type=self.agent_type,
            round_number=round_number,
            recommendation=self._rec_from_str(data.get("recommendation", "hold")),
            conviction_score=self._safe_float(data.get("conviction_score", 0.5), lo=0.0, hi=1.0),
            numeric_score=self._safe_float(data.get("numeric_score", 0.0)),
            thesis_agreement=self._safe_str(data.get("thesis_agreement", ""), max_len=400),
            key_argument=self._safe_str(data.get("key_argument", ""), max_len=600),
            supporting_evidence=self._parse_evidence(data.get("supporting_evidence", [])),
            agent_specific_analysis=data.get("agent_specific_analysis", {}),
            tokens_used=tokens_used,
            tokens_allocated=tokens_allocated,
        )
```

---

## Core Analyst Agents

### 1. ValueInvestorAgent

| Property | Value |
|----------|-------|
| **File** | `agents/value_investor.py` |
| **AgentType** | `AgentType.VALUE_INVESTOR` |
| **AgentType value** | `"value_investor"` |

**Persona**: A disciplined value investor following Benjamin Graham and Warren Buffett principles. Ignores short-term price momentum entirely. Admits being "too early" as a known blind spot. Focused on intrinsic value vs current market price.

**System Prompt Philosophy**: Analyze investments through DCF valuation, competitive moat analysis, earnings power, management quality, and margin of safety. Patient, contrarian, and long-term focused.

**Key `agent_specific_analysis` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `fair_value_estimate` | string | DCF/earnings-power fair value estimate |
| `margin_of_safety_pct` | float or null | Discount to intrinsic value as % |
| `moat_strength` | `"none" \| "narrow" \| "wide"` | Competitive moat assessment |
| `earnings_yield_pct` | float or null | E/P ratio as a percentage |
| `pe_assessment` | `"overvalued" \| "fairly_valued" \| "undervalued"` | P/E multiple judgment |

---

### 2. MomentumTraderAgent

| Property | Value |
|----------|-------|
| **File** | `agents/momentum_trader.py` |
| **AgentType** | `AgentType.MOMENTUM_TRADER` |
| **AgentType value** | `"momentum_trader"` |

**Persona**: A systematic momentum trader who follows price trends, volume patterns, and relative strength. Does not value-anchor. Trend is truth; the tape doesn't lie.

**System Prompt Philosophy**: Analyze investments through trend direction, momentum strength, technical breakout/breakdown signals, relative performance vs benchmark, and institutional flow signals. Short-to-medium term focused. Known blind spot: ignores fundamentals entirely.

**Key `agent_specific_analysis` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `trend_direction` | `"up" \| "down" \| "sideways"` | Current primary trend |
| `momentum_strength` | `"strong" \| "moderate" \| "weak"` | Momentum signal quality |
| `rsi_assessment` | `"overbought" \| "neutral" \| "oversold"` | Momentum oscillator reading |
| `relative_strength` | `"outperforming" \| "inline" \| "underperforming"` | vs. sector/market |
| `breakout_signal` | boolean | Whether a technical breakout is occurring |
| `key_technical_levels` | object | Support and resistance levels |

---

### 3. RiskAnalystAgent

| Property | Value |
|----------|-------|
| **File** | `agents/risk_analyst.py` |
| **AgentType** | `AgentType.RISK_ANALYST` |
| **AgentType value** | `"risk_analyst"` |

**Persona**: A CRO-style risk analyst who stress-tests assumptions, models downside scenarios, and focuses exclusively on what can go wrong. Skeptical of bull cases by default.

**System Prompt Philosophy**: Identify tail risks, concentration risks, liquidity risks, regulatory risks, and correlation risks. Build explicit bear-case scenarios with probability estimates. Challenge every assumption. Known blind spot: can be too conservative and underweight upside optionality.

**Key `agent_specific_analysis` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `primary_risk_category` | string | Dominant risk type (regulatory, financial, operational, macro, etc.) |
| `tail_risk_probability` | float | Estimated probability of severe loss scenario |
| `downside_scenario` | string | Specific bear-case scenario description |
| `max_drawdown_estimate_pct` | float or null | Estimated maximum drawdown in bear case |
| `risk_reward_ratio` | string | e.g., "1:3 (risk $1 to make $3)" |
| `key_risk_triggers` | string[] | Events that would trigger downside scenario |

---

### 4. MacroEconomistAgent

| Property | Value |
|----------|-------|
| **File** | `agents/macro_economist.py` |
| **AgentType** | `AgentType.MACRO_ECONOMIST` |
| **AgentType value** | `"macro_economist"` |

**Persona**: A macro strategist who evaluates investments through the lens of global macroeconomic cycles, interest rates, currency dynamics, geopolitical risk, and central bank policy.

**System Prompt Philosophy**: Analyze the macro environment's impact on the specific investment. Consider rate regime, yield curve, USD strength, commodity cycles, credit spreads, and global growth trajectories. Top-down thinker. Known blind spot: may overlook company-specific factors.

**Key `agent_specific_analysis` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `macro_regime` | `"risk_on" \| "risk_off" \| "transitioning"` | Current macro environment |
| `rate_sensitivity` | `"high" \| "moderate" \| "low"` | How sensitive the thesis is to rate moves |
| `usd_impact` | `"positive" \| "neutral" \| "negative"` | Dollar strength impact on thesis |
| `geopolitical_risk_level` | `"low" \| "moderate" \| "high"` | Geopolitical risk assessment |
| `sector_macro_tailwinds` | string[] | Macro factors supporting the thesis |
| `sector_macro_headwinds` | string[] | Macro factors working against the thesis |

---

### 5. ContrarianAgent

| Property | Value |
|----------|-------|
| **File** | `agents/contrarian.py` |
| **AgentType** | `AgentType.CONTRARIAN` |
| **AgentType value** | `"contrarian"` |

**Persona**: A contrarian analyst whose job is to steelman the opposing view. If the committee consensus is bullish, find the strongest bear case. If bearish, find the strongest bull case. Uses second-order thinking to identify what the market is getting wrong.

**System Prompt Philosophy**: Challenge consensus assumptions. Use second-order thinking. Identify mispricing hypotheses. Known blind spot: can be contrarian for its own sake without sufficient evidence.

**Key `agent_specific_analysis` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `dominant_consensus` | `"bull" \| "bear" \| "mixed"` | What the market/committee consensus is |
| `consensus_assumption_challenged` | string | The specific assumption being challenged |
| `steelman_bull` | string | Strongest possible bull case (even if agent is bearish) |
| `steelman_bear` | string | Strongest possible bear case (even if agent is bullish) |
| `market_mispricing_hypothesis` | string | What the market is getting wrong |
| `second_order_effects` | string | Downstream effects other analysts are ignoring |

---

## Special Agents

### TiebreakerAgent

| Property | Value |
|----------|-------|
| **File** | `agents/tiebreaker.py` |
| **AgentType** | `AgentType.TIEBREAKER` |
| **AgentType value** | `"tiebreaker"` |

**When spawned**: Only when `divergence_report.has_hard_conflicts == True` AND remaining budget ≥ `settings.tiebreaker_min_budget` (3000 tokens).

**Persona**: An impartial senior committee chair who has reviewed the conflicting arguments and must provide a decisive ruling. Acknowledges valid points on both sides, identifies the strongest argument, and drives toward a clear recommendation.

**Role in the system**: The tiebreaker output is added to `state["tiebreaker_outputs"]` and passed to the synthesis agent as additional evidence. The tiebreaker does not override other agents — it provides an additional data point.

**Key `agent_specific_analysis` fields**:

| Field | Type | Description |
|-------|------|-------------|
| `conflicts_reviewed` | string[] | List of conflict IDs reviewed |
| `strongest_argument` | `"bull" \| "bear"` | Which side had the strongest case |
| `key_deciding_factor` | string | The single factor that broke the tie |
| `resolution_confidence` | float | How confident the tiebreaker is (0–1) |

---

### SynthesisAgent

| Property | Value |
|----------|-------|
| **File** | `agents/synthesis.py` |
| **AgentType** | `AgentType.SYNTHESIS` |
| **AgentType value** | `"synthesis"` |

**When invoked**: Once, at the end of the debate, after all rounds and optional tiebreaker are complete.

**Input**: All `AnalystOutput` objects from all rounds + all `ConflictPoint` objects + all `tiebreaker_outputs`.

**Output**: `CommitteeMemo` — the structured final deliverable.

**CommitteeMemo fields**:

| Field | Type | Description |
|-------|------|-------------|
| `final_recommendation` | `Recommendation` | Committee's final vote |
| `conviction` | float | Weighted average conviction (0–1) |
| `vote_breakdown` | `Dict[str, int]` | Count per recommendation type |
| `executive_summary` | string | 2–3 sentence summary of the debate outcome |
| `key_thesis` | string | The core investment thesis as refined by debate |
| `bull_case` | string | Best arguments for the investment |
| `bear_case` | string | Best arguments against the investment |
| `key_risks` | string[] | Top 3–5 risks identified by the committee |
| `catalysts_to_watch` | string[] | Events that would trigger re-evaluation |
| `debate_was_contentious` | bool | Whether significant disagreement existed |
| `dissenting_views` | `List[DissentingView]` | Agents who disagreed with the final recommendation |
| `synthesized_at` | datetime | When the memo was produced |

---

## Step-by-Step: Adding a New Agent

### Step 1: Add the AgentType

In `investment_agents/models/agent_output.py`:

```python
class AgentType(str, Enum):
    VALUE_INVESTOR = "value_investor"
    MOMENTUM_TRADER = "momentum_trader"
    RISK_ANALYST = "risk_analyst"
    MACRO_ECONOMIST = "macro_economist"
    CONTRARIAN = "contrarian"
    TIEBREAKER = "tiebreaker"
    SYNTHESIS = "synthesis"
    TECHNICAL_ANALYST = "technical_analyst"   # ← add your new type
```

### Step 2: Create the Agent File

```python
# investment_agents/agents/technical_analyst.py
from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AnalystOutput, AgentResponse
from typing import Any, Dict, List

SCHEMA = """{
  "recommendation": "strong_buy|buy|hold|sell|strong_sell",
  "conviction_score": 0.0-1.0,
  "numeric_score": -1.0 to 1.0,
  "thesis_agreement": "max 300 chars",
  "key_argument": "max 500 chars",
  "supporting_evidence": [{"claim": "...", "source_type": "technical", "confidence": 0.0-1.0, "supports_thesis": true/false}],
  "agent_specific_analysis": {
    "chart_pattern": "e.g. double_bottom, head_and_shoulders, ascending_triangle",
    "support_level": number,
    "resistance_level": number,
    "volume_trend": "increasing|decreasing|stable",
    "ma_crossover_signal": "bullish|bearish|none"
  },
  "response_to_agents": [],
  "position_changed": false,
  "position_change_reason": null
}"""

SYSTEM = """You are a technical analyst who reads price charts, volume patterns,
and indicator signals. You care only about what the chart is saying.
Always respond with valid JSON only."""


class TechnicalAnalystAgent(BaseAnalystAgent):

    @property
    def agent_type(self) -> AgentType:
        return AgentType.TECHNICAL_ANALYST

    @property
    def system_prompt(self) -> str:
        return SYSTEM

    @property
    def json_schema_description(self) -> str:
        return SCHEMA

    def _parse_output(
        self, data: Dict[str, Any], round_number: int, tokens_used: int, tokens_allocated: int
    ) -> AnalystOutput:
        responses: List[AgentResponse] = []
        for r in data.get("response_to_agents") or []:
            try:
                responses.append(AgentResponse(
                    responding_to_agent=r.get("responding_to_agent", "technical_analyst"),
                    agreement_level=self._safe_float(r.get("agreement_level", 0), lo=-1.0, hi=1.0),
                    rebuttal=self._safe_str(r.get("rebuttal", ""), max_len=400),
                    concession=r.get("concession"),
                ))
            except Exception:
                pass

        return AnalystOutput(
            agent_id=f"technical_analyst_r{round_number}",
            agent_type=self.agent_type,
            round_number=round_number,
            recommendation=self._rec_from_str(data.get("recommendation", "hold")),
            conviction_score=self._safe_float(data.get("conviction_score", 0.5), lo=0.0, hi=1.0),
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
```

### Step 3: Register in the Orchestrator

In `investment_agents/orchestrator/nodes.py`, inside `node_run_agents`:

```python
from investment_agents.agents.technical_analyst import TechnicalAnalystAgent

# In the agents list:
agents = [
    ValueInvestorAgent(llm_client, settings),
    MomentumTraderAgent(llm_client, settings),
    RiskAnalystAgent(llm_client, settings),
    MacroEconomistAgent(llm_client, settings),
    ContrarianAgent(llm_client, settings),
    TechnicalAnalystAgent(llm_client, settings),   # ← add here
]
```

### Step 4: Update the Agent Count Constant

In `investment_agents/budget/allocator.py`:

```python
ANALYST_AGENT_COUNT = 6   # was 5
```

### Step 5: Update the BudgetAllocator agent_types list

In `investment_agents/orchestrator/nodes.py`, where `BudgetAllocator` is instantiated:

```python
allocator = BudgetAllocator(
    agent_types=[
        "value_investor", "momentum_trader", "risk_analyst",
        "macro_economist", "contrarian", "technical_analyst"  # ← add
    ],
    settings=settings,
)
```

### Step 6: Write Tests

Create `tests/unit/test_technical_analyst.py` following the pattern in `tests/test_models.py`.

---

## AnalystOutput — Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Unique ID: `"{agent_type}_r{round_number}"` |
| `agent_type` | `AgentType` | Enum identity |
| `round_number` | int ≥ 1 | Which debate round produced this output |
| `recommendation` | `Recommendation` | `strong_buy \| buy \| hold \| sell \| strong_sell \| insufficient_data` |
| `conviction_score` | float [0,1] | How confident the agent is in their recommendation |
| `numeric_score` | float [-1,1] | Numeric position (`-1` = strong sell, `+1` = strong buy) |
| `thesis_agreement` | string ≤ 400 chars | Concise agreement/disagreement statement |
| `key_argument` | string ≤ 600 chars | The single most important argument |
| `supporting_evidence` | `Evidence[]` | 1–5 evidence items |
| `agent_specific_analysis` | dict | Agent-type-specific metrics |
| `response_to_agents` | `AgentResponse[] \| null` | Cross-agent rebuttals (round 2+) |
| `position_changed` | bool | Whether position changed from last round |
| `position_change_reason` | string or null | Why position changed |
| `tokens_used` | int | Actual tokens consumed by LLM call |
| `tokens_allocated` | int | Budget allocated to this agent for this round |
| `model_used` | string | LiteLLM model string used |
| `created_at` | datetime | UTC timestamp |

---

## CommitteeMemo — Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `final_recommendation` | `Recommendation` | Committee's final vote verdict |
| `conviction` | float [0,1] | Weighted average conviction across agents |
| `vote_breakdown` | dict | `{buy: N, hold: N, sell: N}` |
| `executive_summary` | string | 2–4 sentence summary |
| `key_thesis` | string | Core investment thesis restated by chair |
| `bull_case` | string | Strongest arguments for the thesis |
| `bear_case` | string | Strongest arguments against |
| `key_risks` | string[] | Top risks identified across all agents |
| `catalysts_to_watch` | string[] | Upcoming events that could shift the verdict |
| `debate_was_contentious` | bool | True if `disagreement_score > 0.45` |
| `committee_divided` | bool | True if no clear majority |
| `dissenting_views` | `DissentingView[]` | Minority positions with explanations |
| `reasoning_trace` | `ReasoningStep[]` | Step-by-step synthesis log |
| `synthesis_quality` | `"full" \| "degraded" \| "empty"` | Quality of the synthesis output (added in refactor set-1) |
| `total_rounds` | int | Number of completed debate rounds |
| `total_tokens_used` | int | Total token spend across all agents |
| `model_used` | string | LiteLLM model string |
| `created_at` | datetime | UTC timestamp |

