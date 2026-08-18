# Architecture — Investment Committee Debate System

## Overview

The Investment Committee Debate System is a multi-agent AI orchestration platform that simulates a realistic investment committee debate. Five specialist analyst agents — each with a distinct investment philosophy — debate an investment thesis over multiple rounds, guided by a token-budget-aware explore/exploit policy. The debate concludes with a synthesis agent that produces a structured Committee Memo.

The system is built on three pillars:

1. **LangGraph** — manages the debate as a typed, stateful directed graph with conditional routing.
2. **LiteLLM** — provides a unified interface to any LLM backend (Ollama locally, OpenAI, Anthropic, etc.).
3. **FastAPI + SSE** — exposes the debate orchestrator as a real-time streaming REST API consumed by a React frontend.

---

## Component Map

```
investment_agents/
├── agents/              # 7 analyst agents
│   ├── base.py          # BaseAnalystAgent ABC — retry, JSON parsing, fallback
│   ├── value_investor.py
│   ├── momentum_trader.py
│   ├── risk_analyst.py
│   ├── macro_economist.py
│   ├── contrarian.py
│   ├── tiebreaker.py    # Spawn-on-conflict mediator agent
│   └── synthesis.py     # Produces CommitteeMemo
│
├── analysis/            # Post-round intelligence
│   ├── divergence.py    # DivergenceScorer — composite divergence score
│   ├── convergence.py   # ConvergenceDetector — topic-level convergence signals
│   └── conflict.py      # ConflictResolver — hard/soft conflict labelling
│
├── api/                 # HTTP layer
│   ├── app.py           # FastAPI application factory, CORS, middleware
│   └── routes/
│       ├── debate.py    # POST/GET /debates, SSE streaming endpoint
│       └── health.py    # GET /health
│
├── budget/              # Token economy
│   ├── tracker.py       # TokenBudgetTracker — per-session, thread-safe
│   ├── allocator.py     # BudgetAllocator — explore/exploit allocation formulas
│   └── policy.py        # ExploreExploitPolicy — routing decision logic
│
├── cli/
│   └── main.py          # Typer CLI: debate, serve, list-debates
│
├── config/
│   └── settings.py      # Pydantic-Settings from .env
│
├── llm/
│   └── client.py        # LLMClient wrapping LiteLLM, JSON extraction
│
├── models/              # Pydantic data models (immutable wire types)
│   ├── agent_output.py  # AnalystOutput, AgentType, Recommendation, Evidence
│   ├── budget.py        # TokenBudget, BudgetReport, BudgetSummary
│   ├── debate.py        # DebateRequest, DebateTrace, RoundTrace, RoutingDecision
│   ├── divergence.py    # DivergenceReport, ConflictPoint, ConvergenceSignal
│   ├── streaming.py     # StreamEvent, StreamEventType
│   └── synthesis.py     # CommitteeMemo, DissentingView
│
├── orchestrator/        # LangGraph graph definition
│   ├── graph.py         # build_debate_graph(), DebateOrchestrator
│   ├── nodes.py         # 7 node functions (init, allocate_budget, run_agents, …)
│   ├── edges.py         # Conditional routing functions
│   └── state.py         # DebateState TypedDict — the shared graph state
│
└── storage/
    └── repository.py    # DebateRepository — in-memory + JSON-file persistence
```

---

## LangGraph Graph — Nodes and Edges

### Node Descriptions

| Node | Function | Responsibility |
|------|----------|----------------|
| `init` | `node_init` | Validates the DebateRequest, initialises TokenBudgetTracker, emits `DEBATE_STARTED` SSE event |
| `allocate_budget` | `node_allocate_budget` | Calls `BudgetAllocator.allocate_round()` with current mode and last DivergenceReport; writes per-agent token allocations into state |
| `run_agents` | `node_run_agents` | Runs all 5 analyst agents concurrently (`asyncio.gather`); each agent receives its token allocation and prior outputs; emits `AGENT_OUTPUT` events |
| `score_divergence` | `node_score_divergence` | Calls `DivergenceScorer.score()` on the round's outputs; emits `DIVERGENCE_SCORED` and `CONFLICT_DETECTED` events |
| `run_tiebreaker` | `node_run_tiebreaker` | Spawns the `TiebreakerAgent` when hard conflicts exist; emits `TIEBREAKER_SPAWNED` event |
| `synthesize` | `node_synthesize` | Calls `SynthesisAgent.synthesize()` with all rounds of outputs; produces `CommitteeMemo`; emits `SYNTHESIS_COMPLETE` |
| `prepare_next_round` | `node_prepare_next_round` | Increments round counter, resets per-round state, emits `ROUND_STARTED` |

