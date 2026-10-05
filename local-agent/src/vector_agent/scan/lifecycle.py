"""Production ScanSession and Lifecycle state machine.

Locked lifecycle states:
- CREATED
- PLANNED
- RUNNING
- COMPLETED
- FAILED
- CANCELLED

Transitions are strictly validated. Invalid transitions are rejected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from vector_agent.models.device import (
    DiagnosticResult,
    ScanLifecycleState,
    ScanSummary,
    TrustEngineStatus,
)
from vector_agent.scan.events import DiagnosticEvent
from vector_agent.scan.planner import ScanPlan


class InvalidLifecycleTransitionError(ValueError):
    """Raised when an illegal scan lifecycle transition is attempted."""


_VALID_TRANSITIONS: dict[ScanLifecycleState, set[ScanLifecycleState]] = {
    ScanLifecycleState.CREATED: {
        ScanLifecycleState.PLANNED,
        ScanLifecycleState.CANCELLED,
        ScanLifecycleState.FAILED,
    },
    ScanLifecycleState.PLANNED: {
        ScanLifecycleState.RUNNING,
        ScanLifecycleState.CANCELLED,
        ScanLifecycleState.FAILED,
    },
    ScanLifecycleState.RUNNING: {
        ScanLifecycleState.COMPLETED,
        ScanLifecycleState.FAILED,
        ScanLifecycleState.CANCELLED,
    },
    ScanLifecycleState.COMPLETED: set(),
    ScanLifecycleState.FAILED: set(),
    ScanLifecycleState.CANCELLED: set(),
}

_TERMINAL_STATES: set[ScanLifecycleState] = {
    ScanLifecycleState.COMPLETED,
    ScanLifecycleState.FAILED,
    ScanLifecycleState.CANCELLED,
}


class ScanSession(BaseModel):
    """Execution state model representing what VECTOR knows about a live scan.

    No raw serial persistence. Tracks opaque device_id, ScanPlan, results,
    events, and lifecycle truth.
    """

    scan_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str
    session_epoch: int = 0
    plan: ScanPlan
    state: ScanLifecycleState = ScanLifecycleState.CREATED
    current_diagnostic_id: str | None = None
    diagnostic_results: list[DiagnosticResult] = Field(default_factory=list)
    events: list[DiagnosticEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def is_terminal(self) -> bool:
        """True if the scan session has reached a terminal state."""
        return self.state in _TERMINAL_STATES

    def transition_to(
        self,
        new_state: ScanLifecycleState,
        error: str | None = None,
    ) -> None:
        """Transition scan to a new lifecycle state.

        Guarantees:
        - Timestamps and error details are assigned before the new state is
          published, preventing torn reads by concurrent observers.
        - State assignment occurs last.

        Raises:
            InvalidLifecycleTransitionError: If the transition is illegal.
        """
        allowed = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidLifecycleTransitionError(
                f"Invalid lifecycle transition: cannot move from {self.state.value} to {new_state.value}."
            )
        now = datetime.now(UTC)
        if error:
            self.error = error
        if new_state == ScanLifecycleState.RUNNING and self.started_at is None:
            self.started_at = now
        if new_state in _TERMINAL_STATES and self.completed_at is None:
            self.completed_at = now
        # State assignment occurs LAST to prevent torn reads
        self.state = new_state

    def record_result(self, result: DiagnosticResult) -> None:
        """Record an executed diagnostic result."""
        self.diagnostic_results.append(result)

    def add_event(self, event: DiagnosticEvent) -> None:
        """Append an event to the session event log."""
        self.events.append(event)

    def to_summary(self) -> ScanSummary:
        """Convert to the API-facing ScanSummary DTO.

        Guarantees:
        - Exposes safe ScanPlan context explaining planned vs skipped diagnostics and reasons.
        - trust_engine_status remains NOT_READY.
        - trust_score remains None.
        - trust_confidence remains None.
        """
        return ScanSummary(
            scan_id=self.scan_id,
            device_id=self.device_id,
            state=self.state,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            plan=self.plan,
            diagnostic_results=list(self.diagnostic_results),
            trust_engine_status=TrustEngineStatus.NOT_READY,
            trust_score=None,
            trust_confidence=None,
            error=self.error,
        )
