# Phase 8E correction checkpoint 2A — identity resolution

Scope: PG-02 and PG-03 only. No evidence adapter, comparator expansion, source
conflict handling, catalog correction, or later phase is authorized.

## Baseline

Canonical path `C:\Users\danis\vector`, branch `main`, HEAD and origin/main
`e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`. Zero staged files. Initial dirty tree
contains the 13 entries recorded after Checkpoint 1 (one tracked frontend config
change and twelve untracked files). Initial reference + Checkpoint 1 baseline:
117 passed, exit 0. Hashes for all 312 tracked/preexisting untracked files and a
byte snapshot of resolver.py were captured outside the repository in this chat's
`checkpoint2a` audit directory before editing.

## Identity contract matrix — established before implementation

These are software producer/contract facts, not real-device or OEM qualification.
No adapter/collector is changed. Missing values remain missing.

| Field | Actual source and discovery availability | Meaning / granularity | Supported matching and contradictions |
|---|---|---|---|
| manufacturer | Android bridge `_IDENTITY_PROPS`: `ro.product.manufacturer`, session forwards it. iOS bridge supplies constant `Apple Inc.` | Reported manufacturer; iOS value is adapter-assigned, not independent evidence | Case/whitespace normalization and explicit catalog aliases; terminal full stop ignored for corporate spelling (`Apple Inc.`/`apple inc`). Evaluate separately from brand. Unknown manufacturer blocks exact matching; do not assume it is an alias. |
| brand | Android `ro.product.brand`; iOS constant `Apple` | Brand claim, not automatically equivalent to manufacturer | Only explicit manufacturer aliases establish equivalence. Recognized different manufacturer/brand memberships conflict. Missing brand is not a conflict. |
| marketing_name | Both current discovery producers set None | Manually supplied marketing model name; no current producer observation | Compare full normalized catalog marketed name, not fuzzy substrings. Recognized name incompatible with model/code conflicts. |
| model | Android `ro.product.model`; iOS `ProductType` or `DeviceClass` or literal `Unknown` fallback | Android may carry model name or variant code. iOS normally carries a product-type identifier; fallback does not identify model | Full marketed-name/code matching. iOS product identifier can match catalog device_codenames, never derive a regional A-number. Each independent recognized clue constrains the result. |
| hardware_model | Android session does not populate it. iOS queries allowlisted `HardwareModel` | Opaque hardware identifier; current iOS tests use `D73AP`. No production contract establishes that this is an A-number | Only explicit catalog code relationships may match; unknown board identifiers remain unresolved and block exact matching. No board-to-region inference. Hand-built A-number tests are catalog matching tests, not producer evidence. |
| product_type | Android None; iOS allowlisted `ProductType` | Product/model identifier, e.g. `iPhone15,2`; not regional identity | Narrow full-token normalization maps `iphone15,2` and catalog `iphone15-2` to the same pair, preserving the number boundary. No arbitrary comma removal (`iPhone1,52` is different). |
| device_codename | Android `ro.product.device`; iOS None | Device codename, model-level only where catalog explicitly maps it | Match catalog device_codenames; incompatible recognized codename conflicts; unknown codename is reported as unresolved. Never promotes a sole variant. |
| iOS hardware identifier | `ProductType` and `HardwareModel` are distinct queries in `devices/ios/bridge.py:get_identity` | Existing tests show separate product and board strings; no region mapping exists in the contract | Preserve both independently. `iPhone15,2` matches the existing catalog model token only; D73AP cannot validate any regional A-number. |
| regional variant identifier | No dedicated discovery field. Android model may match an explicit variant code. No current iOS regional A-number query | Exact catalog variant requires a discriminating, compatible code | Intersect all supplied code constraints. Catalog cardinality and candidate order are never evidence. |
| raw_properties | No production caller of reference resolver currently supplies this API | Supplemental caller-supplied claims, not authenticated evidence | Only the identity fields above and their actual Android/iOS producer key names are meaningful. Evaluate them independently of DeviceIdentity instead of overwriting it; ignore unrelated keys and do not expose identifiers such as serial/UDID. |
| platform | Session/adapter platform enum; reference records contain no platform field | Transport context | Preserve known platform; no manufacturer-to-platform rule can be inferred from the catalog. |

