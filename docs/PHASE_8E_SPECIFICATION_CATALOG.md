# VECTOR — PHASE 8E SPECIFICATION CATALOG & COMPARISON ARCHITECTURE
## OEM Device Reference Database, Component Specifications & Evidence-Based Comparison

> Correction checkpoint 1: this document describes uncommitted reference work,
> not an approved change to the canonical roadmap. STATUS.md calls 8E Android
> Provenance / Anomaly Signals. The independent phase gate failed; the overall
> phase remains unapproved. See [the checkpoint contract matrix and handoff](PHASE_8E_CHECKPOINT_1.md).
> Source locators and classifications do not establish claim verification.
> No OEM source retrieval has been established for this seed.

---

## 1. Architecture and Relationship to Phase 8D

The uncommitted reference package proposes a Level 3 comparison layer. Its roadmap placement remains unresolved. Current Phase 8D reuse is limited:
- **Reuse of Canonical Taxonomy**: Reuses `ComponentKind`, `OpaqueId`, and the immutability rules of `DomainModel` (`frozen=True`, `extra="forbid"`, `strict=True`).
- **Separation of Layers**:
  - Phase 8C captures telemetry and diagnostic results (`DiagnosticResult`, `DiagnosticStatus`).
  - Phase 8D reasons over evidence provenance and physical history (`EvidenceRecord`, `ComponentAssessment`, `ProvenanceAuthorityClass`).
  - The reference package stores unverified seed claims about what the OEM designed and advertised for a specific device model and variant (`DeviceSpecification`, `ReferenceCatalog`, `SpecificationComparator`).
- **Strict Separation of Consistency vs Authenticity**:
  - A specification match (`CONSISTENT_WITH_REFERENCE`) proves only that observed hardware characteristics align with documented OEM specifications.
  - A specification match does **NOT** prove physical component originality or genuine OEM origin.
  - A specification mismatch (`DIFFERS_FROM_REFERENCE`) does **NOT** prove counterfeit, tampering, or component failure.
  - The Trust Engine remains `NOT_READY`, `trust_score` remains `None`, and `authenticity` remains `UNKNOWN` unless authenticated cryptographic attestations or OEM service certificates are independently admitted under Phase 8D policies.
  - Physical hardware qualification remains `NOT RUN`.

```
+-----------------------------------------------------------------------------------+
|                            VECTOR Core Pipeline                                   |
|                                                                                   |
|  [Phase 8C: Probe / OS Telemetry]   --> [Phase 8D: Component Provenance Policy]   |
|         |                                        |                                |
|         v                                        v                                |
|  [DeviceIdentity Clues]             [Admitted Cryptographic / Supply Chain Signals]|
|         |                                                                         |
|         v                                                                         |
|  [Phase 8E: DeviceResolver]                                                       |
|         |                                                                         |
|         v                                                                         |
|  [ReferenceCatalog]                 [SpecificationComparator]                     |
|    - Source locators                  - Explicitly incomparable measurements       |
|    - Manufacturers / Models           - No native panel claim from active modes    |
|    - Regional Variants                - No maximum-rate claim from active rate    |
|    - Hardware Specifications          - Remaining charge is not rated capacity     |
|                                       - OS-visible RAM is not installed RAM       |
|                                                  |                                |
|                                                  v                                |
|                                   [SpecificationComparisonReport]                 |
|                                     - CONSISTENT_WITH_REFERENCE                   |
|                                     - DIFFERS_FROM_REFERENCE                      |
|                                     - VARIANT_AMBIGUOUS                           |
|                                     - INSUFFICIENT_EVIDENCE                       |
|                                     - REFERENCE_UNAVAILABLE                       |
+-----------------------------------------------------------------------------------+
```

---

## 2. Reference Data Schema (`vector-catalog-v1`)

The catalog interchange format uses `"vector-catalog-v1"`. The catalog is in-memory only; no durable persistence layer is implemented.

### Top-Level Payload Format
```json
{
  "schema_version": "vector-catalog-v1",
  "sources": [ ... ],
  "manufacturers": [ ... ],
  "models": [ ... ],
  "variants": [ ... ],
  "conflicts": [ ... ],
  "performance_metrics": [ ... ]
}
```

