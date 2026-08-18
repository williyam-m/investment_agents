# Quickstart — Investment Committee Debate System

Get a full AI investment committee debate running in 5 minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | `python3 --version` to check |
| Ollama | Latest | Download from [ollama.ai](https://ollama.ai) |
| Node.js | 18+ (optional) | Only needed for the React frontend |
| Git | Any | For cloning |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-org/investment_agents.git
cd investment_agents
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install the package in editable mode

```bash
pip install -e .
```

### 5. Pull an Ollama model

The default model is `llama2:7b`. For better results or larger context, use `mistral`:

```bash
ollama pull llama2:7b
# or for a stronger reasoning model:
ollama pull mistral
```

### 6. Configure environment

```bash
cp .env.example .env
```

Edit `.env` to set your preferred defaults:

```bash
# .env
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=ollama/llama2:7b
DEFAULT_BUDGET=40000
DEFAULT_MAX_ROUNDS=3
LOG_LEVEL=INFO

# Optional: cloud provider keys
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

---

## Running Your First Debate — CLI

Make sure Ollama is running (`ollama serve` in a separate terminal if not already running).

### Basic debate

```bash
python -m investment_agents.cli.main debate "Apple Inc. is significantly undervalued at current prices and presents a compelling buy opportunity"
```

### With a ticker and custom budget

```bash
python -m investment_agents.cli.main debate \
  "NVIDIA's AI GPU monopoly will persist for at least 5 more years" \
  --ticker NVDA \
  --budget 30000 \
  --rounds 2 \
  --model ollama/llama2:7b
```

### Save the full trace to JSON

```bash
python -m investment_agents.cli.main debate \
  "Tesla will capture 30% of the global EV market by 2030" \
  --ticker TSLA \
  --output traces/tesla_debate.json
```

### Expected Output

```
🏛️  Investment Committee Debate
   Thesis : Tesla will capture 30% of the global EV market by 2030
   Model  : ollama/llama2:7b
   Budget : 40,000 tokens  |  Max rounds: 3

Running debate  [####################]  100%

======================================================================
📋  INVESTMENT COMMITTEE MEMO
======================================================================

  Debate ID  : 3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab
  Status     : complete
  Rounds     : 3

🎯  RECOMMENDATION: HOLD
    Conviction  : 58%
    Vote breakdown: {'buy': 2, 'hold': 2, 'sell': 1}

📝  EXECUTIVE SUMMARY:
    The committee was divided on Tesla's market share prospects...

🐂  BULL CASE:
    Supercharger network moat and software-defined vehicle advantage...

🐻  BEAR CASE:
    BYD's cost advantage in key markets undermines market share thesis...

⚠️   KEY RISKS:
    • China competition intensifying faster than expected
    • Elon Musk distraction premium
    • EV demand slowdown in key markets

⚡  This debate was contentious — committee was divided.

📊  Tokens used: 13,214 / 40,000
======================================================================
```

---

## Running via API

### Start the API server

```bash
python -m investment_agents.cli.main serve --port 8000
# or directly:
uvicorn investment_agents.api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Submit a debate via curl

```bash
curl -X POST http://localhost:8000/api/v1/debates \
  -H "Content-Type: application/json" \
  -d '{
    "thesis": "Amazon Web Services will maintain its cloud market share leadership through 2030",
    "investment_context": {
      "ticker": "AMZN",
      "current_price": 185.50,
      "supporting_data": { "aws_revenue_growth_yoy": 0.17, "cloud_market_share_pct": 31 }
    },
    "total_budget": 25000,
    "max_rounds": 2,
    "model_config": { "model": "ollama/llama2:7b", "temperature": 0.7 }
  }'
```

### Get debate status

```bash
# Replace with your debate_id from the POST response
curl http://localhost:8000/api/v1/debates/3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab
```

### Stream debate events via SSE

```bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8000/api/v1/debates/3f2a1b4c-8d7e-4f9a-b2c1-1234567890ab/stream
```

### List recent debates

```bash
curl http://localhost:8000/api/v1/debates?limit=10
```

---

## Running the Frontend

The React frontend provides a real-time debate dashboard with live SSE streaming.

### Setup

```bash
cd frontend
npm install
```

### Configure frontend environment

```bash
cp .env.example .env.local
# Edit .env.local:
# VITE_API_BASE_URL=http://localhost:8000
```

### Start development server

```bash
npm run dev
# Opens at http://localhost:5173
```

### What you'll see

- **Thesis input form** — paste your investment thesis and configure the debate
- **Live agent cards** — each analyst's output appears as it completes
- **Divergence chart** — real-time score plot showing agreement/disagreement over rounds
- **Budget meter** — live token consumption by agent
- **Committee Memo** — displayed prominently when synthesis completes

---

## Troubleshooting

### Ollama not running

```
Error: Connection refused to http://localhost:11434
```

**Fix**: Start Ollama: `ollama serve` (in a separate terminal, or run as a background service).

**Verify**: `curl http://localhost:11434/api/tags` should return a list of installed models.

---

### Model not found

```
Error: model 'ollama/llama2:7b' not found
```

**Fix**: Pull the model first:
```bash
ollama pull llama2:7b
```

**Check installed models**:
```bash
ollama list
```

Then use the exact model name in your request: `ollama/llama2:7b`, `ollama/llama2:7b`, `ollama/mistral`, etc.

---

### Budget too small — debate ends after round 1

If you see only 1 round completed with `"reason": "Budget nearly exhausted"`, your budget is too small for the model you're using.

**Fix**: Increase the budget:
```bash
python -m investment_agents.cli.main debate "..." --budget 80000
```

Or use a smaller `max_tokens_per_call` in `model_config` (default 1000). For local Llama models, 500 often suffices.

---

### JSON parse errors / fallback outputs

If agents return HOLD with `"key_argument": "Analysis unavailable — fallback response"`, the LLM is not returning valid JSON.

**Fix options**:
1. Use a more capable model: `ollama pull llama2:7b` or `ollama pull mistral`
2. Lower temperature: `--temperature 0.3`
3. Check Ollama logs: `journalctl -u ollama` or terminal output

---

### Pydantic validation error on startup

```
ValidationError: 1 validation error for Settings
```

**Fix**: Ensure your `.env` file exists and has valid values. Copy from `.env.example`:
```bash
cp .env.example .env
```

---

### Port already in use

```
Error: [Errno 48] Address already in use
```

**Fix**: Kill the process on port 8000 or use a different port:
```bash
python -m investment_agents.cli.main serve --port 8001
```

---

### ImportError: sentence_transformers

This is a **warning**, not a fatal error. The system falls back to random divergence scoring (0.4–0.6 range) automatically.

To enable semantic divergence scoring:
```bash
pip install sentence-transformers
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Run debate (CLI) | `python -m investment_agents.cli.main debate "..."` |
| Start API server | `python -m investment_agents.cli.main serve` |
| List saved debates | `python -m investment_agents.cli.main list-debates` |
| Run tests | `pytest` |
| Check Ollama models | `ollama list` |
| Pull llama2:7b | `ollama pull llama2:7b` |
| API health check | `curl http://localhost:8000/api/v1/health` |