Code normalization retains the existing case/whitespace/hyphen/underscore
convention for catalog codes. The iPhone product-token rule is separate and
preserves numeric components. No OEM mapping or new device alias is invented.
The catalog has only Pixel 7 Pro, Galaxy S23 Ultra, iPhone 14 Pro and Synthetic
Model X; `GVU6C` has no mapping here, so its model cannot be asserted. Known
incompatible codes can establish conflict; unmapped codes only establish a gap.

Producer references: `devices/android/bridge.py:178`, `devices/session.py:238`,
`devices/ios/bridge.py:414`, `models/device.py:188`; catalog identity contracts:
`models/reference.py` and `reference/seed.py`. Existing iOS producer tests:
`tests/test_ios_expanded_bridge.py:87`.

## PG-02 — root cause, correction and evidence

Old resolver selected the first recognized manufacturer/brand, then used weighted
model scores. It could prefer a hardware code over a contradictory marketed name,
ignore the second brand claim, ignore unmapped supplied identifiers, and accept
contradictory regional codes. `raw_properties` were echoed but not evaluated.

`reference/resolver.py:72` now extracts all seven identity fields and independently
retains allowlisted supplemental claims. `:119` builds model/manufacturer/variant
constraint sets; `:183` onward intersects them. Empty intersections return
CONFLICTING_IDENTIFIERS with the contributing field labels and their original
values in considered_fields. Unknown claims are recorded and block EXACT_MATCH;
unknown manufacturer/brand returns UNSUPPORTED_DEVICE because its relationship
to the catalog cannot be established. No spelling-based OEM alias is invented.
Private/unrelated raw keys are neither evaluated nor copied into the result.

Concrete before/after results:

| Synthetic input | Old behavior | Corrected behavior |
|---|---|---|
| Xiaomi + SM-S918B | EXACT Samsung | UNSUPPORTED_DEVICE; unmapped manufacturer gap identified |
| Google manufacturer + Samsung brand (and reverse) | No explicit conflict | CONFLICTING_IDENTIFIERS |
| SM-S918B model + Pixel 7 Pro marketing name | EXACT Samsung | CONFLICTING_IDENTIFIERS |
| Pixel 7 Pro model + SM-S918B hardware code | EXACT Samsung without manufacturer constraint | CONFLICTING_IDENTIFIERS |
| Pixel 7 Pro + dm3q codename | Preferred one scored model | CONFLICTING_IDENTIFIERS |
| SM-S918B model + SM-S918U hardware code | Ambiguous variants | CONFLICTING_IDENTIFIERS |
| Known exact candidate plus unmapped supplied model/codename/etc. | Several paths silently exact | Explicit non-exact outcome naming the unresolved field |
| Compatible Samsung manufacturer aliases, dm3q and B/U model codes | EXACT | EXACT preserved |
| Identity Samsung + supplemental ro.product.model Pixel 7 Pro | Supplemental claim ignored | CONFLICTING_IDENTIFIERS |

The same-manufacturer disagreement is also tested using an explicitly synthetic
second model under Google; no real OEM mapping is claimed by that fixture.

## PG-03 — root cause, correction and evidence

The old resolver promoted any sole catalogued variant to EXACT_MATCH, even when
its code did not match. A catalog's incomplete inventory became device evidence.

`reference/resolver.py:253` onward now requires one variant in the intersection
of explicitly matched variant codes, compatible model/manufacturer constraints,
and no unresolved supplied claim. No sole-variant shortcut remains. Synthetic
model/manufacturer sources return UNSUPPORTED_DEVICE; synthetic variant sources
cannot produce an exact real-device match. This is a resolver guard only: the
catalog, comparator, synthetic seed contents, and source-conflict policy are not
changed. The existing source classification is not promoted to OEM verification.

| Synthetic input/catalog | Old behavior | Corrected behavior |
|---|---|---|
| Only GE2AE variant; Pixel 7 Pro model alone | EXACT US GE2AE | MODEL_MATCH_AMBIGUOUS_VARIANT |
| Only GE2AE variant; observed GP4BC | EXACT US GE2AE | MODEL_MATCH_AMBIGUOUS_VARIANT; missing variant mapping identified |
| Only GE2AE variant; observed GVU6C | EXACT US GE2AE | MODEL_MATCH_AMBIGUOUS_VARIANT; code unmapped, no inferred Pixel 7 identity |
| Only GE2AE variant; compatible GE2AE code | EXACT GE2AE | EXACT GE2AE preserved |
| GE2AE model code plus GP4BC hardware code with incomplete catalog | EXACT GE2AE | Non-exact; unmapped variant constraint cannot be overridden |
| Synthetic Model X, with or without synth-x1 | EXACT synthetic variant without output qualification | UNSUPPORTED_DEVICE with synthetic-source reason |
| iOS producer iPhone15,2 + D73AP | UNSUPPORTED_DEVICE | Model matches existing iPhone 14 Pro catalog token; regional variant remains ambiguous, board identifier unresolved |

