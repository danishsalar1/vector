"""Public control-plane state. No diagnostic or provenance verdicts."""

from enum import StrEnum

# ruff: noqa: TID252
from .probe import ProbeCapabilityDescriptor, ProbeModel


class ProbeAvailability(StrEnum):
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLED_UNVERIFIED = "INSTALLED_UNVERIFIED"
    INSTALLED_COMPATIBLE = "INSTALLED_COMPATIBLE"
    INSTALLED_INCOMPATIBLE = "INSTALLED_INCOMPATIBLE"
    UNTRUSTED = "UNTRUSTED"
    DISABLED = "DISABLED"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    CONSENT_DENIED = "CONSENT_DENIED"
    RESTRICTED = "RESTRICTED"
    ERROR = "ERROR"


class ProbeReason(StrEnum):
    NONE = "NONE"
    MANUAL_INSTALL_REQUIRED = "MANUAL_INSTALL_REQUIRED"
    TRUST_CONFIGURATION_REQUIRED = "TRUST_CONFIGURATION_REQUIRED"
    ARTIFACT_NOT_ALLOWLISTED = "ARTIFACT_NOT_ALLOWLISTED"
    PACKAGE_DISABLED = "PACKAGE_DISABLED"
    VERSION_NOT_SUPPORTED = "VERSION_NOT_SUPPORTED"
    APPROVE_ON_DEVICE = "APPROVE_ON_DEVICE"
    USER_DECLINED = "USER_DECLINED"
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    TOOL_ERROR = "TOOL_ERROR"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    CANCELLED = "CANCELLED"
    STOPPED = "STOPPED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_CHANGED = "SESSION_CHANGED"
    DEVELOPMENT_ACCESS_REQUIRED = "DEVELOPMENT_ACCESS_REQUIRED"
    PROBE_NOT_STARTED = "PROBE_NOT_STARTED"


class ProbeState(ProbeModel):
    availability: ProbeAvailability
    reason: ProbeReason = ProbeReason.NONE
    installed: bool | None = None
    identity_trusted: bool = False
    protocol_compatible: bool | None = None
    consent_required: bool = False
    transport_connected: bool = False
    application_version: str | None = None
    protocol_version: int | None = None
    capabilities: tuple[ProbeCapabilityDescriptor, ...] = ()
