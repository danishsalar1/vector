"""Production diagnostic for iOS filesystem storage accounting.

Queries lockdown com.apple.disk_usage domain for storage capacity and utilization metrics.

Enforces:
- Every PASS requires real EvidenceRecord.
- Strict numeric validation and capacity coherence check.
- Never claims NAND hardware health or physical sector integrity.
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

STORAGE_ACCOUNTING_DEFINITION = DiagnosticDefinition(
    diagnostic_id="storage_accounting",
    name="Storage Accounting Telemetry",
    category="storage",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.IOS}),
    required_capabilities=frozenset(),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    prerequisites=frozenset(),
)

_STORAGE_DISCLAIMER = (
    "PASS confirms retrieval of filesystem storage accounting values from device lockdown service. "
    "Does not verify physical NAND health or raw flash block integrity."
)


def _unpack_telemetry(
    res: Any,
) -> tuple[IOSCommandStatus | None, dict[str, Any] | None, str | None]:
    if hasattr(res, "status"):
        return res.status, res.data, res.error
    if isinstance(res, tuple):
        return None, res[0], res[1] if len(res) > 1 else None
    return None, None, "Invalid result"


class IOSStorageAccountingDiagnostic:
    """Production diagnostic for iOS storage accounting."""

    def __init__(self, bridge: IOSDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return STORAGE_ACCOUNTING_DEFINITION

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
                summary="Storage accounting collection timed out before execution.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        # Query ProductVersion to evaluate strategy compatibility dynamically
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
                summary="ProductVersion query timed out during storage diagnostic preflight.",
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

        # R13: Enforce resolver semantics. If known unsupported or unknown version, do not execute subprocess.
        if strategies and any(
            status == StrategyStatus.KNOWN_UNSUPPORTED for _, status in strategies
        ):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Storage accounting is not supported on this iOS version.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        if strategies and all(
            status == StrategyStatus.RUNTIME_UNAVAILABLE for _, status in strategies
        ):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Host toolchain does not include required tools for storage accounting.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        if strategies and all(status == StrategyStatus.UNKNOWN for _, status in strategies):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Device OS version is unknown; storage accounting cannot be verified.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        active_strategy = None
        active_status = None
        for strategy, status in strategies:
            if status in (StrategyStatus.SUPPORTED, StrategyStatus.RUNTIME_PROBE_REQUIRED):
                active_strategy = strategy
                active_status = status
                break

        if not active_strategy:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="No compatible storage accounting strategy available.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        try:
            res = self._bridge.get_disk_usage_telemetry(serial, timeout=remaining())
            r_status, r_data, r_err = _unpack_telemetry(res)
            if r_status == IOSCommandStatus.TIMEOUT:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.ERROR,
                    automation_level=self.definition.automation_level,
                    summary="Storage accounting collection timed out.",
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
                    summary="Host toolchain does not include required tools for storage accounting.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_seconds=time.monotonic() - start_mono,
                )
            facts = r_data
            err = r_err
        except (ADBCommandTimeoutError, TimeoutError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Storage accounting collection timed out.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Storage accounting tool unavailable: %s", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Host toolchain does not include required tools for storage accounting.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except Exception as exc:
            logger.warning("Storage accounting query failed: %s", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary=f"Storage accounting query error ({type(exc).__name__}).",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        if not facts:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=f"Storage accounting telemetry unavailable or malformed ({err or 'no data'}).",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        total_disk = facts.get("total_disk_capacity_bytes")
        total_data = facts.get("total_data_capacity_bytes")
        tot_avail = facts.get("total_data_available_bytes")
        amt_avail = facts.get("amount_data_available_bytes")

        # Defining fact gate: must have at least one valid positive capacity metric
        has_defining_fact = (isinstance(total_disk, int) and total_disk > 0) or (
            isinstance(total_data, int) and total_data > 0
        )
        if not has_defining_fact:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Storage accounting telemetry contains no valid capacity metrics.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Contradiction checks on known impossible relationships
        if isinstance(total_disk, int) and isinstance(total_data, int) and total_data > total_disk:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Storage accounting contradiction: TotalDataCapacity exceeds TotalDiskCapacity.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        if isinstance(total_data, int) and isinstance(tot_avail, int) and tot_avail > total_data:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Storage accounting contradiction: TotalDataAvailable exceeds TotalDataCapacity.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        if isinstance(total_data, int) and isinstance(amt_avail, int) and amt_avail > total_data:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Storage accounting contradiction: AmountDataAvailable exceeds TotalDataCapacity.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Build normalized EvidenceRecord with distinct available storage keys (LOW 24)
        meta = {
            "strategy_id": active_strategy.strategy_id,
            "compatibility_status": active_status.value if active_status else "SUPPORTED",
            "strategy_maturity": active_strategy.maturity.value,
            "disclaimer": _STORAGE_DISCLAIMER,
            "platform": "IOS",
        }
        for k, v in facts.items():
            meta[k] = v

        raw_parts: list[str] = []
        if isinstance(total_disk, int):
            raw_parts.append(f"TotalDiskCapacity={total_disk} bytes")
        if isinstance(total_data, int):
            raw_parts.append(f"TotalDataCapacity={total_data} bytes")
        if isinstance(tot_avail, int):
            raw_parts.append(f"TotalDataAvailable={tot_avail} bytes")
        if isinstance(amt_avail, int):
            raw_parts.append(f"AmountDataAvailable={amt_avail} bytes")
        raw_str = ", ".join(raw_parts) if raw_parts else "Storage accounting values retrieved"

        evidence = EvidenceRecord(
            evidence_id=uuid4(),
            diagnostic_id=self.definition.diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.IDEVICEINFO,
            source_name="ideviceinfo -q com.apple.disk_usage",
            collection_method="libimobiledevice lockdown disk_usage domain",
            timestamp=completed_at,
            raw_value=raw_str,
            normalized_value=None,
            unit="bytes",
            reliability=None,
            confidence=None,
            metadata=meta,
        )

        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category=self.definition.category,
            status=DiagnosticStatus.PASS,
            automation_level=self.definition.automation_level,
            evidence=[evidence],
            summary=f"Storage accounting values retrieved. {_STORAGE_DISCLAIMER}",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
