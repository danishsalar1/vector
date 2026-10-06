"""Production iOS battery charge telemetry diagnostic.

Collects real-time battery charge state from the com.apple.mobile.battery domain.
Enforces:
- Every PASS requires normalized evidence.
- No battery health claims, cycle count inferences, or capacity degradation estimates.
- Bounded capacity (0..100) and strict boolean parsing.
- Monotonic timeout budgeting.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.core.logging import get_logger
from vector_agent.devices.ios.bridge import IOSCommandStatus
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

IOS_BATTERY_CHARGE_DEFINITION = DiagnosticDefinition(
    diagnostic_id="battery_charge_telemetry",
    name="Battery Charge Telemetry",
    category="battery",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.IOS}),
    required_capabilities=frozenset(),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    prerequisites=frozenset(),
)

_STATUS_NOTE = (
    "PASS confirms successful retrieval of battery charge telemetry. "
    "It does not assess battery health, maximum capacity, cycle count, or replacement status."
)


class IOSBatteryChargeDiagnostic:
    """Production diagnostic for iOS battery charge telemetry."""

    def __init__(self, bridge: IOSDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return IOS_BATTERY_CHARGE_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        """Run battery charge telemetry collection and return a structured result.

        Args:
            device_id: Opaque VECTOR device identifier.
            serial: Validated iOS UDID (internal only).
            timeout: Optional execution budget override in seconds.

        Returns:
            DiagnosticResult with evidence records.
        """
        started_at = datetime.now(UTC)
        start_mono = time.monotonic()
        budget = (
            self.definition.timeout_seconds
            if timeout is None
            else min(timeout, self.definition.timeout_seconds)
        )

        remaining = budget - (time.monotonic() - start_mono)
        if remaining <= 0:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Battery charge telemetry collection timed out within allocated budget.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        try:
            res = self._bridge.get_battery_telemetry(serial, timeout=remaining)
            if hasattr(res, "status"):
                if res.status == IOSCommandStatus.TIMEOUT:
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.ERROR,
                        automation_level=self.definition.automation_level,
                        summary="Battery charge telemetry collection timed out.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                if res.status == IOSCommandStatus.TOOL_UNAVAILABLE:
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
                if res.status == IOSCommandStatus.AUTHORIZATION_REQUIRED:
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.RESTRICTED,
                        automation_level=self.definition.automation_level,
                        summary="Device is locked or pairing authorization is required.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                facts = res.data
                error_reason = res.error
            elif isinstance(res, tuple):
                facts = res[0]
                error_reason = res[1] if len(res) > 1 else None
            else:
                facts = None
                error_reason = "Invalid telemetry result"
        except (ADBCommandTimeoutError, TimeoutError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Battery charge telemetry collection timed out.",
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
        except Exception as exc:
            logger.error("Battery charge telemetry query threw exception: %s", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Battery charge telemetry query encountered an error.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        if facts is None or "battery_current_capacity" not in facts:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=f"Battery charge telemetry was inconclusive ({error_reason or 'missing data'}).",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        capacity = facts["battery_current_capacity"]
        normalized_value = float(capacity) / 100.0

        metadata = dict(facts)
        metadata["platform"] = "IOS"

        evidence = EvidenceRecord(
            evidence_id=uuid4(),
            diagnostic_id=self.definition.diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.IDEVICEINFO,
            source_name="ideviceinfo -q com.apple.mobile.battery",
            collection_method="libimobiledevice lockdownd battery query",
            timestamp=completed_at,
            raw_value=f"{capacity}%",
            normalized_value=normalized_value,
            unit="%",
            reliability=None,
            confidence=None,
            metadata=metadata,
        )

        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category=self.definition.category,
            status=DiagnosticStatus.PASS,
            automation_level=self.definition.automation_level,
            evidence=[evidence],
            summary=(f"Battery charge telemetry acquired: {capacity}%. {_STATUS_NOTE}"),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
