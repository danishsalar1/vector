# Relative imports retain type resolution under the repository's src package.
# ruff: noqa: TID252
"""Versioned v1 eligibility rules; no vendor catalog or issuer ranking."""

from types import MappingProxyType
from typing import Final

from ..models.provenance import (
    ProvenanceAuthorityClass as Authority,
)
from ..models.provenance import (
    ProvenanceIssuerType as Issuer,
)
from ..models.provenance import (
    ProvenanceReasonCode as Reason,
)
from ..models.provenance import (
    ProvenanceSignalType as Signal,
)
from ..models.provenance import (
    ProvenanceSubjectBinding as Binding,
)

POLICY_VERSION: Final = "vector-provenance-v1"
MAX_SIGNALS = 256
ELIGIBLE_BINDINGS = frozenset({Binding.COMPONENT_BOUND, Binding.DEVICE_SLOT_BOUND})
ORIGIN_AUTHORITIES = frozenset(
    {
        Authority.OEM_AUTHORITATIVE,
        Authority.AUTHORIZED_SERVICE_RECORD,
        Authority.CRYPTOGRAPHIC_COMPONENT_ASSERTION,
    }
)
HISTORY_AUTHORITIES = frozenset(
    {
        Authority.OEM_AUTHORITATIVE,
        Authority.AUTHORIZED_SERVICE_RECORD,
    }
)
ELIGIBLE_AUTHORITIES = MappingProxyType(
    {
        Signal.OEM_ORIGIN_ASSERTED: ORIGIN_AUTHORITIES,
        Signal.NON_OEM_ORIGIN_ASSERTED: ORIGIN_AUTHORITIES,
        Signal.ORIGINAL_INSTALLATION_ASSERTED: HISTORY_AUTHORITIES,
        Signal.REPLACEMENT_INSTALLATION_ASSERTED: HISTORY_AUTHORITIES,
        Signal.USED_PART_ASSERTED: HISTORY_AUTHORITIES,
        Signal.MANIPULATION_ASSERTED: ORIGIN_AUTHORITIES,
        Signal.ANOMALY_OBSERVED: ORIGIN_AUTHORITIES | {Authority.BEHAVIORAL_MEASUREMENT},
        Signal.NO_ANOMALY_OBSERVED: ORIGIN_AUTHORITIES | {Authority.BEHAVIORAL_MEASUREMENT},
    }
)
ELIGIBLE_ISSUERS = MappingProxyType(
    {
        Authority.OEM_AUTHORITATIVE: frozenset({Issuer.OEM}),
        Authority.AUTHORIZED_SERVICE_RECORD: frozenset(
            {Issuer.OEM, Issuer.AUTHORIZED_SERVICE_PROVIDER}
        ),
        Authority.CRYPTOGRAPHIC_COMPONENT_ASSERTION: frozenset({Issuer.OEM}),
        Authority.BEHAVIORAL_MEASUREMENT: frozenset({Issuer.VECTOR}),
        Authority.REFERENCE_CATALOG: frozenset({Issuer.REFERENCE_CATALOG}),
        Authority.DEVICE_REPORTED_METADATA: frozenset({Issuer.DEVICE}),
        Authority.USER_DECLARATION: frozenset({Issuer.USER}),
    }
)
SUPPORT_REASONS = MappingProxyType(
    {
        Signal.OEM_ORIGIN_ASSERTED: Reason.AUTHORITATIVE_OEM_EVIDENCE,
        Signal.NON_OEM_ORIGIN_ASSERTED: Reason.AUTHORITATIVE_NON_OEM_EVIDENCE,
        Signal.ORIGINAL_INSTALLATION_ASSERTED: Reason.AUTHORITATIVE_ORIGINAL_HISTORY,
        Signal.REPLACEMENT_INSTALLATION_ASSERTED: Reason.AUTHORITATIVE_REPLACEMENT_HISTORY,
        Signal.USED_PART_ASSERTED: Reason.AUTHORITATIVE_USED_PART_HISTORY,
        Signal.MANIPULATION_ASSERTED: Reason.MANIPULATION_EVIDENCE,
        Signal.ANOMALY_OBSERVED: Reason.ANOMALY_EVIDENCE,
        Signal.NO_ANOMALY_OBSERVED: Reason.NO_ANOMALY_IN_OBSERVED_SCOPE,
    }
)
CONFLICT_PAIRS = (
    (
        Signal.OEM_ORIGIN_ASSERTED,
        Signal.NON_OEM_ORIGIN_ASSERTED,
        Reason.CONFLICTING_ORIGIN_EVIDENCE,
    ),
    (
        Signal.ORIGINAL_INSTALLATION_ASSERTED,
        Signal.REPLACEMENT_INSTALLATION_ASSERTED,
        Reason.CONFLICTING_INSTALLATION_EVIDENCE,
    ),
    (Signal.ANOMALY_OBSERVED, Signal.NO_ANOMALY_OBSERVED, Reason.CONFLICTING_ANOMALY_EVIDENCE),
)