### Edge Definitions

```
init → allocate_budget
allocate_budget → run_agents
run_agents → score_divergence

score_divergence --[conditional: route_after_divergence]-→
    ├── "tiebreaker"   → run_tiebreaker
    ├── "next_round"   → prepare_next_round
    └── "synthesize"   → synthesize

run_tiebreaker --[conditional: route_after_tiebreaker]-→
    ├── "next_round"   → prepare_next_round
    └── "synthesize"   → synthesize

prepare_next_round → allocate_budget   (loop back)

synthesize → END
```

### Conditional Routing Logic

**`route_after_divergence`** (in `edges.py`):
1. Check `remaining_tokens < min_synthesis_tokens` → `"synthesize"`
2. Check `round_number >= max_rounds` → `"synthesize"`
3. Check `has_hard_conflicts` AND `tiebreaker_budget_available` → `"tiebreaker"`
4. Otherwise → `"next_round"`

**`route_after_tiebreaker`**:
1. Check `remaining_tokens < min_synthesis_tokens` → `"synthesize"`
2. Check `round_number >= max_rounds` → `"synthesize"`
3. Otherwise → `"next_round"`

---

## Data Flow: DebateRequest → CommitteeMemo

```
Client
  │
  │  POST /api/v1/debates
  │  Body: DebateRequest { thesis, investment_context, total_budget, max_rounds, model_config }
  ▼
FastAPI route (debate.py)
  │  Creates pending entry in DebateRepository
  │  Calls DebateOrchestrator.run(request)
  ▼
DebateOrchestrator._make_initial_state()
  │  Converts DebateRequest → DebateState (TypedDict)
  │  Sets debate_mode="explore", round_number=1
  ▼
LangGraph graph.ainvoke(initial_state)
  │
  ├─── node_init
  │      Creates TokenBudgetTracker(total_budget, reserved_for_synthesis=2000)
  │      Emits DEBATE_STARTED stream event
  │
  ├─── node_allocate_budget
  │      BudgetAllocator.allocate_round(available, round_number, mode="explore")
  │      Equal split: each of 5 agents gets available_tokens / 5
  │      Writes: state["budget_allocations"] = {agent_type: tokens}
  │
  ├─── node_run_agents [parallel asyncio.gather]
  │      For each of 5 analysts:
  │        agent.analyze(thesis, context, round_number, prior_outputs, token_alloc)
  │          → LLMClient.complete(messages, max_tokens=alloc)
  │          → LLMClient.extract_json(raw_text)
  │          → agent._parse_output(data) → AnalystOutput
  │          → TokenBudgetTracker.record_usage(agent_id, round, tokens_used)
  │      Emits AGENT_OUTPUT event per agent
  │      Emits BUDGET_UPDATE event
  │
  ├─── node_score_divergence
  │      DivergenceScorer.score(round_outputs)
  │        1. _normalized_variance(numeric_scores)        [weight 0.40]
  │        2. _mean_pairwise_distance(embeddings)         [weight 0.35]
  │        3. conflict_penalty from _detect_conflicts()   [weight 0.25]
  │      overall_score = w1*rec_var + w2*sem_div + w3*conflict_penalty
  │      Emits DIVERGENCE_SCORED event
  │      For each ConflictPoint: emits CONFLICT_DETECTED event
  │
  ├─── [conditional] ExploreExploitPolicy.decide()
  │      score > 0.55 → EXPLORE  (continue with equal split next round)
  │      score < 0.30 → EXPLOIT  (weight by distinctiveness next round)
  │      else         → TRANSITION (moderate divergence, use exploit allocation)
  │      Emits MODE_CHANGED event
  │
  ├─── [if has_hard_conflicts] node_run_tiebreaker
  │      TiebreakerAgent.analyze(conflicts, all_outputs)
  │      Emits TIEBREAKER_SPAWNED event
  │
  ├─── [loop: prepare_next_round → allocate_budget → run_agents → ...]
  │
  └─── node_synthesize
         SynthesisAgent.synthesize(all_round_outputs, conflicts, tiebreaker_outputs)
           → CommitteeMemo { final_recommendation, conviction, vote_breakdown,
                             executive_summary, bull_case, bear_case, key_risks, ... }
         Emits SYNTHESIS_STARTED, SYNTHESIS_COMPLETE events
         Writes committee_memo into state
  │
DebateOrchestrator._state_to_trace(final_state, request)
  │  Converts DebateState → DebateTrace (Pydantic model)
  ▼
DebateRepository.save(trace)       # persists to in-memory + optional JSON file
  ▼
JSONResponse(trace.model_dump_json())
  ▼
Client receives DebateTrace JSON
```

