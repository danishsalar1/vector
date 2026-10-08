# Phase 8B implementation and independent-review handoff

## Baseline and scope

Initial branch: `main`. Initial HEAD and origin/main:
`8456e352053a802a7cff85eff4ad1751ef14878e`. Initial working tree clean.
The baseline `scripts/verify.ps1` passed 15/15 with normal tool access. An earlier
sandbox run failed on DNS/cache permissions and Vitest EPERM; those were
environment failures, not accepted test results.

STATUS.md, AGENTS.md, roadmap numbering and the Phase 8D provenance implementation
were preserved throughout implementation. The Phase 8B implementation was submitted
to independent Claude review and the formal Phase 8B gate PASSED, followed by a PASSED
staged-boundary review. The implementation was committed as `365f0e88a3da172b27e5021a9ff95257aa83eb25` (`365f0e8`).
Documentation finalization is now in progress. Physical hardware qualification remains NOT RUN.

## Architecture discovered and preserved

The existing Python agent uses FastAPI, platform adapters, mutable in-memory
DeviceSessions managed under an RLock, session epochs, a generic scan planner,
and separate diagnostic/evidence/provenance models. Phase 8A already supplied
strict immutable envelopes, bounded JSON, replay/time/ownership validation,
process-local API authorization, and the abstract ProbeTransport acceptance gate.
There was no Android project or concrete Probe transport. Phase 8D is pure,
platform-neutral provenance policy and is not connected to the new lifecycle.

Phase 8B adds a development Android application, a constrained Android bridge,
an authenticated concrete transport, lifecycle service, and typed backend state.
The existing planner, diagnostic registry, frontend, intelligence engine and
component-provenance evaluator are not changed.

## App identity, discovery, and compatibility

The stable application ID is `org.vector.probe`. No claim of ownership of an
internet domain or production signing authority is made by this namespace.

Package presence alone yields no trust. The desktop operator explicitly enrolls
the controlled debug APK using a known certificate fingerprint. The enrollment
tool verifies its APK signature with Android apksigner, rejects different or
multiple signers, verifies the fixed package and version with aapt2, requires a
debuggable build, and pins the complete SHA-256 artifact digest. A trusted record
is host configuration, never an API body or Probe-reported identity.

For the fixed package and user 0, discovery reads installed/disabled state and
the package manager's APK path. Only one narrowly validated base.apk path under
the package-owned `/data/app` directory is accepted. The fixed sha256sum operation
must return an exact digest/path pair. Matching the enrolled signed artifact
establishes identity relative to that local development build, **conditional on
the trusted Android OS/ADB reporting boundary**. This is neither remote
attestation nor proof that a rooted/compromised OS reports honestly.

There is no fabricated parsing of `dumpsys` signature hashCodes as certificate
fingerprints. An unknown APK digest is UNTRUSTED / ARTIFACT_NOT_ALLOWLISTED; it
could be a different signer or simply an unenrolled build. It is not mislabeled
NOT_INSTALLED or definitively SIGNER_MISMATCH. Missing signer configuration or
unusable package metadata is INSTALLED_UNVERIFIED. Disabled, incompatible,
restricted, unavailable, timeout and malformed-response states stay distinct.

Metadata in the enrolled artifact identifies version 0.1.0, versionCode 1 and
protocol 1. Unknown future versions fail closed. A strictly typed optional
`hello` field extends the v1 response schema with application version, version
code, protocol versions, supported operations and Android API level. Phase 8A
callers can still parse legacy responses without that field; the 8B lifecycle
requires it. All original envelope validation remains in effect. Review this
additive schema decision explicitly: old 8A desktops reject new HELLO metadata
through their existing extra-field policy, rather than silently downgrading.

The actual HELLO must match the enrolled application version and supported
protocol/operation set. GET_CAPABILITIES must declare exactly the three supported
control operations. No static hardware catalog, hardware capability, functional
PASS, provenance conclusion, confidence or Trust Score is manufactured.

## Consent, authentication and wire transport

Manual installation/update only. There is no install, uninstall, permission-grant
or arbitrary package API. Launch and stop target one fixed Activity/package, only
after identity checks and live-session checks. The foreground Activity displays
an on-device Allow/Deny consent prompt and ignores all intent extras. Release
builds refuse the development bootstrap. A deny tap reports CONSENT_DENIED while
visible.

