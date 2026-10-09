# VECTOR — PHASE 8E CHECKPOINT 2C HANDOFF
## PG-13: Reference Source Conflicts and False Specification Verdicts

**DATE:** 2026-10-09  
**STATUS:** COMPLETE — READY FOR INDEPENDENT GATE REVIEW  
**CORRECTION SCOPE:** PG-13 ONLY (Reference Source Conflicts and False Specification Verdicts)  
**QUALIFICATION:** CODE_TESTED  
**AUTHENTICITY:** UNKNOWN  
**TRUST ENGINE:** NOT_READY (`trust_score` remains None)  

---

## 1. Exact Git Baseline and Final State

### Git Baseline (Reconnaissance)
- **Repository Root:** `C:/Users/danis/vector`
- **Branch:** `main`
- **HEAD / origin/main:** `e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`
- **Staged Files:** 0 (`git diff --cached --name-only` empty)
- **Pre-existing Tracked Modifications:** `frontend/vitest.config.ts` (preserved untouched)
- **Pre-existing Untracked Artifacts:** Preserved intact, including `local-agent/3.11/` mypy cache databases (`cache.0.db` to `cache.15.db`, ~11 MB)
- **Baseline Test Suite:** 2,420 passed, 1 warning in 11.55s (exit code 0)

### Final Git State
- **Branch:** `main`
- **HEAD:** `e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`
- **Staged Files:** 0 (No staging, commits, branches, stashes, or pushes performed)
- **Dirty Tree Preserved:** All previous uncommitted Phase 8E files remain untouched
- **Production Files Modified:** `local-agent/src/vector_agent/reference/comparator.py`
- **Test Files Added:** `local-agent/tests/test_phase8e_checkpoint2c.py` (38 production-grade adversarial tests)
- **Handoff Documentation Created:** `docs/PHASE_8E_CHECKPOINT_2C.md`
- **Final Test Suite:** 2,458 passed, 1 warning in 9.01s (exit code 0)

---

## 2. Verified Catalog `ReferenceConflict` Structure

The actual data contract for `ReferenceConflict` resides in `local-agent/src/vector_agent/models/reference.py`:

```python
class ReferenceConflict(DomainModel):
    """Explicit recorded conflict between two credible reference sources."""

    conflict_id: IdentifierSlug
    target_entity_type: Literal["manufacturer", "model", "variant", "component"]
    target_entity_id: IdentifierSlug
    field_path: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    source_a_id: IdentifierSlug
    source_a_value: Annotated[str, Field(strict=True, max_length=256)]
    source_b_id: IdentifierSlug
    source_b_value: Annotated[str, Field(strict=True, max_length=256)]
    conflict_notes: Annotated[str, Field(strict=True, max_length=1024)]
    recorded_at: Annotated[datetime, BeforeValidator(parse_utc_datetime)]
```

### Verified Attributes and Invariants:
- `target_entity_type`: Supports `"manufacturer"`, `"model"`, `"variant"`, and `"component"`.
- `target_entity_id`: Slug identifier of the target model or variant.
- `field_path`: String expressing the dot-separated field path (e.g., `"specifications.soc.core_count"` or `"soc.core_count"`).
- `source_a_id`, `source_b_id`: Validated slug identifiers pointing to registered citations in the catalog.
- `source_a_value`, `source_b_value`: String representations of the mutually contradictory assertions.
- `conflict_notes`: Human-readable explanation of why the sources disagree.
- `recorded_at`: Timezone-aware UTC timestamp.
- **Limitation:** The model currently lacks a `status` (active vs. resolved) field; all recorded conflicts are treated as active and unresolved (conservatively blocking).

---

## 3. Catalog Conflict Creation and Retrieval Path

1. **Conflict Registration:**
   - Public API: `ReferenceCatalog.register_conflict(conflict: ReferenceConflict)`.
   - Thread Safety: Wrapped in `with self._lock:` (`threading.RLock`).
   - Referential Integrity: Checks that both `source_a_id` and `source_b_id` exist in `self._sources`. Raises `CatalogIntegrityError` if either citation is unregistered.
   - Idempotency: Appends to `self._conflicts` only if not already present.
2. **Atomic Batch Import:**
   - Handled via `import_catalog_payload(payload, target_catalog)`.
   - Conflicted claims parsed from payload `"conflicts"` key, validated into `ReferenceConflict` models, staged in an isolated catalog clone, and atomically swapped into the live catalog.