### Schema Invariants
1. **Schema Versioning**: Ingestion strictly rejects any payload where `schema_version != "vector-catalog-v1"`.
2. **Referential Integrity**: Every manufacturer cites a valid `source_id`. Every model cites a valid `manufacturer_id` and `source_ids`. Every variant cites a valid `model_id` and `source_ids`. Orphans abort ingestion.
3. **Payload Bounds**: Max 1,000 sources and 5,000 total entities per batch to prevent memory exhaustion.
4. **Strict Typing & Units**:
   - Frequencies in Hz (`int`, 30–480 Hz)
   - Dimensions in pixels (`resolution_width`, `resolution_height`)
   - Battery capacity in mAh (`rated_capacity_mah` > 0)
   - Voltages in millivolts (`nominal_voltage_mv`)
   - Memory and storage capacities in bytes (`ram_options_bytes`, `storage_options_bytes`)
   - Dates in ISO 8601 UTC format.

---

## 3. Manufacturer, Model, and Variant Identity Model

### Manufacturer (`ManufacturerReference`)
- `manufacturer_id`: Kebab-case slug (e.g. `google`, `samsung`, `apple`).
- `canonical_name`: Official legal or corporate brand name (e.g. `Google`, `Samsung Electronics`, `Apple`).
- `aliases`: Case-insensitive aliases (e.g. `["Google LLC", "Alphabet"]`).
- `source_id`: Citation linking to corporate or regulatory registry.

### Device Model (`DeviceModelReference`)
- `model_id`: Canonical slug (e.g. `pixel-7-pro`, `galaxy-s23-ultra`, `iphone-14-pro`).
- `manufacturer_id`: References parent manufacturer.
- `marketed_name`: Public marketing name (e.g. `Pixel 7 Pro`).
- `model_family`: Product line (e.g. `Pixel`, `Galaxy S`, `iPhone`).
- `generation`: Product generation (e.g. `7`, `23`, `14`).
- `known_model_codes`: Known hardware model codes across all variants.
- `device_codenames`: Internal OS kernel codenames (e.g. `cheetah`, `dm3q`, `iphone15-2`).

### Device Variant (`DeviceVariantReference`)
- `variant_id`: Unique variant slug (e.g. `pixel-7-pro-us-ge2ae`, `galaxy-s23-ultra-us-s918u`).
- `model_id`: References parent model.
- `region_market`: Geographic applicability (e.g. `US`, `Global`, `EU`, `Japan`).
- `model_codes`: Specific hardware identifiers for this variant (e.g. `["ge2ae"]`, `["sm-s918u"]`, `["a2650"]`).
- `sku_numbers`: Manufacturer commercial order numbers (e.g. `["GA03462-US"]`).
- `network_configuration`: Distinguishing modem features (e.g. `5G Sub-6 + mmWave` vs `5G Sub-6`).
- `specifications`: Strongly typed `DeviceSpecification`.

---

## 4. Component Catalog

Phase 8E models component references across canonical `ComponentKind` domains:
- **Display Subsystem**: Panel technology, diagonal size, resolution, refresh-rate capability range (`[min_hz, max_hz]`), discrete supported refresh rates (`[10, 30, 60, 120]`), PPI, HDR standards.
- **Battery Assembly**: Rated capacity (mAh), typical capacity (mAh), nominal voltage (mV), chemistry, charging wattage (wired/wireless), user removability.
- **SoC / Processor**: Chip maker, marketing name, part number, CPU architecture, core count, GPU model, lithography node (nm).
- **Memory & Storage**: Valid RAM configurations (bytes), storage tiers (bytes), RAM technology (`LPDDR5`, `LPDDR5X`), storage technology (`UFS 3.1`, `UFS 4.0`, `NVMe`), microSD expandability.
- **Camera System**: Rear camera sensors (role, MP, aperture f-number, focal length, sensor model, OIS, autofocus), front cameras, flash presence, LiDAR / ToF presence.
- **Sensor Suite**: Biometric fingerprint sensor type, accelerometer, gyroscope, magnetometer, barometer, proximity, ambient light, NFC, Ultra-Wideband (UWB).
- **Connectivity**: Wi-Fi generations, Bluetooth version, cellular generations, USB port type, USB protocol version.
- **Audio & Haptics**: Speaker arrangement (`stereo`, `mono`), 3.5mm jack presence, haptic motor type (`linear_resonant_actuator`, `taptic_engine`).

