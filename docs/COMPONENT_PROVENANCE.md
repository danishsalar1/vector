# Component provenance — vector-provenance-v1

Phase 8D is a platform-neutral domain implementation candidate. It contains no
collectors, APIs, UI, catalog, signature verifier or hardware qualification.
Synthetic tests establish code behavior only (CODE_TESTED), never that a real
component is genuine. Trust Engine remains NOT_READY; no score or numerical
provenance confidence is produced.

## Boundary and ownership

Future flow: collector → validated platform adapter → `ProvenanceSignal` →
`assess_component_provenance` → `ComponentAssessment`. The function accepts typed
internal models, not raw dictionaries or Probe payloads. It revalidates models,
including instances made with unchecked Pydantic copy/construct operations.
There are no platform adapter imports and no Phase 8A protocol changes.

An authority enum is a classification, **not authentication**. Future qualified
adapters must authenticate the source, validate any cryptographic claim, resolve
evidence IDs, establish evidence ownership and component/slot binding, and check
the live session before creating signals. A device claiming to be an OEM is still
device-reported metadata. Evidence IDs alone do not prove those records exist or
that their contents support the assertion. Neither signal construction nor direct
assessment DTO construction establishes truth. Only the policy produces assessed
facts, conditional on its normalized-input contract; no live producer exists yet.
`ComponentAssessment` validates internal v1 consistency on construction and
deserialization: policy version, resolved facts and support reasons, evidence
references, conflict/sufficiency state, and exact derived-label precedence must
agree. This rejects structurally impossible claims, but does not authenticate
referenced evidence. Pydantic's explicit unchecked `model_construct`/`model_copy`
operations are not validating entry points; consumers must revalidate such objects.

## Component identity and privacy

`ComponentReference.create` derives `cmp-` plus 128 bits of SHA-256 from the
versioned, delimiter-separated tuple: opaque device ID, session-scope UUIDv4,
device-session epoch, kind, role and ordinal. All coordinates are validated before
hashing; direct construction verifies that the supplied ID matches them. Kinds
form a closed platform-neutral enum; roles are bounded lowercase ASCII slugs.

Existing device IDs are opaque `android-<12 hex>` / `ios-<12 hex>` values; these
namespace prefixes select no policy behavior. Existing device IDs persist and
session epochs can restart at zero. Therefore the caller must also supply a
desktop-owned `session_scope_id`, newly generated for each session lifetime and
after process restart. Reuse it only within that session. The same coordinates
give the same ID; either a new scope or epoch gives a different ID. This phase
does not integrate scope creation with the session manager or persist scopes.
The reference is a session-local slot identity, not proof of physical continuity;
a future adapter must invalidate the session when component continuity is lost.

No raw serial, IMEI, UDID, vendor JSON, paths, URLs, media or arbitrary metadata
fields exist. Signal/evidence IDs are canonical UUIDv4 strings, compatible with
the existing EvidenceRecord default IDs. Issuer keys, dependency keys and reference
versions are bounded slugs, chosen from adapter-controlled vocabulary. Slug syntax
cannot recognize every possible identifier disguised as a valid word: adapters
must never copy raw device strings into these fields. The policy logs nothing.
Validation error text hides input values; callers must not expose Pydantic's
structured error input payloads. The reference still carries the existing opaque
device ID; this is not a claim of device unlinkability or anonymization.

## Independent dimensions

- Functionality is separate from provenance. Opaque functionality references are
  retained for later reporting; the engine never reads result status or payload.
- OEM origin is separate from original installation. OEM origin alone yields
  `VERIFIED_OEM_ORIGIN_ONLY`. `ORIGINAL_VERIFIED` means the original
  factory-installed component in this device and current installation context.
- Replacement is separate from prior use. Only an explicit eligible used-part
  history assertion establishes `USED_VERIFIED`: reliable evidence that the
  component was previously installed/used before its current installation.
  It does not mean ordinary use since its current installation.
- Anomaly is separate from manipulation. Behavioral inconsistency can indicate
  an anomaly, never manufacturing origin or deliberate manipulation.
- No anomaly means only no defined anomaly in the observed scope. It proves
  neither genuine origin, original installation, health nor no manipulation.
  `NO_INDICATION_IN_OBSERVED_SCOPE` is reserved in the manipulation enum; v1 has
  no negative-manipulation signal and never emits that state.

## Eligibility

All influential signals require at least one evidence ID and either
`COMPONENT_BOUND` or `DEVICE_SLOT_BOUND` binding. Device-only and unbound claims
remain inconclusive. Eligible source classes are:

| Explicit assertion | Eligible authority classes |
|---|---|
| OEM / non-OEM origin | OEM authoritative, authorized service record, cryptographic component assertion |
| Original / replacement installation | OEM authoritative, authorized service record |
| Prior use | OEM authoritative, authorized service record |
| Manipulation | OEM authoritative, authorized service record, cryptographic component assertion |
| Anomaly / no anomaly observed | The three origin classes, or behavioral measurement |

OEM and cryptographic authority require an OEM issuer; service records require
an OEM or authorized service provider; behavioral measurements require VECTOR.
Issuer keys never rank issuers or grant authority. Cryptographic classification
presumes future upstream verification; v1 does not perform it. Behavioral
measurements presume a qualified strategy for the narrowly asserted anomaly.