---

## Budget System Internals

### TokenBudgetTracker

Lives in `budget/tracker.py`. Per-debate, created in `node_init`.

```
total_budget = 40,000  (default)
reserved_for_synthesis = 2,000

available = total_budget - total_used - reserved_for_synthesis
```

The tracker holds:
- `_used_by_agent: Dict[str, int]` — cumulative per agent ID
- `_usage_log: List[{agent_id, round_number, tokens}]` — full audit log
- `_lock: asyncio.Lock` — prevents concurrent over-spend

`record_usage(agent_id, round_number, tokens)` is called after each LLM call completes. If `tokens > available`, raises `BudgetExhaustedError`.

### BudgetAllocator

Lives in `budget/allocator.py`.

**Explore mode (equal split)**:
```
per_agent = max(MIN_AGENT_TOKENS, available_tokens // n_agents)
remainder = available_tokens - per_agent * n_agents
first (remainder) agents get +1 token
```

**Exploit mode (weighted split)**:
```
exploit_order = divergence_report.exploit_worthy_agents  # sorted by |score - mean|
weight[agent] = (len(exploit_order) - rank_in_order)     # most distinctive = highest weight
weight[others] = 1.0

allocated[agent] = max(MIN_AGENT_TOKENS, int(available * weight[agent] / total_weight))
```

If total_allocated > available due to minimums, scale down proportionally.

### Per-round budget flow:
```
Round N starts with: tracker.get_available() tokens
BudgetAllocator splits available across 5 agents
Each agent's LLM call respects max_tokens=allocation
After each call: tracker.record_usage()
Round ends with updated cumulative usage
```

---

## Divergence Scoring Algorithm

`DivergenceScorer.score(outputs, round_number)` computes a composite score in [0, 1]:

### Component 1 — Recommendation Variance (weight = 0.40)

```python
numeric_scores = [o.numeric_score for o in outputs]  # each in [-1, 1]
std_dev = numpy.std(numeric_scores, ddof=0)
rec_var = clip(std_dev / MAX_SCORE_STD_DEV, 0, 1)    # MAX_SCORE_STD_DEV = 1.0
```

### Component 2 — Semantic Divergence (weight = 0.35)

```python
key_arguments = [o.key_argument for o in outputs]
embeddings = SentenceTransformer("all-MiniLM-L6-v2").encode(key_arguments, normalize=True)
# Cosine distance matrix (unit vectors → dot product = similarity)
sim_matrix = embeddings @ embeddings.T
upper_pairs = triu_indices(n, k=1)
distances = clip(1 - sim_matrix[upper_pairs], 0, 1)
sem_div = mean(distances)
```

**Fallback** (when `sentence_transformers` not installed): deterministic random unit vectors seeded by `abs(hash(text)) % 2^31`, producing semantic divergence in the 0.4–0.6 range.

### Component 3 — Conflict Penalty (weight = 0.25)

```python
for each pair (agent_a, agent_b):
    gap = abs(agent_a.numeric_score - agent_b.numeric_score)
    if gap > 1.0:  severity = HARD
    elif gap > 0.5: severity = SOFT

hard_conflicts = [c for c in conflicts if c.severity == HARD]
total_pairs = n * (n-1) / 2
conflict_penalty = min(1.0, len(hard_conflicts) / total_pairs)
```

### Final Score

```python
overall_score = min(1.0, 0.40 * rec_var + 0.35 * sem_div + 0.25 * conflict_penalty)
```

### Exploit-Worthy Agent Ranking

