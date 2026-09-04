# Plan — Pro-Edit Ledger Corrections for T6 and T7 (`specs/pro-edit-corrections`)

Approved-by: Hawa

## Executive Summary
Implement Task T0.2 from `specs/pro-grade-program/tasks.md`:
1. Annotate rows T6 and T7 in `specs/pro-edit/tasks.md` in place, citing ADR D-262 and documenting that they are re-opened as T4.9 and T2.1 respectively, per `HANDOFF.md` §1.6.
2. Create `evidence/two-rows-flipped-for-features-that-did-not-exist.md`.
3. Add proof test `test_the_reopened_rows_cite_the_correction_adr` in `tests/test_claims.py`.
4. Run full gate verification and flip ledger.

## Technical Changes

### 1. `specs/pro-edit/tasks.md`
Add correction text beneath T6 and T7:
- For T6: `*Correction 2026-09-02 (ADR D-262)*: Cited tests proved text data structures under mock judge only, not media rendering or pipeline concatenation. Re-opened as Task T4.9 in pro-grade master.`
- For T7: `*Correction 2026-09-02 (ADR D-262)*: Cited test proved that unavailable diarizer does not falsely claim speaker tracking in contract, not visual speaker-face tracking. Re-opened as Task T2.1 in pro-grade master.`

### 2. `evidence/two-rows-flipped-for-features-that-did-not-exist.md`
Document:
- YAML metadata (`commit:`, `host: HAWAPC01`, `date:`).
- Analysis of what `test_an_assembled_reel_is_judged_as_one` and `test_an_unavailable_diarizer_never_claims_speaker_tracking` proved vs what was missing in the implementation.
- How both tasks are re-opened in `specs/pro-grade-program/tasks.md` as T4.9 and T2.1.

### 3. `tests/test_claims.py`
Add `test_the_reopened_rows_cite_the_correction_adr()`:
- Verifies `specs/pro-edit/tasks.md` contains the ADR D-262 correction citations for both T6 and T7.
- Verifies `evidence/two-rows-flipped-for-features-that-did-not-exist.md` exists and contains required audit phrases.

## Verification Plan
1. `bash scripts/verify.sh --fast`
2. `bash scripts/verify.sh`
3. `bash scripts/update-ledger.sh pro-edit-corrections T1 test_the_reopened_rows_cite_the_correction_adr`
4. Update `specs/pro-grade-program/tasks.md` row T0.2.
