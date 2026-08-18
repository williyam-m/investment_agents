# Investment Committee Multi-Agent Debate System — Documentation

> **Five specialist AI analysts debate every investment thesis — powered by LangGraph, LiteLLM, and an adaptive explore/exploit token budget.**

---

## Documentation Contents

| Page | Description |
|------|-------------|
| [Architecture](./architecture.md) | LangGraph graph design, node/edge flow, divergence scoring, budget internals |
| [Agents](./agents.md) | All 7 agents: personas, prompts, output schemas, and debate logic |
| [Quick Start](./quickstart.md) | Install, configure, run CLI debate, start API server, use frontend |
| [API Reference](./api_reference.md) | All REST endpoints, SSE events, request/response schemas |
| [Budget System](./budget_system.md) | Token budget lifecycle, explore/exploit allocation, safety guarantees |

---

## Project Structure

```
investment_agents/
├── agents/              # 5 analyst agents + tiebreaker + synthesis
│   ├── base.py          # BaseAnalystAgent abstract class
│   ├── value_investor.py
│   ├── momentum_trader.py
│   ├── risk_analyst.py
│   ├── macro_economist.py
│   ├── contrarian.py
│   ├── tiebreaker.py
│   └── synthesis.py
├── analysis/            # Divergence scoring and convergence detection
│   ├── divergence.py
│   ├── convergence.py
│   └── conflict.py
├── api/                 # FastAPI application and routes
│   ├── app.py           # App factory with CORS, request-ID middleware, lifespan
│   └── routes/
│       ├── debate.py    # POST/GET/DELETE /debates endpoints
│       └── health.py
├── budget/              # Token budget system
│   ├── tracker.py
│   ├── allocator.py     # Defensive allocation with MIN_TOKENS floor
│   └── policy.py
├── cli/
│   └── main.py          # Typer CLI
├── config/
│   └── settings.py      # Pydantic-Settings with field validation
├── llm/
│   └── client.py        # LiteLLM wrapper with exponential backoff retry
├── models/              # Pydantic v2 data contracts
│   ├── agent_output.py
│   ├── budget.py
│   ├── debate.py
│   ├── divergence.py
│   ├── streaming.py
│   └── synthesis.py
├── orchestrator/        # LangGraph graph
│   ├── graph.py         # Lazy singleton graph compilation (get_graph())
│   ├── nodes.py         # Node functions with structured error propagation
│   ├── edges.py         # Conditional routing with safe .get() defaults
│   └── state.py         # DebateState TypedDict
└── storage/
    └── repository.py    # DebateRepository with UUID validation + tz-safe sort

examples/                # Complete debate run outputs as JSON
├── apple_undervalued_run.json   # 3-round AAPL debate — MODERATE BUY, disagreement_score 0.42
└── nvidia_overvalued_run.json   # 3-round NVDA debate — HOLD/DO NOT INITIATE, tiebreaker invoked (1:2:2 split)

docs/                    # This documentation
├── index.md             # This file
├── architecture.md
├── agents.md
├── quickstart.md
├── api_reference.md
└── budget_system.md

prompt_used.md           # Engineering prompts behind each commit
```

---

## Recent Changes (Latest Commit: `bdfeb1b`)

The latest refactor pass (`minor refactor set-1`) improved 17 files across 6 quality dimensions:

| Category | What Changed |
|----------|-------------|
| **Security** | UUID path-traversal validation in `repository.py` — only valid UUID filenames are read/written |
| **Correctness** | Timezone-safe datetime sort in `list_debates()` — mixed tz-aware/naive datetimes no longer crash |
| **Performance** | Lazy graph compilation via `get_graph()` singleton — graph compiled once, not per-request |
| **Robustness** | Per-agent error isolation in `run_agents` — single agent failure doesn't abort the round |
| **Robustness** | LLM exponential backoff retry (3 attempts, 2^n second wait) in `client.py` |
| **Correctness** | `total_rounds` now correctly passed through to `CommitteeMemo` (was always 0) |
| **Defensive** | `BudgetAllocator` guards: positive budget check, zero-weight fallback, MIN_TOKENS floor |
| **Clarity** | `get_graph()` singleton, `_ROUTE_MAP` named routing dict, section comments in graph.py |
| **Frontend** | `fetchHistory()` called on mount and after every debate completion (SSE + non-SSE paths) |
| **Dependencies** | `sentence-transformers` uncommented — real semantic divergence scoring now active |

---

## Quick Links

- **README**: [`../README.md`](../README.md)
- **Prompts Used**: [`../prompt_used.md`](../prompt_used.md)
- **Example Outputs**: [`../examples/`](../examples/)
- **Environment Config**: [`../.env.example`](../.env.example)