`resolver.py:51` narrowly normalizes the two components of iPhone product tokens.
It does not remove commas indiscriminately: `iPhone1,52`, `iPhone152`, malformed
double comma and slash tokens do not identify `iPhone15,2`. No regional A-number
is inferred. The known catalog spelling `iphone15-2` is used; the underlying
model mapping remains an unverified seed claim (PG-07), not newly verified here.

## Tests and verification

Before production changes, `uv run pytest tests/test_phase8e_checkpoint2a.py -q
--tb=short` returned exit **1**: **31 failed, 13 passed**. All failures were
assertion failures against the production resolver, including actual Android
bridge/session and iOS identity producer paths with mocked external reads.
No physical device was accessed. The initial 44 cases all pass after correction.
Seven additional tests cover same-manufacturer conflict, a synthetic variant
under a real model, four malformed supplemental values, and iOS product-only
ambiguity. Final checkpoint count: **51 passed**.

| Command/check | Final result | Exit |
|---|---|---|
| `uv run pytest tests/test_phase8e_checkpoint2a.py tests/test_phase8e_reference.py tests/test_phase8e_checkpoint1.py tests/test_ios_bridge.py tests/test_ios_expanded_bridge.py -q --tb=short` | 205 passed: 51 new + 34 reference + 83 Checkpoint 1 + 37 iOS producer tests | 0 |
| `uv run pytest` | 2,288 passed; one preexisting Starlette/httpx deprecation warning | 0 |
| `uv run ruff check src/ tests/` | All checks passed | 0 |
| `uv run ruff format --check src/ tests/` | 145 files already formatted | 0 |
| `uv run mypy src/` | 99 source files clean | 0 |
| `scripts/verify.ps1` | 15/15 checks passed, including Python/intelligence/frontend checks and its declared install steps | 0 |
| `git diff --check` | No whitespace errors; existing package-lock LF/CRLF advisory only | 0 |

An initial mypy run found one local variable name redefinition; it was corrected
and final typing/tests rerun. Formatting touched only resolver.py and the new
test file. Existing test assertions were not altered, weakened, skipped or
deleted. No dependencies were added. Actual old-code execution supplied the
negative control; isolated mutation testing was unnecessary and not run.
Independent Claude review, formal phase gate, Android rebuild and hardware
qualification were not run or claimed. No final Phase 8E gate was requested.

Full logs and the initial resolver byte snapshot are retained in:
`C:\Users\danis\.codex\visualizations\2026\10\09\01a1202a-83f0-7193-8397-2687f8851f92\checkpoint2a`.

## Files and final integrity

Only these three files were changed/created during 2A:

1. Modified `local-agent/src/vector_agent/reference/resolver.py`.
2. Added `local-agent/tests/test_phase8e_checkpoint2a.py`.
3. Added `docs/PHASE_8E_CHECKPOINT_2A.md`.

Final tree has 15 dirty entries: all 13 initial paths plus two additions.
SHA-256 comparison found 311 of 312 preexisting files byte-identical; resolver.py
is the only changed preexisting path. All 300 tracked files and all Checkpoint 1
files retain their initial bytes. Zero staged files; no commit or push. HEAD,
origin/main and branch remain unchanged. No reset, clean, stash, revert, worktree,
branch operation, STATUS.md/AGENTS.md edit, Probe change, trust change, or frontend
configuration edit was performed. The root script's generic "safe to commit"
message is not phase approval or commit authorization.

## Remaining limitations and unresolved findings

- PG-02/PG-03 are corrected against the current identity/catalog contracts.
  Exact means compatible **catalog identity**, never authenticity or OEM-source
  verification. Unmapped facts still cannot be resolved exactly.
- Android discovery has no regional hardware_model field. A model string may
  discriminate only through an explicit catalog code relationship.
- iOS HardwareModel board relationships and regional A-number mapping are absent;
  no inference is made. The product-token seed mapping itself is not newly verified.
