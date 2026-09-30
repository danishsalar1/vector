"""System environment preflight check API endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from vector_agent.models.preflight import PreflightResponse
from vector_agent.services.preflight import SystemPreflightService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/preflight", response_model=PreflightResponse)
async def get_preflight() -> PreflightResponse:
    """Evaluates local host operating system, runtime, and external tooling readiness.

    Verifies laptop platform, Python environment, local agent service, and external
    executable availability (ADB, libimobiledevice). Performs no device discovery.
    """
    service = SystemPreflightService()
    return service.run_preflight()
