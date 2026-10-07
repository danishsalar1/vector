"""Session-scoped component coordinates; never hardware identifiers."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


SafeSlug = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=64, pattern=r"^[a-z]+(?:-[a-z0-9]+)*$"),
]
OpaqueId = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]
ComponentId = Annotated[
    str, StringConstraints(strict=True, min_length=36, max_length=36, pattern=r"^cmp-[0-9a-f]{32}$")
]
OpaqueDeviceId = Annotated[
    str, StringConstraints(strict=True, pattern=r"^(?:android|ios)-[0-9a-f]{12}$", max_length=20)
]
SessionEpoch = Annotated[int, Field(strict=True, ge=0, le=(1 << 63) - 1)]
ComponentOrdinal = Annotated[int, Field(strict=True, ge=0, le=65535)]


class ComponentKind(StrEnum):
    BATTERY = "BATTERY"
    DISPLAY = "DISPLAY"
    REAR_CAMERA = "REAR_CAMERA"
    FRONT_CAMERA = "FRONT_CAMERA"
    BIOMETRIC = "BIOMETRIC"
    LOGIC_BOARD = "LOGIC_BOARD"
    CHARGING_PORT = "CHARGING_PORT"
    SPEAKER = "SPEAKER"
    EARPIECE = "EARPIECE"
    MICROPHONE = "MICROPHONE"
    HAPTIC = "HAPTIC"
    SENSOR = "SENSOR"
    STORAGE = "STORAGE"
    MEMORY = "MEMORY"
    WIRELESS = "WIRELESS"
    NFC = "NFC"
    USB = "USB"
    OTHER = "OTHER"


class _ComponentCoordinates(DomainModel):
    device_id: OpaqueDeviceId
    device_session_epoch: SessionEpoch
    session_scope_id: OpaqueId
    """Desktop-owned UUIDv4, renewed across process/session lifetimes, never device supplied."""
    component_kind: ComponentKind
    component_role: SafeSlug
    ordinal: ComponentOrdinal = 0

    def _component_id(self) -> str:
        canonical = "|".join(
            (
                "vector-component-v1",
                self.device_id,
                self.session_scope_id,
                str(self.device_session_epoch),
                self.component_kind.value,
                self.component_role,
                str(self.ordinal),
            )
        )
        return "cmp-" + sha256(canonical.encode("ascii")).hexdigest()[:32]


class ComponentReference(_ComponentCoordinates):
    component_id: ComponentId

    @model_validator(mode="after")
    def check_identity(self) -> Self:
        if self.component_id != self._component_id():
            raise ValueError("Component identifier does not match session coordinates.")
        return self

    @classmethod
    def create(
        cls,
        *,
        device_id: str,
        device_session_epoch: int,
        session_scope_id: str,
        component_kind: ComponentKind,
        component_role: str,
        ordinal: int = 0,
    ) -> Self:
        coordinates = _ComponentCoordinates(
            device_id=device_id,
            device_session_epoch=device_session_epoch,
            session_scope_id=session_scope_id,
            component_kind=component_kind,
            component_role=component_role,
            ordinal=ordinal,
        )
        return cls(**coordinates.model_dump(), component_id=coordinates._component_id())
