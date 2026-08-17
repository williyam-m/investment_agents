# API Reference — Investment Committee Debate System

Base URL: `http://localhost:8000/api/v1`

All request bodies are JSON. All successful responses are JSON unless noted as SSE.

---

## POST /api/v1/debates

Start a new investment committee debate. Runs synchronously and returns the complete `DebateTrace` when finished.

### Request

```json
POST /api/v1/debates
Content-Type: application/json

{
  "thesis": "Apple Inc. is significantly undervalued at current prices and presents a compelling long-term buy opportunity",
  "investment_context": {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology",
    "current_price": 187.45,
    "market_cap_bn": 2890.0,
    "supporting_data": {
      "pe_ratio": 29.4,
      "revenue_growth_yoy": 0.05,
      "gross_margin": 0.443,
      "free_cash_flow_bn": 99.6
    },
    "relevant_documents": [
      "Q3 2024 earnings: revenue $85.8B, EPS $1.40, beating estimates",
      "Services revenue grew 14% YoY to $24.2B — highest margin segment"
    ]
  },
  "total_budget": 40000,
  "max_rounds": 3,
  "model_config": {
    "model": "ollama/llama3",
    "temperature": 0.7,
    "max_tokens_per_call": 1000,
    "ollama_base_url": "http://localhost:11434"
  },
  "debate_id": "optional-custom-id-or-omit-for-auto"
}
```

### Request Schema

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `thesis` | string | ✅ | — | Investment thesis to debate. 10–1000 characters. |
| `investment_context` | object | ❌ | `{}` | Structured context about the investment |
| `investment_context.ticker` | string | ❌ | null | Stock ticker symbol |
| `investment_context.company_name` | string | ❌ | null | Full company name |
| `investment_context.sector` | string | ❌ | null | Industry sector |
| `investment_context.current_price` | float | ❌ | null | Current share price |
| `investment_context.market_cap_bn` | float | ❌ | null | Market cap in billions |
| `investment_context.supporting_data` | object | ❌ | `{}` | Arbitrary key-value financial metrics |
| `investment_context.relevant_documents` | string[] | ❌ | `[]` | Text snippets for agent context |
| `total_budget` | integer | ❌ | 40000 | Total token budget for debate |
| `max_rounds` | integer | ❌ | 3 | Max debate rounds (1–5) |
| `model_config.model` | string | ❌ | `"ollama/llama2"` | LiteLLM model string |
| `model_config.temperature` | float | ❌ | 0.7 | Sampling temperature (0.0–2.0) |
| `model_config.max_tokens_per_call` | integer | ❌ | 1000 | Max tokens per individual LLM call |
| `model_config.ollama_base_url` | string | ❌ | `"http://localhost:11434"` | Ollama server URL |
| `debate_id` | string | ❌ | auto UUID | Custom debate ID |

### Response — 200 OK

Returns a complete `DebateTrace` object.