```python
mean_score = mean(numeric_scores)
ranked = sorted(outputs, key=lambda o: abs(o.numeric_score - mean_score), reverse=True)
exploit_worthy_agents = [o.agent_type.value for o in ranked]
```

---

## Token Routing — Explore / Exploit / Tiebreaker / Synthesize

`ExploreExploitPolicy.decide(divergence_report, round_number, max_rounds, remaining_tokens, min_synthesis_tokens)`:

```
Decision Tree:
│
├─ remaining_tokens < min_synthesis_tokens (2000)  →  SYNTHESIZE
│    "Budget nearly exhausted"
│
├─ round_number >= max_rounds                       →  SYNTHESIZE
│    "Maximum rounds reached"
│
├─ overall_score > explore_threshold (0.55)         →  EXPLORE
│    "High divergence — agents still disagree widely"
│    Next round: equal budget split (all voices heard equally)
│
├─ overall_score < exploit_threshold (0.30)         →  EXPLOIT
│    "Low divergence — converging"
│    Next round: weighted split by distinctiveness (top outliers get more tokens)
│
└─ else (0.30 ≤ score ≤ 0.55)                      →  TRANSITION
     "Moderate divergence — transition zone"
     Next round: exploit-style weighted allocation
```

**Tiebreaker trigger** (checked in `route_after_divergence` before mode routing):
```
if divergence_report.has_hard_conflicts
   AND tracker.get_available() >= settings.tiebreaker_min_budget (3000)
   → spawn TiebreakerAgent
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/debates` | Start debate, returns `DebateTrace` |
| `GET` | `/api/v1/debates/{id}` | Retrieve completed debate by ID |
| `GET` | `/api/v1/debates/{id}/stream` | SSE stream of debate events |
| `DELETE` | `/api/v1/debates/{id}` | Delete a debate trace; `204 No Content` / `404` |
| `GET` | `/api/v1/debates` | List recent debates (summary) |
| `GET` | `/api/v1/health` | Health check |

See `docs/api_reference.md` for full schemas and examples.

---

## Extension Points

### Adding a New Agent

1. Create `investment_agents/agents/my_agent.py` subclassing `BaseAnalystAgent`.
2. Implement `agent_type`, `system_prompt`, `json_schema_description`, `_parse_output`.
3. Add `MY_AGENT = "my_agent"` to `AgentType` enum in `models/agent_output.py`.
4. Register the agent in `orchestrator/nodes.py` inside `node_run_agents`.
5. Update `budget/allocator.py` `ANALYST_AGENT_COUNT` constant.
6. Add tests in `tests/unit/test_my_agent.py`.

### Swapping LLMs

1. Change `OLLAMA_BASE_URL` and `DEFAULT_MODEL` in `.env`.
2. LiteLLM provider strings: `ollama/llama2:7b`, `gpt-4o`, `anthropic/claude-3-5-sonnet-20241022`, `groq/llama3-8b-8192`.
3. Per-debate override: set `model_config.model` in `DebateRequest`.

### Plugging in a Database

1. Replace `storage/repository.py` with an async SQLAlchemy implementation.
2. `DebateRepository` interface: `save(trace)`, `get(id)`, `list_recent(limit)`.
3. Add `alembic` for migrations; add `DATABASE_URL` to `.env`.

### Adding Observability

- Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env`.
- `Settings.langfuse_enabled` becomes `True`, and `LLMClient` wraps calls with Langfuse callbacks automatically.
- Alternatively, instrument with OpenTelemetry via the `structlog` processors.

### Tuning Divergence Weights

Edit the module-level constants in `analysis/divergence.py`:
```python
_W_REC_VAR: float = 0.40   # recommendation variance weight
_W_SEM_DIV: float = 0.35   # semantic divergence weight
_W_CONFLICT: float = 0.25  # conflict penalty weight
```
They must sum to 1.0.

### Adjusting Explore/Exploit Thresholds

Via `.env`:
```
EXPLORE_THRESHOLD=0.55   # > this → EXPLORE mode
EXPLOIT_THRESHOLD=0.30   # < this → EXPLOIT mode
MIN_SYNTHESIS_TOKENS=2000
TIEBREAKER_MIN_BUDGET=3000
DEFAULT_BUDGET=40000
DEFAULT_MAX_ROUNDS=3
```

