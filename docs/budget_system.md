# Token Budget System — Investment Committee Debate System

## Why Token Budgets Matter in Multi-Agent Systems

Multi-agent LLM systems face a fundamental challenge: each agent call costs tokens, and costs are unbounded without explicit control. In a 3-round debate with 5 agents, a synthesis step, and an optional tiebreaker, the total call count can reach 17+ LLM invocations. Without a budget system:

- **Runaway costs**: A single verbose agent could exhaust resources before the synthesis step runs.
- **Unfair allocation**: Early-round agents with no limit squeeze out later rounds and synthesis.
- **No adaptive routing**: The debate mode (explore vs exploit) should change *based on remaining budget* — impossible without tracking.
- **No audit trail**: Debugging token usage per-agent across rounds requires a structured record.

The budget system in this project solves all four problems with three interconnected components: `TokenBudgetTracker`, `BudgetAllocator`, and `ExploreExploitPolicy`.

---

## TokenBudgetTracker

**Location**: `investment_agents/budget/tracker.py`

**Lifetime**: One instance per debate session, created in `node_init`, stored in `DebateState`.

### API

```python
class TokenBudgetTracker:

    def __init__(self, total_budget: int, reserved_for_synthesis: int = 2000) -> None:
        """
        total_budget: Hard ceiling on total token spend for the debate.
        reserved_for_synthesis: Tokens locked away from agent use.
                                Guarantees the synthesis step always runs.
        """

    async def record_usage(self, agent_id: str, round_number: int, tokens: int) -> None:
        """
        Record token consumption for an agent after an LLM call.
        Thread-safe (asyncio.Lock).
        Raises BudgetExhaustedError if tokens > get_available().
        """

    def get_used(self, agent_id: str) -> int:
        """Return cumulative tokens used by a specific agent across all rounds."""

    def get_total_used(self) -> int:
        """Return total tokens used across all agents and all rounds."""

    def get_remaining(self) -> int:
        """Total budget minus total used (includes reserved)."""

    def get_available(self) -> int:
        """Budget available for agent use: remaining - reserved_for_synthesis.
           Clamped to 0. This is the number agents can actually spend."""

    def is_exhausted(self) -> bool:
        """Returns True when get_available() <= 0."""

    def get_report(self) -> dict:
        """Full breakdown: totals, per-agent usage, usage log."""
```

### Key Invariant

```
available = total_budget - total_used - reserved_for_synthesis

Agents can only spend from `available`.
The synthesis reserve is always protected.
```

### BudgetExhaustedError

```python
class BudgetExhaustedError(Exception):
    def __init__(self, agent_id: str, requested: int, available: int):
        ...
```

Raised when `record_usage()` would exceed available budget. The orchestrator catches this, logs the event, and routes to synthesis immediately.

---

## BudgetAllocator

**Location**: `investment_agents/budget/allocator.py`

**Instantiated**: Once per debate in `node_init` or `node_allocate_budget`, reused every round.

### API

```python
class BudgetAllocator:

    def __init__(self, agent_types: List[str], settings: Optional[Settings] = None) -> None:
        """
        agent_types: Ordered list of agent type strings (e.g., ["value_investor", ...])
        """

    def allocate_round(
        self,
        available_tokens: int,
        round_number: int,
        mode: str,                              # "explore" | "exploit" | "transition"
        divergence_report: Optional[DivergenceReport] = None,
    ) -> Dict[str, int]:
        """
        Returns dict: { agent_type: token_allocation }
        """
```

### Explore Mode — Equal Split

Used in round 1 and when `divergence_score > explore_threshold (0.55)`.

All agents hear equally — no prior knowledge about which views are most distinctive.

```python
base = max(MIN_AGENT_TOKENS, available_tokens // n_agents)   # MIN = 400
remainder = available_tokens - base * n_agents
# First `remainder` agents get base + 1 token
allocations = [base + (1 if i < remainder else 0) for i in range(n_agents)]
```

**Example** (40,000 total, 2,000 synthesis reserve, 5 agents):
```
available = 38,000 for all rounds combined
Round 1 available (assume 38,000): 38,000 / 5 = 7,600 per agent
All agents get 7,600 tokens.
```

### Exploit Mode — Weighted Split

Used when `divergence_score < exploit_threshold (0.30)` or in TRANSITION mode.

Agents with the most distinctive positions (furthest from mean) get proportionally more tokens. This deepens the most valuable perspectives.

```python
exploit_order = divergence_report.exploit_worthy_agents  # sorted by |score - mean| desc

# Weight formula:
for agent in agent_types:
    if agent in exploit_order:
        rank = exploit_order.index(agent)          # 0 = most distinctive
        weight[agent] = len(exploit_order) - rank  # highest rank → highest weight
    else:
        weight[agent] = 1.0                        # minimum weight for agents not ranked

total_weight = sum(weights.values())
allocation[agent] = max(MIN_AGENT_TOKENS, int(available * weight[agent] / total_weight))
```

