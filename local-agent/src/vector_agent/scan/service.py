"""Production ScanService.

Central service coordinating scan planning, execution lifecycle,
and session retrieval.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from vector_agent.core.logging import get_logger
from vector_agent.devices.presence import DevicePresenceMonitor
from vector_agent.devices.session import (
    ConnectionState,
    DeviceNotConnectedError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
    device_session_manager,
)
from vector_agent.diagnostics.registry import (
    DiagnosticRegistry,
    create_default_registry,
)
from vector_agent.models.device import ScanRequest
from vector_agent.scan.events import DiagnosticEvent, DiagnosticEventType
from vector_agent.scan.lifecycle import (
    InvalidLifecycleTransitionError,
    ScanLifecycleState,
    ScanSession,
)
from vector_agent.scan.orchestrator import ScanOrchestrator
from vector_agent.scan.planner import ScanPlan, ScanPlanner

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class DeviceScanActiveError(ValueError):
    """Raised when starting a scan on a device that already has an active non-terminal scan."""


class ScanService:
    """Manages scan sessions, planning, and execution orchestration."""

    def __init__(
        self,
        registry: DiagnosticRegistry | None = None,
    ) -> None:
        self._registry = registry or create_default_registry()
        self._planner = ScanPlanner()
        self._presence: DevicePresenceMonitor | None = None
        self._orchestrator = ScanOrchestrator(
            session_manager=device_session_manager,
            registry=self._registry,
            presence=self._presence,
        )
        self._scans: dict[str, ScanSession] = {}
        self._lock = threading.RLock()

    def set_registry(self, registry: DiagnosticRegistry) -> None:
        """Replace the diagnostic registry (useful for testing)."""
        with self._lock:
            self._registry = registry
            self._orchestrator = ScanOrchestrator(
                session_manager=device_session_manager,
                registry=self._registry,
                presence=self._presence,
            )

    def set_presence_monitor(self, presence: DevicePresenceMonitor | None) -> None:
        """Enable (or, with None, disable) active presence verification for scans.

        Applies to scans that start afterwards; a running scan keeps the orchestrator it began
        with. Off by default so nothing probes hardware unless the agent explicitly wires it.
        """
        with self._lock:
            self._presence = presence
            self._orchestrator = ScanOrchestrator(
                session_manager=device_session_manager,
                registry=self._registry,
                presence=presence,
            )

    @property
    def registry(self) -> DiagnosticRegistry:
        with self._lock:
            return self._registry

    def clear(self) -> None:
        """Clear all active and completed scans (testing helper)."""
        with self._lock:
            self._scans.clear()

    def create_plan(self, request: ScanRequest) -> ScanPlan:
        """Derive an executable plan for the given request.

        Validates device existence and session state before planning.

        Raises:
            DeviceNotFoundError: If the target device does not exist.
            DeviceUnauthorizedError: If the target device is unauthorized.
            DeviceNotConnectedError: If the target device is offline.
            UnknownDiagnosticError: If an unknown diagnostic ID was requested.
            InvalidScanRequestError: If scan request parameters are invalid.
        """
        device_id = request.device_id
        session = device_session_manager.get_session(device_id)
        if not session:
            raise DeviceNotFoundError(f"Device '{device_id}' not found.")

        if session.connection_state == ConnectionState.UNAUTHORIZED:
            raise DeviceUnauthorizedError(
                f"Device '{device_id}' is unauthorized. Authorize this computer on the device before running diagnostics."
            )

        if session.connection_state != ConnectionState.CONNECTED:
            raise DeviceNotConnectedError(
                f"Device '{device_id}' is not connected (state: {session.connection_state.value})."
            )

        with self._lock:
            return self._planner.plan(session, self._registry, request)

    def create_scan(self, request: ScanRequest) -> ScanSession:
        """Create and plan a new scan session without executing it."""
        with self._lock:
            for s in self._scans.values():
                if s.device_id == request.device_id and not s.is_terminal:
                    raise DeviceScanActiveError(
                        f"An active scan '{s.scan_id}' is already in progress for device '{request.device_id}'."
                    )
            plan = self.create_plan(request)
            scan_session = ScanSession(
                device_id=request.device_id,
                plan=plan,
            )
            scan_session.transition_to(ScanLifecycleState.PLANNED)
            self._scans[scan_session.scan_id] = scan_session
            return scan_session

    def _safe_run_scan(self, session: ScanSession) -> ScanSession:
        """Execute scan session with crash protection at the service boundary.

        Guarantees:
        - If an unexpected exception escapes orchestrator:
            - transitions non-terminal scan to FAILED
            - records fixed safe error message (no str(exc) leakage)
            - emits scan.failed exactly once
            - logs only safe exception type
            - does not overwrite a legitimate terminal state
            - does not fabricate diagnostic FAIL
        """
        try:
            return self._orchestrator.run_scan(session)
        except InvalidLifecycleTransitionError:
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error in scan worker/orchestrator: %s",
                type(exc).__name__,
            )
            with self._lock:
                if not session.is_terminal:
                    safe_msg = "An unexpected internal error occurred during scan execution."
                    session.transition_to(
                        ScanLifecycleState.FAILED,
                        error=safe_msg,
                    )
                    session.add_event(
                        DiagnosticEvent(
                            scan_id=session.scan_id,
                            device_id=session.device_id,
                            event_type=DiagnosticEventType.SCAN_FAILED,
                            message=safe_msg,
                        )
                    )
            return session

    def run_scan(self, scan_id: str) -> ScanSession:
        """Execute a previously planned scan session."""
        with self._lock:
            session = self._scans.get(scan_id)
            if not session:
                raise ValueError(f"Scan '{scan_id}' not found.")
            if session.state != ScanLifecycleState.PLANNED:
                raise InvalidLifecycleTransitionError(
                    f"Cannot run scan '{scan_id}' in state {session.state.value}; must be in PLANNED state."
                )
            for s in self._scans.values():
                if s.scan_id != scan_id and s.device_id == session.device_id and not s.is_terminal:
                    raise DeviceScanActiveError(
                        f"An active scan '{s.scan_id}' is already in progress for device '{session.device_id}'."
                    )

        return self._safe_run_scan(session)

    def start_scan(
        self,
        request: ScanRequest,
        run_async: bool = False,
    ) -> ScanSession:
        """Create, plan, and execute a scan.

        Args:
            request: ScanRequest parameters.
            run_async: If True, executes on a background daemon thread.

        Returns:
            ScanSession (running or completed).
        """
        session = self.create_scan(request)

        if run_async:
            thread = threading.Thread(
                target=self._safe_run_scan,
                args=(session,),
                daemon=True,
                name=f"vector-scan-{session.scan_id[:8]}",
            )
            thread.start()
        else:
            self._safe_run_scan(session)

        return session

    def get_scan(self, scan_id: str) -> ScanSession | None:
        """Retrieve a scan session by ID."""
        with self._lock:
            return self._scans.get(scan_id)

    def get_events(self, scan_id: str) -> list[DiagnosticEvent] | None:
        """Retrieve the event log for a specific scan."""
        with self._lock:
            session = self._scans.get(scan_id)
            if not session:
                return None
            return list(session.events)

    def has_active_scan(self, device_id: str) -> bool:
        """Check whether there is an active (non-terminal) scan for a device."""
        with self._lock:
            return any(s.device_id == device_id and not s.is_terminal for s in self._scans.values())

    def list_scans(self) -> list[ScanSession]:
        """List all scan sessions."""
        with self._lock:
            return list(self._scans.values())


# Global singleton for the local agent
scan_service = ScanService()
