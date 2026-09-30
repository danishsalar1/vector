"""Device discovery and listing API endpoints.

GET /api/v1/devices            - list currently visible devices
GET /api/v1/devices/{id}       - get specific device
GET /api/v1/devices/{id}/capabilities  - get capability profile
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vector_agent.models.device import ConnectedDevice, DeviceCapabilityProfile

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceListResponse(BaseModel):
    devices: list[ConnectedDevice]
    count: int


@router.get("", response_model=DeviceListResponse)
async def list_devices() -> DeviceListResponse:
    """Discover and return currently connected devices.

    In Phase 0 this returns an empty list.
    Device discovery is implemented in Phase 2.
    """
    # TODO(phase2): Implement real ADB + iOS discovery.
    return DeviceListResponse(devices=[], count=0)


@router.get("/{device_id}", response_model=ConnectedDevice)
async def get_device(device_id: str) -> ConnectedDevice:
    """Return details for a specific connected device."""
    # TODO(phase2): Look up device from registry.
    raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")


@router.get("/{device_id}/capabilities", response_model=DeviceCapabilityProfile)
async def get_device_capabilities(device_id: str) -> DeviceCapabilityProfile:
    """Return the capability profile for a specific device."""
    # TODO(phase2): Return real capability profile.
    raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
