# OEM-reference correction checkpoint 1

This is a correction to the existing uncommitted reference package, not approval
of its roadmap placement. STATUS.md names 8E **Android Provenance / Anomaly
Signals**; AGENTS.md specifies ordering but does not name that slice. The naming
decision remains with the user. No later phase is authorized.

## Field contract matrix (established before comparison changes)

For emitted metrics below, `models/probe_diagnostics.py::METRICS` fixes the unit;
`DiagnosticReport.predicates` fixes the diagnostic group. After authenticated
lifecycle acceptance, `probe/diagnostic_evidence.py::diagnostic_result` preserves
the name, numeric value (including null), and unit as `EvidenceRecord.source_name`,
`normalized_value`, and `unit`. It records CODE_TESTED and authenticity UNKNOWN.
The comparator's existing flat dictionary has neither this binding nor units.
Its evidence_records and diagnostic_results parameters are unused. No production
adapter is implemented in this checkpoint.

| Android/desktop field | Actual source | Real meaning | Unit | Current comparator use (before correction) | Valid for OEM comparison? | Safe action |
|---|---|---|---|---|---|---|
| charge_counter | BatteryCollector, BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER | Remaining charge, not rated capacity or health | uAh | Guesses uAh/mAh by magnitude; 5% rated-capacity tolerance | No | NOT_COMPARABLE; retain original evidence |
| battery_capacity_design, rated_capacity | NOT EMITTED in Probe schema or collectors | UNVERIFIED | UNVERIFIED | Fallbacks for charge_counter | No established contract | Do not use these aliases |
| ram_total | SystemCollector, ActivityManager.MemoryInfo.totalMem | Memory accessible to kernel, excluding some reserved allocations | bytes | 20% installed-RAM allowance | No | NOT_COMPARABLE; no inferred physical RAM |
| ram_available | SystemCollector, MemoryInfo.availMem | Available OS memory, not installed RAM | bytes | Not consumed | No | Never substitute for ram_total or physical RAM |
| width, height | SystemCollector, Display.getMode().getPhysicalWidth/Height | Dimensions when configured in the active mode | pixels | Equals advertised panel dimensions | No proof of native panel resolution | NOT_COMPARABLE for panel claims |
| display_width, display_height | DiagnosticUi touch geometry, Display.getMode() | Current display-mode dimensions accompanying interactive touch geometry | pixels | Aliases for width/height | No | Do not treat as native panel dimensions |
| window_width/height, tested_width/height | DiagnosticUi window bounds / touch target geometry | App/window/test area | pixels | Not consumed | No | Never substitute for panel dimensions |
| refresh_rate | SystemCollector, active Display.Mode.getRefreshRate | Selected mode rate | Hz | Accepts any rate in OEM min/max range | No proof of maximum capability | NOT_COMPARABLE for advertised maximum |
| mode_count | SystemCollector, Display.getSupportedModes().length | Total OS-reported mode count; only first eight exported | count | Ignored | Describes enumeration, not completeness of panel capabilities | Retain; do not infer missing modes |
| mode0_width/height/rate through mode7_width/height/rate | SystemCollector, first eight supported Display.Mode entries | OS-declared mode dimensions and rate; no native-mode marker | pixels / Hz | Ignored | Can describe runtime modes; does not identify physical native resolution | Preserve mode observations; no native/max claim from unbound flat dictionary |
| nfc_enabled | SystemCollector, NfcAdapter.isEnabled | User/service enabled state; null if no adapter | boolean (numeric 0/1) | Fallback hardware-presence test | No | INSUFFICIENT_EVIDENCE without feature_nfc |
| feature_nfc | SystemCollector, PackageManager.hasSystemFeature(android.hardware.nfc) | Runtime capability declaration | boolean (numeric 0/1) | Truthy-or fallback loses false values | Capability declaration only, not functional or provenance proof | Compare strict 0/1 or bool; never fall back to toggle |
| feature_barometer | SystemCollector, PackageManager.hasSystemFeature(android.hardware.sensor.barometer) | Runtime capability declaration | boolean (numeric 0/1) | bool coercion vs reference presence | Capability declaration only | Strict boolean; no functional claim; preserve variant ambiguity |
| cpu_cores, core_count | NOT EMITTED in Probe schema or collectors | UNVERIFIED; unrelated desktop inventory must not be silently mapped | UNVERIFIED | Integer vs reference SoC core count | No production observation path | Missing stays INSUFFICIENT_EVIDENCE; legacy dictionary rule deferred |
| rear_camera_count, camera_rear_count | NOT EMITTED in Probe schema or collectors | UNVERIFIED; camera capabilities/frames are not physical module counts | UNVERIFIED | Integer vs length of rear reference cameras | No production observation path | Missing stays INSUFFICIENT_EVIDENCE; legacy dictionary rule deferred |
| feature_5g_mmwave | NOT EMITTED in Probe schema or collectors | UNVERIFIED | UNVERIFIED | Boolean vs text in network_configuration | No production observation path | No manufactured value; legacy dictionary rule deferred |

