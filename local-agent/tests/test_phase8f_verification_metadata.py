"""Phase 8F Stage 2B-4: diagnostic verification-level metadata on the scan plan.

Contract (additive): every ``PlannedDiagnostic`` carries ``verification_level`` and
``requires_probe`` copied from the diagnostic's registered definition, so a client can join
any ``DiagnosticResult`` to its level through ``plan.planned_items`` by ``diagnostic_id``.
A PASS from a RUNTIME_DETECTION diagnostic means the permitted observation succeeded, not that
the hardware works. Unknown/missing metadata is ``None`` and is never promoted.

Everything is fabricated; no ADB or iOS tool runs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vector_agent.devices.session import DeviceSession, DeviceSessionManager, device_session_manager
from vector_agent.diagnostics.definition import DiagnosticDefinition
from vector_agent.diagnostics.registry import DiagnosticRegistry, create_default_registry
from vector_agent.main import create_app
from vector_agent.models.device import (
    AutomationLevel,
    ConnectionState,
    DiagnosticApplicability,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    PlannedDiagnostic,
    Platform,
    ScanMode,
    ScanPlan,
    ScanRequest,
    ScanSummary,
    TrustEngineStatus,
    VerificationLevel,
)
from vector_agent.scan import ScanLifecycleState, ScanOrchestrator, ScanPlanner, ScanSession
from vector_agent.scan.events import DiagnosticEvent, DiagnosticEventType
from vector_agent.scan.service import scan_service

NOW = datetime.now(UTC)
RUNTIME = VerificationLevel.RUNTIME_DETECTION
FUNCTIONAL = VerificationLevel.FUNCTIONAL_VERIFICATION
REFERENCE = VerificationLevel.REFERENCE_COMPARISON

ANDROID_IDS = {
    "battery_telemetry",
    "storage_telemetry",
    "memory_telemetry",
    "thermal_telemetry",
    "display_metrics",
    "camera_inventory",
}
IOS_IDS = {
    "software_inventory",
    "battery_charge_telemetry",
    "battery_extended_telemetry",
    "charging_power_telemetry",
    "storage_accounting",
    "developer_mode_state",
}
# Every registered Quick Scan collector is runtime detection today. A new diagnostic must be
# added here deliberately, with its level reviewed, before this test passes again.
EXPECTED_LEVELS = dict.fromkeys(ANDROID_IDS | IOS_IDS, RUNTIME)


# ------------------------------------------------------------------------- helpers


def session(
    platform: Platform = Platform.ANDROID,
    state: ConnectionState = ConnectionState.CONNECTED,
) -> DeviceSession:
    return DeviceSession(
        device_id=f"{platform.value.lower()}-0123456789ab",
        platform=platform,
        connection_state=state,
        last_seen=NOW,
        raw_serial="FABRICATED_SERIAL_2B4",
    )


def full_scan(sess: DeviceSession, registry: DiagnosticRegistry) -> ScanPlan:
    return ScanPlanner().plan(
        sess, registry, ScanRequest(device_id=sess.device_id, mode=ScanMode.FULL_VERIFICATION)
    )


def items(plan: ScanPlan) -> dict[str, PlannedDiagnostic]:
    return {i.diagnostic_id: i for i in plan.planned_items}


class Stub:
    """Runnable fabricated diagnostic with an arbitrary definition."""

    def __init__(
        self,
        diagnostic_id: str,
        level: Any = RUNTIME,
        requires_probe: Any = False,
        platforms: frozenset[Platform] = frozenset({Platform.ANDROID}),
        status: DiagnosticStatus = DiagnosticStatus.PASS,
    ) -> None:
        self.definition = DiagnosticDefinition(
            diagnostic_id=diagnostic_id,
            name=diagnostic_id,
            category="system",
            verification_level=level,
            supported_platforms=platforms,
            requires_probe=requires_probe,
        )
        self._status = status

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(self, *, device_id: str, serial: str) -> DiagnosticResult:
        evidence = (
            [
                EvidenceRecord(
                    diagnostic_id=self.definition.diagnostic_id,
                    device_id=device_id,
                    source_type=EvidenceSourceType.ADB_SHELL,
                    source_name="fabricated",
                    collection_method="fabricated",
                    raw_value="v",
                )
            ]
            if self._status == DiagnosticStatus.PASS
            else []
        )
        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category="system",
            status=self._status,
            automation_level=AutomationLevel.AUTOMATIC,
            evidence=evidence,
            summary="fabricated",
            started_at=NOW,
            completed_at=NOW,
            duration_seconds=0.01,
        )


def registry_of(*diagnostics: Stub) -> DiagnosticRegistry:
    registry = DiagnosticRegistry()
    for d in diagnostics:
        registry.register(d)
    return registry


# ------------------------------------------------------------------------- 1, 2: registry truth


def test_every_registered_diagnostic_exposes_its_correct_level() -> None:
    registry = create_default_registry()
    assert {d.definition.diagnostic_id for d in registry.get_all()} == set(EXPECTED_LEVELS)
    for platform, ids in ((Platform.ANDROID, ANDROID_IDS), (Platform.IOS, IOS_IDS)):
        plan = full_scan(session(platform), registry)
        by_id = items(plan)
        assert set(by_id) == set(EXPECTED_LEVELS)
        for diagnostic_id, level in EXPECTED_LEVELS.items():
            assert by_id[diagnostic_id].verification_level == level, diagnostic_id
            assert by_id[diagnostic_id].requires_probe is False, diagnostic_id
        assert {i for i, p in by_id.items() if p.applicability.value == "APPLICABLE"} == ids


def test_no_quick_scan_diagnostic_is_classified_as_functional() -> None:
    plan = full_scan(session(), create_default_registry())
    assert all(i.verification_level == RUNTIME for i in plan.planned_items)
    assert not any(i.verification_level == FUNCTIONAL for i in plan.planned_items)


def test_metadata_is_derived_from_the_definition_not_hardcoded() -> None:
    registry = registry_of(
        Stub("a_runtime", RUNTIME, False),
        Stub("b_functional", FUNCTIONAL, False),
        Stub("c_reference", REFERENCE, True),
        Stub("d_probe_functional", FUNCTIONAL, True),
    )
    by_id = items(full_scan(session(), registry))
    assert (by_id["a_runtime"].verification_level, by_id["a_runtime"].requires_probe) == (
        RUNTIME,
        False,
    )
    assert (by_id["b_functional"].verification_level, by_id["b_functional"].requires_probe) == (
        FUNCTIONAL,
        False,
    )
    assert (by_id["c_reference"].verification_level, by_id["c_reference"].requires_probe) == (
        REFERENCE,
        True,
    )
    assert (
        by_id["d_probe_functional"].verification_level,
        by_id["d_probe_functional"].requires_probe,
    ) == (FUNCTIONAL, True)
    # Changing only the definition changes only that item's metadata.
    swapped = registry_of(Stub("a_runtime", FUNCTIONAL, True), Stub("b_functional", RUNTIME, False))
    swapped_items = items(full_scan(session(), swapped))
    assert swapped_items["a_runtime"].verification_level == FUNCTIONAL
    assert swapped_items["b_functional"].verification_level == RUNTIME


@pytest.mark.parametrize(
    "mode,request_kwargs",
    [
        (ScanMode.FULL_VERIFICATION, {}),
        (ScanMode.CATEGORY_VERIFICATION, {"category": "battery"}),
        (
            ScanMode.SELECTED_DIAGNOSTICS,
            {"diagnostic_ids": ["camera_inventory", "battery_telemetry"]},
        ),
        (ScanMode.SINGLE_COMPONENT, {"diagnostic_ids": ["display_metrics"]}),
    ],
)
def test_every_request_mode_keeps_metadata_with_the_right_id(
    mode: ScanMode, request_kwargs: dict[str, Any]
) -> None:
    registry = create_default_registry()
    sess = session()
    plan = ScanPlanner().plan(
        sess, registry, ScanRequest(device_id=sess.device_id, mode=mode, **request_kwargs)
    )
    assert plan.planned_items
    ids = [i.diagnostic_id for i in plan.planned_items]
    assert len(ids) == len(set(ids))  # one item per diagnostic id: the join key is unambiguous
    for item in plan.planned_items:
        defn = registry.get_definition(item.diagnostic_id)
        assert defn is not None
        assert item.verification_level == defn.verification_level
        assert item.requires_probe == defn.requires_probe
    if mode == ScanMode.SELECTED_DIAGNOSTICS:
        assert ids == ["camera_inventory", "battery_telemetry"]  # request order preserved


# ------------------------------------------------------------------------- 3: Probe truth


def test_requires_probe_is_truthful_and_a_probe_check_is_never_presented_as_operational() -> None:
    registry = registry_of(Stub("needs_probe", FUNCTIONAL, True), Stub("host_only", RUNTIME, False))
    by_id = items(full_scan(session(), registry))
    probe = by_id["needs_probe"]
    assert probe.requires_probe is True and probe.verification_level == FUNCTIONAL
    assert probe.applicability == DiagnosticApplicability.UNAVAILABLE  # nothing installs a Probe
    assert probe.reason and "Probe" in probe.reason
    assert by_id["host_only"].requires_probe is False
    assert by_id["host_only"].applicability == DiagnosticApplicability.APPLICABLE
    plan = full_scan(session(), registry)
    assert "needs_probe" not in plan.diagnostics_planned


def test_no_registered_diagnostic_requires_a_probe_today() -> None:
    assert not any(d.definition.requires_probe for d in create_default_registry().get_all())


# ------------------------------------------------------------------------- 4, 5: applicability


def test_android_and_ios_applicability_is_unchanged_and_not_applicable_stays_distinct() -> None:
    registry = create_default_registry()
    android = items(full_scan(session(Platform.ANDROID), registry))
    ios = items(full_scan(session(Platform.IOS), registry))
    for diagnostic_id in ANDROID_IDS:
        assert android[diagnostic_id].applicability == DiagnosticApplicability.APPLICABLE
        assert ios[diagnostic_id].applicability == DiagnosticApplicability.NOT_APPLICABLE
    for diagnostic_id in IOS_IDS:
        assert ios[diagnostic_id].applicability == DiagnosticApplicability.APPLICABLE
        assert android[diagnostic_id].applicability == DiagnosticApplicability.NOT_APPLICABLE
    # Metadata is present for every item, including those that do not apply.
    for item in (*android.values(), *ios.values()):
        assert item.verification_level == RUNTIME and item.requires_probe is False


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ConnectionState.UNAUTHORIZED, DiagnosticApplicability.RESTRICTED),
        (ConnectionState.OFFLINE, DiagnosticApplicability.UNAVAILABLE),
    ],
)
def test_not_applicable_is_distinguishable_from_unavailable_or_restricted_checks(
    state: ConnectionState, expected: DiagnosticApplicability
) -> None:
    by_id = items(full_scan(session(Platform.ANDROID, state), create_default_registry()))
    for diagnostic_id in ANDROID_IDS:
        assert by_id[diagnostic_id].applicability == expected
        assert by_id[diagnostic_id].verification_level == RUNTIME
    for diagnostic_id in IOS_IDS:  # the other platform's checks never "apply" or "fail" here
        assert by_id[diagnostic_id].applicability == DiagnosticApplicability.NOT_APPLICABLE


# ------------------------------------------------------------------------- 6: PASS semantics


def test_a_runtime_detection_pass_is_not_functional_verification() -> None:
    real_def = create_default_registry().get_definition("battery_telemetry")
    assert real_def is not None
    stub = Stub("battery_telemetry", real_def.verification_level, real_def.requires_probe)
    registry = registry_of(stub)
    manager = DeviceSessionManager()
    sess = session()
    manager._sessions[sess.device_id] = sess
    plan = full_scan(sess, registry)
    scan = ScanSession(device_id=sess.device_id, plan=plan)
    scan.transition_to(ScanLifecycleState.PLANNED)
    ScanOrchestrator(manager, registry).run_scan(scan)

    assert scan.state == ScanLifecycleState.COMPLETED
    result = scan.diagnostic_results[0]
    assert result.status == DiagnosticStatus.PASS and result.evidence
    level_by_id = {i.diagnostic_id: i.verification_level for i in plan.planned_items}
    assert level_by_id[result.diagnostic_id] == RUNTIME  # a PASS here proves collection only
    assert level_by_id[result.diagnostic_id] != FUNCTIONAL


def test_every_result_joins_to_exactly_one_plan_item() -> None:
    registry = registry_of(Stub("d0", RUNTIME), Stub("d1", FUNCTIONAL), Stub("d2", RUNTIME))
    manager = DeviceSessionManager()
    sess = session()
    manager._sessions[sess.device_id] = sess
    plan = full_scan(sess, registry)
    scan = ScanSession(device_id=sess.device_id, plan=plan)
    scan.transition_to(ScanLifecycleState.PLANNED)
    ScanOrchestrator(manager, registry).run_scan(scan)
    by_id = items(plan)
    assert {r.diagnostic_id for r in scan.diagnostic_results} == set(by_id)
    for result in scan.diagnostic_results:
        assert (
            by_id[result.diagnostic_id].verification_level
            == registry.get_definition(result.diagnostic_id).verification_level
        )  # type: ignore[union-attr]


# ------------------------------------------------------------------------- 7: fail closed


@pytest.mark.parametrize(
    "bad", [None, "", "FUNCTIONAL", "functional_verification", "BOGUS", 3, [], object()]
)
def test_a_missing_or_unknown_level_is_unknown_never_functional(bad: Any) -> None:
    item = items(full_scan(session(), registry_of(Stub("odd", bad))))["odd"]
    assert item.verification_level is None
    assert item.verification_level != FUNCTIONAL


def test_a_valid_level_given_as_a_plain_string_is_recognised() -> None:
    item = items(full_scan(session(), registry_of(Stub("s", "RUNTIME_DETECTION"))))["s"]
    assert item.verification_level == RUNTIME


@pytest.mark.parametrize("bad", [None, "yes", 1, 0, [], "False"])
def test_a_non_boolean_probe_requirement_is_unknown_not_false(bad: Any) -> None:
    item = items(full_scan(session(), registry_of(Stub("odd", RUNTIME, bad))))["odd"]
    assert item.requires_probe is None


def test_the_model_defaults_are_unknown_and_unknown_values_are_rejected() -> None:
    legacy = PlannedDiagnostic(diagnostic_id="x", applicability=DiagnosticApplicability.APPLICABLE)
    assert legacy.verification_level is None and legacy.requires_probe is None
    with pytest.raises(ValidationError):
        PlannedDiagnostic(
            diagnostic_id="x",
            applicability=DiagnosticApplicability.APPLICABLE,
            verification_level="BOGUS",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        PlannedDiagnostic.model_validate_json(
            '{"diagnostic_id":"x","applicability":"APPLICABLE","verification_level":"functional"}'
        )


# ------------------------------------------------------------------------- 9: serialization / API


@pytest.fixture
def api() -> Iterator[TestClient]:
    device_session_manager._sessions.clear()
    scan_service.clear()
    sess = session()
    device_session_manager._sessions[sess.device_id] = sess
    yield TestClient(create_app(), base_url="http://127.0.0.1:8742")
    device_session_manager._sessions.clear()
    scan_service.clear()


LEGACY_ITEM_KEYS = {"diagnostic_id", "applicability", "reason"}
NEW_ITEM_KEYS = {"verification_level", "requires_probe"}


def test_plan_endpoint_exposes_the_metadata_additively(api: TestClient) -> None:
    device_id = next(iter(device_session_manager._sessions))
    response = api.post(
        "/api/v1/scans/plan", json={"device_id": device_id, "mode": "FULL_VERIFICATION"}
    )
    assert response.status_code == 200
    plan = response.json()
    assert set(plan["planned_items"][0]) == LEGACY_ITEM_KEYS | NEW_ITEM_KEYS
    for item in plan["planned_items"]:
        assert item["verification_level"] == "RUNTIME_DETECTION"
        assert item["requires_probe"] is False
    # Legacy plan fields and computed fields are exactly as before.
    assert set(plan) == {
        "plan_id",
        "device_id",
        "platform",
        "mode",
        "diagnostics_requested",
        "diagnostics_planned",
        "diagnostics_skipped",
        "planned_items",
        "planning_session_epoch",
        "capability_profiled_at",
        "registry_diagnostic_ids",
        "created_at",
        "skip_reasons",
        "total_planned",
        "total_skipped",
    }
    assert set(plan["diagnostics_planned"]) == ANDROID_IDS
    assert set(plan["diagnostics_skipped"]) == IOS_IDS


def test_scan_retrieval_keeps_the_plan_result_association(api: TestClient) -> None:
    device_id = next(iter(device_session_manager._sessions))
    scan = scan_service.create_scan(
        ScanRequest(device_id=device_id, mode=ScanMode.FULL_VERIFICATION)
    )
    scan.transition_to(ScanLifecycleState.RUNNING)
    result = Stub("battery_telemetry").execute(device_id=device_id, serial="x")
    scan.record_result(result)
    for path in (f"/api/v1/scans/{scan.scan_id}", f"/api/v1/scans/{scan.scan_id}/results"):
        body = api.get(path).json()
        levels = {
            i["diagnostic_id"]: i["verification_level"] for i in body["plan"]["planned_items"]
        }
        assert [r["diagnostic_id"] for r in body["diagnostic_results"]] == ["battery_telemetry"]
        assert levels["battery_telemetry"] == "RUNTIME_DETECTION"
        assert body["diagnostic_results"][0]["status"] == "PASS"
        assert "verification_level" not in body["diagnostic_results"][0]  # no duplicate metadata


def test_plan_round_trips_and_legacy_plans_without_the_fields_still_parse() -> None:
    plan = full_scan(session(), create_default_registry())
    assert ScanPlan.model_validate_json(plan.model_dump_json()) == plan
    legacy = json.loads(plan.model_dump_json())
    for item in legacy["planned_items"]:
        del item["verification_level"], item["requires_probe"]
    parsed = ScanPlan.model_validate(legacy)
    assert all(
        i.verification_level is None and i.requires_probe is None for i in parsed.planned_items
    )


# ------------------------------------------------------------------------- 10, 11: nothing else changes


def test_public_models_gain_exactly_the_two_approved_fields() -> None:
    assert set(PlannedDiagnostic.model_fields) == LEGACY_ITEM_KEYS | NEW_ITEM_KEYS
    assert set(DiagnosticResult.model_fields) == {
        "automation_level", "category", "completed_at", "diagnostic_id", "diagnostic_name",
        "duration_seconds", "evidence", "started_at", "status", "summary",
    }  # fmt: skip
    assert set(DiagnosticEvent.model_fields) == {
        "device_id", "diagnostic_id", "event_id", "event_type", "evidence", "message",
        "progress", "result", "scan_id", "timestamp",
    }  # fmt: skip
    assert set(EvidenceRecord.model_fields) == {
        "collection_method", "confidence", "device_id", "diagnostic_id", "error", "evidence_id",
        "metadata", "normalized_value", "raw_value", "redacted", "reliability", "source_name",
        "source_type", "timestamp", "unit",
    }  # fmt: skip
    assert set(ScanSummary.model_fields) == {
        "completed_at", "created_at", "device_id", "diagnostic_results", "error", "plan",
        "scan_id", "started_at", "state", "trust_confidence", "trust_engine_status", "trust_score",
    }  # fmt: skip


def test_scan_events_and_evidence_are_unchanged_by_the_metadata() -> None:
    registry = registry_of(Stub("d0"), Stub("d1", FUNCTIONAL))
    manager = DeviceSessionManager()
    sess = session()
    manager._sessions[sess.device_id] = sess
    plan = full_scan(sess, registry)
    scan = ScanSession(device_id=sess.device_id, plan=plan)
    scan.transition_to(ScanLifecycleState.PLANNED)
    events: list[DiagnosticEvent] = []
    ScanOrchestrator(manager, registry).run_scan(scan, event_callback=events.append)
    assert [e.event_type for e in events] == [
        DiagnosticEventType.SCAN_STARTED,
        DiagnosticEventType.DIAGNOSTIC_STARTED,
        DiagnosticEventType.DIAGNOSTIC_EVIDENCE,
        DiagnosticEventType.DIAGNOSTIC_COMPLETED,
        DiagnosticEventType.DIAGNOSTIC_STARTED,
        DiagnosticEventType.DIAGNOSTIC_EVIDENCE,
        DiagnosticEventType.DIAGNOSTIC_COMPLETED,
        DiagnosticEventType.SCAN_COMPLETED,
    ]
    assert [e.diagnostic_id for e in events if e.diagnostic_id] == ["d0"] * 3 + ["d1"] * 3
    assert all(
        r.status == DiagnosticStatus.PASS and len(r.evidence) == 1 for r in scan.diagnostic_results
    )


def test_no_trust_score_health_or_authenticity_is_fabricated() -> None:
    sess = session()
    scan = ScanSession(device_id=sess.device_id, plan=full_scan(sess, create_default_registry()))
    summary = scan.to_summary()
    assert summary.trust_engine_status == TrustEngineStatus.NOT_READY
    assert summary.trust_score is None and summary.trust_confidence is None
    dumped = summary.model_dump_json().lower()
    for forbidden in ("authentic", "genuine", "health_score", "health_percentage", "oem_"):
        assert forbidden not in dumped
    # The unverified OEM catalog is not reachable from any scan or API module.
    root = Path(__file__).resolve().parents[1] / "src" / "vector_agent"
    for folder in ("api", "scan", "diagnostics"):
        for source in (root / folder).rglob("*.py"):
            assert not re.search(
                r"vector_agent\.reference|from \.+reference", source.read_text("utf-8")
            ), source
