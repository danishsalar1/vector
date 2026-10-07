# Phase 8A control-plane contract

Implementation candidate only: no Android application, concrete transport, physical
diagnostic, attestation, provenance classifier, or new HTTP route is implemented.
No hardware qualification has been performed. Existing routes remain unchanged.

## Ownership and entry points

The desktop creates `ProbeProtocolSession` using an opaque device ID and current
device epoch. It creates each request; the peer cannot select the session, scan,
diagnostic, attempt, or challenge. Challenge bindings include a desktop-selected
`collection_not_before` timestamp. Control operations have no challenge binding;
START_CHALLENGE, CANCEL_CHALLENGE and FETCH_OBSERVATIONS require one.

The session ID and scan/attempt/challenge IDs are canonical lowercase UUIDv4 values.
Diagnostic/collector IDs are bounded lowercase identifiers. The local device ID
uses the existing opaque Android/iOS ID format and is never accepted from the wire.

`parse_request` and `parse_response` validate schemas only. External observations
must enter through `ingest_probe_response`, which uses the session's acceptance
gate. Direct model construction is NOT evidence validation. This boundary protects
against untrusted device input, not malicious Python code within the agent process.

The pipeline is bytes -> bounded JSON -> strict v1 schema -> outstanding-request
and live-epoch binding -> time/replay checks -> immutable attributed observations.
Only a later desktop diagnostic may interpret them or create EvidenceRecord and
DiagnosticResult objects. Neither OK nor RECEIVED means hardware PASS.

## Version, payloads, and bounds

Only version 1 is accepted; no negotiation fallback or downgrade exists. Operations
are HELLO, GET_CAPABILITIES, START_CHALLENGE, CANCEL_CHALLENGE, FETCH_OBSERVATIONS,
and HEARTBEAT. No free-form command, URL, path, intent, metadata, raw media, or
location-history field exists. All model fields are strict and extras are rejected.

The initial observation vocabulary is control acknowledgement, sample count, and
collection duration. These are collection/control data, not physical diagnostics.
Later collectors require explicitly reviewed schema additions. Counts require
integers and count units; durations require finite nonnegative numbers and ms;
acknowledgements require booleans without units. Booleans cannot become numbers.

Limits: 65,536 encoded bytes/message, 4,096 characters/string (including keys),
256 items/array, 64 keys/object, and six nested containers including the root.
IDs have stricter individual limits. JSON duplicate keys, non-finite numbers,
lone Unicode surrogates, non-UTF-8 bytes, and out-of-range integers are rejected.
Nesting is checked before parsing. The byte cap bounds parser allocations, but
the future concrete transport must itself cap reads before allocating a message.

## Replay, time, and invalidation

Requests use 32 random bytes from `secrets.token_urlsafe`, represented by 43 URL-safe
characters. Responses echo the request nonce and sequence. One request is allowed
in flight; increasing desktop-issued sequences are never reused, including after
timeout/cancellation. Nonce digests and accepted observation IDs are retained for
the whole session, without eviction. Duplicate observations cannot be rewrapped
under a new nonce. All validation succeeds before replay state is committed.
Dispatch ownership is reserved on the session, so a second adapter cannot send or
clear an active exchange. Transport acceptance atomically checks the exact issued
request as well as the current pending request. Completion releases only its own
dispatch; it cannot consume or clear a replacement request issued during I/O.
Creating a request releases an expired pending request under the session lock,
using the same wall/monotonic expiry policy as acceptance. This preserves dispatch
ownership and replay history; an undispatched request cannot block creation beyond
its lifetime. Pending request identity and monotonic start time are cleared together.

The request lifetime is at most 30 seconds, with a five-second response clock-skew
allowance and a 900-second session lifetime. Responses cannot extend request expiry.
UTC-aware timestamps are mandatory. Collection windows must be ordered, within
the desktop's challenge window, and no later than response issuance. Wall-clock
rollback invalidates the session; monotonic budgets also limit session/request age.
An unchanged caller-supplied snapshot is not a live-epoch check: future integration
must read the authoritative session manager before dispatch AND acceptance.

Replay state is capped at 4,096 issued requests and 4,096 accepted observations.
Exhaustion fails closed and requires a new session identity, not history eviction.
Disconnect, revocation, or epoch change must close the old session. Closing is
idempotent; a closed session never reopens. No state persists across process exit.
Closing an adapter closes its shared session, invalidating every adapter using it.

## Authentication and transport

`LocalApiAuth` creates a process-local 256-bit bearer token. The lazy accessor
returns one holder per process. Trusted local bootstrap can explicitly access the
token; no distribution endpoint is supplied. Holders redact repr and reject pickle
serialization. Missing/malformed/wrong tokens all use a fixed-length
`hmac.compare_digest` path and produce the same safe authorization outcome.

`require_local_authorization` is an opt-in FastAPI dependency for future Probe
routes, using only `X-Vector-Local-Authorization`; duplicate headers are rejected.
It never reads a query token or logs credentials. Clients must never put tokens
in URLs, where HTTP infrastructure may log them. Header auth does not replace
future Origin/Host controls, consent, transport peer authentication, or encryption.

`ProbeTransport` is an abstract base with production request validation and cleanup.
Adapters implement only bounded authenticated I/O and resource cleanup. They receive
a typed issued request, an explicit monotonic deadline, and cooperative cancellation.
The base validates returned bytes, rechecks the device epoch, discards late/cancelled
replies, maps exceptions to fixed transport outcomes, and closes once. It cannot
forcibly interrupt an adapter that ignores deadlines; concrete I/O must honor them.
Deterministic adapters exist only in tests. There are no transport dependencies.

Nonce matching proves request correlation, NOT peer identity or hardware integrity.
The optional artifact SHA-256 is self-reported build attribution, NOT verified
signing identity. Confidence and reliability remain None; accepted observations
contain no nonce, local token, free-form metadata or physical/provenance verdict.

## Subprocess debt decision

Reviewed all `run_command` callers in AndroidDeviceBridge, IOSDeviceBridge and
SystemPreflightService, plus subprocess, privacy, timeout and bridge regression
tests. The current primitive uses `subprocess.run(capture_output=True)` and truncates
stdout only after capture; stderr capture is also unbounded. Its output limit is
NOT a capture-memory bound.

True bounded capture on Windows requires concurrent stdout/stderr draining,
overflow policy, timeout/process cleanup and pipe-reader lifecycle handling.
Changing that shared primitive merits a dedicated hardening pass. Phase 8A leaves
it unchanged and introduces no subprocess or larger-output command. Its existing
post-read truncation must not be described as fixing the memory-exhaustion debt.
