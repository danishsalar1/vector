"""Scan management API endpoints.

POST /api/v1/scans                       - start a new scan
GET  /api/v1/scans/{scan_id}             - get scan status
GET  /api/v1/scans/{scan_id}/results     - get full results
GET  /api/v1/scans/{scan_id}/events      - SSE stream of scan events
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from vector_agent.models.device import ScanRequest, ScanState, ScanSummary

router = APIRouter(prefix="/scans", tags=["scans"])


class ScanStartResponse(BaseModel):
    scan_id: str
    state: ScanState


@router.post("", response_model=ScanStartResponse, status_code=201)
async def start_scan(request: ScanRequest) -> ScanStartResponse:
    """Initiate a new device scan.

    Returns a scan_id immediately.  Poll /scans/{scan_id} or use /events SSE.
    """
    # TODO(phase3): Implement scan orchestrator and state machine.
    from uuid import uuid4

    scan_id = str(uuid4())
    return ScanStartResponse(scan_id=scan_id, state=ScanState.IDLE)


@router.get("/{scan_id}", response_model=ScanSummary)
async def get_scan(scan_id: str) -> ScanSummary:
    """Return current state of a scan."""
    # TODO(phase3): Look up from scan store.
    raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")


@router.get("/{scan_id}/results", response_model=ScanSummary)
async def get_scan_results(scan_id: str) -> ScanSummary:
    """Return full results of a completed scan."""
    raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")


async def _scan_event_generator(scan_id: str) -> AsyncIterator[str]:
    """Server-Sent Events generator for scan progress.

    Streams scan state transitions until the scan completes or times out.
    """
    # TODO(phase3): Hook into real scan state machine.
    yield f'data: {{"event": "CONNECTED", "scan_id": "{scan_id}"}}\n\n'
    await asyncio.sleep(0.5)
    yield f'data: {{"event": "SCAN_NOT_FOUND", "scan_id": "{scan_id}"}}\n\n'


@router.get("/{scan_id}/events")
async def scan_events(scan_id: str) -> StreamingResponse:
    """Stream scan progress as Server-Sent Events.

    The client should use EventSource to consume this endpoint.
    """
    return StreamingResponse(
        _scan_event_generator(scan_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
