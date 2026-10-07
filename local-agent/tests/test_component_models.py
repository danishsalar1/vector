"""Privacy-safe component identity and strict normalized contract tests."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vector_agent.models.component import ComponentKind, ComponentReference
from vector_agent.models.provenance import (
    ProvenanceAuthorityClass as Authority,
)
from vector_agent.models.provenance import (
    ProvenanceIssuerType as Issuer,
)
from vector_agent.models.provenance import (
    ProvenanceSignal,
)
from vector_agent.models.provenance import (
    ProvenanceSignalType as Signal,
)
from vector_agent.models.provenance import (
    ProvenanceSubjectBinding as Binding,
)

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


def opaque_id(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012x}"


def component(**changes: object) -> ComponentReference:
    values = {
        "device_id": "android-012345abcdef",
        "device_session_epoch": 3,
        "session_scope_id": opaque_id(1),
        "component_kind": ComponentKind.BATTERY,
        "component_role": "battery-main",
        "ordinal": 0,
    }
    values.update(changes)
    return ComponentReference.create(**values)


def signal(
    kind: Signal = Signal.OEM_ORIGIN_ASSERTED, number: int = 10, **changes: object
) -> ProvenanceSignal:
    values = {
        "signal_id": opaque_id(number),
        "component_id": component().component_id,
        "signal_type": kind,
        "authority_class": Authority.OEM_AUTHORITATIVE,
        "subject_binding": Binding.COMPONENT_BOUND,
        "issuer_type": Issuer.OEM,
        "issuer_key": "fixture-oem",
        "evidence_ids": (opaque_id(number + 1000),),
        "source_dependency_key": "fixture-record",
        "observed_at": NOW,
    }
    values.update(changes)
    return ProvenanceSignal(**values)


def test_component_identity_is_deterministic_and_session_scoped():
    original = component()
    assert original == component()
    assert len(original.component_id) == 36
    variants = [
        component(device_session_epoch=4),
        component(session_scope_id=opaque_id(2)),
        component(device_id="ios-012345abcdef"),
        component(ordinal=1),
        component(component_role="battery-bms"),
        component(component_kind=ComponentKind.OTHER),
    ]
    assert len({original.component_id, *(v.component_id for v in variants)}) == 7
    assert original == ComponentReference.model_validate_json(original.model_dump_json())


def test_component_id_golden_vector():
    # Independent SHA-256 vector for ASCII:
    # vector-component-v1|android-012345abcdef|00000000-0000-4000-8000-000000000001|3|BATTERY|battery-main|0
    assert component().component_id == "cmp-4a9cdaa1d85350c8a6679540a1431969"


def test_component_identity_field_boundaries_cannot_collapse():
    left = component(component_role="battery-main-1", ordinal=23)
    right = component(component_role="battery-main-12", ordinal=3)
    # Naive concatenation is ambiguous; the actual canonical delimiter is not.
    assert left.component_role + str(left.ordinal) == right.component_role + str(right.ordinal)
    assert left.component_id != right.component_id
    with pytest.raises(ValidationError):
        component(component_role="battery-main|1")


@pytest.mark.parametrize("kind", ComponentKind)
def test_every_component_kind(kind):
    assert component(component_kind=kind).component_kind == kind


@pytest.mark.parametrize(
    "role",
    [
        "../battery",
        "battery/main",
        r"battery\main",
        "battery main",
        "Battery",
        "bаttery",
        "battery:main",
        "a" * 65,
        "",
        "battery\n",
        "battery;whoami",
        "battery--main",
    ],
)
def test_reject_unsafe_roles(role):
    with pytest.raises(ValidationError):
        component(component_role=role)


@pytest.mark.parametrize(
    "field,value",
    [
        ("device_session_epoch", -1),
        ("device_session_epoch", True),
        ("device_session_epoch", 1.0),
        ("device_session_epoch", "1"),
        ("device_session_epoch", 2**63),
        ("ordinal", -1),
        ("ordinal", True),
        ("ordinal", 65536),
        ("ordinal", 1.0),
        ("ordinal", "1"),
        ("device_id", "FABRICATED-SERIAL"),
        ("device_id", "123456789012345"),
        ("device_id", "android-012345abcdef\n"),
        ("session_scope_id", "raw-serial"),
        ("component_kind", "BATTERY"),
        ("component_kind", "ANDROID_BATTERY"),
    ],
)
def test_reject_invalid_coordinates(field, value):
    with pytest.raises(ValidationError):
        component(**{field: value})


@pytest.mark.parametrize("value", ["cmp-bad", "cmp-" + "0" * 32, "FABRICATED-SERIAL"])
def test_reject_forged_component_id(value):
    values = component().model_dump()
    values["component_id"] = value
    with pytest.raises(ValidationError):
        ComponentReference.model_validate(values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("signal_id", "signal-1"),
        ("signal_id", opaque_id(1).upper().replace("4000", "4ABC")),
        ("component_id", "raw-component"),
        ("evidence_ids", ()),
        ("evidence_ids", []),
        ("evidence_ids", [opaque_id(1)]),
        ("evidence_ids", ("evidence-1",)),
        ("evidence_ids", (opaque_id(1), opaque_id(1))),
        ("evidence_ids", tuple(opaque_id(n) for n in range(33))),
        ("issuer_key", "https://example.test"),
        ("issuer_key", "user@example.test"),
        ("issuer_key", "123456789012345"),
        ("issuer_key", "OEM"),
        ("issuer_key", "a" * 65),
        ("issuer_key", "fixture\n"),
        ("source_dependency_key", "../record"),
        ("source_dependency_key", r"c:\record"),
        ("source_dependency_key", "x;whoami"),
        ("source_dependency_key", "a" * 65),
        ("reference_version", "https://example.test"),
        ("observed_at", NOW.replace(tzinfo=None)),
        ("observed_at", NOW.isoformat()),
        ("observed_at", datetime(2026, 10, 7, tzinfo=None)),
        ("observed_at", float("nan")),
        ("observed_at", True),
        ("signal_type", "GENUINE"),
        ("authority_class", "OEM_AUTHORITATIVE"),
        ("subject_binding", "COMPONENT_BOUND"),
        ("issuer_type", "OEM"),
        ("metadata", {"serial": "FABRICATED-SERIAL"}),
        ("raw_serial", "FABRICATED-SERIAL"),
    ],
)
def test_reject_unsafe_signal_fields(field, value):
    with pytest.raises(ValidationError):
        signal(**{field: value})


def test_signal_references_are_canonical_and_frozen():
    s = signal(evidence_ids=(opaque_id(2), opaque_id(1)))
    assert s.evidence_ids == (opaque_id(1), opaque_id(2))
    assert s == ProvenanceSignal.model_validate_json(s.model_dump_json())
    with pytest.raises(ValidationError):
        s.issuer_key = "another"
    with pytest.raises(ValidationError):
        component().ordinal = 3
    with pytest.raises(ValidationError):
        signal(observed_at=NOW.astimezone(timezone(timedelta(hours=1))))


def test_unexpected_component_fields_and_safe_validation_message():
    values = component().model_dump() | {"raw_serial": "FABRICATED-PRIVATE-MARKER"}
    with pytest.raises(ValidationError) as error:
        ComponentReference.model_validate(values)
    assert "FABRICATED-PRIVATE-MARKER" not in str(error.value)
