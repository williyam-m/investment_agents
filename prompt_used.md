# Prompts Used : Investment Agents

---

## Commit 1 — `b38b11083c326d0c6cd5d8f55e2f6c5c877f7267`

**Message:** `Feat: ship version 1 - Investment Committee with 5 agents as analysts - support cli and ui`

---

### Prompt

```
You are a senior Python engineer and AI systems architect. Build a production-quality
multi-agent investment committee system from scratch. The system must be fully functional
and deployable by the end of this session.

─── TECH STACK ────────────────────────────────────────────────────────────────
Runtime        : Python 3.11+
Agent Graph    : LangGraph (StateGraph with TypedDict DebateState)
LLM Backend    : LiteLLM (model-agnostic; default gemini/gemini-2.5-flash)
API Framework  : FastAPI + uvicorn with Server-Sent Events (SSE) streaming
Frontend       : React 18 + Vite, Tailwind CSS, no external UI library
CLI            : Typer + Rich (pretty terminal output)
Data Models    : Pydantic v2 (BaseModel + model_validator)
Logging        : structlog (JSON-structured, level-based)
Testing        : pytest + pytest-asyncio
Config         : pydantic-settings (reads from .env)
Persistence    : In-memory dict + optional JSON file persistence to ./debates/

─── AGENTS TO IMPLEMENT ────────────────────────────────────────────────────────
Create 5 specialist analyst agents + 1 synthesis agent + 1 tiebreaker agent.

Each analyst agent must:
  - Extend BaseAnalystAgent (abstract class)
  - Accept (thesis, prior_outputs, round_number, token_allocation) as inputs
  - Return AgentResponse with AnalystOutput containing conviction_score [0,1],
    numeric_score [-1,1], recommendation (buy/hold/sell), key_argument,
    supporting_evidence list, and agent_specific_analysis dict
  - Use a SYSTEM prompt that encodes the agent's investment persona
  - Use a USER prompt template that injects thesis + debate context

Agents:
  1. ValueInvestor   — Benjamin Graham / Buffett; DCF, P/E, moat analysis
  2. MomentumTrader  — price trend, RSI, MACD, volume signals
  3. RiskAnalyst     — VaR, tail risk, drawdown, position sizing, Kelly criterion
  4. MacroEconomist  — interest rates, inflation, GDP, geopolitical macro flows
  5. Contrarian      — Devil's advocate; challenges consensus, hunts crowd errors

  6. SynthesisAgent  — reads all 5 analyst outputs + conflict points, produces
                       CommitteeMemo (final_recommendation, consensus_score,
                       confidence_score, key_insights list, risk_factors list,
                       dissenting_views list, token_usage dict, debate metadata)

  7. TiebreakerAgent — activated only when divergence_score > threshold AND
                       round == max_rounds; reads strongest bull vs bear argument
                       and produces a tie_break_reason + final lean

─── ORCHESTRATION ARCHITECTURE ────────────────────────────────────────────────
Use LangGraph StateGraph. Nodes (in order):

  initialize_debate  → allocate_budget → run_agents → score_divergence
       → [conditional edge] → synthesize | tiebreaker | next_round (loop)

DebateState (TypedDict) fields:
  debate_id, thesis, current_round, max_rounds, agent_outputs (list),
  divergence_score, convergence_history, budget_state, final_memo, status,
  error, streaming_callback

Routing logic (ConditionalEdge):
  - IF current_round >= max_rounds AND divergence_score > tiebreaker_threshold
      → tiebreaker → synthesize
  - IF current_round >= max_rounds
      → synthesize
  - IF divergence_score < convergence_threshold
      → synthesize  (early exit — consensus reached)
  - ELSE → next_round (loop back to run_agents)

─── TOKEN BUDGET SYSTEM ────────────────────────────────────────────────────────
Implement a three-class budget system:

  TokenBudgetTracker : tracks total_budget, spent, remaining per debate
  BudgetAllocator    : distributes tokens across agents per round using
                       explore/exploit mode switching
  ExploreExploitPolicy : switches to "exploit" mode when convergence_score
                         exceeds exploit_threshold; in exploit mode, agents
                         with high conviction get larger token shares

  Allocation formula:
    - Explore mode: equal split across all agents with ±15% jitter
    - Exploit mode: weighted split — top-2 conviction agents get 2x share

─── DIVERGENCE SCORING ────────────────────────────────────────────────────────
Implement AnalysisDivergenceScorer with 3 components (each [0,1]):
  1. numeric_divergence     : std-dev of numeric_scores normalised to [0,1]
  2. recommendation_spread  : fraction of agents NOT in majority vote
  3. semantic_divergence    : cosine distance of key_argument embeddings
                              (use sentence-transformers if available, else 0.0)

  Final divergence_score = weighted average:
    0.35 * numeric + 0.35 * recommendation + 0.30 * semantic

ConflictPoint: surface pairs of agents with opposing recommendations +
  argument excerpts into a ConflictPoint list for SynthesisAgent context.

─── API ENDPOINTS ────────────────────────────────────────────────────────────
POST   /api/v1/debates           — start debate (returns debate_id immediately)
GET    /api/v1/debates/{id}      — fetch full DebateTrace (memo + history)
GET    /api/v1/debates/{id}/stream — SSE stream of DebateStreamEvent objects
GET    /api/v1/debates           — list recent debates (paginated)
GET    /api/v1/health            — health check

SSE event types: agent_update, round_complete, synthesis_start,
                 debate_complete, error

─── FRONTEND ─────────────────────────────────────────────────────────────────
React 18 + Vite SPA. Components:
  DebateForm      — thesis input, max_rounds slider, total_budget input
  LiveFeed        — SSE consumer; renders streamed agent cards in real time
  BudgetBar       — animated progress bar for token usage
  CommitteeMemo   — renders final CommitteeMemo JSON as rich card layout
  StatusBar       — shows current round, mode (explore/exploit), status
  HistoryPanel    — sidebar listing past debates with thesis + status

─── CLI ──────────────────────────────────────────────────────────────────────
`python -m investment_agents.cli.main debate "<thesis>" --rounds 3 --budget 50000`
  - Pretty-print each agent response table with Rich
  - Show budget usage bar
  - Print CommitteeMemo as formatted JSON at end

─── DELIVERABLES ─────────────────────────────────────────────────────────────
- All source files in investment_agents/ package
- Comprehensive docs/ (architecture.md, agents.md, quickstart.md,
  api_reference.md, budget_system.md, index.md)
- README.md (full project overview, ASCII architecture diagram, quickstart)
- .env.example with all required variables
- requirements.txt
- pytest test suite (unit + integration)
- pyproject.toml

Ensure all code is type-annotated, uses structlog for logging, follows
PEP 8, and passes `mypy --strict` with no errors on core modules.
```

