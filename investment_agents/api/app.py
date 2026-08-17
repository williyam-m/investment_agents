from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from investment_agents.api.routes.debate import router as debate_router
from investment_agents.api.routes.health import router as health_router


def configure_logging() -> None:
    """Configure structlog for structured JSON logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup / shutdown logic."""
    configure_logging()
    log = structlog.get_logger(__name__)
    log.info("app.startup", title=app.title, version=app.version)
    yield
    log.info("app.shutdown")


# ── Application instance ───────────────────────────────────────────────────
app = FastAPI(
    title="Investment Committee Debate API",
    version="1.0.0",
    description=(
        "Multi-agent investment committee debate system. "
        "Orchestrates a panel of AI analysts (value investor, momentum trader, "
        "risk analyst, macro economist, contrarian) to produce structured "
        "investment recommendations via structured debate."
    ),
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(debate_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")


# ── Global exception handler ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log = structlog.get_logger(__name__)
    log.error(
        "unhandled_exception",
        path=str(request.url),
        method=request.method,
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "path": str(request.url.path),
        },
    )