```json
{
  "debate_id": "3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab",
  "thesis": "Apple Inc. is significantly undervalued...",
  "investment_context": { "ticker": "AAPL", "..." : "..." },
  "model_used": "ollama/llama3",
  "rounds": [
    {
      "round_number": 1,
      "mode": "explore",
      "budget_allocated": {
        "value_investor": 7600,
        "momentum_trader": 7600,
        "risk_analyst": 7600,
        "macro_economist": 7600,
        "contrarian": 7600
      },
      "budget_used": {
        "value_investor": 712,
        "momentum_trader": 689,
        "risk_analyst": 744,
        "macro_economist": 701,
        "contrarian": 698
      },
      "agent_outputs": [ { "...": "AnalystOutput objects" } ],
      "divergence_report": {
        "round_number": 1,
        "overall_score": 0.6123,
        "recommendation_variance": 0.58,
        "semantic_divergence": 0.61,
        "conflict_penalty": 0.25,
        "has_hard_conflicts": true,
        "conflicts": [ { "...": "ConflictPoint objects" } ],
        "exploit_worthy_agents": ["contrarian", "value_investor", "momentum_trader", "risk_analyst", "macro_economist"],
        "agent_scores": {
          "value_investor": 0.5,
          "momentum_trader": 0.5,
          "risk_analyst": -0.5,
          "macro_economist": 0.0,
          "contrarian": -1.0
        }
      },
      "routing_decision": {
        "after_round": 1,
        "decision": "tiebreaker",
        "reason": "Hard conflict detected between contrarian and value_investor",
        "divergence_score": 0.6123,
        "previous_mode": "explore",
        "new_mode": "explore"
      }
    }
  ],
  "total_rounds_completed": 3,
  "conflicts": [ { "conflict_id": "conflict_1_contrarian_value_investor_abc123", "agent_a": "contrarian", "agent_b": "value_investor", "severity": "hard", "score_gap": 1.5, "resolved": false, "detected_at_round": 1 } ],
  "tiebreaker_outputs": [ { "...": "AnalystOutput from tiebreaker" } ],
  "committee_memo": {
    "final_recommendation": "buy",
    "conviction": 0.72,
    "vote_breakdown": { "buy": 3, "hold": 1, "sell": 1 },
    "executive_summary": "The committee reached a BUY consensus...",
    "key_thesis": "Apple's services flywheel and installed base create durable competitive advantages...",
    "bull_case": "Services revenue growing 14% YoY with 70%+ gross margins provides a durable earnings engine...",
    "bear_case": "Hardware saturation risk and China exposure remain significant headwinds...",
    "key_risks": ["China regulatory risk", "AI compute cost escalation", "Premium pricing fatigue"],
    "catalysts_to_watch": ["Vision Pro adoption curve", "India manufacturing ramp", "AI feature differentiation"],
    "debate_was_contentious": true,
    "dissenting_views": [ { "agent_type": "contrarian", "recommendation": "strong_sell", "conviction": 0.8, "key_argument": "Market consensus is too bullish on services margins..." } ],
    "synthesized_at": "2024-01-15T14:32:01.123Z"
  },
  "budget_summary": {
    "total_budget": 40000,
    "total_used": 12847,
    "remaining": 27153,
    "efficiency_pct": 32.1,
    "by_agent": { "value_investor": 2134, "momentum_trader": 2089, "..." : 0 }
  },
  "status": "complete",
  "error": null,
  "started_at": "2024-01-15T14:31:45.000Z",
  "completed_at": "2024-01-15T14:32:01.123Z",
  "duration_seconds": 16.123
}
```

### Error Responses

| Status | Condition |
|--------|-----------|
| 422 | Request validation failed (thesis too short, max_rounds out of range, etc.) |
| 500 | Debate execution failed (LLM unreachable, orchestrator error) |

---

## GET /api/v1/debates/{id}

Retrieve a completed debate by its ID.

### Request

```
GET /api/v1/debates/3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab
```

### Response — 200 OK

Returns the full `DebateTrace` object (same schema as POST response above).

### Response — 202 Accepted

Returned when the debate exists but is still running or failed.

```json
{
  "debate_id": "3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab",
  "status": "running",
  "message": "Debate is still in progress or failed.",
  "error": null
}
```

### Response — 404 Not Found

```json
{
  "detail": "Debate '3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab' not found."
}
```

---

## GET /api/v1/debates/{id}/stream

Server-Sent Events (SSE) stream. Yields events in real time as the debate progresses, or replays all stored events if the debate is already complete.

```
GET /api/v1/debates/3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab/stream
Accept: text/event-stream
```

Each event follows the SSE format:
```
id: <uuid>
event: <event_type>
data: <json_payload>
```

### Event Types

#### `debate_started`
Emitted once at the beginning of the debate.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:45.000Z",
  "data": {
    "debate_id": "3f2a1b4c-...",
    "thesis": "Apple Inc. is significantly undervalued...",
    "total_budget": 40000,
    "max_rounds": 3,
    "model": "ollama/llama3"
  }
}
```

#### `round_started`
Emitted at the start of each debate round.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:46.500Z",
  "data": {
    "round_number": 1,
    "mode": "explore",
    "allocations": {
      "value_investor": 7600,
      "momentum_trader": 7600,
      "risk_analyst": 7600,
      "macro_economist": 7600,
      "contrarian": 7600
    }
  }
}
```

#### `agent_output`
Emitted when each analyst agent completes its analysis for a round.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:48.200Z",
  "data": {
    "agent_id": "value_investor_r1",
    "agent_type": "value_investor",
    "round_number": 1,
    "recommendation": "buy",
    "conviction_score": 0.78,
    "numeric_score": 0.5,
    "thesis_agreement": "Strong agreement — Apple's moat justifies current valuation",
    "key_argument": "Trailing FCF yield of 3.5% is superior to 10yr treasury at current rates",
    "tokens_used": 712,
    "tokens_allocated": 7600
  }
}
```

#### `budget_update`
Emitted after each round's agents complete, showing cumulative token usage.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:50.100Z",
  "data": {
    "used": 3544,
    "remaining": 36456,
    "by_agent": {
      "value_investor": 712,
      "momentum_trader": 689,
      "risk_analyst": 744,
      "macro_economist": 701,
      "contrarian": 698
    }
  }
}
```