---

## Commit 2 — `1a4f1229bc0b4f2af74c5ebb402d21f82401ed0e`

**Message:** `Feat: support delete debate api, list view and dark mode ui`

---

### Prompt

```
You are a senior full-stack engineer. Extend the existing investment_agents system
(LangGraph + FastAPI + React/Vite) with three specific features. Make minimal,
surgical changes — do not refactor existing logic.

─── TECH STACK (existing — do not change) ────────────────────────────────────
Backend  : FastAPI + uvicorn, Python 3.11+, Pydantic v2, structlog
Frontend : React 18 + Vite, Tailwind CSS
Storage  : DebateRepository (in-memory dict + JSON file persistence)
API base : /api/v1/

─── FEATURE 1: DELETE DEBATE API ─────────────────────────────────────────────
Add a new endpoint to the debate router:

  DELETE /api/v1/debates/{debate_id}

  Behaviour:
    - Validate that debate_id exists in DebateRepository
    - Remove from in-memory _traces dict AND _pending dict
    - Delete the corresponding JSON file from persist_dir if it exists
    - Return 200 {"deleted": true, "debate_id": debate_id} on success
    - Return 404 {"detail": "Debate not found"} if not found
    - Log the deletion with structlog (repository.deleted event)

  Add a `delete(debate_id: str) -> bool` method to DebateRepository:
    - Returns True if found and removed, False otherwise
    - Thread-safe: acquire self._lock before mutating state

─── FEATURE 2: LIST VIEW — DEBATE HISTORY ────────────────────────────────────
The GET /api/v1/debates endpoint already exists but the frontend does not
render it as a proper list view. Implement HistoryPanel as a full sidebar:

  React component: frontend/src/components/HistoryPanel.jsx
    Props: { debates: Array, onSelect: fn, onDelete: fn, loading: bool }

    Renders a scrollable list. Each row shows:
      - Truncated thesis (max 80 chars)
      - Status badge (running / complete / failed) with colour coding:
          running  → yellow pulse animation
          complete → green
          failed   → red
      - Round count ("3 rounds")
      - Relative timestamp ("2 min ago")
      - Delete button (trash icon, red on hover)
          Calls onDelete(debate_id) → hits DELETE /api/v1/debates/{id}
          Optimistically removes from local state immediately

    On row click → calls onSelect(debate) → loads debate detail view

  App.jsx changes:
    - Add deleteDebate(id) async handler that calls DELETE /api/v1/debates/{id}
    - On success: remove from debates state array
    - Pass onDelete={deleteDebate} to HistoryPanel

─── FEATURE 3: DARK MODE ─────────────────────────────────────────────────────
Add system-level dark mode support to the React frontend.

  Implementation:
    - Read prefers-color-scheme media query on mount
    - Store preference in localStorage key "theme" ("dark" | "light")
    - Add a toggle button (moon / sun icon) in the top-right corner of App.jsx
    - Apply Tailwind's `dark:` variant classes — DO NOT use a CSS framework switch
    - Use `document.documentElement.classList.toggle("dark", isDark)` pattern
    - Persist toggle state across page reloads via localStorage

  Tailwind config (frontend/tailwind.config.js or vite.config.js):
    - Set `darkMode: "class"` if not already set

  Component updates needed:
    - App.jsx         — root bg, text colours, header bg
    - HistoryPanel    — panel bg, row hover, badge colours
    - CommitteeMemo   — card bg, border, text
    - LiveFeed        — agent card bg + text
    - BudgetBar       — track + fill colours

─── CONSTRAINTS ──────────────────────────────────────────────────────────────
- No new npm packages beyond what's in package.json
- No new Python dependencies — use only what's in requirements.txt
- Keep existing API contract unchanged (no breaking changes)
- All new Python code must be type-annotated and use structlog
- Tailwind classes only — no inline style objects in React
- DELETE must be idempotent (calling twice returns 404 on second call)
```

