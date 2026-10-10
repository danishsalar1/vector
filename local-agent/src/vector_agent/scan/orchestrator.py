"""Production scan execution orchestrator.

Coordinates:
Plan -> Start -> Diagnostic execution -> Evidence -> Result -> Events -> Finish

Safety rules:
- Validates opaque device_id and session epoch before and during execution.
- Disconnect or session epoch change stops execution; stale results are discarded.
- Subprocess / diagnostic execution occurs outside DeviceSessionManager global lock.
- Execution exceptions become DiagnosticStatus.ERROR, not fabricated hardware FAIL.
- Battery telemetry PASS means valid telemetry was acquired, NOT battery health.
- Emits real DiagnosticEvents only; no fake progress, no simulated percentages.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from vector_agent.core.logging import get_logger
from vector_agent.devices.presence import DevicePresenceMonitor, PresenceVerdict
from vector_agent.devices.session import DeviceSession, DeviceSessionManager
from vector_agent.diagnostics.registry import DiagnosticRegistry
from vector_agent.models.device import (
    AutomationLevel,
    ConnectionState,
    DiagnosticResult,
    DiagnosticStatus,
)
from vector_agent.scan.events import DiagnosticEvent, DiagnosticEventType
from vector_agent.scan.lifecycle import (
    InvalidLifecycleTransitionError,
    ScanLifecycleState,
    ScanSession,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ScanOrchestrator:
    """Executes planned diagnostics and drives the ScanSession lifecycle."""

    def __init__(
        self,
        session_manager: DeviceSessionManager,
        registry: DiagnosticRegistry,
        presence: DevicePresenceMonitor | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._registry = registry
        # Optional active presence verification (Stage 2B-3). Without it the orchestrator
        # relies solely on what the session manager already records (previous behaviour).
        self._presence = presence

    def _device_lost(self, device_id: str, session: DeviceSession, epoch: int) -> bool:
        """True only when the bound device's loss is confirmed (and recorded) or already known.

        An unverifiable answer (timeout, tool error, flapping) returns False: the scan goes on
        and the diagnostics themselves report any real failure. Never raises.
        """
        if self._presence is None:
            return False
        verdict = self._presence.verify(device_id, session, epoch)
        return verdict is PresenceVerdict.LOST

    def run_scan(
        self,
        scan_session: ScanSession,
        event_callback: Callable[[DiagnosticEvent], None] | None = None,
    ) -> ScanSession:
        """Run all planned diagnostics in the scan session sequentially.

        Args:
            scan_session: Prepared ScanSession in PLANNED state.
            event_callback: Optional callback invoked for each emitted DiagnosticEvent.

        Returns:
            ScanSession in terminal state (COMPLETED or FAILED).
        """
        if scan_session.state != ScanLifecycleState.PLANNED:
            raise InvalidLifecycleTransitionError(
                f"Cannot run scan {scan_session.scan_id} in state {scan_session.state.value}; must be PLANNED."
            )

        def emit(event: DiagnosticEvent) -> None:
            scan_session.add_event(event)
            if event_callback:
                try:
                    event_callback(event)
                except Exception as cb_err:
                    logger.warning("Event callback error: %s", cb_err)

        device_id = scan_session.device_id

        # Step 1: Pre-flight session validation
        dev_session = self._session_manager.get_session(device_id)
        if not dev_session:
            scan_session.transition_to(
                ScanLifecycleState.FAILED,
                error=f"Device '{device_id}' not found.",
            )
            emit(
                DiagnosticEvent(
                    scan_id=scan_session.scan_id,
                    device_id=device_id,
                    event_type=DiagnosticEventType.SCAN_FAILED,
                    message="Target device was not found.",
                )
            )
            return scan_session

        if dev_session.connection_state != ConnectionState.CONNECTED:
            scan_session.transition_to(
                ScanLifecycleState.FAILED,
                error=f"Device '{device_id}' is not connected (state: {dev_session.connection_state.value}).",
            )
            emit(
                DiagnosticEvent(
                    scan_id=scan_session.scan_id,
                    device_id=device_id,
                    event_type=DiagnosticEventType.SCAN_FAILED,
                    message=f"Device is not connected (state: {dev_session.connection_state.value}).",
                )
            )
            return scan_session

        # Verify plan-time session epoch matches current session epoch
        if dev_session.session_epoch != scan_session.plan.planning_session_epoch:
            logger.warning(
                "Device %s session epoch changed between planning (epoch %d) and execution (epoch %d).",
                device_id,
                scan_session.plan.planning_session_epoch,
                dev_session.session_epoch,
            )
            scan_session.transition_to(
                ScanLifecycleState.FAILED,
                error="Device session changed between planning and execution. Re-plan required.",
            )
            emit(
                DiagnosticEvent(
                    scan_id=scan_session.scan_id,
                    device_id=device_id,
                    event_type=DiagnosticEventType.SCAN_FAILED,
                    message="Device session changed between planning and execution. Re-plan required.",
                )
            )
            return scan_session

        # Capture epoch to safeguard against reconnection/stale retargeting
        initial_epoch = dev_session.session_epoch
        scan_session.session_epoch = initial_epoch

        # Step 2: Transition to RUNNING and emit scan.started
        scan_session.transition_to(ScanLifecycleState.RUNNING)
        emit(
            DiagnosticEvent(
                scan_id=scan_session.scan_id,
                device_id=device_id,
                event_type=DiagnosticEventType.SCAN_STARTED,
                message="Scan started.",
            )
        )

        # Step 3: Execute planned diagnostics
        for diagnostic_id in scan_session.plan.diagnostics_planned:
            # Check for stale device / epoch change BEFORE diagnostic
            current_dev = self._session_manager.get_session(device_id)
            if (
                current_dev is None
                or current_dev.connection_state != ConnectionState.CONNECTED
                or current_dev.session_epoch != initial_epoch
                or current_dev is not dev_session
                or self._device_lost(device_id, dev_session, initial_epoch)
            ):
                logger.warning(
                    "Device %s disconnected or session epoch changed before diagnostic %s",
                    device_id,
                    diagnostic_id,
                )
                scan_session.transition_to(
                    ScanLifecycleState.FAILED,
                    error="Device disconnected or session changed during scan.",
                )
                emit(
                    DiagnosticEvent(
                        scan_id=scan_session.scan_id,
                        device_id=device_id,
                        diagnostic_id=diagnostic_id,
                        event_type=DiagnosticEventType.SCAN_FAILED,
                        message="Device disconnected during scan.",
                    )
                )
                return scan_session

            serial = current_dev.get_serial_for_diagnostic()
            if not serial:
                scan_session.transition_to(
                    ScanLifecycleState.FAILED,
                    error="Device serial unavailable for diagnostics.",
                )
                emit(
                    DiagnosticEvent(
                        scan_id=scan_session.scan_id,
                        device_id=device_id,
                        diagnostic_id=diagnostic_id,
                        event_type=DiagnosticEventType.SCAN_FAILED,
                        message="Device serial unavailable.",
                    )
                )
                return scan_session

            # Notify diagnostic started
            scan_session.current_diagnostic_id = diagnostic_id
            emit(
                DiagnosticEvent(
                    scan_id=scan_session.scan_id,
                    device_id=device_id,
                    diagnostic_id=diagnostic_id,
                    event_type=DiagnosticEventType.DIAGNOSTIC_STARTED,
                )
            )

            diag = self._registry.get(diagnostic_id)
            if diag is None:
                # Diagnostic missing from registry
                result = DiagnosticResult(
                    diagnostic_id=diagnostic_id,
                    diagnostic_name=diagnostic_id,
                    category="unknown",
                    status=DiagnosticStatus.ERROR,
                    automation_level=AutomationLevel.AUTOMATIC,
                    summary=f"Diagnostic implementation '{diagnostic_id}' not found in registry.",
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    duration_seconds=0.0,
                )
            else:
                # Execute diagnostic (outside lock)
                start_dt = datetime.now(UTC)
                try:
                    result = diag.execute(device_id=device_id, serial=serial)
                except Exception as exc:
                    logger.error(
                        "Diagnostic '%s' execution threw exception: %s",
                        diagnostic_id,
                        type(exc).__name__,
                    )
                    # Requirement 19: execution exception becomes ERROR, NOT hardware FAIL
                    result = DiagnosticResult(
                        diagnostic_id=diagnostic_id,
                        diagnostic_name=diag.definition.name,
                        category=diag.definition.category,
                        status=DiagnosticStatus.ERROR,
                        automation_level=diag.definition.automation_level,
                        summary=f"Diagnostic execution error: {type(exc).__name__}",
                        started_at=start_dt,
                        completed_at=datetime.now(UTC),
                        duration_seconds=round((datetime.now(UTC) - start_dt).total_seconds(), 3),
                    )

            # Enforce execution contract:
            # - PASS or DEGRADED with zero evidence -> convert to ERROR
            # - PENDING or RUNNING must never be accepted as terminal results -> convert to ERROR
            # - FAIL represents a measured diagnostic result (preserved)
            # - INCONCLUSIVE remains distinct
            if (
                result.status in (DiagnosticStatus.PASS, DiagnosticStatus.DEGRADED)
                and not result.evidence
            ):
                logger.error(
                    "Diagnostic '%s' returned %s with zero evidence records. Violates execution contract.",
                    diagnostic_id,
                    result.status.value,
                )
                result = DiagnosticResult(
                    diagnostic_id=result.diagnostic_id,
                    diagnostic_name=result.diagnostic_name,
                    category=result.category,
                    status=DiagnosticStatus.ERROR,
                    automation_level=result.automation_level,
                    summary=f"Execution contract violation: {result.status.value} returned with zero evidence records.",
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    duration_seconds=result.duration_seconds,
                )
            elif result.status in (DiagnosticStatus.PENDING, DiagnosticStatus.RUNNING):
                logger.error(
                    "Diagnostic '%s' returned non-terminal status %s.",
                    diagnostic_id,
                    result.status.value,
                )
                result = DiagnosticResult(
                    diagnostic_id=result.diagnostic_id,
                    diagnostic_name=result.diagnostic_name,
                    category=result.category,
                    status=DiagnosticStatus.ERROR,
                    automation_level=result.automation_level,
                    summary=f"Execution contract violation: non-terminal status {result.status.value} returned.",
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    duration_seconds=result.duration_seconds,
                )

            # Check for stale device / epoch change AFTER diagnostic execution
            # A clean measured outcome proves the device answered while it ran; anything else
            # (ERROR, INCONCLUSIVE, RESTRICTED, ...) is exactly how an unplug shows up, so
            # confirm the device is still attached before trusting or recording the result.
            current_dev = self._session_manager.get_session(device_id)
            if (
                current_dev is None
                or current_dev.connection_state != ConnectionState.CONNECTED
                or current_dev.session_epoch != initial_epoch
                or current_dev is not dev_session
                or (
                    result.status
                    not in (DiagnosticStatus.PASS, DiagnosticStatus.FAIL, DiagnosticStatus.DEGRADED)
                    and self._device_lost(device_id, dev_session, initial_epoch)
                )
            ):
                logger.warning(
                    "Device %s disconnected or session changed during diagnostic %s",
                    device_id,
                    diagnostic_id,
                )
                scan_session.transition_to(
                    ScanLifecycleState.FAILED,
                    error="Device disconnected or session changed during diagnostic execution.",
                )
                emit(
                    DiagnosticEvent(
                        scan_id=scan_session.scan_id,
                        device_id=device_id,
                        diagnostic_id=diagnostic_id,
                        event_type=DiagnosticEventType.SCAN_FAILED,
                        message="Device disconnected during diagnostic execution.",
                    )
                )
                return scan_session

            # Record result into scan session
            scan_session.record_result(result)

            # Emit evidence events for each collected EvidenceRecord
            for evidence_record in result.evidence:
                emit(
                    DiagnosticEvent(
                        scan_id=scan_session.scan_id,
                        device_id=device_id,
                        diagnostic_id=diagnostic_id,
                        event_type=DiagnosticEventType.DIAGNOSTIC_EVIDENCE,
                        evidence=evidence_record,
                    )
                )

            # Emit terminal diagnostic event matching result
            terminal_event_type = self._map_status_to_event_type(result.status)
            emit(
                DiagnosticEvent(
                    scan_id=scan_session.scan_id,
                    device_id=device_id,
                    diagnostic_id=diagnostic_id,
                    event_type=terminal_event_type,
                    result=result,
                    message=result.summary,
                )
            )

        # Step 4: Final verification. Clean results skip the per-diagnostic post-check, so a
        # phone unplugged during/after the LAST diagnostic would otherwise still read as a
        # completed scan. One bounded probe per scan (not per diagnostic) closes that gap;
        # recorded results and evidence are kept, exactly as for any other mid-scan loss.
        if self._device_lost(device_id, dev_session, initial_epoch):
            logger.warning("Device %s disconnected before scan completion", device_id)
            scan_session.current_diagnostic_id = None
            scan_session.transition_to(
                ScanLifecycleState.FAILED,
                error="Device disconnected or session changed during scan.",
            )
            emit(
                DiagnosticEvent(
                    scan_id=scan_session.scan_id,
                    device_id=device_id,
                    event_type=DiagnosticEventType.SCAN_FAILED,
                    message="Device disconnected during scan.",
                )
            )
            return scan_session

        # Step 5: Complete scan
        scan_session.current_diagnostic_id = None
        scan_session.transition_to(ScanLifecycleState.COMPLETED)
        emit(
            DiagnosticEvent(
                scan_id=scan_session.scan_id,
                device_id=device_id,
                event_type=DiagnosticEventType.SCAN_COMPLETED,
                message="All planned diagnostics completed.",
            )
        )

        return scan_session

    @staticmethod
    def _map_status_to_event_type(status: DiagnosticStatus) -> DiagnosticEventType:
        """Map DiagnosticStatus to the locked terminal event concept.

        Semantics:
        - diagnostic.completed = normal completion producing a legitimate
          measured or skipped/unsupported result: PASS, FAIL, DEGRADED,
          UNSUPPORTED, RESTRICTED, SKIPPED.
        - diagnostic.inconclusive = execution completed but result is INCONCLUSIVE.
        - diagnostic.failed = execution/infrastructure/runtime error (ERROR).
        """
        if status in (
            DiagnosticStatus.PASS,
            DiagnosticStatus.FAIL,
            DiagnosticStatus.DEGRADED,
            DiagnosticStatus.UNSUPPORTED,
            DiagnosticStatus.RESTRICTED,
            DiagnosticStatus.SKIPPED,
        ):
            return DiagnosticEventType.DIAGNOSTIC_COMPLETED
        if status == DiagnosticStatus.INCONCLUSIVE:
            return DiagnosticEventType.DIAGNOSTIC_INCONCLUSIVE
        if status == DiagnosticStatus.ERROR:
            return DiagnosticEventType.DIAGNOSTIC_FAILED
        raise ValueError(f"Unhandled diagnostic status for terminal event mapping: {status}")
