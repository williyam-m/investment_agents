# Investment Committee Debate System — Documentation

## Contents

1. [Quickstart](quickstart.md) — Get running in 5 minutes
2. [Architecture](architecture.md) — System design and data flow
3. [Agents](agents.md) — Agent personas and extension guide
4. [Budget System](budget_system.md) — Token budget and routing logic
5. [API Reference](api_reference.md) — REST and SSE endpoints

## Project Structure

```
investment_agents/
├── agents/          # 7 analyst agents + base class
├── analysis/        # Divergence scoring, conflict resolution
├── api/             # FastAPI app + routes
├── budget/          # Token tracker, allocator, policy
├── cli/             # Typer CLI
├── config/          # Pydantic-settings
├── llm/             # LiteLLM client
├── models/          # Pydantic data models
├── orchestrator/    # LangGraph graph, nodes, edges
└── storage/         # In-memory + JSON persistence
tests/               # 24 unit tests
docs/                # This documentation
frontend/            # React dashboard
```
