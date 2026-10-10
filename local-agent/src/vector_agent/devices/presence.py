"""Reliable physical-presence verification for the device bound to a scan (Stage 2B-3).

Discovery (``GET /devices``) is the only other thing that notices an unplugged phone, and it
only runs when a client asks. This module lets the scan backend verify the bound device itself:

* One targeted, bounded probe of THE bound device through its platform's supported discovery
  tool (``adb devices -l`` / ``idevice_id -l``); never a full reconcile, never other devices.
* A loss is CONFIRMED only after consecutive trustworthy observations agree. A timeout, a
  tool error, an unrecognised answer, a daemon restart or a flapping answer is UNCERTAIN and
  changes nothing: uncertainty is never promoted to "disconnected".
* A confirmed loss is applied through ``DeviceSessionManager.mark_device_lost``, bound to the
  exact session object, epoch and serial that were observed, so a scan can neither be
  transferred to another phone nor act on a replaced session.
* Probes are made only when a scan asks (before/after diagnostics), are rate limited, and run
  outside every lock. No background thread exists.

Raw serials stay inside the provider call and are never logged or placed in results.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AdbDeviceState, AndroidDeviceBridge
from vector_agent.devices.ios.bridge import IOSDeviceBridge, IOSToolchainStatus
from vector_agent.devices.session import DeviceSession, DeviceSessionManager
from vector_agent.models.device import ConnectionState, Platform

logger = get_logger(__name__)

DEFAULT_PROBE_TIMEOUT_SECONDS = 3.0
MAX_PROBE_TIMEOUT_SECONDS = 10.0
_MAX_TRACKED_DEVICES = 64


class PresenceStatus(StrEnum):
    PRESENT = "PRESENT"  # listed and usable
    ABSENT = "ABSENT"  # trustworthy listing without the device
    NOT_USABLE = "NOT_USABLE"  # listed, but offline/unauthorized (``state`` says which)
    UNCERTAIN = "UNCERTAIN"  # no trustworthy answer: timeout, tool error, unknown output


@dataclass(frozen=True)
class PresenceObservation:
    status: PresenceStatus
    state: ConnectionState | None = None


class PresenceVerdict(StrEnum):
    PRESENT = "PRESENT"
    LOST = "LOST"  # confirmed; the session manager now records it
    UNCERTAIN = "UNCERTAIN"  # nothing was changed


class DevicePresenceProvider(Protocol):
    """Platform adapter. Must be bounded by ``timeout`` and must not raise for tool failures."""

    def observe(self, serial: str, timeout: float) -> PresenceObservation: ...


class AdbPresenceProvider:
    """Android presence through one trustworthy ``adb devices -l`` snapshot."""

    def __init__(self, bridge_factory: Callable[[], AndroidDeviceBridge]) -> None:
        self._bridge_factory = bridge_factory

    def observe(self, serial: str, timeout: float) -> PresenceObservation:
        entries = self._bridge_factory().list_attached_devices(timeout=timeout)
        if entries is None:
            return PresenceObservation(PresenceStatus.UNCERTAIN)
        for entry in entries:
            if entry.serial != serial:
                continue
            if entry.state == AdbDeviceState.DEVICE:
                return PresenceObservation(PresenceStatus.PRESENT)
            state = (
                ConnectionState.UNAUTHORIZED
                if entry.state == AdbDeviceState.UNAUTHORIZED
                else ConnectionState.OFFLINE
            )
            return PresenceObservation(PresenceStatus.NOT_USABLE, state)
        return PresenceObservation(PresenceStatus.ABSENT)


class IosPresenceProvider:
    """iOS presence through ``idevice_id -l`` (listed by the bound UDID or not)."""

    def __init__(self, bridge_factory: Callable[[], IOSDeviceBridge]) -> None:
        self._bridge_factory = bridge_factory

    def observe(self, serial: str, timeout: float) -> PresenceObservation:
        result = self._bridge_factory().discover_devices_result(timeout=timeout)
        if result.status != IOSToolchainStatus.AVAILABLE:
            return PresenceObservation(PresenceStatus.UNCERTAIN)
        if serial in result.udids:
            return PresenceObservation(PresenceStatus.PRESENT)
        return PresenceObservation(PresenceStatus.ABSENT)


class DevicePresenceMonitor:
    """Verifies, on demand, that a scan's bound device is still physically attached."""

    def __init__(
        self,
        manager: DeviceSessionManager,
        providers: Mapping[Platform, DevicePresenceProvider],
        *,
        probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
        confirmations: int = 2,
        confirm_interval_seconds: float = 0.3,
        present_cache_seconds: float = 0.5,
        uncertain_cooldown_seconds: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < probe_timeout_seconds <= MAX_PROBE_TIMEOUT_SECONDS:
            raise ValueError("probe_timeout_seconds out of range.")
        if not 2 <= confirmations <= 5:
            raise ValueError("A loss needs at least two agreeing observations.")
        self._manager = manager
        self._providers = dict(providers)
        self._timeout = probe_timeout_seconds
        self._confirmations = confirmations
        self._interval = confirm_interval_seconds
        self._present_cache = present_cache_seconds
        self._cooldown = uncertain_cooldown_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        # device_id -> (epoch, monotonic time, verdict) of the last PRESENT / UNCERTAIN answer.
        self._recent: dict[str, tuple[int, float, PresenceVerdict]] = {}

    def verify(
        self, device_id: str, expected_session: DeviceSession, expected_epoch: int
    ) -> PresenceVerdict:
        """Check the physical presence of the device a scan is bound to.

        Never raises for tool failures. ``LOST`` is returned only after the loss has been
        confirmed AND recorded in the session manager (or the manager already shows that this
        session is gone or changed). Everything else leaves the manager untouched.
        """
        target = self._manager.bound_device_target(
            device_id, expected_session=expected_session, expected_epoch=expected_epoch
        )
        if target is None:
            return PresenceVerdict.LOST  # the manager already knows it changed or went away
        platform, serial = target
        provider = self._providers.get(platform)
        if provider is None or not serial:
            return PresenceVerdict.UNCERTAIN  # no supported mechanism for this device

        cached = self._cached(device_id, expected_epoch)
        if cached is not None:
            return cached

        first = self._observe(provider, serial)
        if first.status == PresenceStatus.PRESENT:
            return self._remember(device_id, expected_epoch, PresenceVerdict.PRESENT)
        if first.status == PresenceStatus.UNCERTAIN:
            return self._remember(device_id, expected_epoch, PresenceVerdict.UNCERTAIN)

        # A non-present answer needs independent agreeing confirmations before it is believed.
        for _ in range(self._confirmations - 1):
            self._sleep(self._interval)
            again = self._observe(provider, serial)
            if again != first:
                # Present again, unknown, or a different state: not sufficient evidence.
                return self._remember(device_id, expected_epoch, PresenceVerdict.UNCERTAIN)

        new_state = (
            first.state if first.status == PresenceStatus.NOT_USABLE else ConnectionState.OFFLINE
        )
        assert new_state is not None
        applied = self._manager.mark_device_lost(
            device_id,
            expected_session=expected_session,
            expected_epoch=expected_epoch,
            expected_serial=serial,
            new_state=new_state,
        )
        with self._lock:
            self._recent.pop(device_id, None)
        logger.warning(
            "Device %s presence loss confirmed (%s)%s",
            device_id,
            first.status.value,
            "" if applied else "; session had already changed",
        )
        return PresenceVerdict.LOST

    def _observe(self, provider: DevicePresenceProvider, serial: str) -> PresenceObservation:
        try:
            return provider.observe(serial, self._timeout)
        except Exception as exc:  # fail-uncertain backstop: only the type is logged
            logger.warning("Presence provider failed (%s)", type(exc).__name__)
            return PresenceObservation(PresenceStatus.UNCERTAIN)

    def _cached(self, device_id: str, epoch: int) -> PresenceVerdict | None:
        now = self._monotonic()
        with self._lock:
            entry = self._recent.get(device_id)
        if entry is None or entry[0] != epoch:
            return None
        window = self._present_cache if entry[2] == PresenceVerdict.PRESENT else self._cooldown
        return entry[2] if now - entry[1] < window else None

    def _remember(self, device_id: str, epoch: int, verdict: PresenceVerdict) -> PresenceVerdict:
        with self._lock:
            self._recent.pop(device_id, None)
            self._recent[device_id] = (epoch, self._monotonic(), verdict)
            while len(self._recent) > _MAX_TRACKED_DEVICES:
                self._recent.pop(next(iter(self._recent)))
        return verdict
