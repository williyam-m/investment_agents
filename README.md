# 🏛️ Investment Committee Multi-Agent Debate System

> **Five specialist AI analysts debate every investment thesis — powered by LangGraph, LiteLLM, and an adaptive explore/exploit token budget.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Agent Roster](#agent-roster)
- [Explore / Exploit Routing](#explore--exploit-routing)
- [Token Budget System](#token-budget-system)
- [Example Output](#example-output)
- [Development](#development)
- [Environment Variables](#environment-variables)
- [License](#license)

---

## Overview

The **Investment Committee Multi-Agent Debate System** simulates a real investment committee by orchestrating **five specialist AI analysts** who read the same thesis, form independent views, argue against each other across multiple rounds, and ultimately converge on a structured **CommitteeMemo** — a production-quality investment recommendation with full reasoning trace.

### What makes this different from a single LLM prompt?

| Single LLM                | Multi-Agent Debate                                    |
| ------------------------- | ----------------------------------------------------- |
| One perspective, one pass | Five distinct perspectives, N rounds                  |
| No adversarial pressure   | Agents rebut each other's arguments                   |
| Sycophantic by default    | Contrarian agent steelmans opposing view              |
| No convergence tracking   | DivergenceScorer measures disagreement quantitatively |
| Fixed compute             | Adaptive token budget (explore/exploit)               |
| Black-box reasoning       | Full reasoning trace + dissenting views               |

### Core capabilities

- **5 parallel specialist agents** run concurrently every round (Value Investor, Momentum Trader, Risk Analyst, Macro Economist, Contrarian)
- **LangGraph StateGraph** orchestrates the debate as a stateful directed graph with conditional branching
- **DivergenceScorer** measures agent disagreement via recommendation variance, semantic embedding distance, and conflict detection
- **Explore/Exploit routing** dynamically adjusts how many rounds to run and how to allocate tokens based on live divergence scores
- **Tiebreaker agent** is invoked when agents reach hard conflicts and budget permits
- **SynthesisAgent** (committee chair) reads the full debate and produces a `CommitteeMemo`
- **FastAPI + SSE** streams live events to the frontend as the debate progresses
- **Token budget is a first-class primitive** — every LLM call is tracked, and synthesis tokens are always reserved

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                     │
│   React Frontend  ←──SSE──   FastAPI (:8000)   ←──REST──  CLI / API    │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │  POST /api/v1/debates
                                    │  DebateRequest
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH ORCHESTRATOR                               │
│                                                                         │
│   ┌─────────┐   ┌──────────────────┐   ┌───────────────────────────┐   │
│   │  init   │──►│ allocate_budget  │──►│       run_agents          │   │
│   └─────────┘   └──────────────────┘   │  (5 agents in parallel)   │   │
│                                         │                           │   │
│                   ┌─────────────────────┤  ● ValueInvestorAgent     │   │
│                   │                     │  ● MomentumTraderAgent    │   │
│                   │                     │  ● RiskAnalystAgent       │   │
│                   │                     │  ● MacroEconomistAgent    │   │
│                   │                     │  ● ContrarianAgent        │   │
│                   │                     └───────────────────────────┘   │
│                   │                                   │                 │
│                   │                                   ▼                 │
│                   │                     ┌─────────────────────────┐    │
│                   │                     │   score_divergence       │    │
│                   │                     │  ● Rec variance (40%)   │    │
│                   │                     │  ● Semantic dist (35%)  │    │
│                   │                     │  ● Conflict penalty(25%)│    │
│                   │                     └────────────┬────────────┘    │
│                   │                                  │                  │
│                   │              ┌───────────────────┼──────────────┐   │
│                   │              │                   │              │   │
│                   │              ▼                   ▼              ▼   │
│                   │      ┌─────────────┐   ┌──────────────┐  ┌──────┐  │
│                   │      │  tiebreaker │   │  next_round  │  │synth │  │
│                   │      │  (hard conf)│   │  (explore /  │  │esize │  │
│                   │      └──────┬──────┘   │   exploit)   │  └──┬───┘  │
│                   │             │          └──────┬───────┘     │      │
│                   └─────────────┴─────────────────┘             │      │
│                        (loop: prepare_next_round)               │      │
│                                                                  │      │
│   ┌──────────────────────────────────────────────────────────┐  │      │
│   │              SynthesisAgent (committee chair)            │◄─┘      │
│   │  Reads full debate → produces CommitteeMemo              │         │
│   └──────────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                           CommitteeMemo JSON
                  (recommendation, conviction, bull/bear case,
                   key risks, catalysts, dissenting views,
                   reasoning trace, budget summary)
```

### Graph node flow

| Node                       | Responsibility                                                                |
| -------------------------- | ----------------------------------------------------------------------------- |
| `init`                   | Validate request, generate`debate_id`, set initial state                    |
| `allocate_budget`        | Run`ExploreExploitPolicy` to distribute tokens across agents for this round |
| `run_agents`             | Fan-out: invoke all 5 analyst agents concurrently via`asyncio.gather`       |
| `score_divergence`       | Compute`DivergenceReport` from agent outputs (embeddings + statistics)      |
| `route_after_divergence` | Conditional edge: →`tiebreaker` / `prepare_next_round` / `synthesize`  |
| `run_tiebreaker`         | Invoke`TiebreakerAgent` when hard conflicts detected                        |
| `prepare_next_round`     | Increment round counter, carry outputs forward                                |
| `synthesize`             | `SynthesisAgent` reads full debate history → emit `CommitteeMemo`        |

---

## Tech Stack

| Layer                   | Technology                                                                                             | Purpose                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| **Orchestration** | [LangGraph](https://github.com/langchain-ai/langgraph) 0.2+                                             | Stateful agent graph with conditional edges and streaming        |
| **LLM**           | [LiteLLM](https://github.com/BerriAI/litellm) 1.40+                                                     | Unified API — Ollama (local), OpenAI, Anthropic, Google         |
| **API**           | [FastAPI](https://fastapi.tiangolo.com) 0.111+ + [sse-starlette](https://github.com/sysid/sse-starlette) | REST endpoints + Server-Sent Events streaming                    |
| **Models**        | [Pydantic v2](https://docs.pydantic.dev/latest/) 2.5+                                                   | Typed data contracts for all state, requests, and outputs        |
| **Settings**      | [Pydantic-Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 2.0+                  | `.env`-driven configuration with type validation               |
| **Budget**        | `TokenBudgetTracker` (custom)                                                                        | First-class token accounting — tracks spend per agent per round |
| **Divergence**    | [Sentence-Transformers](https://www.sbert.net) + [NumPy](https://numpy.org)                              | Semantic embedding distance + statistical variance scoring       |
| **Conflict**      | Custom`DivergenceScorer`                                                                             | Hard/soft conflict detection across all agent pairs              |
| **CLI**           | [Typer](https://typer.tiangolo.com) 0.12+ + [Rich](https://github.com/Textualize/rich)                   | Command-line interface with progress bars and colour output      |
| **Storage**       | SQLite via[SQLAlchemy](https://www.sqlalchemy.org) 2.0 + aiosqlite                                      | Async debate persistence and retrieval                           |
| **Logging**       | [structlog](https://www.structlog.org) 24+                                                              | Structured JSON logging throughout                               |
| **Server**        | [Uvicorn](https://www.uvicorn.org) 0.30+                                                                | ASGI server with optional auto-reload                            |

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **[Ollama](https://ollama.com)** running locally (for the default local model) — *or* an OpenAI / Anthropic API key

### 1. Install Ollama and pull a model

```bash
# macOS
brew install ollama
ollama serve          # runs on http://localhost:11434

# Pull the default model
ollama pull llama2

# Optional: use a stronger model
ollama pull llama3
ollama pull mistral
```

### 2. Clone and install

```bash
git clone https://github.com/your-org/investment_agents.git
cd investment_agents

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env as needed (see Environment Variables section)
```

### 4. Run a debate via CLI

```bash
# Basic debate — uses Ollama llama2 by default
investment-agents debate "Apple is undervalued at current P/E of 28x given its services growth trajectory" \
  --ticker AAPL \
  --rounds 3

# With a cloud model
investment-agents debate "NVIDIA's AI revenue growth justifies a 40x forward P/E" \
  --ticker NVDA \
  --model gpt-4o \
  --budget 60000 \
  --rounds 3

# Save the full JSON trace
investment-agents debate "Tesla's FSD revenue will drive re-rating to software multiples" \
  --ticker TSLA \
  --output traces/tesla_debate.json

# Specify temperature
investment-agents debate "Amazon AWS margin expansion justifies 3.5x revenue multiple" \
  --model anthropic/claude-3-5-sonnet-20241022 \
  --temperature 0.8
```

### 5. Start the API server

```bash
# Via CLI
investment-agents serve

# Via Python entry point (with auto-reload)
python main.py

# Custom host/port
python main.py --host 127.0.0.1 --port 8080 --no-reload --log-level debug
```

The API will be available at `http://localhost:8000`.
Interactive docs (Swagger UI): `http://localhost:8000/docs`

### 6. List past debates

```bash
investment-agents list-debates --limit 20 --verbose
```

---

## API Reference

All endpoints are prefixed with `/api/v1`.

---

### `POST /api/v1/debates`

Start a new debate session. Runs synchronously and returns the complete `DebateTrace` when finished.

**Request body** (`application/json`):

```json
{
  "thesis": "Apple is undervalued at current P/E of 28x given its services growth trajectory",
  "investment_context": {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology",
    "current_price": 189.50,
    "market_cap_bn": 2950.0,
    "supporting_data": {
      "pe_ratio": 28.4,
      "revenue_growth_yoy_pct": 6.1,
      "services_revenue_bn": 24.2,
      "free_cash_flow_bn": 99.6
    },
    "relevant_documents": [
      "Q4 2024 earnings: services revenue +14% YoY, 1B paid subscriptions"
    ]
  },
  "total_budget": 40000,
  "max_rounds": 3,
  "model_config": {
    "model": "ollama/llama2",
    "temperature": 0.7,
    "max_tokens_per_call": 1000,
    "ollama_base_url": "http://localhost:11434"
  }
}
```

**Response**: Full `DebateTrace` JSON (see [Example Output](#example-output)).

---

### `GET /api/v1/debates/{debate_id}`

Retrieve a stored `DebateTrace` by its ID.

- Returns `200` with full trace if complete.
- Returns `202` with status info if still running or failed.
- Returns `404` if the ID does not exist.

```bash
curl http://localhost:8000/api/v1/debates/550e8400-e29b-41d4-a716-446655440000
```

---

### `GET /api/v1/debates/{debate_id}/stream`

**Server-Sent Events** endpoint — stream debate progress in real time.

- If debate is **already complete**: replays all stored events immediately (useful for reconnecting clients).
- If debate is **in progress**: forwards live events from the orchestrator.
- If debate **not found**: emits an error event and closes the stream.

```javascript
// Browser example
const evtSource = new EventSource(
  `http://localhost:8000/api/v1/debates/${debateId}/stream`
);
evtSource.addEventListener("agent_complete", (e) => {
  const data = JSON.parse(e.data);
  console.log(`${data.agent_type} → ${data.recommendation}`);
});
evtSource.addEventListener("debate_complete", (e) => {
  console.log("Debate finished!", JSON.parse(e.data));
  evtSource.close();
});
```

**Event types emitted**:

| Event type             | Payload                                                                |
| ---------------------- | ---------------------------------------------------------------------- |
| `debate_started`     | `debate_id`, `thesis`, `max_rounds`, `budget`                  |
| `round_started`      | `round_number`, `mode` (explore/exploit)                           |
| `agent_complete`     | `agent_type`, `recommendation`, `numeric_score`, `tokens_used` |
| `divergence_scored`  | `overall_score`, `has_hard_conflicts`, `agent_scores`            |
| `tiebreaker_invoked` | `reason`, `conflicts`                                              |
| `routing_decision`   | `decision`, `reason`, `divergence_score`                         |
| `synthesis_started`  | `total_rounds_completed`                                             |
| `debate_complete`    | `debate_id`, `status`, `has_memo`                                |
| `error`              | `code`, `message`                                                  |

---

### `GET /api/v1/debates`

List recent debates (completed + pending), newest first.

```bash
curl "http://localhost:8000/api/v1/debates?limit=10"
```

**Query parameters**:

- `limit` (int, default `20`) — maximum number of results

---

### `GET /api/v1/health`

Health check endpoint.

```bash
curl http://localhost:8000/api/v1/health
# {"status": "ok", "version": "1.0.0"}
```

---

## Agent Roster

Each agent receives the **same thesis and investment context** but approaches the analysis from its own philosophical lens. In rounds 2+, agents also receive prior round arguments from all other agents and are expected to respond, rebut, or concede.

| Agent                    | Class                   | Perspective                        | Analytical Focus                                                  | Known Blind Spot                                                 |
| ------------------------ | ----------------------- | ---------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------- |
| **ValueInvestor**  | `ValueInvestorAgent`  | Benjamin Graham / Buffett disciple | DCF valuation, competitive moat, margin of safety, earnings yield | Ignores price momentum; often buys early or too early            |
| **MomentumTrader** | `MomentumTraderAgent` | Trend-following quant              | Price trends, RSI, earnings catalysts, institutional flow         | Ignores intrinsic valuation; tends to overpay at peaks           |
| **RiskAnalyst**    | `RiskAnalystAgent`    | Portfolio risk manager             | Tail risks, liquidity conditions, max drawdown, correlation       | Excessively conservative; consistently underweights upside       |
| **MacroEconomist** | `MacroEconomistAgent` | Top-down macro strategist          | Interest rates, credit cycle, geopolitics, sector rotation        | Misses company-specific alpha; macro views can be slow to update |
| **Contrarian**     | `ContrarianAgent`     | Devil's advocate                   | Steelmans the opposing consensus view, second-order effects       | Sometimes contrarian for its own sake rather than evidence       |

### Tiebreaker

| Agent                     | Invocation                                                                                                                                                                                                                                            |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **TiebreakerAgent** | Automatically invoked when`has_hard_conflicts=True` and budget ≥ `TIEBREAKER_MIN_BUDGET` (default 3,000 tokens). Acts as an independent arbitrator — reviews conflicting positions and issues a casting recommendation with explicit reasoning. |

### SynthesisAgent

The **committee chair** — invoked once as the final node. It reads the complete debate history (all rounds, all agent outputs, all conflicts, any tiebreaker output) and produces the `CommitteeMemo`. The chair:

- Weighs arguments by evidence quality and conviction scores
- Computes a vote breakdown across all analyst recommendations
- Acknowledges and records dissenting views
- Produces a full reasoning trace (step-by-step synthesis log)
- Flags when the committee was divided or the debate was contentious

---

## Explore / Exploit Routing

After each debate round, the **`route_after_divergence`** conditional edge examines the `DivergenceReport` and applies a three-way routing policy.

### Routing decision logic

```
After scoring divergence for round N:

  1. IF remaining_tokens < MIN_SYNTHESIS_TOKENS (default: 2,000)
       → SYNTHESIZE immediately (budget protection)

  2. IF round_number >= max_rounds
       → SYNTHESIZE (respect the round cap)

  3. IF has_hard_conflicts AND remaining_tokens >= TIEBREAKER_MIN_BUDGET (default: 3,000)
       → TIEBREAKER (arbitrate the hard conflict)

  4. OTHERWISE
       → NEXT_ROUND (prepare and re-run agents)
```

### Debate modes

| Mode              | Divergence score | Token allocation strategy                                                                                                    |
| ----------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Explore** | score > 0.55     | Tokens distributed**equally** across all 5 agents. Keep all perspectives active — the committee is divided.           |
| **Exploit** | score < 0.30     | Tokens concentrated on the**2–3 most distinctive agents** (highest `\|score − mean\|`). Deep-dive the outlier views. |
| **Neutral** | 0.30 – 0.55     | Balanced allocation with mild weighting toward agents with stronger conviction.                                              |

The `ExploreExploitPolicy` re-runs every round, so a debate can flip between modes: start in **explore** (high disagreement), drift toward **exploit** as consensus forms, and trigger **tiebreaker** if one pair remains in hard conflict.

### DivergenceScorer weights

```
overall_score = 0.40 × recommendation_variance
              + 0.35 × semantic_divergence
              + 0.25 × conflict_penalty
```

- **Recommendation variance**: std dev of agents' `numeric_score` (−1.0 to +1.0), normalized to [0, 1]
- **Semantic divergence**: mean pairwise cosine distance between `key_argument` embeddings (via `all-MiniLM-L6-v2`)
- **Conflict penalty**: fraction of agent pairs in hard conflict (`|score_a − score_b| > 1.0`)

---

## Token Budget System

Token spend is treated as a **first-class constraint**, not an afterthought.

### Budget lifecycle

```
DebateRequest.total_budget (default: 40,000 tokens)
    │
    ├── RESERVED: synthesis_tokens (default: 2,000) — always held back
    │
    └── AVAILABLE for rounds:
            └── Round 1 budget = available × round_fraction
                    ├── agent_1_allocation
                    ├── agent_2_allocation
                    ├── ...
                    └── MIN_AGENT_TOKENS = 400 (guaranteed floor)
```

### Key components

| Component                | Role                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------- |
| `TokenBudget`          | Tracks`total`, `used`, `reserved_for_synthesis`, `available`, `remaining` |
| `BudgetAllocator`      | Splits round budget across agents based on mode and divergence scores               |
| `ExploreExploitPolicy` | Determines allocation ratios based on`DebateMode`                                 |
| `TokenBudgetTracker`   | Records every LLM call's actual token spend                                         |
| `BudgetReport`         | Live state object — per-agent and per-round breakdowns                             |
| `BudgetSummary`        | Final summary in`DebateTrace` — efficiency %, spend by agent/round               |

### Safety guarantees

- **Hard floor**: every agent receives at least `MIN_AGENT_TOKENS = 400` tokens, preventing starvation
- **Synthesis reservation**: the orchestrator routes to synthesis before touching the reserved pool
- **Over-budget detection**: each `BudgetAllocation` tracks `efficiency = used / allocated`
- **Retry accounting**: LLM retries on JSON parse failure consume from the same allocation

---

## Example Output

A realistic `CommitteeMemo` produced after a 3-round AAPL debate:

```json
{
  "debate_id": "550e8400-e29b-41d4-a716-446655440000",
  "thesis": "Apple is undervalued at current P/E of 28x given its services growth trajectory",
  "status": "complete",
  "total_rounds_completed": 3,
  "committee_memo": {
    "final_recommendation": "buy",
    "conviction": 0.72,
    "vote_breakdown": {
      "buy": 3,
      "hold": 1,
      "sell": 1
    },
    "executive_summary": "The committee reaches a BUY recommendation with moderate conviction (72%). Three of five analysts favour accumulation at current levels, citing the services flywheel and durable free cash flow. The Risk Analyst dissents, flagging elevated macro sensitivity and multiple compression risk if rate cuts disappoint.",
    "key_thesis": "Apple's transition from hardware-centric to services-led model justifies a premium multiple. With $99.6B in annual free cash flow and 1B+ paid subscribers, intrinsic value exceeds current market price at a 28x P/E.",
    "bull_case": "Services revenue growing at 14% YoY with near-80% gross margins provides durable earnings power. The installed base of 2.2B active devices creates an extraordinarily sticky ecosystem. At 28x earnings, Apple trades at a discount to software peers despite software-quality cash generation.",
    "bear_case": "Hardware units remain cyclical and China exposure (18% of revenue) creates geopolitical tail risk. Services growth may decelerate as the installed base matures. The stock already embeds optimistic assumptions — any macro shock compresses the multiple before the fundamentals deteriorate.",
    "key_risks": [
      "China revenue concentration and regulatory risk (App Store antitrust rulings)",
      "Multiple compression if Federal Reserve delays rate cuts",
      "Hardware refresh cycle elongation reducing upgrade revenue",
      "Regulatory pressure on App Store economics in EU and US",
      "Generative AI integration lagging Samsung and Google Pixel"
    ],
    "catalysts_to_watch": [
      "Apple Intelligence feature adoption rate in iOS 19 cycle",
      "Services margin trajectory in Q1 and Q2 2025 earnings",
      "China iPhone market share vs Huawei in H1 2025",
      "Federal Reserve rate decision and impact on growth multiples"
    ],
    "debate_was_contentious": true,
    "committee_divided": false,
    "dissenting_views": [
      {
        "agent_type": "risk_analyst",
        "recommendation": "hold",
        "conviction": 0.68,
        "key_argument": "Tail risk from China revenue concentration is under-priced. A 10% China revenue shock would compress EPS by ~$0.35 and trigger a de-rating.",
        "why_not_adopted": "The majority view that services revenue diversification reduces China risk was more compelling. The risk is real but partially mitigated."
      },
      {
        "agent_type": "momentum_trader",
        "recommendation": "hold",
        "conviction": 0.55,
        "key_argument": "RSI at 61 and recent underperformance vs the QQQ suggests the near-term entry point may improve in Q1 2025 as macro uncertainty peaks.",
        "why_not_adopted": "Timing the entry was judged less important than the fundamental long-term value proposition. The committee prefers accumulating at intrinsic value."
      }
    ],
    "reasoning_trace": [
      {
        "step": "vote_aggregation",
        "description": "Count and weight recommendations across all rounds and agents",
        "input_summary": "15 agent outputs across 3 rounds: 8 buy/strong_buy, 4 hold, 3 sell",
        "output_summary": "Weighted vote: BUY with 72% conviction"
      },
      {
        "step": "conflict_resolution",
        "description": "Resolve hard conflict between ValueInvestor (strong_buy) and RiskAnalyst (sell) identified in Round 1",
        "input_summary": "Score gap of 1.4 triggered tiebreaker in Round 2",
        "output_summary": "Tiebreaker sided with bull case on services margin durability; RiskAnalyst moved to hold"
      },
      {
        "step": "bull_bear_synthesis",
        "description": "Extract strongest arguments from each side",
        "input_summary": "ValueInvestor DCF, MomentumTrader catalyst analysis, MacroEconomist rate view",
        "output_summary": "Services flywheel and FCF generation dominate bull case; China + macro headline risk dominate bear case"
      }
    ],
    "total_rounds": 3,
    "total_tokens_used": 34817,
    "model_used": "ollama/llama2",
    "synthesis_quality": "full",
    "created_at": "2025-01-15T14:23:41.882Z"
  },
  "budget_summary": {
    "total_allocated": 40000,
    "total_used": 34817,
    "efficiency_pct": 87.04,
    "by_agent": {
      "value_investor": 7200,
      "momentum_trader": 6100,
      "risk_analyst": 6800,
      "macro_economist": 5900,
      "contrarian": 5817,
      "synthesis": 3000
    },
    "by_round": {
      "1": 13200,
      "2": 11617,
      "3": 7000
    }
  }
}
```

---

## Development

### Running tests

```bash
# Full test suite with coverage
pytest

# Specific test file
pytest tests/unit/test_divergence.py -v

# Skip slow integration tests
pytest tests/unit/ -v

# Run with coverage report
pytest --cov=investment_agents --cov-report=html
open htmlcov/index.html
```

### Project structure

```
investment_agents/
├── agents/              # Specialist analyst implementations
│   ├── base.py          # BaseAnalystAgent (abstract) — inherit this for new agents
│   ├── value_investor.py
│   ├── momentum_trader.py
│   ├── risk_analyst.py
│   ├── macro_economist.py
│   ├── contrarian.py
│   ├── tiebreaker.py
│   └── synthesis.py     # Committee chair — produces CommitteeMemo
├── analysis/
│   ├── divergence.py    # DivergenceScorer — embedding + stats
│   ├── convergence.py   # ConvergenceDetector
│   └── conflict.py      # Conflict classification utilities
├── api/
│   ├── app.py           # FastAPI application factory
│   └── routes/
│       ├── debate.py    # POST/GET /debates endpoints
│       └── health.py    # GET /health
├── budget/
│   ├── tracker.py       # TokenBudgetTracker + BudgetExhaustedError
│   ├── allocator.py     # BudgetAllocator — per-agent token distribution
│   └── policy.py        # ExploreExploitPolicy + DebateMode enum
├── cli/
│   └── main.py          # Typer CLI (debate, serve, list-debates)
├── config/
│   └── settings.py      # Pydantic-Settings — all config from .env
├── llm/
│   └── client.py        # LiteLLM wrapper + JSON extraction
├── models/
│   ├── agent_output.py  # AnalystOutput, AgentType, Recommendation, Evidence
│   ├── budget.py        # TokenBudget, BudgetReport, BudgetSummary
│   ├── debate.py        # DebateRequest, DebateTrace, RoundTrace
│   ├── divergence.py    # DivergenceReport, ConflictPoint
│   ├── streaming.py     # StreamEvent, StreamEventType
│   └── synthesis.py     # CommitteeMemo, DissentingView, ReasoningStep
├── orchestrator/
│   ├── graph.py         # DebateOrchestrator + build_debate_graph()
│   ├── nodes.py         # Graph node functions (init, run_agents, synthesize, …)
│   ├── edges.py         # Conditional edge routing functions
│   └── state.py         # DebateState TypedDict
└── storage/
    └── repository.py    # DebateRepository — SQLite persistence
```

### Adding a new analyst agent

1. **Create** `investment_agents/agents/my_agent.py`:

```python
from investment_agents.agents.base import BaseAnalystAgent
from investment_agents.models.agent_output import AgentType, AnalystOutput

class MyAnalystAgent(BaseAnalystAgent):
    """My custom analyst perspective."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.MY_ANALYST   # add to AgentType enum first

    @property
    def system_prompt(self) -> str:
        return "You are a specialized analyst who focuses on X..."

    @property
    def json_schema_description(self) -> str:
        return '{ "recommendation": "...", "key_argument": "...", ... }'

    def _parse_output(self, data, round_number, tokens_used, tokens_allocated) -> AnalystOutput:
        return AnalystOutput(
            agent_id=f"my_analyst_r{round_number}",
            agent_type=self.agent_type,
            # ... parse the LLM response dict into AnalystOutput fields
        )
```

2. **Register** the new `AgentType` in `investment_agents/models/agent_output.py`
3. **Add** to `_AGENT_TYPES` list and import in `investment_agents/orchestrator/nodes.py`
4. **Add** to the `run_agents` node's `asyncio.gather` call

### Code quality

```bash
# Lint and format
ruff check investment_agents/ --fix
ruff format investment_agents/

# Type checking
mypy investment_agents/
```

---

## Environment Variables

All settings are loaded from `.env` via Pydantic-Settings. Copy `.env.example` to `.env` to start.

| Variable                  | Default                                         | Description                                                                   |
| ------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------- |
| `OLLAMA_BASE_URL`       | `http://localhost:11434`                      | Ollama server URL for local inference                                         |
| `DEFAULT_MODEL`         | `ollama/llama2`                               | LiteLLM model string for all agents                                           |
| `OPENAI_API_KEY`        | *(empty)*                                     | OpenAI API key (optional — for`gpt-4o`, etc.)                              |
| `ANTHROPIC_API_KEY`     | *(empty)*                                     | Anthropic API key (optional — for Claude models)                             |
| `GOOGLE_API_KEY`        | *(empty)*                                     | Google API key (optional — for Gemini models)                                |
| `DATABASE_URL`          | `sqlite+aiosqlite:///./debates.db`            | Async SQLAlchemy database URL                                                 |
| `LOG_LEVEL`             | `INFO`                                        | Structlog log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)             |
| `API_HOST`              | `0.0.0.0`                                     | FastAPI bind host                                                             |
| `API_PORT`              | `8000`                                        | FastAPI bind port                                                             |
| `CORS_ORIGINS`          | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed CORS origins                                          |
| `DEFAULT_BUDGET`        | `40000`                                       | Default total token budget per debate                                         |
| `DEFAULT_MAX_ROUNDS`    | `3`                                           | Default maximum debate rounds (1–5)                                          |
| `MIN_SYNTHESIS_TOKENS`  | `2000`                                        | Tokens reserved for synthesis — triggers early synthesis if remaining < this |
| `TIEBREAKER_MIN_BUDGET` | `3000`                                        | Minimum remaining budget required to invoke tiebreaker                        |
| `EXPLORE_THRESHOLD`     | `0.55`                                        | Divergence score above which → EXPLORE mode                                  |
| `EXPLOIT_THRESHOLD`     | `0.30`                                        | Divergence score below which → EXPLOIT mode                                  |
| `LANGFUSE_PUBLIC_KEY`   | *(empty)*                                     | Langfuse observability public key (optional)                                  |
| `LANGFUSE_SECRET_KEY`   | *(empty)*                                     | Langfuse observability secret key (optional)                                  |
| `LANGFUSE_HOST`         | `https://cloud.langfuse.com`                  | Langfuse host URL                                                             |

### Using cloud models

```bash
# OpenAI
DEFAULT_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Anthropic
DEFAULT_MODEL=anthropic/claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-...

# Google
DEFAULT_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=AIza...
```

LiteLLM handles the API translation automatically — the agents remain unchanged regardless of which provider is used.

---

## License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2025 Investment Agents Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

*Built with LangGraph, LiteLLM, FastAPI, and a healthy obsession with structured reasoning.*