3. **Retrieval API:**
   - `ReferenceCatalog.all_conflicts() -> tuple[ReferenceConflict, ...]`.
   - `ReferenceCatalog.get_conflicts_for_entity(entity_type, entity_id) -> tuple[ReferenceConflict, ...]`.

---

## 4. Exact PG-13 Root Cause

Prior to Checkpoint 2C, `SpecificationComparator` queried `self.catalog.find_variants_for_model()` and retrieved specifications via `_reference_value(variant, path)`. It did **NOT** query `self.catalog.all_conflicts()` or `self.catalog.get_conflicts_for_entity()` anywhere.

Consequently:
- When a reference catalog recorded an explicit conflict between two sources for a specification property (e.g., Source A claiming 8 CPU cores vs. Source B claiming 6 CPU cores), the catalog preserved the conflict record in `_conflicts`.
- During comparison, the comparator examined only the single stored value in `variant.specifications` (which happened to be Source A's 8 cores).
- If the observed handset hardware reported 8 cores, the comparator returned `ComparisonOutcome.CONSISTENT_WITH_REFERENCE`, claiming the device conclusively matched reference specifications.
- If the handset reported 6 cores, the comparator returned `ComparisonOutcome.DIFFERS_FROM_REFERENCE`, claiming the device mismatched reference specifications—falsely blaming the device when in fact an underlying reference source supported that exact value.

---

## 5. Before-Fix Reproduction Output

Executed via isolated reproduction script (`scratch/reproduce_pg13.py`) against baseline code:

```
BEFORE FIX: property_path=soc.core_count
BEFORE FIX: outcome=CONSISTENT_WITH_REFERENCE
BEFORE FIX: reason=Observed 8 CPU cores matches reference 8 cores.
BEFORE FIX: consistent_count=1
```

When observed cores was 6:
```
BEFORE FIX: property_path=soc.core_count
BEFORE FIX: outcome=DIFFERS_FROM_REFERENCE
BEFORE FIX: reason=Observed 6 cores differs from reference 8 cores.
BEFORE FIX: differs_count=1
```

**Verdict:** Confirmed defect PG-13. Disputed reference was ignored, resulting in a false definitive hardware verdict.

---

## 6. Property/Model/Variant Conflict Semantics

The comparator implements strict inheritance and scope containment:

1. **Property-Level Isolation:**
   - A conflict on `soc.core_count` blocks definitive conclusions for `soc.core_count` only.
   - Uncontested properties (e.g., `camera.rear_cameras_count`, `sensors.nfc_present`) evaluate normally and produce definitive outcomes (`CONSISTENT_WITH_REFERENCE` or `DIFFERS_FROM_REFERENCE`).
   - A conflict on battery specifications does not poison NFC.
2. **Model-Level Inheritance:**
   - A conflict registered with `target_entity_type="model"` targeting `model_id` applies to all variants inheriting from that model.
3. **Variant-Level Confinement:**
   - A conflict registered with `target_entity_type="variant"` targeting `variant_id` affects only that specific variant.
   - Sibling variants under the same model without conflicts evaluate uncontested.
4. **Model Confinement:**
   - A conflict on Model A never contaminates Model B.
5. **Manufacturer Alias Confinement:**
   - Manufacturer-level records never poison device specifications.
6. **Candidate Ambiguity:**
   - In `MODEL_MATCH_AMBIGUOUS_VARIANT`, if any candidate variant has an applicable conflict on a property, that property returns `REFERENCE_UNAVAILABLE`.
   - The presence of a conflict on a candidate never eliminates that candidate or artificially upgrades identity resolution to `EXACT_MATCH`.

---

## 7. Explicit Source-Precedence Policy: NONE Unless Already Verified

- **No First-In Selection:** Source A is never preferred simply because it was registered first.
- **No Last-In Selection:** Source B is never preferred simply because it was imported last.
- **No Averaging / Interpolation:** Contradictory numeric values are never averaged.
- **No Majority Voting:** Multiple assertions do not override minority dissent.
- **No Credential Precedence:** An assertion is never favored merely because a source title or URL includes "OEM" or "Official".
- **Policy Invariant:** Any unresolved, applicable contradiction between active sources produces `ComparisonOutcome.REFERENCE_UNAVAILABLE`.

---

## 8. Production Changes and API Compatibility

### Production File: `local-agent/src/vector_agent/reference/comparator.py`
1. Added `_PROPERTY_CONFLICT_MAP` to map comparison property paths (`"soc.core_count"`, `"sensors.nfc_present"`, `"display.resolution"`, etc.) to both explicit property names and underlying schema attributes (e.g., `"specifications.sensors.nfc"`).
2. Added `_property_matches_conflict(property_path, conflict_field_path)` to perform prefix-stripping (`"specifications."`, `"base_specifications."`) and alias normalization.
3. Added `_get_applicable_conflicts(property_path, target_variant, candidate_variants, model_id)` to filter catalog conflicts by entity scope (variant vs. model), property path matching, and genuine value divergence.
4. Updated `_reference_item()`:
   - Evaluates `_get_applicable_conflicts()` before reading values.
   - If conflicts exist, returns `SpecificationComparisonItem` with `outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE`, `reference_value=None`, and `source_ids=tuple(sorted(conflicting_source_ids))`.
   - Aggregates conflict notes into item `limitations`.
5. Updated domain evaluation routines (`_compare_soc_properties`, `_compare_cameras`, `_compare_sensors_presence`, `_compare_network_configuration`, `_incomparable_measurement`):
   - Preserves caller's `observed_value` on the item if supplied, but halts evaluation and returns `REFERENCE_UNAVAILABLE`.
   - Never evaluates `is_match` or generates `CONSISTENT_WITH_REFERENCE` / `DIFFERS_FROM_REFERENCE` for conflicted properties.

### API Compatibility:
- Public signatures of `SpecificationComparator.compare()` and `_compare_properties()` remain completely unchanged.
- Fully backwards compatible with existing Checkpoint 1, 2A, 2B, and 2B.1 consumers.

---

## 9. Reference Conflict Outcome Representation

- **Outcome Enum:** `ComparisonOutcome.REFERENCE_UNAVAILABLE` (Existing canonical enum value).
- **Reference Value:** `reference_value = None` (reflecting that no uncontested reference value exists).
- **Observed Value:** Preserved on the item if supplied by caller, enabling UI reporting without generating a hardware verdict.
- **Reason Template (Single Conflict):**
  `"Reference specification for '{property_path}' is disputed between conflicting sources ({source_a_id} claims '{source_a_value}' vs {source_b_id} claims '{source_b_value}'); no authoritative reference specification is available."`
- **Reason Template (Multiple Conflicts):**
  `"Reference specification for '{property_path}' is disputed across {count} conflicting source assertions; no authoritative reference specification is available."`

---

## 10. Traceability of Conflicting Sources

- Every affected `SpecificationComparisonItem` includes `source_ids = tuple(sorted(all_conflicting_sources))`.
- Detailed conflict notes from all matching `ReferenceConflict` records are preserved in `limitations`.
- No session identifiers, device serials, adb commands, or private tokens are leaked into the report reason or limitations.

---

## 11. Impact on Comparison Report Counts

In `SpecificationComparisonReport`:
- `consistent_count`: **0** for conflicted properties (NOT incremented).
- `differs_count`: **0** for conflicted properties (NOT incremented).
- `reference_unavailable_count`: **Incremented by 1** for each conflicted property.
- `items`: The conflicted property remains present in `report.items` with complete explanation.

---

## 12. Unsupported / Conflicting Unit Handling

- Where sources assert measurements with differing units without a canonical conversion contract (e.g., "5000 mAh" vs. "18.5 Wh"), the string values do not match and are treated as conflicting assertions.
- The property is marked `REFERENCE_UNAVAILABLE`, preventing false consistency or mismatch claims.

---

## 13. Evidence Adapter Integration

- `DiagnosticEvidenceAdapter` executes `_compare()` which invokes `self._comparator._compare_properties()`.
- Because conflict handling is enforced in `_compare_properties()`, evidence arriving via `collect_and_compare()` or `compare()` cannot bypass conflict detection.
- Authenticated lifecycle feature declarations (e.g., `feature_nfc=1`) evaluated against a catalog with an active NFC conflict produce `REFERENCE_UNAVAILABLE`, preserving `consistent_count=0`.
- Verified by production test `test_checkpoint2b_evidence_adapter_cannot_bypass_applicable_reference_conflict`.

---

## 14. Test Names, Counts, Results and Exit Codes

### Checkpoint 2C Test Suite (`local-agent/tests/test_phase8e_checkpoint2c.py`)
- **Total Tests:** 38 passed in 0.34s (exit code 0)
- **Breakdown by Group:**
  - Group 1 (Primary failure): 6 tests
  - Group 2 (No false positives): 6 tests
  - Group 3 (Hierarchy & scope): 5 tests
  - Group 4 (Values & source semantics): 6 tests
  - Group 5 (Integration protection): 7 tests
  - Group 6 (Report invariants): 8 tests

### Test Inventory:
1. `test_two_sources_disagree_same_property_blocks_definitive_verdict` (VERIFIED BY PRODUCTION TEST)
2. `test_conflict_observed_value_equals_source_a_remains_non_definitive` (VERIFIED BY PRODUCTION TEST)
3. `test_conflict_observed_value_equals_source_b_remains_non_definitive` (VERIFIED BY PRODUCTION TEST)
4. `test_conflict_observed_value_matches_neither_source_remains_non_definitive` (VERIFIED BY PRODUCTION TEST)
5. `test_reverse_source_insertion_order_produces_identical_conflict_outcome` (VERIFIED BY PRODUCTION TEST)
6. `test_reverse_observation_construction_order_produces_identical_conflict_outcome` (VERIFIED BY PRODUCTION TEST)
7. `test_two_sources_identical_compatible_assertions_no_conflict` (VERIFIED BY PRODUCTION TEST)
8. `test_same_source_asserted_twice_with_identical_value_no_conflict` (VERIFIED BY PRODUCTION TEST)
9. `test_different_sources_assert_different_properties_no_conflict` (VERIFIED BY PRODUCTION TEST)
10. `test_missing_or_unknown_source_assertion_no_conflict` (VERIFIED BY PRODUCTION TEST)
11. `test_unrelated_conflict_from_different_model_does_not_poison` (VERIFIED BY PRODUCTION TEST)
12. `test_unrelated_conflict_from_different_variant_does_not_poison` (VERIFIED BY PRODUCTION TEST)
13. `test_model_level_conflict_inherited_by_variant` (VERIFIED BY PRODUCTION TEST)
14. `test_variant_only_conflict_does_not_poison_sibling_variant` (VERIFIED BY PRODUCTION TEST)
15. `test_ambiguous_variant_cannot_become_exact_because_of_conflict` (VERIFIED BY PRODUCTION TEST)
16. `test_unknown_model_does_not_result_in_invented_reference` (VERIFIED BY PRODUCTION TEST)
17. `test_conflicts_affecting_optional_missing_fields_reported_truthfully` (VERIFIED BY PRODUCTION TEST)
18. `test_different_units_without_explicit_conversion_treated_as_conflict` (VERIFIED BY PRODUCTION TEST)
19. `test_empty_or_malformed_conflict_property_reference_handled_safely` (VERIFIED BY PRODUCTION TEST)
20. `test_dangling_source_identifier_in_conflict_handled_safely` (VERIFIED BY PRODUCTION TEST)
21. `test_source_metadata_change_without_spec_value_change_no_conflict` (VERIFIED BY PRODUCTION TEST)
22. `test_multiple_conflicting_sources_for_single_property` (VERIFIED BY PRODUCTION TEST)
23. `test_multiple_independent_conflicts_for_different_properties` (VERIFIED BY PRODUCTION TEST)
24. `test_checkpoint2a_exact_match_behavior_remains_intact_when_no_conflicts` (VERIFIED BY PRODUCTION TEST)
25. `test_variant_ambiguity_remains_non_definitive` (VERIFIED BY PRODUCTION TEST)
26. `test_checkpoint2b_evidence_adapter_cannot_bypass_applicable_reference_conflict` (VERIFIED BY PRODUCTION TEST)
27. `test_caller_supplied_evidence_remains_unverified` (VERIFIED BY PRODUCTION TEST)
28. `test_hardware_authenticity_remains_unknown` (VERIFIED BY PRODUCTION TEST)
29. `test_reference_conflict_cannot_be_presented_as_evidence_of_replacement_or_tampering` (VERIFIED BY PRODUCTION TEST)
30. `test_no_source_disagreement_can_become_trust_engine_score_or_verdict` (VERIFIED BY PRODUCTION TEST)
31. `test_conflict_property_counted_exactly_once_in_items` (VERIFIED BY PRODUCTION TEST)
32. `test_conflict_property_not_counted_as_consistent` (VERIFIED BY PRODUCTION TEST)
33. `test_conflict_property_not_counted_as_differs` (VERIFIED BY PRODUCTION TEST)
34. `test_unaffected_properties_retain_valid_outcomes_and_counts` (VERIFIED BY PRODUCTION TEST)
35. `test_stable_deterministic_output_across_equivalent_source_orders` (VERIFIED BY PRODUCTION TEST)
36. `test_conflict_reason_references_only_legitimately_available_source_data` (VERIFIED BY PRODUCTION TEST)
37. `test_repeated_comparisons_do_not_mutate_catalog_state` (VERIFIED BY PRODUCTION TEST)
38. `test_repeated_comparisons_produce_identical_results_for_unchanged_catalog_state` (VERIFIED BY PRODUCTION TEST)

### Regression Test Suite Results:
- `test_phase8e_reference.py`, `test_phase8e_checkpoint1.py`, `test_phase8e_checkpoint2a.py`, `test_phase8e_checkpoint2b.py`, `test_phase8e_checkpoint2c.py`: **338 passed in 1.22s** (exit code 0)
- `test_phase8c_cross_language.py`: **28 passed in 0.39s** (exit code 0)
- Full local-agent test suite: **2,458 passed, 1 warning in 9.01s** (exit code 0)
- Lint (`uv run ruff check src/ tests/`): **All checks passed!** (exit code 0)
- Formatting (`uv run ruff format --check src/ tests/`): **148 files already formatted** (exit code 0)
- Type checking (`uv run mypy src/`): **Success: no issues found in 100 source files** (exit code 0)

---

## 15. Mutation-Testing Results & Historical Correction (CG-01)

### Historical Correction: Invalid Initial Checkpoint 2C Claim
The previous handoff claimed a 12 / 12 (100.0%) mutation kill rate via `scratch/run_2c_mutations.py`. **That claim was invalid**, as identified in Claude's independent Checkpoint 2B.1 + 2C gate review (Finding CG-01):

1. **Eight mutations failed with SyntaxError / IndentationError** due to brittle line-replacement in the ad-hoc runner, rather than being killed by test assertions. Counting syntax errors as assertion kills was invalid.
2. **Two mutations targeted an unrelated comparator path** or had no semantic effect on the test assertions.
3. **Only two mutations were valid relevant mutations** killed by actual test assertions.
4. **The original runner temporarily modified the LIVE comparator file**, which violated safety policies.

### Independent Review Breakdown of Initial 12 Mutants
- **Mutants with SyntaxError / IndentationError (8)**: M02, M03, M04, M07, M08, M09, M10, M12
- **Mutants targeting wrong/unrelated paths (2)**: M05, M06
- **Valid Relevant Mutation Kills (2)**: M01 (ignore all conflicts), M11 (source registration order)
- **Actual Historical Kill Rate**: 2 / 12 valid kills (16.7%).

### Correction in Checkpoint 2C.1
As mandated by CG-01, the mutation framework was redesigned from scratch in Checkpoint 2C.1 (`scratch/run_2c1_mutations.py`):
- Operates strictly on an isolated scratch copy in `scratch/mutation_sandbox/` outside the repository.
- Live repository files are verified with SHA-256 hashes before and after and are **never mutated**.
- Validates syntax compilation via `py_compile` before test execution. Syntax errors are never counted as kills.
- Confirms kills strictly by relevant assertion failure (`AssertionError`).
- In Checkpoint 2C.1, 16 prioritized mutations were executed against the expanded 55-test suite, achieving **16 / 16 valid kills (100%)**. Full details are recorded in `docs/PHASE_8E_CHECKPOINT_2C1.md`.

---

## 16. Unaffected Comparator Behavior and Compatibility Tests

- All baseline comparison methods (`EXACT_MATCH`, `NUMERIC_TOLERANCE`, `RANGE_BOUND`, `SUBSET_MATCH`, `CAPABILITY_PRESENCE`) continue to operate without modification when no catalog conflicts are registered.
- Incomparable physical telemetry (`display.resolution`, `display.refresh_rate_hz`, `battery.rated_capacity_mah`, `memory.ram_total_bytes`) retains `NOT_COMPARABLE` outcomes when observations exist and no reference conflicts are registered.
- Variant ambiguity (`VARIANT_AMBIGUOUS`) continues to be returned when candidate regional variants diverge.
- Missing telemetry continues to report `INSUFFICIENT_EVIDENCE`.

---

## 17. Complete Changed-File Inventory

| File Path | Action | Description |
| :--- | :--- | :--- |
| `local-agent/src/vector_agent/reference/comparator.py` | MODIFIED | Implemented catalog conflict detection, property mapping, and non-definitive `REFERENCE_UNAVAILABLE` outcome logic. |
| `local-agent/tests/test_phase8e_checkpoint2c.py` | ADDED | 38 comprehensive adversarial regression tests across 6 groups. |
| `docs/PHASE_8E_CHECKPOINT_2C.md` | ADDED | Complete 20-section Checkpoint 2C handoff document. |

---

## 18. Hash Audit of Previously Dirty Files

| File Path | Baseline SHA-256 | Current SHA-256 | Status |
| :--- | :--- | :--- | :--- |
| `frontend/vitest.config.ts` | `379CD3A4DACCA4B71B9CCCC38FDDD48299E2A95EFE31507E04C2BF236F7B5BB0` | `379CD3A4DACCA4B71B9CCCC38FDDD48299E2A95EFE31507E04C2BF236F7B5BB0` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/models/reference.py` | `160B4B42F7C83B757C747960B547B36C434975E800361BC2177A2A54E839C5CF` | `160B4B42F7C83B757C747960B547B36C434975E800361BC2177A2A54E839C5CF` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/catalog.py` | `603A4ED99260FBFDF340E1FBC100AD6C7363D2B2DE54D94FD91FB80E36070021` | `603A4ED99260FBFDF340E1FBC100AD6C7363D2B2DE54D94FD91FB80E36070021` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/evidence_adapter.py` | `851B5409A75237938AC47948BD6171EE5F2131AD8898AB8F087105C917F5E754` | `851B5409A75237938AC47948BD6171EE5F2131AD8898AB8F087105C917F5E754` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/importer.py` | `FA9EFDFE5306BB5309419770C72C7214C6CC7C2827420F97969898128F3EF439` | `FA9EFDFE5306BB5309419770C72C7214C6CC7C2827420F97969898128F3EF439` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/performance.py` | `EAEDB1449DA5FE24380EEEAD5399B1F10C6651C867535BE9C3CC6AA65FA56F36` | `EAEDB1449DA5FE24380EEEAD5399B1F10C6651C867535BE9C3CC6AA65FA56F36` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/resolver.py` | `53144B631D88070EF47EC304439D8CF5ECEE77AA5266AA15FD185E8204C3160C` | `53144B631D88070EF47EC304439D8CF5ECEE77AA5266AA15FD185E8204C3160C` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/seed.py` | `97C979DC4206EACFC9647AF2D1CB56AFD46781BBDCCB02AE628F233C170845DE` | `97C979DC4206EACFC9647AF2D1CB56AFD46781BBDCCB02AE628F233C170845DE` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/__init__.py` | `54AF0E83EA0758E08C2C77BF21ECAAEE88FF88083E0C4603BF1FB59FDBE19D83` | `54AF0E83EA0758E08C2C77BF21ECAAEE88FF88083E0C4603BF1FB59FDBE19D83` | **MATCH (UNTOUCHED)** |
| `local-agent/src/vector_agent/reference/comparator.py` | `3C560685CDC86A1FBD9CCE0761D1991D6D96D50A748F653FC418CEBC1E3B83CE` | `1EE2C73E3D68632444729F41AD898559E440029095D27AAD35D3889E4491062A` | **MODIFIED (PG-13 FIX)** |

---

## 19. Remaining PG Findings (Explicitly Preserved Open)

As instructed, this checkpoint resolved PG-13 exclusively. The following findings remain open and pending their authorized checkpoints:
- **PG-04:** Remaining variant ambiguity limitations.
- **PG-07:** OEM reference source correctness and citation audits.
- **PG-12:** Catalog/import integrity and conflict resolution lifecycle.
- **PG-14:** Production versus synthetic catalog isolation.
- **PG-15:** Remaining mutation-testing gaps across catalog importer.
- **PG-16:** Performance-reference baseline methodology.
- **PG-17:** Broad report-accounting validation.
- **PG-18:** Frontend configuration.
- **PG-19:** Canonical roadmap mismatch.
- **PG-20:** Catalog persistence/documentation claims.

All security safeguards from PG-01, PG-02, PG-03, PG-08, and Checkpoint 2B.1 remain active.
`STATUS.md` is unchanged.

---

## 20. Exact Next Checkpoint Prerequisites

Before initiating any subsequent checkpoint (e.g., Checkpoint 3 or Phase 8E gate):
1. Independent gate verification of Checkpoint 2C.
2. Authorization for catalog schema lifecycle improvements (PG-12) or citation audits (PG-07).
3. Continued preservation of the dirty working tree (no staging or committing).
