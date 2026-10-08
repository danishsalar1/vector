"""Authorized local control API; production frontend integration is deferred."""

from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from vector_agent.models.probe_lifecycle import ProbeState
from vector_agent.probe.lifecycle import ProbeService
from vector_agent.security.local_api_auth import require_local_authorization


async def local_control(request: Request) -> None:
    await require_local_authorization(request)
    # Initial engineering client is in-process/native. Browser integration needs
    # its own reviewed bootstrap and is explicitly outside Phase 8B.
    if request.headers.getlist("origin") or request.url.hostname not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        raise HTTPException(403, "Local control required.")


router = APIRouter(prefix="/devices", tags=["probe"], dependencies=[Depends(local_control)])


class ProbeAction(StrEnum):
    DISCOVER = "discover"
    LAUNCH = "launch"
    CONNECT = "connect"
    HEARTBEAT = "heartbeat"
    STOP = "stop"


def perform(request: Request, device_id: str, action: ProbeAction | None) -> ProbeState:
    service: ProbeService = request.app.state.probe_service
    if action is None:
        try:
            return service.get_state(device_id)
        except ValueError:
            raise HTTPException(409, "Android device unavailable for Probe control.") from None
    try:
        connection = service.connection(device_id)
    except ValueError:
        raise HTTPException(409, "Android device unavailable for Probe control.") from None
    if action == ProbeAction.STOP:
        return connection.stop(stop_app=True)
    operations = {
        ProbeAction.DISCOVER: connection.discover,
        ProbeAction.LAUNCH: connection.launch,
        ProbeAction.CONNECT: connection.connect,
        ProbeAction.HEARTBEAT: connection.heartbeat,
    }
    return operations[action]()


@router.get("/{device_id}/probe", response_model=ProbeState)
async def get_probe_state(request: Request, device_id: str) -> ProbeState:
    return await run_in_threadpool(perform, request, device_id, None)


@router.post("/{device_id}/probe/{action}", response_model=ProbeState)
async def control_probe(request: Request, device_id: str, action: ProbeAction) -> ProbeState:
    return await run_in_threadpool(perform, request, device_id, action)