---

## 5. Provenance and Source Requirements

Every factual assertion must cite a verifiable source record (`ReferenceSource`).

### Hierarchy of Authority (`SOURCE_AUTHORITY_RANK`)
1. **`OEM_DOCUMENTATION`** (Rank 1): Official manufacturer specifications, service manuals, support portals.
2. **`REGULATORY_FILING`** (Rank 2): FCC filings, CE technical documentation, national telecommunications certificates.
3. **`STANDARDS_BODY`** (Rank 3): USB-IF, Bluetooth SIG, Wi-Fi Alliance, JEDEC compliance listings.
4. **`AUTHORIZED_TECHNICAL_RESOURCE`** (Rank 4): OEM authorized repair networks, official developer documentation.
5. **`CREDIBLE_INDEPENDENT_REFERENCE`** (Rank 5): Professional teardowns (e.g. iFixit), verified chip analyses.
6. **`SYNTHETIC_FIXTURE`** (Rank 99): Explicitly marked mock fixtures used exclusively for software testing.

### Provenance Policies
- **No Uncited Facts**: Required policy; not fully enforced. Missing or dangling specification citations remain PG-12 debt.
- **Synthetic Isolation**: Synthetic sources must declare `is_synthetic=True` and `source_classification="SYNTHETIC_FIXTURE"`. Source flags are enforced. Synthetic device fixtures remain in the seed (PG-14); no production performance baselines are loaded. No device is counted as verified.
- **Metadata Honesty**: Unknown retrieval/publication dates and revisions are null. Supplied UTC timestamps retain validation and serialize unchanged; they do not authenticate a source. Unsupported real seed license assertions are unset. Synthetic fixture dates are also unset.
- **No Scraping**: No automated bypassing of web access controls; only factual specifications are modeled.

---

## 6. Import and Update Workflow

### Ingestion Flow (`import_catalog_payload`)
1. **JSON Schema Check**: Verifies dictionary structure and `schema_version == "vector-catalog-v1"`.
2. **Payload Size Guard**: Enforces `len(sources) <= 1000` and `total_entities <= 5000`.
3. **Atomic Staging**: Validates and inserts all records into an isolated staging `ReferenceCatalog` instance first.
4. **Referential Integrity Verification**: Ensures all citations and parent keys resolve within the payload or target catalog.
5. **Commit or Rollback**: If any record fails validation, the staging catalog is discarded and the target catalog remains untouched (transactional fail-closed behavior).
6. **Idempotence**: Re-importing identical payloads is safe and preserves existing records without duplicating entities.

### Conflict Management (`ReferenceConflict`)
When two credible sources disagree (e.g. an OEM support page states 5,000 mAh typical while a teardown cites 4,855 mAh rated):
- Both sources are preserved in `ReferenceSource`.
- An explicit `ReferenceConflict` record is created containing `field_path`, `source_a_id`, `source_a_value`, `source_b_id`, `source_b_value`, and `conflict_notes`.
- The system never silently discards or overrides one source.

---

## 7. Comparison Rules and Permitted Conclusions

### Comparison Outcomes (`ComparisonOutcome`)
- **`CONSISTENT_WITH_REFERENCE`**: Observed hardware value matches or falls within documented OEM capability range.
- **`DIFFERS_FROM_REFERENCE`**: Observed hardware value falls outside documented reference parameters.
- **`INSUFFICIENT_EVIDENCE`**: Telemetry was not collected during the scan for this property.
- **`REFERENCE_UNAVAILABLE`**: Reference catalog lacks documented specifications for this property or device is unresolved.
- **`VARIANT_AMBIGUOUS`**: Property differs across candidate variants and device resolution is ambiguous.
- **`NOT_COMPARABLE`**: Measurement models are incompatible.

