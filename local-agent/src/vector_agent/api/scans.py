"""Scan management API endpoints.

POST /api/v1/scans/plan                   - generate scan plan without executing
POST /api/v1/scans                        - start a new scan
GET  /api/v1/scans/{scan_id}             - get scan summary / status
GET  /api/v1/scans/{scan_id}/results     - get full results
GET  /api/v1/scans/{scan_id}/events      - get event log (JSON polling)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from vector_agent.core.logging import get_logger
from vector_agent.devices.session import (
    DeviceNotConnectedError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
)
from vector_agent.models.device import ScanLifecycleState, ScanRequest, ScanSummary
from vector_agent.scan.events import DiagnosticEvent
from vector_agent.scan.planner import (
    InvalidScanRequestError,
    ScanPlan,
    UnknownDiagnosticError,
)
from vector_agent.scan.service import DeviceScanActiveError, scan_service

logger = get_logger(__name__)

router = APIRouter(prefix="/scans", tags=["scans"])


class ScanStartResponse(BaseModel):
    """Response returned when initiating a scan."""

    scan_id: str
    state: ScanLifecycleState
    plan: ScanPlan | None = None


class ScanEventsResponse(BaseModel):
    """Response returned when polling scan events."""

    scan_id: str
    events: list[DiagnosticEvent]


@router.post("/plan", response_model=ScanPlan)
async def generate_plan(request: ScanRequest) -> ScanPlan:
    """Generate an immutable ScanPlan for the given request without executing it."""
    try:
        return await run_in_threadpool(scan_service.create_plan, request)
    except DeviceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeviceUnauthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DeviceNotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (UnknownDiagnosticError, InvalidScanRequestError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Scan planning failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Scan planning failed.") from None


@router.post("", response_model=ScanStartResponse, status_code=201)
async def start_scan(
    request: ScanRequest,
    sync: bool = Query(
        default=False,
        description="If True, wait for all planned diagnostics to complete before returning.",
    ),
) -> ScanStartResponse:
    """Initiate a new device scan.

    Returns the scan_id and initial state. Execution occurs asynchronously
    unless sync=True is specified.
    """
    try:
        session = await run_in_threadpool(
            scan_service.start_scan,
            request,
            run_async=not sync,
        )
        return ScanStartResponse(
            scan_id=session.scan_id,
            state=session.state,
            plan=session.plan,
        )
    except DeviceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeviceUnauthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DeviceNotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (UnknownDiagnosticError, InvalidScanRequestError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DeviceScanActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Scan start failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Scan initiation failed.") from None


@router.get("/{scan_id}", response_model=ScanSummary)
async def get_scan(scan_id: str) -> ScanSummary:
    """Return the current lifecycle state and summary of a scan."""
    session = scan_service.get_scan(scan_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")
    return session.to_summary()


@router.get("/{scan_id}/results", response_model=ScanSummary)
async def get_scan_results(scan_id: str) -> ScanSummary:
    """Return full results of a scan."""
    session = scan_service.get_scan(scan_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")
    return session.to_summary()


@router.get("/{scan_id}/events", response_model=ScanEventsResponse)
async def get_scan_events(scan_id: str) -> ScanEventsResponse:
    """Retrieve diagnostic events for a scan via JSON polling."""
    session = scan_service.get_scan(scan_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")

    events = scan_service.get_events(scan_id) or []
    return ScanEventsResponse(
        scan_id=scan_id,
        events=events,
    )