**Example** (exploit_worthy_agents = [contrarian, value_investor, risk_analyst, momentum_trader, macro_economist]):
```
Weights: contrarian=5, value_investor=4, risk_analyst=3, momentum_trader=2, macro_economist=1
Total weight = 15

With 5,000 tokens available:
contrarian:     int(5000 * 5/15) = 1,666 tokens
value_investor: int(5000 * 4/15) = 1,333 tokens
risk_analyst:   int(5000 * 3/15) = 1,000 tokens
momentum_trader: int(5000 * 2/15) = 666 tokens
macro_economist: int(5000 * 1/15) = 333 tokens → bumped to MIN=400
```

### Named Constants

```python
# budget/allocator.py
AGENT_FRACTION     = 0.85   # 85% of available budget goes to analyst agents
SYNTHESIS_FRACTION = 0.10   # 10% reserved for synthesis agent
BUFFER_FRACTION    = 0.05   # 5% held as safety buffer
MIN_TOKENS         = 200    # Hard floor — no agent ever receives fewer than 200 tokens
```

These constants are used internally by `allocate_round()` and can be adjusted directly in `budget/allocator.py`.

### Minimum Agent Token Guard

`MIN_TOKENS = 200`. No agent ever receives fewer than 200 tokens per round, regardless of weight or budget constraints. If weighted allocations would sum beyond available tokens due to minimums, they are scaled down proportionally. If total budget is zero or negative, `BudgetAllocator.__init__` raises `ValueError` immediately. If all exploit weights resolve to zero, the allocator falls back to equal split automatically.

---

## ExploreExploitPolicy

**Location**: `investment_agents/budget/policy.py`

Makes the routing decision after each round's divergence score is computed.

### API

```python
class ExploreExploitPolicy:

    def __init__(
        self,
        explore_threshold: float = 0.55,
        exploit_threshold: float = 0.30,
    ) -> None:
        ...

    def decide(
        self,
        divergence_report: DivergenceReport,
        round_number: int,
        max_rounds: int,
        remaining_tokens: int,
        min_synthesis_tokens: int,
    ) -> Tuple[DebateMode, str]:
        """Returns (DebateMode, reason_string)."""
```

### Decision Tree

```
decide(divergence_report, round_number, max_rounds, remaining_tokens, min_synthesis_tokens):
│
├─ remaining_tokens < min_synthesis_tokens
│    → SYNTHESIZE: "Budget nearly exhausted: X tokens remaining < Y minimum for synthesis."
│
├─ round_number >= max_rounds
│    → SYNTHESIZE: "Maximum rounds reached: round N of M."
│
├─ overall_score > explore_threshold (0.55)
│    → EXPLORE: "High divergence (0.X > 0.55): agents still disagree widely — continuing to EXPLORE."
│    Budget effect: next round uses equal split
│
├─ overall_score < exploit_threshold (0.30)
│    → EXPLOIT: "Low divergence (0.X < 0.30): converging — switching to EXPLOIT."
│    Budget effect: next round uses weighted split by distinctiveness
│
└─ 0.30 ≤ score ≤ 0.55 (transition zone)
     → TRANSITION: "Moderate divergence (0.X): in transition zone — using EXPLOIT allocation."
     Budget effect: next round uses weighted split (same as EXPLOIT)
```

### DebateMode Enum

```python
class DebateMode(str, Enum):
    EXPLORE    = "explore"
    EXPLOIT    = "exploit"
    TRANSITION = "transition"
    SYNTHESIZE = "synthesize"
```

---

## Configuration via .env

All budget system parameters are tunable without code changes:

```bash
# .env

# Total token budget for debates (if not specified in request)
DEFAULT_BUDGET=40000

# Tokens reserved for synthesis step — always protected
# Corresponds to TokenBudgetTracker(reserved_for_synthesis=...)
# Configurable via: settings.min_synthesis_tokens (synthesis reserve)
MIN_SYNTHESIS_TOKENS=2000

# Minimum budget required to spawn a tiebreaker agent
TIEBREAKER_MIN_BUDGET=3000

# ExploreExploitPolicy thresholds
EXPLORE_THRESHOLD=0.55    # divergence score above this → EXPLORE mode
EXPLOIT_THRESHOLD=0.30    # divergence score below this → EXPLOIT mode
# Transition zone: 0.30 ≤ score ≤ 0.55 → TRANSITION (uses exploit allocation)

# Default maximum debate rounds (overridden per-request)
DEFAULT_MAX_ROUNDS=3

# Agent retry settings (affects token usage indirectly)
AGENT_MAX_RETRIES=3
AGENT_REQUEST_TIMEOUT=120
```