#### `divergence_scored`
Emitted after the divergence scorer runs on a completed round.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:50.500Z",
  "data": {
    "round_number": 1,
    "overall_score": 0.6123,
    "recommendation_variance": 0.58,
    "semantic_divergence": 0.61,
    "conflict_penalty": 0.25,
    "has_hard_conflicts": true,
    "mode_decision": "tiebreaker"
  }
}
```

#### `conflict_detected`
Emitted once per detected conflict pair (HARD or SOFT) in a round.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:50.550Z",
  "data": {
    "conflict_id": "conflict_1_contrarian_value_investor_abc123",
    "agent_a": "contrarian",
    "agent_b": "value_investor",
    "severity": "hard",
    "score_gap": 1.5,
    "description": "contrarian (strong_sell, score=-1.00) vs value_investor (buy, score=+0.50)"
  }
}
```

#### `tiebreaker_spawned`
Emitted when the tiebreaker agent is invoked to mediate hard conflicts.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:51.000Z",
  "data": {
    "round_number": 1,
    "conflict_count": 2,
    "conflicts": ["conflict_1_contrarian_value_investor_abc123"],
    "tiebreaker_budget": 3000
  }
}
```

#### `synthesis_started`
Emitted when synthesis begins (all debate rounds complete).

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:59.000Z",
  "data": {
    "total_rounds_completed": 3,
    "total_outputs": 15,
    "budget_remaining": 27153
  }
}
```

#### `synthesis_complete`
Emitted when the CommitteeMemo is produced.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:32:01.000Z",
  "data": {
    "final_recommendation": "buy",
    "conviction": 0.72,
    "vote_breakdown": { "buy": 3, "hold": 1, "sell": 1 },
    "debate_was_contentious": true,
    "executive_summary": "The committee reached a BUY consensus driven by Apple's services flywheel..."
  }
}
```

#### `error`
Emitted when an unrecoverable error occurs.

```json
{
  "id": "evt-uuid",
  "debate_id": "3f2a1b4c-...",
  "timestamp": "2024-01-15T14:31:52.000Z",
  "data": {
    "code": "STREAM_ERROR",
    "message": "Connection to Ollama timed out after 120 seconds"
  }
}
```

---

## GET /api/v1/debates

List recent debates (newest first). Returns summary objects, not full traces.

### Request

```
GET /api/v1/debates?limit=20
```

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `limit` | integer | 20 | Maximum number of debates to return |

### Response — 200 OK

```json
[
  {
    "debate_id": "3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab",
    "thesis": "Apple Inc. is significantly undervalued...",
    "status": "complete",
    "total_rounds_completed": 3,
    "final_recommendation": "buy",
    "started_at": "2024-01-15T14:31:45.000Z",
    "completed_at": "2024-01-15T14:32:01.123Z",
    "duration_seconds": 16.123,
    "tokens_used": 12847
  },
  {
    "debate_id": "pending-debate-id",
    "thesis": "Tesla will dominate global EV market by 2030",
    "status": "running",
    "total_rounds_completed": 1,
    "final_recommendation": null,
    "started_at": "2024-01-15T14:35:00.000Z",
    "completed_at": null,
    "duration_seconds": null,
    "tokens_used": 3200
  }
]
```

---

## GET /api/v1/health

Health check endpoint.

### Response — 200 OK

```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2024-01-15T14:32:01.123Z"
}
```

---

## Error Response Format

All error responses follow FastAPI's standard format:

```json
{
  "detail": "Human-readable error message"
}
```

For validation errors (422):

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "thesis"],
      "msg": "String should have at least 10 characters",
      "input": "Buy AAPL",
      "ctx": { "min_length": 10 }
    }
  ]
}
```

---

## Notes

- The `POST /debates` endpoint is **synchronous** — it blocks until the debate completes. For real-time updates, use the SSE streaming endpoint.
- To run a debate and watch it live: first `POST /debates` (which saves the debate_id), then `GET /debates/{id}/stream` from a second client, or use the streaming-first pattern via the React frontend.
- `debate_id` values are UUIDs by default. Custom IDs are accepted if they are unique strings.
- Token counts in responses are real LiteLLM-reported values, not estimates.
