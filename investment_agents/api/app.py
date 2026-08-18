from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from investment_agents.api.routes.debate import router as debate_router
from investment_agents.api.routes.health import router as health_router
from investment_agents.config.settings import get_settings
from investment_agents.orchestrator.graph import DebateOrchestrator
from investment_agents.storage.repository import DebateRepository


def configure_logging() -> None:
    """Configure structlog for structured JSON logging."""
    settings = get_settings()
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
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup / shutdown logic."""
    configure_logging()
    log = structlog.get_logger(__name__)
    app.state.repo = DebateRepository()
    app.state.orchestrator = DebateOrchestrator()
    log.info("app.startup", title=app.title, version=app.version)
    yield
    log.info("app.shutdown")


# ── Application instance ───────────────────────────────────────────────────
app = FastAPI(  # noqa: E501
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware ─────────────────────────────────────────────────────────────
# allow_origins=["*"] + allow_credentials=True is a CORS spec violation.
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,  # use configured origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
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
            "error": "InternalServerError",
            "detail": "An unexpected error occurred. Please try again later.",
            "path": str(request.url.path),
        },
    )
