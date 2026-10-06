# VECTOR engineering rules

- Read `STATUS.md` before every substantial task; treat it as the project source of truth.
- Work only within the explicitly authorized phase/subphase. Stop at its boundary; do not start another phase.
- Do not stage, commit, push, or modify `STATUS.md` without explicit user authorization.

## Evidence and architecture

- Every PASS requires evidence. Certainty must never exceed evidence.
- Unsupported != Failed; Restricted != Failed; Inconclusive != Failed; execution ERROR != hardware FAIL.
- LIVE must never silently fall back to DEMO.
- Level 1 runtime detection != Level 2 functional verification != Level 3 reference comparison.
- Physical diagnostic claims remain CODE_TESTED until real-device qualification; never claim HARDWARE_VALIDATED without it.
- Keep functionality separate from authenticity/provenance. Never infer genuine/original from successful function.
- Use UNKNOWN/INCONCLUSIVE when provenance cannot be defensibly established. Never claim VERIFIED_GENUINE from ordinary Android telemetry or behavior; use no numerical provenance confidence.
- Keep Android/iOS adapters below platform-neutral domain and evidence models.

## Security and approved Phase 8 defaults

- Protect raw serials, UDIDs, IMEIs, and private data in APIs, evidence, logs, and storage.
- Use fixed executables + validated argv arrays + shell=False + bounded timeouts and output.
- No automatic iOS pairing.
- Android minimum API 26 is provisional; gate capabilities per API.
- Probe installation is explicit/manual for the first increment. No automatic install, uninstall, or permission grant.
- No root, exploit, hidden service, repair/calibration write, BMS reset, or security bypass.
- Development signing only; do not create or store production release keys in this repository.
- Initial operation is local-only, with no external/cloud attestation dependency.
- Phase 8 order: 8A -> 8D -> 8B -> 8C -> 8E -> 8F -> 8G. These defaults persist unless the user explicitly changes them; this order does not authorize advancing beyond the assigned slice.

## Implementation workflow

Implementation -> focused tests -> regression -> `scripts/verify.ps1` -> diff audit -> Claude independent review -> corrections -> formal phase gate -> controlled commit.
Retest corrections before the formal gate. Report unavailable checks/review honestly; never claim an unperformed gate passed. A controlled commit still requires explicit user authorization.
