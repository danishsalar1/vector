"""Health check API endpoint.

GET /api/v1/health - basic liveness check
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    mode: str


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Basic liveness check. Returns 200 if the agent is running."""
    from vector_agent import __version__
    from vector_agent.core.config import get_settings

    settings = get_settings()
    return HealthResponse(
        status="OK",
        timestamp=datetime.now(UTC),
        version=__version__,
        mode="DEMO" if settings.demo_mode else "LIVE",
    )