---

## Example Budget Trace — 3-Round Debate

**Setup**: thesis about AAPL, 40,000 total budget, 3 max rounds, 5 agents.

```
TokenBudgetTracker(total_budget=40000, reserved_for_synthesis=2000)
Available for agents: 38,000 tokens

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROUND 1 — mode: EXPLORE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BudgetAllocator.allocate_round(available=38000, round=1, mode="explore")
  → Equal split: 38000 // 5 = 7600 per agent

  value_investor:   7,600 allocated  →  712 used  (9.4% utilisation)
  momentum_trader:  7,600 allocated  →  689 used
  risk_analyst:     7,600 allocated  →  744 used
  macro_economist:  7,600 allocated  →  701 used
  contrarian:       7,600 allocated  →  698 used

ROUND 1 USAGE: 3,544 tokens consumed
tracker.get_total_used() = 3,544
tracker.get_available()  = 34,456  (38000 - 3544)

DivergenceScorer.score(round_1_outputs):
  recommendation_variance = 0.58   (agents disagree on numeric scores)
  semantic_divergence      = 0.61   (key_arguments have low cosine similarity)
  conflict_penalty         = 0.25   (1 hard conflict detected / 10 pairs)
  overall_score            = 0.40*0.58 + 0.35*0.61 + 0.25*0.25 = 0.61

ExploreExploitPolicy.decide(score=0.61, round=1, max=3, remaining=36456, min_synth=2000):
  0.61 > 0.55 → EXPLORE mode (continue equal split next round)
  Tiebreaker check: has_hard_conflicts=True, available(34456) > 3000 → SPAWN TIEBREAKER

TiebreakerAgent:
  Allocated: 3,000 tokens   →  Used: 892 tokens

POST-ROUND-1 BUDGET:
  Total used: 4,436 tokens
  Remaining:  35,564 tokens
  Available:  33,564 tokens (excl. 2,000 synthesis reserve)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROUND 2 — mode: EXPLORE (score was 0.61 > 0.55)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BudgetAllocator.allocate_round(available=33564, round=2, mode="explore")
  → Equal split: 33564 // 5 = 6712 per agent

  value_investor:   6,712 allocated  →  731 used
  momentum_trader:  6,712 allocated  →  704 used
  risk_analyst:     6,712 allocated  →  756 used
  macro_economist:  6,712 allocated  →  719 used
  contrarian:       6,712 allocated  →  711 used

ROUND 2 USAGE: 3,621 tokens
tracker.get_total_used() = 8,057
tracker.get_available()  = 29,943

DivergenceScorer.score(round_2_outputs):
  overall_score = 0.38   (still above exploit threshold, below explore threshold)
  → TRANSITION mode (0.30 ≤ 0.38 ≤ 0.55)
  → exploit_worthy_agents: [contrarian, risk_analyst, value_investor, macro_economist, momentum_trader]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROUND 3 — mode: TRANSITION → EXPLOIT allocation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BudgetAllocator.allocate_round(available=29943, round=3, mode="transition")
  → Weighted split by exploit_worthy_agents ranking

  weights: contrarian=5, risk_analyst=4, value_investor=3, macro_economist=2, momentum_trader=1
  total_weight = 15

  contrarian:      int(29943 * 5/15) = 9,981 allocated  →  889 used
  risk_analyst:    int(29943 * 4/15) = 7,984 allocated  →  801 used
  value_investor:  int(29943 * 3/15) = 5,988 allocated  →  742 used
  macro_economist: int(29943 * 2/15) = 3,992 allocated  →  693 used
  momentum_trader: int(29943 * 1/15) = 1,996 allocated  →  681 used

ROUND 3 USAGE: 3,806 tokens
tracker.get_total_used() = 11,863

ExploreExploitPolicy.decide(score=0.38, round=3, max=3, remaining=28137, min_synth=2000):
  round_number (3) >= max_rounds (3) → SYNTHESIZE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SYNTHESIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SynthesisAgent: budget from synthesis reserve (2,000 tokens)
  Used: 1,284 tokens

FINAL BUDGET REPORT:
  total_budget:           40,000
  total_used:             13,147
  remaining:              26,853
  efficiency:             32.9%
  reserved_for_synthesis:  2,000  (1,284 actually used)
  by_agent:
    value_investor:        2,185
    momentum_trader:       2,084
    risk_analyst:          2,301
    macro_economist:       2,113
    contrarian:            2,298
    tiebreaker:              892
    synthesis:             1,284
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Note: Actual token consumption depends heavily on the LLM model, response length, and thesis complexity. Local Llama 3 models typically use 600–900 tokens per agent per round. Cloud models (GPT-4o, Claude) may use similar or more depending on temperature and `max_tokens_per_call` settings.

