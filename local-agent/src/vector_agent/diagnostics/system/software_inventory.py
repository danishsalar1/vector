"""Production software inventory diagnostic for iOS.

Queries allowlisted device metadata (ProductType, ProductVersion, BuildVersion, DeviceClass)
from trusted iOS lockdownd services.
Enforces:
- Every PASS requires normalized evidence.
- No raw UDID, serial number, device name, or account information.
- PASS semantics confirm successful software/class inventory retrieval;
  never implies hardware health, genuine status, or unmodified OS.
- Monotonic timeout budgeting.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.core.logging import get_logger
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

_PRODUCT_TYPE_RE = re.compile(r"^[A-Za-z]+[0-9]+,[0-9]+\Z")

SOFTWARE_INVENTORY_DEFINITION = DiagnosticDefinition(
    diagnostic_id="software_inventory",
    name="Software & Device Identity Inventory",
    category="system",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.IOS}),
    required_capabilities=frozenset(),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    prerequisites=frozenset(),
)

_STATUS_NOTE = (
    "PASS confirms successful retrieval of iOS software and device-class inventory. "
    "It does not verify OS authenticity, activation lock state, or hardware integrity."
)


class SoftwareInventoryDiagnostic:
    """Production diagnostic for iOS software inventory."""

    def __init__(self, bridge: IOSDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return SOFTWARE_INVENTORY_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        """Run software inventory collection and return a structured result.

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
                summary="Software inventory collection timed out within allocated budget.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        try:
            identity = self._bridge.get_identity(serial, timeout=remaining)
        except (ADBCommandTimeoutError, TimeoutError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Software inventory collection timed out.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Software inventory tool unavailable (%s)", type(exc).__name__)
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
            logger.error("Software inventory query threw exception: %s", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Software inventory query encountered an error.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        if identity is None or not identity.ios_version or not identity.product_type:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Insufficient software inventory fields returned by device.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        if not isinstance(identity.ios_version, str) or not isinstance(identity.product_type, str):
            parsed_version = None
        else:
            parsed_version = AppleOSVersion.parse(identity.ios_version)

        if (
            parsed_version is None
            or not isinstance(identity.product_type, str)
            or not _PRODUCT_TYPE_RE.match(identity.product_type.strip())
        ):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Malformed ProductVersion or ProductType; cannot verify software inventory.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Build normalized EvidenceRecord
        evidence = EvidenceRecord(
            evidence_id=uuid4(),
            diagnostic_id=self.definition.diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.IDEVICEINFO,
            source_name="ideviceinfo -k <allowlisted_key>",
            collection_method="libimobiledevice lockdownd query",
            timestamp=completed_at,
            raw_value=(
                f"iOS {identity.ios_version} ({identity.build_version or 'unknown'}) "
                f"[{identity.product_type}]"
            ),
            normalized_value=None,
            unit=None,
            reliability=None,
            confidence=None,
            metadata={
                "product_type": identity.product_type,
                "os_version": identity.ios_version,
                "build_version": identity.build_version,
                "device_class": identity.device_class,
                "hardware_model": identity.hardware_model,
                "cpu_architecture": identity.cpu_architecture,
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
            summary=f"iOS software inventory retrieved. {_STATUS_NOTE}",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