API semantics checked against Android documentation:
[BatteryManager](https://developer.android.com/reference/android/os/BatteryManager#BATTERY_PROPERTY_CHARGE_COUNTER),
[MemoryInfo](https://developer.android.com/reference/android/app/ActivityManager.MemoryInfo#totalMem),
[Display.Mode](https://developer.android.com/reference/android/view/Display.Mode#getPhysicalWidth()),
[PackageManager NFC feature](https://developer.android.com/reference/android/content/pm/PackageManager#FEATURE_NFC).
These API checks do not verify any OEM seed citation or retrieval metadata.

## Scope limitations

No emitted field establishes rated battery capacity, installed physical RAM, or
native panel identity. No positive native-resolution comparison is justified by
the current contract, even if a supported mode numerically matches. Mode-specific
capability reporting needs explicit observation ownership/units in the later
adapter; it must not be described as physical panel verification here.

Questionable seed assertions remain queued for PG-07: Google SKU/region mappings,
Sunwoda/ATL supplier attribution, FCC grant date and battery-support claim;
Samsung URLs and global-versus-US applicability; Apple's battery mAh, RAM amount
and technology, NVMe assertion, A2890 scope and missing regional variants;
publication dates, source revision labels and license assumptions. Citation
existence is not claim verification. No OEM source was retrieved in this workflow.

## A. Baseline and repository integrity

- Canonical implementation directory: `C:\Users\danis\vector`; branch `main`.
- HEAD and origin/main both `e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`, unchanged.
- Initial inventory: one tracked modification (`frontend/vitest.config.ts`) plus
  ten untracked reference implementation/test/documentation files.
- Final inventory: same entries plus this handoff and
  `local-agent/tests/test_phase8e_checkpoint1.py` (13 dirty entries total).
- Staged files: zero initially and finally. All 300 tracked files match their
  initial SHA-256 hashes, including the preexisting frontend change. All initial
  dirty paths remain present. No unrelated source modification was detected.
- Six existing files modified by this session: reference `comparator.py`,
  `seed.py`, `catalog.py`, `models/reference.py`, `test_phase8e_reference.py`, and
  `docs/PHASE_8E_SPECIFICATION_CATALOG.md`. Two files added as listed above.
- `resolver.py`, `importer.py`, `performance.py`, package `__init__.py`, and
  frontend configuration retain their initial bytes. No dependency added.
- Initial hashes, byte snapshots, session diff and test logs are in the external
  checkpoint1 audit directory under this chat's visualization workspace.

## B. Diagnostic contract

The complete matrix above was written before any comparison logic changed.
The real Java fixtures were subsequently replayed through the production Python
transport/session/evidence lifecycle. Battery evidence retains its original
value and uAh unit; display telemetry no longer yields a physical-panel mismatch.
These are fixture-based CODE_TESTED results, not device qualification.

## C. Target findings

All six targeted defects are corrected within the authorized scope. The initial
79-case checkpoint run had 64 failures and 15 passing controls against unchanged
production code. Those same cases pass after correction. Four additional tests
cover Java battery evidence, invariant NFC amid other variant differences,
absence of authenticity output, and wholly missing observations.

| Finding | Reproduction and root cause | Fix and location | Regression | Remaining limitation |
|---|---|---|---|---|
| PG-01 | 2,463,000 uAh became DIFFERS; 4,926,000 and 4,926 became CONSISTENT. Remaining charge used as rated capacity, guessed units and 5% tolerance. | `reference/comparator.py:285`: no rated observation is manufactured; remaining charge yields NOT_COMPARABLE. | `test_pg01_remaining_charge_never_compares_as_rated_capacity` (six cases) failed before and passes after; missing/alias/unit cases also covered. | Rated-capacity measurement unavailable; no health or origin inference. |
| PG-05 | Production metric `geekbench-single-core-tensor-g2` exposed invented 1350-1500/1420/35/n=25 data under Google OEM source. | `reference/seed.py:985`: production performance list empty. Existing storage performance test now cites synthetic source only. Performance infrastructure unchanged. | `test_pg05_production_has_no_invented_performance_distribution` failed before and passes after. Production manager returns REFERENCE_UNAVAILABLE, no source attribution. | No verified performance distribution supplied. General performance validation remains PG-16. |
| PG-06 | Eight sources hard-coded retrieval 2026-10-01, publication/revision assertions without evidence; required datetime prevented truthful unknown. | `models/reference.py:127` permits null/omitted retrieval while preserving UTC validation. `reference/seed.py:36` onward clears unsupported retrieval/publication/revision/license assertions. `reference/catalog.py:249` and seed coverage report zero verified records. | `test_pg06_seed_does_not_invent_retrieval_publication_or_revision`, `test_pg06_unknown_metadata_imports_and_roundtrips`, and coverage regression failed before and pass after. Explicit metadata round-trip and invalid UTC controls pass. | Metadata is not authentication or claim-level verification. No source verification status exists; verified counts conservatively remain zero. |
| PG-09 | 1080x2340 current display reported DIFFERS; arbitrary 73 Hz in range reported CONSISTENT. Active settings confused with panel/capability claims. | `reference/comparator.py:247` and `:266`: active or unbound supported modes are NOT_COMPARABLE for panel/native/maximum claims; no numeric equality, range or orientation verdict. | `test_pg09_active_resolution_is_not_native_panel_evidence`, `test_pg09_active_rate_cannot_prove_advertised_maximum`, mode-list tests and Java display replay failed before and pass after. | No native marker exists. Positive runtime supported-mode capability reporting awaits a validated evidence contract; no physical-panel comparison is claimed. |
| PG-10 | 9.7, 10 and 11.2 GiB OS-visible RAM passed against 12 GiB under universal allowance. | `reference/comparator.py:372`: removes reservation tolerance; NOT_COMPARABLE with no installed-RAM observation. | `test_pg10_os_visible_ram_has_no_installed_memory_tolerance` failed before and passes after. Free/missing memory and explicit unit cases covered. | Installed physical RAM cannot be established by current collector. |
| PG-11 | Toggle false reported DIFFERS; feature false could be overridden by enabled true using `or`. | `reference/comparator.py:390`: strict bool/numeric 0/1 feature declaration only; no enabled fallback; missing/malformed feature stays insufficient. | `test_pg11_nfc_toggle_alone_is_not_hardware_evidence`, false-feature/true-toggle and malformed-feature tests failed before and pass after. Optional absent variant and invariant capability controls pass. | Comparison is a runtime declaration, not NFC function or provenance verification. |

## D. Safety boundaries

Unknown rated battery capacity, active display modes, and OS-visible RAM cannot
produce physical specification consistency or mismatch. Corresponding
`observed_value` is null; raw diagnostic readings and units remain unchanged.
Missing observations remain INSUFFICIENT_EVIDENCE. Missing reference properties
remain REFERENCE_UNAVAILABLE. NFC disabled state never replaces feature evidence.

The shared per-property reference guard requires equal values across every
catalogued candidate; a missing property on one candidate is also uncertainty.
It returns VARIANT_AMBIGUOUS and no selected reference value. This does not repair
incorrect EXACT_MATCH resolutions (PG-02/03). Invariant NFC may still compare when
another property differs. No camera/core/mmWave input is synthesized.

All eight seed retrieval/publication/revision fields are unknown. Synthetic
source classification/flag consistency remains enforced. No synthetic benchmark
loads during seed construction. Existing synthetic device data remains PG-14.
No whole-dataset verification claim is made.

Compatibility: `retrieved_at` is relaxed to nullable/omittable; previously valid
explicit UTC metadata retains its value. No catalog schema version was changed.
Existing source-identity conflicts on reimport remain PG-12 debt. Consumers must
handle nullable dates. Coverage retains old verified-count keys with truthful
zero values and adds explicitly unverified inventory; no production consumer was
found. Comparator property paths and enums remain stable.

## E. Verification

| Executed check | Result |
|---|---|
| Original `uv run pytest tests/test_phase8e_reference.py -q` before fixes | 34 passed |
| New regression suite against old production code | 64 failed, 15 passed; expected red evidence retained |
| Neighboring original reference suite after production correction, before expectation repair | 7 failed, 27 passed; seven old tests encoded invalid comparisons/verified coverage |
| `uv run pytest tests/test_phase8e_reference.py tests/test_phase8e_checkpoint1.py tests/test_phase8c_diagnostics.py tests/test_phase8c_cross_language.py -q --tb=short` | 284 passed: 34 reference + 83 checkpoint + 139 Phase 8C diagnostics + 28 cross-language; one existing warning |
| `uv run pytest` | 2,237 passed, one existing Starlette/httpx deprecation warning |
| `uv run ruff check src/ tests/` | PASS |
| `uv run ruff format --check src/ tests/` | PASS; 144 files |
| `uv run mypy src/` | PASS; 99 source files |
| `scripts/verify.ps1` | Exit 0, 15/15 PASS, including local-agent, intelligence and frontend checks/install steps |
| `git diff --check` | Exit 0; tracked diff only |
| Additional whitespace scan of every dirty file, including untracked | Zero trailing-whitespace errors |
| SHA-256 baseline comparison | 304 of 310 original files byte-identical; only six authorized preexisting untracked files changed |
| Mutation controls | Not run; actual old production code supplied before-fix failures |
| Independent Claude review / formal phase gate | Not run; no phase gate requested for this checkpoint |
| Android rebuild / physical hardware qualification | Not run; Android source unchanged |

Initial sandbox attempts at Git diff and uv failed on worktree/cache access.
The same checks ran successfully with approved execution outside the sandbox.
An initial uv invocation from the root also failed to resolve the pytest script;
all reported Python verification used the canonical local-agent directory.
Initial Ruff import-order errors were corrected only in changed files and all
checks rerun successfully. No test was deleted or disabled.

## F. Deferred defects

| Finding | State and next work |
|---|---|
| PG-02 | OPEN: collect and reconcile every identity claim; resolver contradictions. |
| PG-03 | OPEN: sole catalogued variant must not become an unsupported exact match. |
| PG-04 | PARTIALLY ADDRESSED: property guards prevent first-candidate guesses; resolver/candidate completeness and remaining legacy-rule integration need review. |
| PG-07 | OPEN: verify or remove seed claims individually; questionable assertions listed above. |
| PG-08 | PARTIALLY ADDRESSED: producer/evidence matrix and real Java lifecycle tests exist; full ownership/unit adapter and real iOS identity normalization remain open. |
| PG-12 | OPEN: importer/catalog citation, alias, payload bounds, conflict targets and supersession validation. Summary labels corrected only. |
| PG-13 | OPEN: recorded source conflicts do not yet control comparison output. |
| PG-14 | PARTIALLY ADDRESSED: no synthetic performance seed, no verified coverage claim; synthetic device fixtures remain and report propagation is absent. |
| PG-15 | PARTIALLY ADDRESSED: 83 focused checkpoint cases; unrelated surviving mutation gaps remain. |
| PG-16 | OPEN: sample counts, methodology, zero deviation, variant constraints. |
| PG-17 | OPEN: ignored evidence/result parameters, report-count validation and outcome accounting. |
| PG-18 | OPEN: frontend filesystem-security workaround untouched and unproven. |
| PG-19 | OPEN: STATUS.md names 8E Android Provenance / Anomaly Signals; no roadmap amendment authorized. AGENTS.md lists ordering, not that name. |
| PG-20 | PARTIALLY ADDRESSED: docs explicitly state in-memory storage; no durable persistence implementation or broader catalog claim is implied. |

## G. Git and phase status

No staging, commit, push, branch/worktree operation, STATUS.md or AGENTS.md change,
Phase 8F start, trust activation, Probe change, signing change or device operation.
Trust Engine NOT_READY; trust_score None; authenticity UNKNOWN; hardware
qualification NOT RUN. Overall Phase 8E remains incomplete and its independent
gate failed. SAFE TO COMMIT: NO (remaining phase defects and no authorization).

## H. Next engineer handoff

1. Re-read STATUS.md and this checkpoint; recheck HEAD and preserve the dirty tree.
2. With Checkpoint 2 authorization, fix PG-02/03 in
   `local-agent/src/vector_agent/reference/resolver.py`: reconcile manufacturer,
   brand, model, marketing name and hardware codes; require positive variant-code
   evidence; handle real iOS product_type punctuation without guessing region.
3. Build PG-08's scoped evidence adapter around `models/device.py::EvidenceRecord`
   and `probe/diagnostic_evidence.py` outputs. Establish device/session ownership,
   source/error state, units and duplicate/conflicting measurements before
   populating reference observations. Keep Android/iOS concerns below domain
   contracts. Do not invent design capacity, physical RAM or native panel fields.
4. Preserve these checkpoint regressions. Extend
   `tests/test_phase8e_checkpoint1.py` / `tests/test_phase8e_reference.py` with
   resolver contradiction and missing-variant negatives; reuse the committed
   cross-language replay harness rather than idealized dictionaries for integration.
5. Keep PG-07/12/13/14/16/17/18/19 open until their authorized checkpoint. Do not
   revive benchmark data or metadata to increase coverage. Do not start 8F or
   request the final phase gate while these corrections remain.