Allow/Deny protects against accidental connection and unauthorized non-ADB local
or third-party app processes on the device. The ADB-authorized development host
is inside the Phase 8B trust boundary; Phase 8B is not designed to resist a
malicious authorized ADB host (an authorized ADB host can inject input events
or read debuggable app state via run-as). HMAC/session bootstrap does not protect
the debug Probe from its authorized ADB host, and the on-device Allow action is
not claimed to be cryptographically unspoofable against desktop input injection.
Production non-debuggable bootstrap/pairing is future production-blocking work.

After consent the app creates a fresh 256-bit secret and random abstract socket
name. The bootstrap is atomically written into its private app directory. The
desktop obtains it through the fixed `run-as org.vector.probe cat
files/vector-probe-session` operation. This is an explicitly development-only
use of ordinary Android debugging authorization, not a permission/root bypass.
The installed artifact is checked again after bootstrap retrieval.

ADB allocates a localhost forward with `tcp:0` to that exact randomized endpoint.
No caller chooses an arbitrary endpoint/port. A local socket client is accepted
only from shell UID 2000. Root or other UIDs are rejected. OEM SELinux/adbd
differences may prohibit this path and require qualification; no fallback exists.

Frames are: 4-byte network-order length, 32-byte HMAC-SHA256, then bounded UTF-8
JSON. MAC input is `request\0` or `response\0` followed by the exact JSON bytes.
Both directions authenticate before protocol parsing. Direction separation stops
reflection. Frame sizes are capped before allocation. Desktop reads and writes
use monotonic deadlines and cancellation-aware 100ms socket slices. Android has
a complete-frame watchdog as well as socket timeout. HMAC provides integrity and
possession of the bootstrap key; confidentiality relies on the local/authorized
ADB boundary. No remote TCP listener, TLS claim, or cloud service is introduced.

The Android JVM protocol validates exact fields, duplicate keys, UTF-8, surrogate
pairs, JSON structure bounds, strict integers, operation/binding shape, protocol
version, UTC expiry, session/epoch, nonces, sequence and bounded session history.
It requires HELLO first, binds one session, and never accepts a second HELLO on
that connection. Challenges always return UNAVAILABLE without creating state or
executing hardware work. The desktop still passes every response through the
original Phase 8A evidence acceptance boundary.

## Lifecycle and ownership

ProbeConnection owns one DeviceSession **object identity** and epoch. The manager
provides an atomic ownership/authorization lookup. This also rejects a replacement
DeviceSession with the same opaque ID and epoch after clear/recreation. Epoch is
checked before dispatch and acceptance; side effects also recheck ownership after
discovery. Disconnect, stale/late responses, explicit stop, timeout, bad MAC,
incompatibility, malformed data and process shutdown clear capabilities and close
the protocol session. No pending request/authorization is transferred to a new
connection. Cancellation events are private to each connection; no request body
can nominate another session, scan, diagnostic, attempt or challenge to cancel.

The backend enforces a cap of at most 16 LIVE device connections concurrently active,
with one monitor thread per record, a 1s ownership poll and a heartbeat after 5s
without a successful control heartbeat. Stale or dead records are pruned, and retiring
a connection allows a new device to be admitted up to the 16 live connection ceiling. Each exchange has a 3s budget. Per-device operations serialize;
different devices do not block each other's heartbeat deadlines. GET state queries
do not allocate a new connection or worker, and cross-device service-wide lock contention
was mitigated. However, same-device GET/connection operations may still wait behind an
in-flight operation (accepted debt FG-06, requiring correction before Phase 8F). The app requires
traffic within 12s and expires the whole consent after 900s. Liveness means only
that the authenticated control endpoint responded, never hardware health.

The first successful HELLO consumes the bootstrap. The app's foreground consent
is revoked on pause/destroy, deny, socket loss or deadline. Process death destroys
the socket; a stale private bootstrap cannot restore the missing endpoint. A new
launch resets that file, and a new Allow action creates fresh credentials. Desktop
restart, Probe restart, USB reconnect or ADB restart require explicit reconnect
and fresh consent after the old connection fails. There is no auto-retry loop.