### Domain-Specific Matching Rules
1. **Display Resolution**: Current and supported OS display modes do not identify native panel resolution. Numeric equality or landscape orientation cannot establish physical panel identity. Present mode observations return `NOT_COMPARABLE`; missing observations return `INSUFFICIENT_EVIDENCE`.
2. **Display Refresh Rate**: An active 60 Hz mode does not prove or disprove a 120 Hz maximum. The flat dictionary lacks validated mode units and ownership; supported-mode capability comparison awaits the evidence adapter. No broad min/max acceptance rule remains.
3. **Battery Capacity**: `charge_counter` is remaining charge in uAh. It never supplies an observed rated capacity; there is no magnitude-based conversion or 5% tolerance. `NOT_COMPARABLE` explains the missing rated-capacity measurement. Original diagnostic evidence is untouched.
4. **RAM Capacity**: `ram_total` is kernel-accessible memory, not installed RAM. It returns `NOT_COMPARABLE`; no universal reservation allowance is applied. Available memory is never substituted.
5. **NFC / Barometer**: Only strict boolean or numeric 0/1 feature declarations compare capability. `nfc_enabled` is never used as presence evidence. Declaration consistency proves neither physical function nor origin.
6. **Variants**: Compared properties must be invariant across all catalogued candidates, including missing specifications. Differing or missing candidate properties return `VARIANT_AMBIGUOUS`, without a selected reference value. Resolver correctness itself remains open.
7. **Legacy dictionary rules**: Camera counts, CPU core counts and mmWave keys are not emitted by the current Probe. Their standalone rules are not a production evidence integration; no observations are synthesized.

---

## 8. Unsupported and Ambiguous Reference Handling

### Resolution Engine Outcomes (`ResolutionStatus`)
- **`EXACT_MATCH`**: Unambiguously matches a single variant code (e.g. `GE2AE` -> `pixel-7-pro-us-ge2ae`).
- **`MODEL_MATCH_AMBIGUOUS_VARIANT`**: Matches model name (e.g. `Pixel 7 Pro`), but hardware model code is missing. Returns all candidate variants with deterministic ranking. **Never silently guesses or defaults to the US or most popular variant.**
- **`MULTIPLE_CANDIDATES`**: Multiple models match available evidence equally.
- **`CONFLICTING_IDENTIFIERS`**: Contradictory evidence detected (e.g. manufacturer declared as `Google` but hardware code is `SM-S918U` belonging to Samsung).
- **`UNSUPPORTED_DEVICE`**: Manufacturer known but model not in catalog, or unknown model.
- **`UNKNOWN_DEVICE`**: Provided identity clue fields were empty.

---

## 9. Data Coverage Inventory

`get_coverage_inventory()` reports `UNVERIFIED_STARTER_DATASET`, zero verified
devices, three unverified named device models, one synthetic model, seven
variants, and eight sources. `ReferenceCatalog.summary()` reports zero verified
sources; non-synthetic source classification is not verification. These zero
verified counts remain conservative even when supplied metadata includes a date,
since the schema has no independent claim-verification record.

The Pixel 7 Pro, Galaxy S23 Ultra and iPhone 14 Pro seed claims still require
claim-level verification (PG-07). Synthetic Model X remains deferred PG-14 work.
There are **zero performance metrics** in the production seed. Test-only numeric
performance fixtures cite `SYNTHETIC_FIXTURE` sources and are registered only in
the individual test catalog.

---

## 10. Executable Tests and Verification Commands

