"""Health-check router."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
async def health() -> dict:
    """Return service health status."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "investment-committee-debate",
    }