Normal teardown closes/shuts down the socket, wipes retained key references,
invalidates the protocol session, and removes only a forward whose current list
entry still matches the owned device/port/endpoint. If ownership changed or ADB
is unavailable, cleanup reports ERROR and does not remove someone else's rule.
Note that if socket connection fails during transport construction after creating
the port forward, cleanup error handling is incomplete and could leak the forward
until daemon restart (accepted debt FG-03, targeted for Phase 8G).
Abrupt desktop death can leave an ADB forwarding rule; the app's idle timeout
closes its endpoint. Removing stale rules after crashes remains manual. Atomic
ownership against a malicious concurrent local adb operator is not claimed.

## Backend/API, privacy, errors and permissions

GET `/api/v1/devices/{opaque-id}/probe` returns typed state. POST actions under
that path are `discover`, `launch`, `connect`, `heartbeat`, `stop`. There are no
command/package/path/URL/intent/body parameters. Every route requires the existing
process-local authorization header, a localhost Host and no browser Origin.
The token is available only to trusted in-process bootstrap, never via an HTTP
distribution endpoint. Phase 8F must design any frontend bootstrap separately.
DEMO mode rejects the service instead of producing fake or real Probe activity.

Raw ADB serials remain transient/private; public state contains closed reason
codes and verified build metadata, not raw tool output, exception strings, paths,
MACs or bootstrap keys. Fixtures are fabricated. No device identifier is persisted
in the trust record or Android bootstrap. No logging of these channels is added.

New subprocesses use fixed tool/configuration roots and constrained argv lists,
explicit shell=False, fixed budgets, strict decoding and return-code checks.
Both output pipes are concurrently drained with bounded retained data; overflow
kills the process and rejects the result. The old shared capture_output debt is
unchanged and is not used by the new Probe operations. A misbehaving descendant
which inherits pipe handles could leave a daemon reader until those handles close;
the caller times out and retained memory stays bounded. This primitive is only
used with trusted adb/Java/Android build tools, not arbitrary executables via API.

Manifest permission count: **0**. No services, receivers, providers, dynamic
permission requests or foreground-service/notification behavior. Purpose-specific
foreground UI only. See android-probe/README.md for the per-mechanism audit.

## Verification and remaining review requirements

Final automated results after audit corrections and toolchain verification:

- Phase 8B focused: 120 passed.
- Phase 8A foundation: 254 passed (including local API authorization).
- Full local-agent regression: 1953 passed.
- Intelligence: 21 passed; Ruff, format, mypy passed.
- Frontend: 96 passed in 10 files; ESLint, TypeScript and production build passed.
- Local-agent Ruff, format and mypy: passed (88 source files).
- Final `scripts/verify.ps1`: 15/15 passed, exit 0.
- Existing Starlette/httpx testclient deprecation warning remains.
- Android Gradle unit tests, lint, compilation and assembleDebug:
  **VERIFIED AND PASSED**.
  Host environment: JDK 17.0.20.1, Gradle 8.11.1, Android SDK platform 35, Build Tools 35.0.0.
  Target minSdk is 26, targetSdk is 35, compileSdk is 35.
  Executed: `gradle --no-daemon clean testDebugUnitTest lintDebug compileDebugJavaWithJavac assembleDebug`.
  - `:app:testDebugUnitTest`: PASSED (6 tests executed, 0 failures; all in `ControlProtocolTest`; `ProbeActivity` lifecycle tests deferred to Phase 8G under FG-05).
  - `:app:lintDebug`: PASSED (0 errors, 0 warnings; resolved orientation lock and fail-closed data extraction / backup rules).
  - `:app:compileDebugJavaWithJavac`: PASSED.
  - `:app:assembleDebug`: PASSED.
  - Signed debug APK assembled: `android-probe/app/build/outputs/apk/debug/app-debug.apk`.
  - Signer verification (`apksigner verify --verbose --print-certs`): Verified using v2 scheme; 1 signer (`CN=Android Debug, O=Android, C=US`).
  - Package dump (`aapt2 dump badging`): package `org.vector.probe`, `versionCode=1`, `versionName=0.1.0`, `sdkVersion=26`, `targetSdkVersion=35`, `application-debuggable` present, 0 permissions.
- VECTOR Trust Enrollment:
  **VERIFIED AND PASSED**.
  Enrolled real generated APK into `local-agent/.data/probe-trust.json` using actual signer SHA-256 fingerprint.
