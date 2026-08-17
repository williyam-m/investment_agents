"""
Investment Committee Debate CLI
================================
Commands
--------
  debate       — run a full debate synchronously and print the committee memo
  serve        — start the FastAPI server via uvicorn
  list-debates — list recent debates from persisted JSON files
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import structlog
import typer

# ── Typer app ──────────────────────────────────────────────────────────────
app = typer.Typer(
    help="Investment Committee Debate System — AI-powered multi-agent debate.",
    add_completion=False,
)
logger = structlog.get_logger(__name__)


# ── debate ─────────────────────────────────────────────────────────────────

@app.command()
def debate(
    thesis: str = typer.Argument(..., help="Investment thesis to debate"),
    ticker: Optional[str] = typer.Option(None, "--ticker", "-t", help="Stock ticker symbol"),
    budget: int = typer.Option(40_000, "--budget", "-b", help="Total token budget"),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Maximum debate rounds (1-5)"),
    model: str = typer.Option(
        "ollama/llama2:7b",
        "--model",
        "-m",
        help="LiteLLM model string (e.g. 'ollama/llama2:7b', 'gpt-4o', 'anthropic/claude-3-5-sonnet')",
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write full JSON trace to this file"
    ),
    temperature: float = typer.Option(0.7, "--temperature", help="LLM sampling temperature"),
) -> None:
    """Run a full investment committee debate and print the committee memo."""
    from investment_agents.models.debate import DebateRequest, InvestmentContext, ModelConfig
    from investment_agents.orchestrator.graph import DebateOrchestrator

    typer.echo("\n🏛️  Investment Committee Debate")
    typer.echo(f"   Thesis : {thesis}")
    typer.echo(f"   Model  : {model}")
    typer.echo(f"   Budget : {budget:,} tokens  |  Max rounds: {rounds}")
    if ticker:
        typer.echo(f"   Ticker : {ticker}")
    typer.echo("")

    ctx = InvestmentContext(ticker=ticker) if ticker else InvestmentContext()
    req = DebateRequest(
        thesis=thesis,
        investment_context=ctx,
        total_budget=budget,
        max_rounds=rounds,
        model_config=ModelConfig(model=model, temperature=temperature),
    )

    orchestrator = DebateOrchestrator()

    async def _run():
        return await orchestrator.run(req)

    try:
        with typer.progressbar(length=100, label="Running debate") as progress:
            # We can't hook into async progress easily here, so just mark
            # it as running and complete when done.
            progress.update(10)
            trace = asyncio.run(_run())
            progress.update(90)
    except Exception as exc:
        typer.echo(f"\n❌  Debate failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # ── Print committee memo ───────────────────────────────────────────────
    memo = trace.committee_memo
    sep = "=" * 70

    if memo:
        typer.echo(f"\n{sep}")
        typer.echo("📋  INVESTMENT COMMITTEE MEMO")
        typer.echo(sep)
        typer.echo(f"\n  Debate ID  : {trace.debate_id}")
        typer.echo(f"  Status     : {trace.status}")
        typer.echo(f"  Rounds     : {trace.total_rounds_completed}")
        typer.echo(f"\n🎯  RECOMMENDATION: {memo.final_recommendation.value.upper()}")
        typer.echo(f"    Conviction  : {memo.conviction:.0%}")
        typer.echo(f"    Vote breakdown: {memo.vote_breakdown}")
        typer.echo(f"\n📝  EXECUTIVE SUMMARY:\n    {memo.executive_summary}")
        typer.echo(f"\n📌  KEY THESIS:\n    {memo.key_thesis}")
        typer.echo(f"\n🐂  BULL CASE:\n    {memo.bull_case}")
        typer.echo(f"\n🐻  BEAR CASE:\n    {memo.bear_case}")
        typer.echo(f"\n⚠️   KEY RISKS:")
        for risk in memo.key_risks:
            typer.echo(f"    • {risk}")
        if memo.catalysts_to_watch:
            typer.echo(f"\n🔭  CATALYSTS TO WATCH:")
            for cat in memo.catalysts_to_watch:
                typer.echo(f"    → {cat}")
        if memo.debate_was_contentious:
            typer.echo("\n⚡  This debate was contentious — committee was divided.")
        if memo.dissenting_views:
            typer.echo(f"\n🗣️   DISSENTING VIEWS ({len(memo.dissenting_views)}):")
            for dv in memo.dissenting_views:
                typer.echo(
                    f"    [{dv.agent_type.value}] {dv.recommendation.value}"
                    f" ({dv.conviction:.0%}) — {dv.key_argument[:80]}"
                )
        if trace.budget_summary:
            typer.echo(
                f"\n📊  Tokens used: {trace.budget_summary.total_used:,} / "
                f"{trace.budget_summary.total_allocated:,}"
            )
        typer.echo(f"\n{sep}\n")
    else:
        typer.echo(
            "\n⚠️  The debate completed but synthesis did not produce a committee memo.\n"
            f"    Status: {trace.status}"
        )
        if trace.error:
            typer.echo(f"    Error : {trace.error}")

    # ── Persist full trace ─────────────────────────────────────────────────
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(trace.model_dump_json(indent=2))
        typer.echo(f"✅  Full trace saved → {output_file}")


# ── serve ──────────────────────────────────────────────────────────────────

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable uvicorn auto-reload"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level"),
) -> None:
    """Start the FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("❌  uvicorn is not installed. Run: pip install uvicorn[standard]", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"🚀  Starting Investment Committee Debate API on {host}:{port}")
    uvicorn.run(
        "investment_agents.api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,  # reload incompatible with multiple workers
        log_level=log_level,
    )


# ── list-debates ───────────────────────────────────────────────────────────

@app.command(name="list-debates")
def list_debates(
    data_dir: Path = typer.Option(
        Path("data/debates"),
        "--dir",
        "-d",
        help="Directory containing persisted debate JSON files",
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of debates to show"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full thesis"),
) -> None:
    """List recent debates from the persisted data directory."""
    if not data_dir.exists():
        typer.echo(f"⚠️  Directory not found: {data_dir}")
        raise typer.Exit(code=0)

    files = sorted(data_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]

    if not files:
        typer.echo(f"No debate files found in {data_dir}.")
        raise typer.Exit(code=0)

    typer.echo(f"\n📂  Recent debates in {data_dir}  ({len(files)} shown)\n")
    typer.echo(f"{'ID':>10}  {'Status':10}  {'Rounds':6}  {'Thesis'}")
    typer.echo("-" * 80)

    for f in files:
        try:
            raw = json.loads(f.read_text())
            debate_id = raw.get("debate_id", "?")[:12]
            status = raw.get("status", "?")
            rounds = str(raw.get("total_rounds_completed", "?"))
            thesis = raw.get("thesis", "")
            thesis_display = thesis if verbose else thesis[:55]
            typer.echo(f"{debate_id:<12}  {status:<10}  {rounds:<6}  {thesis_display}")
        except Exception as exc:
            typer.echo(f"  {f.name}: could not parse — {exc}")

    typer.echo("")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
