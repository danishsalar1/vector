"""VECTOR Scan framework.

Exports planning, lifecycle, event taxonomy, orchestration, and service contracts.
"""

from vector_agent.scan.events import DiagnosticEvent, DiagnosticEventType
from vector_agent.scan.lifecycle import (
    InvalidLifecycleTransitionError,
    ScanLifecycleState,
    ScanSession,
)
from vector_agent.scan.orchestrator import ScanOrchestrator
from vector_agent.scan.planner import (
    DiagnosticApplicability,
    InvalidScanRequestError,
    PlannedDiagnostic,
    ScanPlan,
    ScanPlanner,
    ScanPlanningError,
    UnknownDiagnosticError,
)
from vector_agent.scan.service import DeviceScanActiveError, ScanService, scan_service

__all__ = [
    "DeviceScanActiveError",
    "DiagnosticApplicability",
    "DiagnosticEvent",
    "DiagnosticEventType",
    "InvalidLifecycleTransitionError",
    "InvalidScanRequestError",
    "PlannedDiagnostic",
    "ScanLifecycleState",
    "ScanOrchestrator",
    "ScanPlan",
    "ScanPlanner",
    "ScanPlanningError",
    "ScanService",
    "ScanSession",
    "UnknownDiagnosticError",
    "scan_service",
]