- Python↔Java protocol compatibility:
  Reviewed and validated with canonical golden request/response test vectors and HMAC-SHA256 validation across both Python and Java test suites.
- Physical-device qualification: **NOT RUN**. Fixture/socket tests are code tests
  only. No HARDWARE_VALIDATED claim.
- Operational & Scope Constraints:
  - Probe is DEVELOPMENT-ONLY, debuggable, and uses the documented `run-as` bootstrap.
  - Production non-debuggable bootstrap and production signer trust are NOT implemented.
  - Trust Engine remains NOT_READY; `trust_score` remains None.
  - No hardware PASS or component authenticity claims arise from 8B.
  - Actual Android minSdk is 26, not 28.
- Independent Claude review & formal gate:
  - Narrow review: PASSED (0 BLOCKER, 0 HIGH, 0 MEDIUM, 9 LOW, 13 INFO); cleanup items N-1 through N-6 implemented.
  - Formal Phase 8B gate: PASSED (0 BLOCKER, 0 HIGH, 0 MEDIUM, 6 LOW, 9 INFO).
  - Staged-boundary review: PASSED.
  - Implementation committed as `365f0e88a3da172b27e5021a9ff95257aa83eb25` (`365f0e8`).

Reviewer attention: Actual adbd peer UID/SELinux behavior, profile/version differences,
consent lifecycle, restart races and forward cleanup on real devices need physical
qualification later. No production signer or release transport is claimed. No security gate is inferred
from passing fixture tests.

8C NOT STARTED; 8E NOT STARTED; 8F NOT STARTED; 8G NOT STARTED.
Trust Engine NOT_READY; trust_score remains None. No SaaS, billing or production
UX redesign. The only Android UI is the required Probe consent screen.

## Exact file boundary and disposition

Modified tracked files (5):

```text
.gitignore
local-agent/src/vector_agent/devices/session.py
local-agent/src/vector_agent/evidence/validation.py
local-agent/src/vector_agent/main.py
local-agent/src/vector_agent/models/probe.py
```

New candidate untracked files (23):

```text
android-probe/README.md
android-probe/app/build.gradle.kts
android-probe/app/src/main/AndroidManifest.xml
android-probe/app/src/main/java/org/vector/probe/ControlProtocol.java
android-probe/app/src/main/java/org/vector/probe/ProbeActivity.java
android-probe/app/src/main/java/org/vector/probe/ProbeServer.java
android-probe/app/src/main/res/drawable/ic_probe.xml
android-probe/app/src/main/res/values/strings.xml
android-probe/app/src/main/res/xml/backup_rules.xml
android-probe/app/src/main/res/xml/data_extraction_rules.xml
android-probe/app/src/test/java/org/vector/probe/ControlProtocolTest.java
android-probe/build.gradle.kts
android-probe/gradle.properties
android-probe/settings.gradle.kts
docs/PHASE_8B_PROBE.md
local-agent/src/vector_agent/api/probe.py
local-agent/src/vector_agent/devices/android/probe_bridge.py
local-agent/src/vector_agent/models/probe_lifecycle.py
local-agent/src/vector_agent/probe/adb_transport.py
local-agent/src/vector_agent/probe/lifecycle.py
local-agent/src/vector_agent/probe/trust_build.py
local-agent/src/vector_agent/security/bounded_process.py
local-agent/tests/test_phase8b_probe.py
```

Implementation commit: `365f0e88a3da172b27e5021a9ff95257aa83eb25` (`365f0e8`).
Commit message: `feat: add signed Android Probe discovery, consent and lifecycle control plane`.
Formal Claude gate: PASSED.
Staged-boundary review: PASSED.
Final STATUS.md documentation update in progress.
Physical hardware qualification remains NOT RUN.

## Primary implementation references

- [Android Gradle 8.9 compatibility](https://developer.android.com/build/releases/agp-8-9-0-release-notes)
- [Android apksigner verification](https://developer.android.com/tools/apksigner)
- [Android LocalSocket peer credentials](https://developer.android.com/reference/android/net/LocalSocket)
- [Android LocalServerSocket](https://developer.android.com/reference/android/net/LocalServerSocket)
- [Gson 2.11 strict streaming reader](https://javadoc.io/static/com.google.code.gson/gson/2.11.0/com.google.gson/com/google/gson/stream/JsonReader.html)