### Test Execution Commands
```powershell
# 1. Focused reference and checkpoint regression tests
cd local-agent
uv run pytest tests/test_phase8e_reference.py tests/test_phase8e_checkpoint1.py -v

# 2. Local-agent linter and typechecker
uv run ruff check .
uv run ruff format --check .
uv run mypy src/

# 3. Full local-agent test suite (see checkpoint handoff for actual result)
uv run pytest

# 4. Intelligence test suite (21 tests)
cd ../intelligence
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest

# 5. Frontend test suite (96 tests)
cd ../frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build

# 6. Repository-wide verification script
cd ..
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

---

## 11. Security and Privacy Assessment

- **No New Privileges Required**: Ingestion and comparison consume only existing public OS telemetry properties. No IMEI, IMSI, private phone numbers, or user files are captured or stored.
- **Untrusted Input Treatment**: Imported JSON payloads are treated as untrusted data, parsed strictly via Pydantic with forbidden extra keys and bounded collection sizes.
- **Fail-Closed Deserialization**: No arbitrary code execution or unsafe deserialization (e.g. `pickle` is prohibited).
- **Session Protection**: Probe authentication, nonce challenges, and session isolation established in Phase 8A/8B/8C remain unaltered.

---

## 12. Known Unresolved Work and Technical Debt

1. **Catalog Breadth Expansion**: The starter reference set contains 3 flagship devices (6 regional variants). Population of hundreds of older or regional devices requires operational ingestion using `import_catalog_payload`.
2. **Performance Baselines**: Phase 8E establishes the data structures and query evaluation for benchmark metrics (`PerformanceMetricReference`, `PerformanceEvaluationResult`). Actual verified multi-sample distributions require empirical benchmarking under controlled conditions.
3. **Component Serialization**: Public component part numbers are supported when published by the OEM, but manufacturer internal trace codes (e.g. battery QR serials) remain subject to physical teardown inspection.

---

## 13. Independent Review Status

The original independent phase gate **FAILED** (PG-01 through PG-20). The old
checked checklist overstated evidence and is superseded by that report.
Checkpoint 1 corrects only its authorized findings. It is not a final phase gate.
See the checkpoint handoff for executed tests and the explicit deferred findings.

---

## 14. Phase 8F Integration Contract

Phase 8F remains deferred. Checkpoint 2B adds a library boundary in
`reference/evidence_adapter.py`; it is not wired to scans, routes or frontend.
`DiagnosticEvidenceAdapter.collect_and_compare(connection, operation,
diagnostic_id, owner=owner, manager=manager)` consumes the canonical result directly
from an already connected lifecycle. It checks the connection's existing owner and
manager references before issuing a command, validates record ownership/units/state,
and returns the canonical diagnostic result, a comparison report, and per-record
admission decisions linking existing evidence UUIDs to comparison property paths.
No connection, permission grant, install, automatic retry or polling is performed.

`DiagnosticEvidenceAdapter.compare(result, owner=owner)` accepts an existing
canonical DiagnosticResult but treats it as unverified: metadata resemblance is
not authentication. Such records cannot yield a match/mismatch. Reuse one adapter
for the lifetime of each connection; repeated terminal polls of the same challenge
are not admitted as fresh observations. No multi-diagnostic aggregation is provided.
See `PHASE_8E_CHECKPOINT_2B.md` for exact contracts and fixture limitations.

The following old sketch is a **caller-supplied, unverified dictionary example**;
`scan_telemetry` is not produced by this package and it must not be presented as
Probe ingestion. Explicit evidence_records or diagnostic_results arguments to
compare now raise ValueError directing the caller to DiagnosticEvidenceAdapter:

### Public Ingestion and Lookup Contract
```python
from vector_agent.reference import (
    ReferenceCatalog,
    DeviceResolver,
    SpecificationComparator,
    PerformanceReferenceManager,
    build_seed_catalog,
    get_coverage_inventory,
)

# 1. Resolve connected device identity
catalog = build_seed_catalog()
resolver = DeviceResolver(catalog)
resolution = resolver.resolve(device_session.identity)

# 2. Compare observed properties
comparator = SpecificationComparator(catalog)
report = comparator.compare(
    resolution=resolution,
    observed_properties=scan_telemetry,
    device_id=device_session.device_id,
)

# 3. Consume report fields in UI (Phase 8F)
# report.resolution.status: "EXACT_MATCH", "MODEL_MATCH_AMBIGUOUS_VARIANT", etc.
# report.consistent_count: Number of consistent items
# report.differs_count: Number of differing items
# report.items: List of SpecificationComparisonItem with property_path, outcome, reason, honesty_warning
# report.honesty_disclaimer: Level 3 reference comparison disclaimer
```

**Boundary Rule for Phase 8F**: Phase 8F visual components MUST NOT render "Genuine OEM" badges or compute authenticity scores based on `CONSISTENT_WITH_REFERENCE` outcomes. Phase 8F must display `honesty_warning` and `limitations` prominently whenever specification comparisons are shown to operators.
