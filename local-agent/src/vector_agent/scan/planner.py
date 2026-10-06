"""Production ScanPlanner and ScanPlan contracts.

Derives an executable scan plan from current truth:
- DeviceSession
- Platform
- ConnectionState
- DeviceCapabilityProfile
- DiagnosticRegistry
- Prerequisites and restrictions

Truthful classification:
- APPLICABLE
- NOT_APPLICABLE
- UNSUPPORTED
- RESTRICTED
- UNAVAILABLE
- BLOCKED_BY_PREREQUISITE
- UNKNOWN

Permanent rule:
Missing capability or incomplete knowledge NEVER creates a diagnostic FAIL.
Planning happens before execution; no diagnostic PASS/FAIL exists in the plan.
"""

from __future__ import annotations

from vector_agent.devices.session import DeviceSession
from vector_agent.diagnostics.definition import DiagnosticDefinition
from vector_agent.diagnostics.registry import DiagnosticRegistry
from vector_agent.models.device import (
    CapabilityStatus,
    ConnectionState,
    DiagnosticApplicability,
    PlannedDiagnostic,
    Platform,
    ScanMode,
    ScanPlan,
    ScanRequest,
)


class ScanPlanningError(Exception):
    """Base error for scan planning failures."""


class UnknownDiagnosticError(ScanPlanningError, ValueError):
    """Raised when an unknown diagnostic ID is requested."""


class InvalidScanRequestError(ScanPlanningError, ValueError):
    """Raised when a scan request has invalid parameters."""


