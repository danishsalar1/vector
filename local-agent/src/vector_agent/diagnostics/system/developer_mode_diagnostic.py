"""Production diagnostic for iOS Developer Mode status.

Queries Developer Mode state via read-only 'idevicedevmodectl list'.
Strictly prohibits mutating actions (enable, arm, confirm, reveal).

Enforces:
- Every PASS requires real EvidenceRecord.
- Unsupported on iOS < 16.0 (returns UNSUPPORTED, not hardware FAIL).
- Level 1 RUNTIME_DETECTION.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.core.logging import get_logger
from vector_agent.devices.ios.bridge import IOSCommandStatus
from vector_agent.devices.ios.compatibility import IOSCompatibilityResolver, StrategyStatus
from vector_agent.devices.ios.version import AppleOSVersion
from vector_agent.diagnostics.definition import DiagnosticDefinition
from vector_agent.models.device import (
    AutomationLevel,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    Platform,
    VerificationLevel,
)

if TYPE_CHECKING:
    from vector_agent.devices.ios.bridge import IOSDeviceBridge

logger = get_logger(__name__)

DEVELOPER_MODE_DEFINITION = DiagnosticDefinition(
    diagnostic_id="developer_mode_state",
    name="Developer Mode Status",
    category="system",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.IOS}),
    required_capabilities=frozenset(),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=10.0,
    requires_probe=False,
    prerequisites=frozenset(),
)

_DEVMODE_DISCLAIMER = (
    "PASS confirms detection of Developer Mode configuration on device. "
    "Does not evaluate overall device security posture or hardware authenticity."
)


def _unpack_devmode(res: Any) -> tuple[IOSCommandStatus | None, str, str | None]:
    if hasattr(res, "status"):
        return res.status, res.state, res.message
    if isinstance(res, tuple):
        return None, res[0], res[1] if len(res) > 1 else None
    return None, "UNKNOWN", "Invalid result"


class IOSDeveloperModeDiagnostic:
    """Production diagnostic for iOS Developer Mode state."""

    def __init__(self, bridge: IOSDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return DEVELOPER_MODE_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        started_at = datetime.now(UTC)
        start_mono = time.monotonic()
        budget = (
            self.definition.timeout_seconds
            if timeout is None
            else min(timeout, self.definition.timeout_seconds)
        )

        def remaining() -> float:
            return float(budget - (time.monotonic() - start_mono))

        if remaining() <= 0:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Developer Mode query timed out before execution.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        # Query ProductVersion to evaluate compatibility dynamically via resolver
        try:
            raw_os_ver = None
            if remaining() > 0:
                raw_os_ver = self._bridge.get_metadata_field(
                    serial, "ProductVersion", timeout=min(2.0, remaining())
                )
        except (ADBCommandTimeoutError, TimeoutError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="ProductVersion query timed out during developer mode preflight.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except (FileNotFoundError, PermissionError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Host toolchain does not include 'ideviceinfo'.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        os_ver = AppleOSVersion.parse(raw_os_ver) if isinstance(raw_os_ver, str) else None

        resolver = IOSCompatibilityResolver(available_tools=self._bridge.get_available_tools())
        strategies = resolver.resolve_strategies(self.definition.diagnostic_id, os_ver)

        active_strategy = None
        active_status = None
        for strategy, status in strategies:
            if status == StrategyStatus.KNOWN_UNSUPPORTED:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.UNSUPPORTED,
                    automation_level=self.definition.automation_level,
                    summary=f"Developer Mode requires iOS 16.0+ (device reports iOS {raw_os_ver or 'below 16'}).",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            if status == StrategyStatus.KNOWN_BROKEN:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.UNSUPPORTED,
                    automation_level=self.definition.automation_level,
                    summary="Developer Mode strategy is known broken on this environment.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            if status == StrategyStatus.RESTRICTED:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.RESTRICTED,
                    automation_level=self.definition.automation_level,
                    summary="Developer Mode query is restricted or requires device authorization.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            if status == StrategyStatus.RUNTIME_UNAVAILABLE:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.UNSUPPORTED,
                    automation_level=self.definition.automation_level,
                    summary="Host toolchain does not include 'idevicedevmodectl'.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            if status == StrategyStatus.UNKNOWN:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.INCONCLUSIVE,
                    automation_level=self.definition.automation_level,
                    summary="Device OS version is unknown; Developer Mode cannot be safely queried.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            if status in (StrategyStatus.SUPPORTED, StrategyStatus.RUNTIME_PROBE_REQUIRED):
                active_strategy = strategy
                active_status = status
                break

        if active_strategy is None or active_status not in (
            StrategyStatus.SUPPORTED,
            StrategyStatus.RUNTIME_PROBE_REQUIRED,
        ):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="No supported Developer Mode strategy resolved for this device.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        try:
            res = self._bridge.get_developer_mode_state(serial, timeout=remaining())
            r_status, r_state, r_msg = _unpack_devmode(res)
            if r_status == IOSCommandStatus.TIMEOUT:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.ERROR,
                    automation_level=self.definition.automation_level,
                    summary="Developer Mode query timed out.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            if r_status == IOSCommandStatus.TOOL_UNAVAILABLE:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.UNSUPPORTED,
                    automation_level=self.definition.automation_level,
                    summary="Host toolchain does not include 'idevicedevmodectl'.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            status_str = r_state
            message = r_msg
        except (ADBCommandTimeoutError, TimeoutError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Developer Mode query timed out.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Developer mode tool unavailable: %s", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Host toolchain does not include 'idevicedevmodectl'.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except Exception as exc:
            logger.warning("Developer Mode query failed: %s", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary=f"Developer Mode query error ({type(exc).__name__}).",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        if status_str == "NOT_APPLICABLE":
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Developer Mode is not supported on this iOS version (requires iOS 16+).",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        if status_str == "UNKNOWN":
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=f"Developer Mode state could not be determined: {message}",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Build normalized EvidenceRecord for ENABLED or DISABLED
        # Note: normalized_value is None because Developer Mode is categorical state, NOT a trust score
        evidence = EvidenceRecord(
            evidence_id=uuid4(),
            diagnostic_id=self.definition.diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.LIBIMOBILEDEVICE,
            source_name="idevicedevmodectl list",
            collection_method="Apple Developer Mode lockdown query",
            timestamp=completed_at,
            raw_value=f"DeveloperMode={status_str}",
            normalized_value=None,
            unit=None,
            reliability=None,
            confidence=None,
            metadata={
                "strategy_id": getattr(active_strategy, "strategy_id", "devmodectl_list"),
                "compatibility_status": active_status.value if active_status else "SUPPORTED",
                "strategy_maturity": getattr(
                    getattr(active_strategy, "maturity", None), "value", "CODE_TESTED"
                ),
                "developer_mode_status": status_str,
                "disclaimer": _DEVMODE_DISCLAIMER,
                "platform": "IOS",
            },
        )

        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category=self.definition.category,
            status=DiagnosticStatus.PASS,
            automation_level=self.definition.automation_level,
            evidence=[evidence],
            summary=f"Developer Mode state confirmed as {status_str}. {_DEVMODE_DISCLAIMER}",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