---

## Commit 3 — `bdfeb1b3ea41b627051b8a5bc51f5e73b3615742`

**Message:** `minor refactor(set-1): improve code quality, security, performance,..`

---

### Prompt

```
You are a senior Python/React engineer performing a structured code-quality pass
on the investment_agents codebase (LangGraph + FastAPI + React). Apply targeted
improvements across 17 files. Do NOT change public API contracts or data model
field names. This is a non-breaking refactor pass.

─── TECH STACK ────────────────────────────────────────────────────────────────
Python 3.11+, LangGraph, FastAPI, Pydantic v2, LiteLLM, structlog
React 18 + Vite, Tailwind CSS

─── OBJECTIVE AREAS ──────────────────────────────────────────────────────────
Apply improvements in 6 categories:
  A) Security hardening
  B) Performance & correctness
  C) Robustness & error resilience
  D) Code clarity & maintainability
  E) Frontend UX consistency
  F) Dependency correctness

─── CATEGORY A: Security Hardening ─────────────────────────────────────────
1. storage/repository.py — Path traversal prevention:
   - Add _UUID_PATTERN = re.compile(r"^[0-9a-f-]{36}$")
   - Add _validate_debate_id(debate_id: str) helper that raises ValueError
     if the ID does not match UUID format
   - Call _validate_debate_id() in _persist_trace() before writing files
   - In _load_persisted(), skip files whose stem does not match _UUID_PATTERN
     (log a warning: "repository.load_skipped_invalid_name")

─── CATEGORY B: Performance & Correctness ───────────────────────────────────
2. storage/repository.py — Fix sort key timezone bug:
   - list_debates() currently crashes when mixing tz-aware and tz-naive datetimes
   - Add inner helper _to_utc(dt: datetime) → datetime:
       if dt.tzinfo is None: return dt.replace(tzinfo=timezone.utc)
       return dt
   - Use _to_utc as the sort key lambda in sorted()

3. orchestrator/graph.py — Lazy graph compilation:
   - Wrap the compiled LangGraph in a module-level singleton pattern
   - Add get_graph() -> CompiledGraph function that compiles once on first call
     and caches result in a module-level _GRAPH variable
   - Update all callers in nodes.py to use get_graph() instead of direct import

4. orchestrator/nodes.py — Structured error propagation:
   - In run_agents node: catch individual agent exceptions, log them with
     structlog (agent_id, error), and store partial results — do not abort
     the entire round on a single agent failure
   - In synthesize node: pass total_rounds=state["current_round"] to
     SynthesisAgent.synthesize() (was missing, caused CommitteeMemo to
     always show rounds=0)

5. agents/synthesis.py — Forward total_rounds to _parse_memo:
   - Add total_rounds: int = 0 parameter to synthesize() signature
   - Store as self._total_rounds
   - Pass total_rounds=total_rounds to _parse_memo()
   - Add total_rounds: int = 0 parameter to _parse_memo() signature

6. budget/allocator.py — Defensive allocation guards:
   - If total_budget <= 0: raise ValueError("total_budget must be positive")
   - If sum of weights is zero in exploit mode: fall back to equal split
   - Ensure per-agent allocation is always >= MIN_TOKENS_PER_AGENT = 100
   - Clamp all allocations so their sum never exceeds total_budget

─── CATEGORY C: Robustness & Error Resilience ───────────────────────────────
7. llm/client.py — Retry with exponential backoff:
   - Wrap the LiteLLM completion call in a retry loop (max 3 attempts)
   - On rate-limit (429) or transient error: wait 2^attempt seconds then retry
   - Log each retry attempt: "llm.retry", attempt=n, error=str(e)
   - Raise on final failure with original error

8. orchestrator/edges.py — Guard missing state fields:
   - Use .get() with safe defaults for all state accesses
   - If divergence_score is None: treat as 0.0 (do not raise KeyError)
   - Log the routing decision: "graph.routing", decision=node_name

9. analysis/convergence.py — Numeric stability:
   - Guard against division by zero in convergence score calculation
   - If agent_outputs is empty list: return 0.0 immediately
   - Clamp final convergence_score to [0.0, 1.0]

─── CATEGORY D: Code Clarity & Maintainability ──────────────────────────────
10. orchestrator/graph.py — Node registration cleanup:
    - Group node additions (graph.add_node) and edge additions (graph.add_edge)
      into clearly commented sections: # --- Nodes --- and # --- Edges ---
    - Extract the conditional routing dict into a named variable
      `_ROUTE_MAP` for readability

11. config/settings.py — Typed settings + validation:
    - Add model_validator(mode="after") that warns (via logger) if
      TOTAL_BUDGET_DEFAULT > 200_000 (likely misconfiguration)
    - Add field descriptions to all Settings fields using Field(description=...)
    - Group fields into logical sections with comments:
        # LLM, # Budget, # Debate, # Server, # Storage

12. models/*.py — Pydantic strict mode:
    - Add model_config = ConfigDict(strict=False, frozen=False) to:
        AgentOutput, AgentResponse, DebateRequest, CommitteeMemo,
        DivergenceResult, StreamingEvent
    - Replace all bare dict type hints with Dict[str, Any] (already imported)

13. api/app.py — CORS & middleware cleanup:
    - Restrict CORS allow_origins to settings value (not hardcoded ["*"])
    - Add a request_id middleware that attaches a UUID to each request
      and includes it in response headers as X-Request-ID
    - Ensure lifespan context manager is used (not deprecated @app.on_event)

─── CATEGORY E: Frontend UX Consistency ─────────────────────────────────────
14. frontend/src/App.jsx — History refresh on completion:
    - Add a useEffect on mount that calls fetchHistory() immediately
      so the history count is ready before the user opens the panel
    - After debate completion (both SSE debate_complete and non-SSE path),
      call fetchHistory() to refresh the list automatically
    - Call fetchHistory() in es.onerror handler too (debate may have saved)

15. api/routes/debate.py — Response model typing:
    - Add response_model= annotation to all route decorators that were missing it
    - Use JSONResponse with explicit status_code on error paths

─── CATEGORY F: Dependency Correctness ──────────────────────────────────────
16. requirements.txt:
    - Uncomment sentence-transformers>=3.0.0 (remove the leading "# ")
    - This enables real semantic divergence scoring instead of 0.0 fallback

─── CONSTRAINTS ──────────────────────────────────────────────────────────────
- Zero breaking changes to public API (endpoints, request/response shapes)
- Zero changes to agent prompts or investment logic
- All Python changes must remain type-annotated
- Each change must be independently reviewable (small, focused diffs)
- Do not change test files unless a refactored function signature breaks them
- React changes: Tailwind classes only, no new npm packages
```
