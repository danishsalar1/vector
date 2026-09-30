"""Health and preflight check API endpoints.

GET /api/v1/health    - basic liveness check
GET /api/v1/system/preflight  - detailed environment check
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    mode: str


class PreflightItem(BaseModel):
    name: str
    status: str  # READY | NOT_FOUND | NOT_RUN
    detail: str | None = None


class PreflightResponse(BaseModel):
    overall: str
    items: list[PreflightItem]
    timestamp: datetime


def _check_tool(name: str, path: str) -> PreflightItem:
    """Check whether a command-line tool is available on PATH."""
    found = shutil.which(path)
    if found:
        return PreflightItem(name=name, status="READY", detail=str(found))
    return PreflightItem(name=name, status="NOT_FOUND", detail=f"'{path}' not found on PATH.")


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def get_health() -> HealthResponse:
    """Basic liveness check.  Returns 200 if the agent is running."""
    from vector_agent import __version__
    from vector_agent.core.config import get_settings

    settings = get_settings()
    return HealthResponse(
        status="OK",
        timestamp=datetime.now(UTC),
        version=__version__,
        mode="DEMO" if settings.demo_mode else "LIVE",
    )


@router.get("/system/preflight", response_model=PreflightResponse, tags=["system"])
async def get_preflight() -> PreflightResponse:
    """Detailed pre-scan environment check.

    Verifies that required external tools are available.
    Does NOT attempt to connect to a device (that is done in /devices).
    """
    from vector_agent.core.config import get_settings

    settings = get_settings()

    items: list[PreflightItem] = []

    # Python version
    py_ok = sys.version_info >= (3, 11)
    items.append(
        PreflightItem(
            name="Python",
            status="READY" if py_ok else "DEGRADED",
            detail=f"{sys.version}",
        )
    )

    # ADB
    items.append(_check_tool("ADB (Android Debug Bridge)", settings.adb_path))

    # iOS tools
    items.append(_check_tool("idevice_id (libimobiledevice)", settings.idevice_id_path))
    items.append(_check_tool("ideviceinfo (libimobiledevice)", settings.ideviceinfo_path))
    items.append(
        _check_tool("idevicediagnostics (libimobiledevice)", settings.idevicediagnostics_path)
    )

    # Agent self-check
    items.append(PreflightItem(name="VECTOR Agent", status="READY", detail="Agent is running."))

    overall = (
        "READY"
        if all(
            i.status == "READY"
            for i in items
            if i.name in ("Python", "VECTOR Agent")  # Only mandatory items affect overall
        )
        else "DEGRADED"
    )

    return PreflightResponse(
        overall=overall,
        items=items,
        timestamp=datetime.now(UTC),
    )