Device metadata, catalog matches/mismatches and user declarations establish none
of these facts in v1. Generic Android telemetry, familiar vendor/model strings,
matching functionality and repeated weak observations cannot establish OEM origin.
Catalog context is preserved without calling a part counterfeit. More signals,
even with different dependency keys, never accumulate into higher authority.

## Conflicts, sufficiency and summary

No issuer ranking or latest-record-wins heuristic exists. Opposing eligible
origin assertions produce UNKNOWN origin, INCONCLUSIVE sufficiency and SUSPICIOUS
summary. Opposing eligible original/replacement assertions produce UNKNOWN
installation; opposing anomaly/no-anomaly assertions produce UNKNOWN anomaly.
Both also make the aggregate assessment INCONCLUSIVE and suspicious, unless an
explicit resolved non-OEM fact takes summary precedence. Other dimensions retain
their independently supported facts. Weak counterclaims are recorded and make
aggregate sufficiency INCONCLUSIVE, but do not erase an eligible resolved fact.

Eligible non-OEM origin plus original factory installation is a cross-dimension
conflict (`CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE`). Original installation plus
prior use is also a conflict (`CONFLICTING_ORIGINAL_USED_EVIDENCE`). In both cases
installation becomes UNKNOWN, while the independently supported non-OEM or
prior-use fact is retained; sufficiency becomes INCONCLUSIVE. Both evidence sets
are included in contradicting IDs, and retained facts also keep supporting IDs.
The summary is NON_OEM_INDICATED for resolved non-OEM origin, otherwise SUSPICIOUS.
All conflicts are detected from the eligible assertions before resolution, so
overlapping conflicts cannot hide each other. Existing origin conflicts still
leave origin UNKNOWN and take SUSPICIOUS precedence. Weak claims do not trigger
these authoritative conflict rules. No timestamp precedence or issuer ranking
is introduced.

No signals means NOT_ASSESSED and unknown dimensions (`NOT_ESTABLISHED` for use).
Any ineligible claim or unresolved eligible conflict means INCONCLUSIVE. Otherwise
SUPPORTED means the **explicit observed claims** are supported under this policy;
it does not mean every dimension was assessed. No-anomaly-only input can therefore
be SUPPORTED while origin, installation and manipulation remain UNKNOWN.
This aggregate-sufficiency limitation remains accepted F-01 LOW debt. Consumers
must not treat aggregate sufficiency alone as proof that origin, installation,
manipulation, or every provenance dimension is established. Per-dimension
sufficiency is deferred to Phase 8F/9; this correction does not redesign it.

Summary precedence is: origin conflict → SUSPICIOUS; resolved non-OEM →
NON_OEM_INDICATED; other eligible conflict, manipulation or anomaly → SUSPICIOUS;
otherwise verified OEM plus explicit original/replacement/used history determines
the matching OEM label; OEM without installation history gives ORIGIN_ONLY;
otherwise UNKNOWN. OEM plus anomaly retains VERIFIED_OEM origin but summarizes as
SUSPICIOUS. The label is a convenience view; dimensions and sufficiency must stay
available to future consumers.

## Traceability, determinism and limits

Supporting IDs belong to resolved claims. Contradicting IDs contain both sides
of eligible conflicts and weak opposing claims. Contextual IDs preserve ineligible
claims without presenting them as support for resolved facts. These sets may
overlap when a record supports several assertions; no record count is a score.
Signal IDs and dependency groups preserve links back to immutable input signals;
the caller must retain those signals and referenced evidence for later explanation.
No evidence payload is embedded. Closed reason codes explain eligibility,
resolved facts and conflicts without generated prose.

Required UTC `assessed_at` is supplied by the caller; the engine reads no clock.
Signals observed after assessment time are rejected. No arbitrary age/expiry rule
is invented; freshness and source history applicability belong to future adapters.
Exact duplicate signals are deduplicated; conflicting contents under one ID fail
closed. Evidence/reference tuples reject duplicates and sort canonically; all
output collections are immutable and sorted. Input order never affects output.

Bounds: 256 input signals (including duplicates), 32 evidence IDs per signal,
8192 IDs per assessment evidence set, 256 functionality refs/dependency groups,
64-character slugs/functional refs, 63-bit nonnegative epochs, ordinals 0–65535.
Strict validation rejects bool-as-int, coercions, unknown fields and naive/non-UTC
timestamps. Functionality references use bounded lowercase identifier syntax;
the current DiagnosticResult has no separate result UUID, so future integration
must resolve them within report/scan context.

## Deferred

No real provenance collector, Android OEM strategy, iOS parts-history strategy,
battery manipulation detector, display authenticity detector, component serial
verification, OEM service integration or hardware validation exists in 8D.
No component is hardware-verified genuine. Hardware qualification NOT RUN.
8B, 8C, 8E, 8F and 8G remain NOT STARTED. The initial independent Claude review
completed; F-02–F-05 corrections require narrow re-review and the formal Phase 8D
gate remains pending. F-06 adapter authentication/ownership/freshness, F-07 tighter
installation binding, F-08 persistent device-ID redesign and F-09 import/naming
cleanup remain deferred. This document does not approve the phase.