class ScanPlanner:
    """Derives an executable ScanPlan from current device truth."""

    def plan(
        self,
        session: DeviceSession,
        registry: DiagnosticRegistry,
        request: ScanRequest,
    ) -> ScanPlan:
        """Derive an immutable ScanPlan from the device session and registry.

        Args:
            session: Active DeviceSession with current connection and capabilities.
            registry: Central DiagnosticRegistry.
            request: ScanRequest specifying mode, optional category, or diagnostic IDs.

        Returns:
            Immutable ScanPlan.

        Raises:
            UnknownDiagnosticError: If an unknown diagnostic ID was explicitly requested.
            InvalidScanRequestError: If scan request parameters are incoherent.
        """
        all_registry_ids = tuple(registry.list_ids())

        # Step 1: Select candidate diagnostics based on request mode with strict validation
        candidates: list[DiagnosticDefinition] = []
        diagnostics_requested: list[str] = []

        if request.mode == ScanMode.FULL_VERIFICATION:
            if request.category is not None:
                raise InvalidScanRequestError(
                    "category must not be specified for FULL_VERIFICATION mode."
                )
            if request.diagnostic_ids:
                raise InvalidScanRequestError(
                    "diagnostic_ids must not be specified for FULL_VERIFICATION mode."
                )
            candidates = [d.definition for d in registry.get_all()]
            diagnostics_requested = [d.diagnostic_id for d in candidates]

        elif request.mode == ScanMode.CATEGORY_VERIFICATION:
            if not request.category or not request.category.strip():
                raise InvalidScanRequestError(
                    "category must be specified and non-empty for CATEGORY_VERIFICATION mode."
                )
            if request.diagnostic_ids:
                raise InvalidScanRequestError(
                    "diagnostic_ids must not be specified for CATEGORY_VERIFICATION mode."
                )
            cat_clean = request.category.strip()
            candidates = registry.get_definitions_by_category(cat_clean)
            if not candidates:
                raise InvalidScanRequestError(
                    f"Unknown or empty category '{request.category}'. No matching diagnostics found."
                )
            diagnostics_requested = [d.diagnostic_id for d in candidates]

        elif request.mode == ScanMode.SELECTED_DIAGNOSTICS:
            if request.category is not None:
                raise InvalidScanRequestError(
                    "category must not be specified for SELECTED_DIAGNOSTICS mode."
                )
            if not request.diagnostic_ids:
                raise InvalidScanRequestError(
                    "diagnostic_ids must not be empty for SELECTED_DIAGNOSTICS mode."
                )
            # Expose caller errors: reject duplicate IDs
            if len(request.diagnostic_ids) != len(set(request.diagnostic_ids)):
                raise InvalidScanRequestError(
                    "Duplicate diagnostic IDs specified in diagnostic_ids."
                )
            for diag_id in request.diagnostic_ids:
                defn = registry.get_definition(diag_id)
                if defn is None:
                    raise UnknownDiagnosticError(f"Unknown diagnostic ID '{diag_id}'.")
                candidates.append(defn)
            diagnostics_requested = list(request.diagnostic_ids)

        elif request.mode == ScanMode.SINGLE_COMPONENT:
            if request.category is not None:
                raise InvalidScanRequestError(
                    "category must not be specified for SINGLE_COMPONENT mode."
                )
            if len(request.diagnostic_ids) != 1:
                raise InvalidScanRequestError(
                    "Exactly one diagnostic ID must be specified for SINGLE_COMPONENT mode."
                )
            diag_id = request.diagnostic_ids[0]
            defn = registry.get_definition(diag_id)
            if defn is None:
                raise UnknownDiagnosticError(f"Unknown diagnostic ID '{diag_id}'.")
            candidates.append(defn)
            diagnostics_requested = [diag_id]

        else:
            raise InvalidScanRequestError(f"Unsupported scan mode '{request.mode}'.")

        # Step 2: Classify applicability for each candidate diagnostic
        diagnostics_planned: list[str] = []
        diagnostics_skipped: list[str] = []
        planned_items: list[PlannedDiagnostic] = []

        for defn in candidates:
            applicability, reason = self._evaluate_diagnostic(defn, session, registry)

            planned_items.append(
                PlannedDiagnostic(
                    diagnostic_id=defn.diagnostic_id,
                    applicability=applicability,
                    reason=reason,
                )
            )

            if applicability == DiagnosticApplicability.APPLICABLE:
                diagnostics_planned.append(defn.diagnostic_id)
            else:
                diagnostics_skipped.append(defn.diagnostic_id)

        capability_ts = (
            session.capability_profile.profiled_at if session.capability_profile else None
        )

        return ScanPlan(
            device_id=session.device_id,
            platform=session.platform,
            mode=request.mode,
            diagnostics_requested=tuple(diagnostics_requested),
            diagnostics_planned=tuple(diagnostics_planned),
            diagnostics_skipped=tuple(diagnostics_skipped),
            planned_items=tuple(planned_items),
            planning_session_epoch=session.session_epoch,
            capability_profiled_at=capability_ts,
            registry_diagnostic_ids=all_registry_ids,
        )

    def _evaluate_diagnostic(
        self,
        defn: DiagnosticDefinition,
        session: DeviceSession,
        registry: DiagnosticRegistry,
    ) -> tuple[DiagnosticApplicability, str | None]:
        """Evaluate a single diagnostic against current device session truth.

        Prerequisite semantics (Phase 5):
        A prerequisite in Phase 5 indicates a structural definition dependency:
        the required diagnostic definition must be registered and available in
        the catalog. It does NOT assert that the prerequisite has executed or
        passed at plan time (runtime DAG ordering is deferred).
        """
        # 1. Platform support check
        if session.platform not in defn.supported_platforms:
            return (
                DiagnosticApplicability.NOT_APPLICABLE,
                f"Platform {session.platform.value} is not supported by '{defn.diagnostic_id}'.",
            )

        # 2. Connection and authorization check
        if session.connection_state == ConnectionState.UNAUTHORIZED:
            msg = (
                "Device is unauthorized. Approve USB debugging on the device."
                if session.platform == Platform.ANDROID
                else "Device is unauthorized. Pairing and trust authorization required on the device."
            )
            return (
                DiagnosticApplicability.RESTRICTED,
                msg,
            )

        if session.connection_state != ConnectionState.CONNECTED:
            return (
                DiagnosticApplicability.UNAVAILABLE,
                f"Device is not connected (state: {session.connection_state.value}).",
            )

        # 3. VECTOR Probe requirement check
        if defn.requires_probe:
            return (
                DiagnosticApplicability.UNAVAILABLE,
                "VECTOR Probe is required but not installed/available.",
            )

        # 4. Prerequisites check (structural registration and circularity)
        if defn.prerequisites:
            for prereq_id in sorted(defn.prerequisites):
                if prereq_id == defn.diagnostic_id:
                    return (
                        DiagnosticApplicability.BLOCKED_BY_PREREQUISITE,
                        f"Circular prerequisite: diagnostic '{defn.diagnostic_id}' cannot depend on itself.",
                    )
                prereq_defn = registry.get_definition(prereq_id)
                if prereq_defn is None:
                    return (
                        DiagnosticApplicability.BLOCKED_BY_PREREQUISITE,
                        f"Required prerequisite diagnostic '{prereq_id}' is not registered in catalog.",
                    )
                if defn.diagnostic_id in prereq_defn.prerequisites:
                    return (
                        DiagnosticApplicability.BLOCKED_BY_PREREQUISITE,
                        f"Circular prerequisite detected between '{defn.diagnostic_id}' and '{prereq_id}'.",
                    )

        # 5. Required capabilities check
        if defn.required_capabilities:
            if session.capability_profile is None:
                return (
                    DiagnosticApplicability.UNKNOWN,
                    "Device capability profile is not available to evaluate required capabilities.",
                )

            for cap_name in sorted(defn.required_capabilities):
                cap_status = session.capability_profile.get(cap_name)

                if cap_status in (CapabilityStatus.ABSENT, CapabilityStatus.UNSUPPORTED):
                    return (
                        DiagnosticApplicability.UNSUPPORTED,
                        f"Required capability '{cap_name}' is {cap_status.value} on device.",
                    )

                if cap_status == CapabilityStatus.RESTRICTED:
                    return (
                        DiagnosticApplicability.RESTRICTED,
                        f"Required capability '{cap_name}' is RESTRICTED on device.",
                    )

                if cap_status == CapabilityStatus.NOT_REPORTED:
                    return (
                        DiagnosticApplicability.UNAVAILABLE,
                        f"Required capability '{cap_name}' is NOT_REPORTED by device.",
                    )

                if cap_status == CapabilityStatus.UNKNOWN:
                    return (
                        DiagnosticApplicability.UNKNOWN,
                        f"Required capability '{cap_name}' status is UNKNOWN on device.",
                    )

                if cap_status == CapabilityStatus.PRESENT:
                    continue

        # All checks passed
        return DiagnosticApplicability.APPLICABLE, None