- No platform field exists on catalog models. No manufacturer-to-platform rule
  was assumed. Aliases/codes supplied by the catalog are conditional inputs;
  catalog completeness, validity and claim support remain separate open work.
- All resolver outputs are software-tested only. No connected-device observation
  is authenticated by this API, and no physical authenticity is established.
- PG-04, PG-07, PG-08 (full evidence adapter), PG-12, PG-13, PG-14 (broader synthetic
  isolation), PG-15 (remaining unrelated gaps), PG-16 through PG-20 retain their
  prior open/partially-addressed status. PG-08's identity-token normalization and
  PG-14's exact-identity guard are addressed only within this resolver scope.
- The canonical roadmap still names 8E Android Provenance / Anomaly Signals.
  This correction does not approve the uncommitted OEM-reference work as that phase.
- Trust Engine NOT_READY, trust_score None, authenticity UNKNOWN, hardware
  qualification NOT RUN. Phase 8E remains incomplete. No 2B/2C/3/8F work started.

## Instructions for Checkpoint 2B — deferred, not executed

On explicit 2B authorization, first read STATUS.md, both checkpoint handoffs,
the actual 2B requirements, and capture this dirty-tree baseline. Preserve the
new resolver constraints and all three reference test files. Inspect
`models/device.py::EvidenceRecord`, `models/probe_diagnostics.py`,
`probe/diagnostic_evidence.py`, and the existing cross-language lifecycle replay
harness before designing the adapter. Establish ownership (device/session),
source/error state, units, duplicates and contradictory observations before
constructing comparison inputs. Use existing measurements only; do not invent
rated battery capacity, physical RAM or native-panel identity. Add negative and
real-fixture contract tests before implementation. Do not fold PG-13 reference
source-conflict handling or catalog corrections into 2B without its authorization.

Stop here. No staging, commit, push or further checkpoint work is authorized.

## Exact old-code failing cases (all pass in the final suite)

- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields0]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields1]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields2]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields3]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields4]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields5]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields6]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields7]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_all_recognized_claims_must_agree[fields8]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unknown_manufacturer_cannot_be_silently_assumed_samsung`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict[model]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict[marketing_name]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict[device_codename]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict[hardware_model]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict[product_type]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict[brand]`
- `tests/test_phase8e_checkpoint2a.py::test_pg03_one_catalog_variant_is_not_evidence_of_that_variant[fields0]`
- `tests/test_phase8e_checkpoint2a.py::test_pg03_one_catalog_variant_is_not_evidence_of_that_variant[fields1]`
- `tests/test_phase8e_checkpoint2a.py::test_pg03_one_catalog_variant_is_not_evidence_of_that_variant[fields2]`
- `tests/test_phase8e_checkpoint2a.py::test_pg03_missing_catalog_variant_code_cannot_be_overridden_by_another_code`
- `tests/test_phase8e_checkpoint2a.py::test_pg03_synthetic_identity_never_becomes_real_exact_identity[None]`
- `tests/test_phase8e_checkpoint2a.py::test_pg03_synthetic_identity_never_becomes_real_exact_identity[synth-x1]`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_raw_producer_claim_cannot_be_ignored_or_override_identity`
- `tests/test_phase8e_checkpoint2a.py::test_pg02_raw_producer_claims_resolve_without_fabricated_identity_fields`
- `tests/test_phase8e_checkpoint2a.py::test_unrelated_raw_identifiers_are_not_exported`
- `tests/test_phase8e_checkpoint2a.py::test_ios_product_identifier_matches_model_without_inventing_region[iPhone15,2]`
- `tests/test_phase8e_checkpoint2a.py::test_ios_product_identifier_matches_model_without_inventing_region[iphone15-2]`
- `tests/test_phase8e_checkpoint2a.py::test_ios_product_identifier_matches_model_without_inventing_region[ IPHONE15,2 ]`
- `tests/test_phase8e_checkpoint2a.py::test_ios_product_normalization_does_not_collapse_distinct_identifiers[iPhone152]`
- `tests/test_phase8e_checkpoint2a.py::test_actual_android_bridge_and_session_identity_to_resolver[Xiaomi-UNSUPPORTED_DEVICE]`
- `tests/test_phase8e_checkpoint2a.py::test_actual_ios_identity_producer_preserves_unknown_board_and_ambiguous_region`
