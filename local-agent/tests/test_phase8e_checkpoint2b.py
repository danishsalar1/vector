"""2B: Java/Robolectric replay and fabricated negative inputs, never handset qualification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.cross_language_contract import Frame, fabricated_owner, replay, scenario
from vector_agent.models.device import DeviceIdentity, EvidenceSourceType, Platform
from vector_agent.models.probe import ProbeChallengeBinding
from vector_agent.models.probe import ProbeOperation as Operation
from vector_agent.models.probe_diagnostics import DiagnosticReport
from vector_agent.models.reference import ComparisonOutcome as Outcome
from vector_agent.models.reference import ResolutionStatus
from vector_agent.probe.diagnostic_evidence import diagnostic_result
from vector_agent.probe.lifecycle import DiagnosticSessionError, DiagnosticUnavailableError
from vector_agent.reference import (
    DiagnosticEvidenceAdapter,
    SpecificationComparator,
    build_seed_catalog,
)
from vector_agent.reference.resolver import DeviceResolver


def test_repeated_terminal_poll_cannot_gain_new_attribution():
    manager, owner, result = fabricated_result()
    from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
    from vector_agent.probe.lifecycle import ProbeConnection

    connection = ProbeConnection(manager, owner, AndroidProbeBridge(serial="FABRICATED"), None)
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    duplicate = result.model_copy(deep=True)
    for record in duplicate.evidence:
        record.evidence_id = uuid4()  # normalizer can issue new IDs for another terminal fetch
        record.timestamp = datetime.now(UTC)
    # Unit-only lifecycle seam; wire authenticity is covered by genuine replay tests.
    with patch.object(connection, "diagnostic", side_effect=[result, duplicate]):
        first = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
        repeated = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert first.report.consistent_count == 1
    assert not repeated.transport_attributed
    assert repeated.report.consistent_count == repeated.report.differs_count == 0
    assert repeated.diagnostic_result == duplicate


@pytest.mark.parametrize("key", ["probe_session_id", "challenge_id"])
def test_different_contexts_on_distinct_metrics_cannot_be_merged(key):
    _, owner, result = fabricated_result()
    result.evidence[1].metadata[key] = str(uuid4())
    compared = unit_admission(result, owner)
    assert compared.rejection is not None
    assert compared.report.consistent_count == compared.report.differs_count == 0


def test_missing_unit_cannot_be_replaced_and_missing_error_value_cannot_pass():
    _, owner, result = fabricated_result()
    result.evidence[0].error = "UNSUPPORTED_MEASUREMENT"
    compared = unit_admission(result, owner)
    assert not compared.uses[0].admitted
    assert by_property(compared)["sensors.nfc_present"].outcome == Outcome.INSUFFICIENT_EVIDENCE


def test_existing_variant_guard_is_exercised_by_admitted_declaration():
    from vector_agent.reference import ReferenceCatalog, build_seed_payload, import_catalog_payload

    payload = build_seed_payload()
    pixels = [v for v in payload["variants"] if v["model_id"] == "pixel-7-pro"]
    pixels[0]["specifications"]["sensors"]["nfc"] = True
    pixels[1]["specifications"]["sensors"]["nfc"] = False
    catalog = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, catalog)
    _, owner, result = fabricated_result()
    compared = unit_admission(result, owner, catalog)
    assert by_property(compared)["sensors.nfc_present"].outcome == Outcome.VARIANT_AMBIGUOUS
    assert by_property(compared)["sensors.nfc_present"].observed_value is None


def test_missing_reference_remains_unavailable_with_admitted_evidence():
    from vector_agent.reference import ReferenceCatalog

    _, owner, result = fabricated_result()
    compared = unit_admission(result, owner, ReferenceCatalog(test_only=True))
    assert all(item.outcome == Outcome.REFERENCE_UNAVAILABLE for item in compared.report.items)


def test_invalid_normalized_outcome_is_not_accepted():
    _, owner, result = fabricated_result()
    result.status = "PASS"
    compared = unit_admission(result, owner)
    assert compared.rejection is not None
    assert compared.report.consistent_count == compared.report.differs_count == 0


def fabricated_result(
    metrics=None,
    diagnostic_id="connectivity",
    *,
    state="COMPLETED",
    outcome="INCONCLUSIVE",
    reason="CAPABILITY_ONLY",
):
    """Unit-only software input. Does NOT establish actual transport or hardware evidence."""
    manager, owner = fabricated_owner()
    owner.identity = DeviceIdentity(
        platform=Platform.ANDROID, manufacturer="Google", model="Pixel 7 Pro"
    )
    report = DiagnosticReport.model_validate(
        {
            "schema_version": 1,
            "diagnostic_id": diagnostic_id,
            "state": state,
            "outcome": outcome,
            "reason": reason,
            "elapsed_ms": 100,
            "metrics": tuple(
                metrics
                if metrics is not None
                else [
                    {"name": "feature_nfc", "value": 1, "unit": "boolean"},
                    {"name": "feature_barometer", "value": 0, "unit": "boolean"},
                ]
            ),
        }
    )
    binding = ProbeChallengeBinding(
        scan_id=str(uuid4()),
        diagnostic_id=diagnostic_id,
        attempt_id=str(uuid4()),
        challenge_id=str(uuid4()),
        collection_not_before=datetime.now(UTC),
    )
    result = diagnostic_result(
        report,
        device_id=owner.device_id,
        epoch=owner.session_epoch,
        session_id=str(uuid4()),
        binding=binding,
    )
    return manager, owner, result


def unit_admission(result, owner, catalog=None):
    """Exercise private admission rules with explicit synthetic internal context.

    Public authenticated entry is tested separately using genuine Java wire replay.
    This helper is not proof that fabricated results can enter the public trusted API.
    """
    return DiagnosticEvidenceAdapter(catalog or build_seed_catalog(test_only=True))._compare(
        result, owner=owner, epoch=owner.session_epoch, attributed=True
    )


def by_property(compared):
    return {item.property_path: item for item in compared.report.items}


@pytest.mark.parametrize(
    "name", ["storage", "camera", "touch_display", "audio_haptics", "sensors_battery"]
)
def test_entire_genuine_java_scenario_through_adapter(name):
    with replay(name) as run:
        run.connection.connect()
        owner = run.manager.list_sessions()[0]
        assert owner.identity is None  # Never inject a convenient regional identity.
        adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
        for exchange in scenario(name)["exchanges"][2:]:
            if exchange["status"] == "UNAVAILABLE":
                with pytest.raises(DiagnosticUnavailableError):
                    adapter.collect_and_compare(
                        run.connection,
                        Operation(exchange["op"]),
                        exchange.get("diagnostic_id"),
                        owner=owner,
                        manager=run.manager,
                    )
                continue
            compared = adapter.collect_and_compare(
                run.connection,
                Operation(exchange["op"]),
                exchange.get("diagnostic_id"),
                owner=owner,
                manager=run.manager,
            )
            assert compared.rejection is None
            assert compared.report.resolution.status == ResolutionStatus.UNKNOWN_DEVICE
            assert all(i.outcome == Outcome.REFERENCE_UNAVAILABLE for i in compared.report.items)
            assert compared.report.consistent_count == compared.report.differs_count == 0
            assert compared.qualification == "CODE_TESTED"
            assert compared.authenticity.value == "UNKNOWN"
            expected = run.connection._diagnostic_last
            assert expected is not None
            records = compared.diagnostic_result.evidence
            assert [(e.source_name, e.normalized_value, e.unit) for e in records] == [
                (m.name, m.value, m.unit) for m in expected.metrics
            ]
            assert [e.evidence_id for e in records] == [u.evidence_id for u in compared.uses]
            assert all(e.metadata["device_session_epoch"] == owner.session_epoch for e in records)
            assert not any(
                u.admitted for u in compared.uses
            )  # These transcripts have no connectivity report.
        assert run.peer.errors == []
        assert len(run.peer.received) == len(scenario(name)["exchanges"])


def test_only_completed_feature_declarations_are_comparable_unit_control():
    _, owner, result = fabricated_result()
    compared = unit_admission(result, owner)
    items = by_property(compared)
    assert items["sensors.nfc_present"].outcome == Outcome.CONSISTENT_WITH_REFERENCE
    # FR-06: with the variant unresolved, a difference from the catalogued candidates'
    # consensus is withheld as ambiguous instead of asserted as a mismatch.
    assert items["sensors.barometer_present"].outcome == Outcome.VARIANT_AMBIGUOUS
    assert items["sensors.barometer_present"].observed_value is False
    assert any(
        "Mismatch verdict withheld" in text
        for text in items["sensors.barometer_present"].limitations
    )
    assert all(u.admitted for u in compared.uses)
    assert compared.report.resolution.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert compared.report.resolution.resolved_variant is None
    assert compared.diagnostic_result == result
    compared.diagnostic_result.evidence[0].metadata["qualification"] = "tampered"
    assert result.evidence[0].metadata["qualification"] == "CODE_TESTED"


@pytest.mark.parametrize(
    "status,reason,state",
    [
        ("INCONCLUSIVE", "PARTIAL", "COMPLETED"),
        ("INCONCLUSIVE", "COLLECTING", "RUNNING"),
        ("INCONCLUSIVE", "STOPPING", "RUNNING"),
        ("INCONCLUSIVE", "CANCELLED", "CANCELLED"),
        ("INCONCLUSIVE", "TIMEOUT", "EXPIRED"),
        ("ERROR", "EXECUTION_ERROR", "COMPLETED"),
        ("RESTRICTED", "PERMISSION_REQUIRED", "COMPLETED"),
        ("UNSUPPORTED", "HARDWARE_ABSENT", "COMPLETED"),
    ],
)
def test_incomplete_or_error_numeric_declaration_never_matches(status, reason, state):
    _, owner, result = fabricated_result(state=state, outcome=status, reason=reason)
    compared = unit_admission(result, owner)
    assert not any(u.admitted for u in compared.uses)
    assert by_property(compared)["sensors.nfc_present"].outcome == Outcome.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    "name,value,unit,diagnostic_id,path",
    [
        ("charge_counter", 4926000, "uAh", "battery", "battery.rated_capacity_mah"),
        ("ram_total", 12 * 1024**3, "bytes", "system", "memory.ram_total_bytes"),
        ("ram_available", 12 * 1024**3, "bytes", "system", "memory.ram_total_bytes"),
        ("width", 1440, "pixels", "display", "display.resolution"),
        ("height", 3120, "pixels", "display", "display.resolution"),
        ("refresh_rate", 120, "Hz", "display", "display.refresh_rate_hz"),
        ("mode7_rate", 120, "Hz", "display", "display.refresh_rate_hz"),
        ("mode0_width", 1440, "pixels", "display", "display.resolution"),
        ("mode_count", 9, "count", "display", "display.resolution"),
    ],
)
def test_valid_units_never_convert_unrelated_telemetry_to_physical_specs(
    name, value, unit, diagnostic_id, path
):
    _, owner, result = fabricated_result(
        [{"name": name, "value": value, "unit": unit}], diagnostic_id, reason="TELEMETRY_ONLY"
    )
    compared = unit_admission(result, owner)
    assert compared.rejection is None
    assert by_property(compared)[path].outcome == Outcome.NOT_COMPARABLE
    assert by_property(compared)[path].observed_value is None
    assert compared.diagnostic_result.evidence[0].normalized_value == value
    assert compared.diagnostic_result.evidence[0].unit == unit


@pytest.mark.parametrize("name,value", [("feature_nfc", None), ("nfc_enabled", 1)])
def test_missing_and_toggle_never_become_hardware_presence(name, value):
    _, owner, result = fabricated_result([{"name": name, "value": value, "unit": "boolean"}])
    compared = unit_admission(result, owner)
    assert by_property(compared)["sensors.nfc_present"].outcome == Outcome.INSUFFICIENT_EVIDENCE
    assert by_property(compared)["sensors.nfc_present"].observed_value is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", None),
        ("unit", "count"),
        ("unit", "unknown"),
        ("normalized_value", True),
        ("normalized_value", "1"),
        ("normalized_value", float("nan")),
        ("normalized_value", float("inf")),
        ("normalized_value", -1),
        ("normalized_value", 2),
        ("normalized_value", 2**54),
        ("normalized_value", {"value": 1}),
        ("source_name", "feature_5g_mmwave"),
        ("source_name", "cpu_cores"),
        ("source_name", "rear_camera_count"),
        ("source_type", EvidenceSourceType.USER_ASSISTED),
        ("source_type", EvidenceSourceType.SYNTHETIC_TEST_ONLY),
        ("device_id", "android-000000000000"),
    ],
)
def test_admission_revalidates_mutated_canonical_record(field, value):
    _, owner, result = fabricated_result()
    setattr(result.evidence[0], field, value)
    compared = unit_admission(result, owner)
    assert compared.rejection is not None
    assert not compared.transport_attributed
    assert not any(u.admitted for u in compared.uses)
    assert compared.report.consistent_count == compared.report.differs_count == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("qualification", "HARDWARE_VALIDATED"),
        ("qualification", None),
        ("authenticity", "VERIFIED_GENUINE"),
        ("probe_session_id", None),
        ("challenge_id", None),
        ("device_session_epoch", True),
        ("device_session_epoch", 999),
        ("collection_state", "UNAVAILABLE"),
        ("reason", "MADE_UP"),
        ("reason", "READBACK_MATCH"),
        ("collection_elapsed_ms", -1),
    ],
)
def test_invalid_or_missing_context_never_admits(field, value):
    _, owner, result = fabricated_result()
    for record in result.evidence:
        record.metadata[field] = value
    compared = unit_admission(result, owner)
    assert compared.rejection is not None
    assert compared.report.consistent_count == compared.report.differs_count == 0


@pytest.mark.parametrize(
    "change", ["value", "unit", "session", "device", "challenge", "human", "restricted"]
)
def test_duplicate_conflicts_are_order_independent(change):
    _, owner, result = fabricated_result()
    duplicate = result.evidence[0].model_copy(deep=True, update={"evidence_id": uuid4()})
    if change == "value":
        duplicate.normalized_value = 0
    elif change == "unit":
        duplicate.unit = "count"
    elif change == "session":
        duplicate.metadata["probe_session_id"] = str(uuid4())
    elif change == "challenge":
        duplicate.metadata["challenge_id"] = str(uuid4())
    elif change == "device":
        duplicate.device_id = "android-000000000000"
    elif change == "human":
        duplicate.source_type = EvidenceSourceType.USER_ASSISTED
    elif change == "restricted":
        duplicate.metadata["reason"] = "PERMISSION_REQUIRED"
    result.evidence.append(duplicate)
    forward = unit_admission(result, owner)
    result.evidence.reverse()
    reverse = unit_admission(result, owner)
    assert forward.rejection is not None and reverse.rejection == forward.rejection
    assert forward.report.items == reverse.report.items
    assert len(forward.diagnostic_result.evidence) == 3
    assert forward.report.consistent_count == forward.report.differs_count == 0


def test_exact_duplicate_record_is_idempotent_but_distinct_samples_are_not_selected():
    _, owner, result = fabricated_result()
    original = unit_admission(result, owner)
    result.evidence.append(result.evidence[0].model_copy(deep=True))
    duplicated = unit_admission(result, owner)
    assert duplicated.report.items == original.report.items
    assert duplicated.diagnostic_result.evidence[-1].timestamp == result.evidence[0].timestamp
    assert len(duplicated.uses) == len(original.uses)
    assert duplicated.uses == original.uses
    result.evidence[-1].evidence_id = uuid4()
    ambiguous_samples = unit_admission(result, owner)
    assert ambiguous_samples.rejection is not None
    assert ambiguous_samples.report.consistent_count == 0


def test_repeated_id_with_conflicting_value_is_rejected():
    _, owner, result = fabricated_result()
    result.evidence.append(
        result.evidence[0].model_copy(deep=True, update={"normalized_value": 0.0})
    )
    assert unit_admission(result, owner).rejection is not None


def test_unverified_records_and_flat_dictionaries_cannot_claim_pipeline_attribution():
    _, owner, result = fabricated_result()
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    supplied = adapter.compare(result, owner=owner)
    assert not supplied.transport_attributed and not any(u.admitted for u in supplied.uses)
    assert supplied.report.consistent_count == supplied.report.differs_count == 0
    with pytest.raises(TypeError):
        adapter.compare(result.model_dump(), owner=owner)
    with pytest.raises(TypeError):
        adapter.collect_and_compare(result, Operation.FETCH_OBSERVATIONS, owner=owner, manager=None)


def test_corrupt_java_bytes_cannot_reach_comparison():
    def corrupt(index, frame):
        wire = bytearray(frame.encoded())
        if index == 3:
            wire[-2] ^= 1
        return bytes(wire)

    with replay("storage", responder=corrupt) as run:
        run.connection.connect()
        owner = run.manager.list_sessions()[0]
        adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
        adapter.collect_and_compare(
            run.connection, Operation.START_CHALLENGE, "storage", owner=owner, manager=run.manager
        )
        with pytest.raises(DiagnosticSessionError):
            adapter.collect_and_compare(
                run.connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=run.manager
            )


@pytest.mark.parametrize("field", ["probe_session_id", "device_epoch", "binding"])
def test_authenticated_but_wrong_java_response_context_rejected_by_existing_transport(field):
    import json

    def corrupt_context(index, frame):
        data = frame.json()
        if index == 3:
            if field == "binding":
                data["binding"]["challenge_id"] = str(uuid4())
            elif field == "device_epoch":
                data[field] += 1
            else:
                data[field] = str(uuid4())
            return Frame.sign(
                "response", json.dumps(data, separators=(",", ":")).encode()
            ).encoded()
        return frame.encoded()

    with replay("storage", responder=corrupt_context) as run:
        run.connection.connect()
        owner = run.manager.list_sessions()[0]
        adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
        adapter.collect_and_compare(
            run.connection, Operation.START_CHALLENGE, "storage", owner=owner, manager=run.manager
        )
        with pytest.raises(DiagnosticSessionError):
            adapter.collect_and_compare(
                run.connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=run.manager
            )


def test_stale_desktop_owner_rejected_before_exchange():
    with replay("storage") as run:
        run.connection.connect()
        owner = run.manager.list_sessions()[0]
        run.manager.mark_platform_offline(Platform.ANDROID)
        with pytest.raises(ValueError, match="owner"):
            DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True)).collect_and_compare(
                run.connection,
                Operation.START_CHALLENGE,
                "storage",
                owner=owner,
                manager=run.manager,
            )
        assert len(run.peer.received) == 2


@pytest.mark.parametrize("foreign", ["owner", "manager"])
def test_foreign_owner_or_manager_is_rejected_before_any_command(foreign):
    with replay("storage") as run:
        run.connection.connect()
        other_manager, other_owner = fabricated_owner()
        owner = other_owner if foreign == "owner" else run.manager.list_sessions()[0]
        manager = other_manager if foreign == "manager" else run.manager
        with pytest.raises(ValueError, match="different desktop owner"):
            DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True)).collect_and_compare(
                run.connection, Operation.START_CHALLENGE, "storage", owner=owner, manager=manager
            )
        assert len(run.peer.received) == 2


def test_private_caller_values_do_not_escape_comparison_or_repr():
    _, owner, result = fabricated_result()
    result.evidence[0].raw_value = "PRIVATE_TEST_MARKER"
    result.evidence[0].metadata["raw_serial"] = "PRIVATE_TEST_MARKER"
    compared = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True)).compare(
        result, owner=owner
    )
    assert compared.rejection is not None
    assert "PRIVATE_TEST_MARKER" not in compared.report.model_dump_json()
    assert "PRIVATE_TEST_MARKER" not in repr(compared)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", None),
        ("unit", "unknown"),
        ("unit", "mAh"),
        ("normalized_value", True),
        ("normalized_value", "65536"),
        ("normalized_value", float("nan")),
        ("normalized_value", float("inf")),
        ("normalized_value", -1),
        ("normalized_value", 2**54),
        ("normalized_value", []),
        ("source_name", "cpu_cores"),
        ("device_id", "android-000000000000"),
    ],
)
def test_malformed_or_foreign_record_never_enters_comparison(field, value):
    from vector_agent.reference import DiagnosticEvidenceAdapter

    with replay("storage") as run:
        run.connection.connect()
        run.connection.diagnostic(Operation.START_CHALLENGE, "storage")
        result = run.connection.diagnostic(Operation.FETCH_OBSERVATIONS)
        owner = run.manager.list_sessions()[0]
    evidence = next(e for e in result.evidence if e.source_name == "bytes_written")
    setattr(evidence, field, value)  # model mutation bypass: the adapter must fail closed
    compared = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True)).compare(
        result, owner=owner
    )
    assert not any(use.admitted for use in compared.uses)
    assert compared.report.consistent_count == compared.report.differs_count == 0
    assert compared.rejection is not None


@pytest.mark.parametrize("argument", ["evidence_records", "diagnostic_results"])
def test_legacy_compare_must_not_silently_ignore_canonical_evidence(argument):
    with replay("storage") as run:
        run.connection.connect()
        run.connection.diagnostic(Operation.START_CHALLENGE, "storage")
        result = run.connection.diagnostic(Operation.FETCH_OBSERVATIONS)
    catalog = build_seed_catalog(test_only=True)
    values = result.evidence if argument == "evidence_records" else [result]
    with pytest.raises(ValueError, match="DiagnosticEvidenceAdapter"):
        SpecificationComparator(catalog).compare(
            DeviceResolver(catalog).resolve(), {}, **{argument: values}
        )


def test_real_java_result_reaches_public_adapter_without_flattening():
    from vector_agent.reference import DiagnosticEvidenceAdapter

    with replay("storage") as run:
        run.connection.connect()
        owner = run.manager.list_sessions()[0]
        adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
        adapter.collect_and_compare(
            run.connection, Operation.START_CHALLENGE, "storage", owner=owner, manager=run.manager
        )
        compared = adapter.collect_and_compare(
            run.connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=run.manager
        )
        assert run.peer.errors == []
    assert compared.transport_attributed
    assert compared.report.resolution.resolved_variant is None
    assert compared.report.consistent_count == compared.report.differs_count == 0
    written = next(
        e for e in compared.diagnostic_result.evidence if e.source_name == "bytes_written"
    )
    assert (written.normalized_value, written.unit) == (65536, "bytes")
    assert written.evidence_id in {use.evidence_id for use in compared.uses}


def test_caller_records_cannot_inherit_authentication_from_matching_metadata():
    from vector_agent.reference import DiagnosticEvidenceAdapter

    with replay("storage") as run:
        run.connection.connect()
        run.connection.diagnostic(Operation.START_CHALLENGE, "storage")
        result = run.connection.diagnostic(Operation.FETCH_OBSERVATIONS)
        owner = run.manager.list_sessions()[0]
    compared = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True)).compare(
        result, owner=owner
    )
    assert not compared.transport_attributed
    assert not any(use.admitted for use in compared.uses)
    assert compared.report.consistent_count == compared.report.differs_count == 0


# =============================================================================
# QG-01, QG-02, QG-03, QG-04 REGRESSION TESTS (Checkpoint 2B.1)
# =============================================================================


def test_epoch_change_after_diagnostic_exchange_rejects_attribution():
    from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
    from vector_agent.probe.lifecycle import ProbeConnection

    manager, owner, result = fabricated_result()
    connection = ProbeConnection(manager, owner, AndroidProbeBridge(serial="FABRICATED"), None)
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))

    def diagnostic_side_effect(*args, **kwargs):
        owner.session_epoch += 1
        return result

    with (
        patch.object(connection, "diagnostic", side_effect=diagnostic_side_effect),
        pytest.raises(ValueError, match="ownership changed during diagnostic exchange"),
    ):
        adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )


def test_epoch_change_during_comparison_rejects_and_prevents_terminal_recording():
    from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
    from vector_agent.probe.lifecycle import ProbeConnection

    manager, owner, result = fabricated_result()
    connection = ProbeConnection(manager, owner, AndroidProbeBridge(serial="FABRICATED"), None)
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    orig_compare = adapter._compare

    def compare_side_effect(*args, **kwargs):
        owner.session_epoch += 1
        return orig_compare(*args, **kwargs)

    with (
        patch.object(connection, "diagnostic", return_value=result),
        patch.object(adapter, "_compare", side_effect=compare_side_effect),
        pytest.raises(ValueError, match="ownership changed during comparison"),
    ):
        adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert connection not in adapter._terminal


def test_diagnostic_id_mismatch_between_record_and_result_is_rejected():
    _, owner, result = fabricated_result()
    result.evidence[0].diagnostic_id = "storage"
    compared = unit_admission(result, owner)
    assert compared.rejection is not None
    assert not compared.transport_attributed
    assert not any(u.admitted for u in compared.uses)


@pytest.mark.parametrize(
    "invalid_timestamp",
    [
        "2026-10-09T12:00:00Z",
        1728475200,
        None,
        datetime(2026, 10, 9, 12, 0),
        datetime(2026, 10, 9, 12, 0, tzinfo=timezone(timedelta(hours=5))),
    ],
)
def test_invalid_timestamp_types_and_timezones_fail_predictably(invalid_timestamp):
    from vector_agent.reference.evidence_adapter import _validated_report

    _, owner, result = fabricated_result()
    result.evidence[0].timestamp = invalid_timestamp
    with pytest.raises(ValueError):
        _validated_report(result, owner, owner.session_epoch)
    compared = unit_admission(result, owner)
    assert compared.rejection is not None
    assert not compared.transport_attributed


def test_valid_timezone_aware_utc_timestamp_is_accepted():
    from vector_agent.reference.evidence_adapter import _validated_report

    _, owner, result = fabricated_result()
    ts = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    result.evidence[0].timestamp = ts
    report, _ = _validated_report(result, owner, owner.session_epoch)
    assert report is not None
    compared = unit_admission(result, owner)
    assert compared.rejection is None


@pytest.mark.parametrize("bad_owner", [None, "invalid_owner", 12345])
def test_invalid_owner_type_in_compare_raises_type_error(bad_owner):
    _, _, result = fabricated_result()
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    with pytest.raises(TypeError, match="Canonical diagnostic result and desktop owner required"):
        adapter.compare(result, owner=bad_owner)


@pytest.mark.parametrize("bad_result", [None, "invalid_result", {"status": "COMPLETED"}])
def test_invalid_result_type_in_compare_raises_type_error(bad_result):
    _, owner, _ = fabricated_result()
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    with pytest.raises(TypeError, match="Canonical diagnostic result and desktop owner required"):
        adapter.compare(bad_result, owner=owner)


@pytest.mark.parametrize(
    "name,unit,forbidden_negative",
    [
        ("bytes_written", "bytes", True),
        ("width", "pixels", True),
        ("mode_count", "count", True),
        ("refresh_rate", "Hz", True),
        ("charge_counter", "uAh", True),
        ("axis0_mean", "m_s2", False),
        ("axis1_mean", "rad_s", False),
        ("axis2_mean", "celsius", False),
    ],
)
def test_negative_measurement_quantities(name, unit, forbidden_negative):
    from vector_agent.reference.evidence_adapter import _validated_report

    if forbidden_negative:
        diag_id = (
            "storage"
            if unit == "bytes"
            else ("display" if unit in {"pixels", "count", "Hz"} else "battery")
        )
        val = 100 if unit != "Hz" else 60.0
        _, owner, result = fabricated_result(
            metrics=[{"name": name, "value": val, "unit": unit}],
            diagnostic_id=diag_id,
            reason="TELEMETRY_ONLY",
        )
        result.evidence[0].normalized_value = -100.0
        with pytest.raises(ValueError, match="Negative collection quantity"):
            _validated_report(result, owner, owner.session_epoch)
        compared = unit_admission(result, owner)
        assert compared.rejection is not None
    else:
        _, owner, result = fabricated_result(
            metrics=[{"name": name, "value": -9.8, "unit": unit}],
            diagnostic_id="sensor_0",
            reason="SAMPLES_OBSERVED",
        )
        report, _ = _validated_report(result, owner, owner.session_epoch)
        assert report is not None
        assert report.metrics[0].value == -9.8


def test_running_versus_completed_state_coherence():
    from vector_agent.models.device import DiagnosticStatus
    from vector_agent.reference.evidence_adapter import _validated_report

    # Case 1: RUNNING status with COMPLETED metadata state -> rejected
    _, owner, result = fabricated_result(state="COMPLETED", reason="CAPABILITY_ONLY")
    result.status = DiagnosticStatus.RUNNING
    with pytest.raises(ValueError, match="Normalized status disagrees with collection state"):
        _validated_report(result, owner, owner.session_epoch)
    assert unit_admission(result, owner).rejection is not None

    # Case 2: INCONCLUSIVE status with RUNNING metadata state -> rejected
    _, owner, result2 = fabricated_result(state="RUNNING", reason="COLLECTING")
    result2.status = DiagnosticStatus.INCONCLUSIVE
    with pytest.raises(ValueError, match="Normalized status disagrees with collection state"):
        _validated_report(result2, owner, owner.session_epoch)
    assert unit_admission(result2, owner).rejection is not None


def test_evidence_use_binding_and_authority_classification():
    from vector_agent.models.provenance import (
        AuthenticityLabel,
        ProvenanceAuthorityClass,
        ProvenanceSubjectBinding,
    )

    _, owner, result = fabricated_result()
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))

    supplied = adapter.compare(result, owner=owner)
    for use in supplied.uses:
        assert use.binding == ProvenanceSubjectBinding.UNBOUND
        assert use.authority == ProvenanceAuthorityClass.DEVICE_REPORTED_METADATA
        assert use.authority != ProvenanceAuthorityClass.OEM_AUTHORITATIVE
    assert supplied.authenticity == AuthenticityLabel.UNKNOWN
    assert supplied.qualification == "CODE_TESTED"

    attributed = unit_admission(result, owner)
    for use in attributed.uses:
        assert use.binding == ProvenanceSubjectBinding.DEVICE_BOUND
        assert use.authority == ProvenanceAuthorityClass.DEVICE_REPORTED_METADATA
        assert use.authority != ProvenanceAuthorityClass.OEM_AUTHORITATIVE
    assert attributed.authenticity == AuthenticityLabel.UNKNOWN
    assert attributed.qualification == "CODE_TESTED"


@pytest.mark.parametrize(
    "metric_name,val,unit,diag_id,prop",
    [
        ("charge_counter", 4500000, "uAh", "battery", "battery.rated_capacity_mah"),
        ("ram_total", 8 * 1024**3, "bytes", "system", "memory.ram_total_bytes"),
        ("width", 1080, "pixels", "display", "display.resolution"),
        ("refresh_rate", 90, "Hz", "display", "display.refresh_rate_hz"),
    ],
)
def test_lifecycle_telemetry_preserves_not_comparable_conclusion(
    metric_name, val, unit, diag_id, prop
):
    _, owner, result = fabricated_result(
        metrics=[{"name": metric_name, "value": val, "unit": unit}],
        diagnostic_id=diag_id,
        reason="TELEMETRY_ONLY",
    )
    compared = unit_admission(result, owner)
    assert compared.rejection is None
    assert by_property(compared)[prop].outcome == Outcome.NOT_COMPARABLE
    assert by_property(compared)[prop].observed_value is None


@pytest.mark.parametrize("kwarg", ["evidence_records", "diagnostic_results"])
def test_legacy_comparator_explicit_empty_list_triggers_rejection(kwarg):
    catalog = build_seed_catalog(test_only=True)
    comparator = SpecificationComparator(catalog)
    resolution = DeviceResolver(catalog).resolve()
    with pytest.raises(ValueError, match="DiagnosticEvidenceAdapter"):
        comparator.compare(resolution, {}, **{kwarg: []})


def test_new_challenge_after_terminal_poll_receives_attribution():
    """CG-04: Isolates challenge ID component while preserving connection, probe session, and epoch."""
    from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
    from vector_agent.probe.lifecycle import ProbeConnection

    manager, owner, result1 = fabricated_result()
    connection = ProbeConnection(manager, owner, AndroidProbeBridge(serial="FABRICATED"), None)
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))

    with patch.object(connection, "diagnostic", return_value=result1):
        first = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert first.transport_attributed

    with patch.object(connection, "diagnostic", return_value=result1):
        repeated = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert not repeated.transport_attributed

    # CG-04 isolation: Preserves the same probe session ID and desktop epoch from result1,
    # varying ONLY the challenge ID to prove challenge component alone breaks deduplication.
    result2 = result1.model_copy(deep=True)
    new_challenge_id = str(uuid4())
    for r in result2.evidence:
        r.metadata["challenge_id"] = new_challenge_id
    with patch.object(connection, "diagnostic", return_value=result2):
        new_chal = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert new_chal.transport_attributed


def test_new_desktop_epoch_after_terminal_poll_receives_attribution():
    """CG-04: Different authorized desktop epoch receives attribution while session and challenge remain constant."""
    from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
    from vector_agent.probe.lifecycle import ProbeConnection

    manager, owner, result1 = fabricated_result()
    connection = ProbeConnection(manager, owner, AndroidProbeBridge(serial="FABRICATED"), None)
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))

    with patch.object(connection, "diagnostic", return_value=result1):
        first = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert first.transport_attributed

    with patch.object(connection, "diagnostic", return_value=result1):
        repeated = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert not repeated.transport_attributed

    # Advance authorized desktop epoch on owner/manager
    new_epoch = owner.session_epoch + 1
    owner.session_epoch = new_epoch

    result_new_epoch = result1.model_copy(deep=True)
    for r in result_new_epoch.evidence:
        r.metadata["device_session_epoch"] = new_epoch
    with patch.object(connection, "diagnostic", return_value=result_new_epoch):
        new_epoch_res = adapter.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert new_epoch_res.transport_attributed


def test_terminal_deduplication_is_local_to_adapter_instance():
    from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
    from vector_agent.probe.lifecycle import ProbeConnection

    manager, owner, result = fabricated_result()
    connection = ProbeConnection(manager, owner, AndroidProbeBridge(serial="FABRICATED"), None)
    adapter1 = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    adapter2 = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))

    with patch.object(connection, "diagnostic", return_value=result):
        res1 = adapter1.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert res1.transport_attributed

    with patch.object(connection, "diagnostic", return_value=result):
        res2 = adapter2.collect_and_compare(
            connection, Operation.FETCH_OBSERVATIONS, owner=owner, manager=manager
        )
    assert res2.transport_attributed


def test_nfc_toggle_cannot_prove_hardware_presence_even_when_completed():
    _, owner, result = fabricated_result(
        metrics=[{"name": "nfc_enabled", "value": 1, "unit": "boolean"}],
        diagnostic_id="connectivity",
        state="COMPLETED",
        outcome="INCONCLUSIVE",
        reason="CAPABILITY_ONLY",
    )
    compared = unit_admission(result, owner)
    assert not any(u.admitted for u in compared.uses)
    assert by_property(compared)["sensors.nfc_present"].outcome == Outcome.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    "status,state,reason",
    [
        ("RUNNING", "RUNNING", "COLLECTING"),
        ("RESTRICTED", "COMPLETED", "PERMISSION_REQUIRED"),
        ("UNSUPPORTED", "COMPLETED", "HARDWARE_ABSENT"),
    ],
)
def test_zero_metric_lifecycle_response_has_truthful_disclaimer(status, state, reason):
    from vector_agent.models.device import DiagnosticResult, DiagnosticStatus

    manager, owner = fabricated_owner()
    empty_result = DiagnosticResult.model_validate(
        {
            "diagnostic_id": "connectivity",
            "diagnostic_name": "Connectivity Diagnostic",
            "category": "HARDWARE",
            "automation_level": "AUTOMATIC",
            "status": DiagnosticStatus(status),
            "evidence": [],
        }
    )
    adapter = DiagnosticEvidenceAdapter(build_seed_catalog(test_only=True))
    compared = adapter._compare(
        empty_result, owner=owner, epoch=owner.session_epoch, attributed=True
    )
    assert not compared.transport_attributed
    assert (
        "Authenticated lifecycle exchange produced no diagnostic evidence"
        in compared.report.honesty_disclaimer
    )
    assert "Unverified supplied evidence" not in compared.report.honesty_disclaimer
    assert len(compared.uses) == 0

    supplied = adapter.compare(empty_result, owner=owner)
    assert not supplied.transport_attributed
    assert (
        "Unverified supplied evidence; no authenticated Probe attribution"
        in supplied.report.honesty_disclaimer
    )
    assert "Authenticated lifecycle exchange" not in supplied.report.honesty_disclaimer


def test_duplicate_evidence_record_produces_single_evidence_use_order_independent():
    _, owner, result = fabricated_result()
    dup = result.evidence[0].model_copy(deep=True)
    result.evidence.append(dup)

    compared = unit_admission(result, owner)
    assert len(compared.uses) == 2
    assert len(compared.diagnostic_result.evidence) == 3
    assert {u.evidence_id for u in compared.uses} == {e.evidence_id for e in result.evidence}

    result.evidence.reverse()
    reversed_compared = unit_admission(result, owner)
    assert len(reversed_compared.uses) == 2
    assert len(reversed_compared.diagnostic_result.evidence) == 3
    assert {u.evidence_id for u in reversed_compared.uses} == {
        e.evidence_id for e in result.evidence
    }
    assert reversed_compared.report.consistent_count == compared.report.consistent_count
    assert reversed_compared.report.differs_count == compared.report.differs_count
