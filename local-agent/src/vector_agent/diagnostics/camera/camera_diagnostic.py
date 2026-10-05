"""Camera Inventory Diagnostic — VECTOR production Android standard diagnostic.

Wraps AndroidDeviceBridge.get_camera_inventory() and produces
structured DiagnosticResult + EvidenceRecord(s) through the production
Diagnostic contract.

Camera inventory semantics (permanent):
- PASS  = valid camera device inventory was retrieved from the camera service.
- PASS != cameras can focus, capture, or produce quality images (inventory only).
- Zero cameras is handled conservatively as INCONCLUSIVE, never hardware FAIL.
- Client history and private package names are discarded.
- Missing or malformed evidence -> INCONCLUSIVE, never false PASS or hardware FAIL.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.android.camera import CameraInventory
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

logger = get_logger(__name__)

CAMERA_INVENTORY_DEFINITION = DiagnosticDefinition(
    diagnostic_id="camera_inventory",
    name="Camera Inventory Verification",
    category="camera",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.ANDROID}),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    required_capabilities=frozenset(),
    prerequisites=frozenset(),
)

_STATUS_NOTE = (
    "PASS confirms successful camera inventory retrieval. "
    "It does not verify optical performance, focus, capture, or image quality."
)


class CameraInventoryDiagnostic:
    """Production diagnostic for Android camera inventory."""

    def __init__(self, bridge: AndroidDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return CAMERA_INVENTORY_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        """Run camera inventory collection and return a structured result.

        Args:
            device_id: Opaque VECTOR device identifier.
            serial: Validated ADB serial (internal only).
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
                summary="Camera inventory collection timed out within allocated budget.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(time.monotonic() - start_mono, 3),
            )

        try:
            bridge_result = self._bridge.get_camera_inventory(serial, timeout=remaining)
        except Exception as exc:
            duration = time.monotonic() - start_mono
            logger.error("Camera inventory diagnostic failed (%s)", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Camera inventory collection failed due to an execution error.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(duration, 3),
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        status = _map_status(bridge_result.status)

        evidence: list[EvidenceRecord] = []
        if bridge_result.inventory is not None and bridge_result.inventory.camera_count > 0:
            evidence = _build_evidence_records(
                inventory=bridge_result.inventory,
                device_id=device_id,
                diagnostic_id=self.definition.diagnostic_id,
                evidence_source=bridge_result.evidence_source,
                collection_method=bridge_result.collection_method,
                confidence=bridge_result.confidence,
                collected_at=bridge_result.collected_at,
            )

        summary = _build_summary(status, bridge_result.error)

        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category=self.definition.category,
            status=status,
            automation_level=self.definition.automation_level,
            evidence=evidence,
            summary=summary,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=round(duration, 3),
        )


def _map_status(bridge_status: str) -> DiagnosticStatus:
    mapping = {
        "PASS": DiagnosticStatus.PASS,
        "INCONCLUSIVE": DiagnosticStatus.INCONCLUSIVE,
        "RESTRICTED": DiagnosticStatus.RESTRICTED,
        "UNSUPPORTED": DiagnosticStatus.UNSUPPORTED,
        "ERROR": DiagnosticStatus.ERROR,
    }
    return mapping.get(bridge_status, DiagnosticStatus.ERROR)


def _build_summary(status: DiagnosticStatus, error: str | None = None) -> str:
    if status == DiagnosticStatus.PASS:
        return _STATUS_NOTE
    if status == DiagnosticStatus.INCONCLUSIVE:
        if error and "0 camera" in error:
            return "Camera service reported 0 camera devices. Inconclusive without reference specification."
        return "Camera inventory was partially collected or ambiguous."
    if status == DiagnosticStatus.RESTRICTED:
        return "Camera service access restricted by platform permissions."
    if status == DiagnosticStatus.UNSUPPORTED:
        return "Camera service interface is not available on this device."
    return "Camera inventory collection encountered an execution error."


def _build_evidence_records(
    *,
    inventory: CameraInventory,
    device_id: str,
    diagnostic_id: str,
    evidence_source: str,
    collection_method: str,
    confidence: float,
    collected_at: datetime,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []

    # Total camera count
    records.append(
        EvidenceRecord(
            diagnostic_id=diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.ADB_DUMPSYS,
            source_name=evidence_source,
            collection_method=collection_method,
            timestamp=collected_at,
            raw_value=str(inventory.camera_count),
            normalized_value=float(inventory.camera_count),
            unit="count",
            reliability=1.0,
            confidence=confidence,
            metadata={"field": "camera_device_count"},
        )
    )

    # Individual cameras (if enumerated)
    for cam in inventory.cameras:
        meta = {
            "field": f"camera_{cam.camera_id}",
            "camera_id": cam.camera_id,
        }
        if cam.facing:
            meta["facing"] = cam.facing

        raw_str = f"Camera {cam.camera_id}" + (f" ({cam.facing})" if cam.facing else "")
        records.append(
            EvidenceRecord(
                diagnostic_id=diagnostic_id,
                device_id=device_id,
                source_type=EvidenceSourceType.ADB_DUMPSYS,
                source_name=evidence_source,
                collection_method=collection_method,
                timestamp=collected_at,
                raw_value=raw_str,
                normalized_value=None,
                unit=None,
                reliability=1.0,
                confidence=confidence,
                metadata=meta,
            )
        )

    return records
