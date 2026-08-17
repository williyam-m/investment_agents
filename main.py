"""
Entry point — starts the Investment Committee Debate FastAPI server.

Usage
-----
    python main.py                   # default: 0.0.0.0:8000 with reload
    python main.py --host 127.0.0.1 --port 8080

Or via the CLI:
    python -m investment_agents.cli.main serve --port 8000
"""
from __future__ import annotations

import argparse

import uvicorn


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Investment Committee Debate API server"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--reload",
        action="store_true",
        default=True,
        help="Enable auto-reload on code changes (default: True)",
    )
    parser.add_argument(
        "--no-reload",
        action="store_false",
        dest="reload",
        help="Disable auto-reload",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Uvicorn log level (default: info)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    uvicorn.run(
        "investment_agents.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
