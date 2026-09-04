# Research — Pro-Edit Ledger Corrections for T6 and T7 (Task T0.2)

## 1. Problem Context

In `specs/pro-grade-program/research.md` §6.2, an audit of the ledger identified that two tasks in `specs/pro-edit/tasks.md` were flipped to `[x]` based on tests that proved negative or mock conditions rather than true functional capability:

1. **`pro-edit` T6 (Assembly)**:
   - Flipped on 2026-08-29 in commit `d79501e`.
   - Cited tests: `test_an_assembled_reel_is_judged_as_one`, `test_the_verdict_is_recorded_against_the_assembly`, `test_editorial_thresholds_apply_to_the_assembly`.
   - **What was proven**: Text-only sentence concatenation and timestamp arithmetic in Python data structures under `MockEditorialJudge`.
   - **What was NOT proven**: No media rendering, no FFmpeg splice filtergraph, no frame extraction, and zero callers in `src/`. Real `GeminiJudge` rejected the request because it lacked video frames (`gemini.py:~415`).

2. **`pro-edit` T7 (Speaker tracking)**:
   - Flipped on 2026-08-29 in commit `9152e59`.
   - Cited test: `test_an_unavailable_diarizer_never_claims_speaker_tracking`.
   - **What was proven**: That when diarization is unavailable, the contract's `reframe` block does not emit `speaker_face`.
   - **What was NOT proven**: No actual speaker-to-face audiovisual tracking (`SpeakerSubjectTracker` protocol in `reframe.py` was an unimplemented abstract protocol).

## 2. Policy & Architecture Directives

Per `HANDOFF.md` §1.6:
> "A wrong record is corrected in place, keeping the wrong claim. Deleting a flipped row from a ledger destroys the evidence of what was believed and when... Add the correction directly beneath the original claim."

ADR **`D-262`** in `DECISIONS.md` has already established the formal record:
- The historical claims and commit records for T6 and T7 are preserved in `specs/pro-edit/tasks.md` and `specs/pro-edit/ledger.log`.
- Both capabilities are formally re-opened in `specs/pro-grade-program/tasks.md`:
  - Assembly re-opened as **T4.9** (Cold-open assembly: media concatenation, timeline re-timing, and real frame judging — now completed in `specs/cold-open-assembly`).
  - Active-speaker reframe re-opened as **T2.1** (Active-speaker reframe).

## 3. Required Deliverables for T0.2

1. **In-place corrections in `specs/pro-edit/tasks.md`**:
   Add correction annotations beneath the T6 and T7 rows citing ADR D-262 and the re-opened task IDs (T4.9 and T2.1).
2. **Evidence file `evidence/two-rows-flipped-for-features-that-did-not-exist.md`**:
   Document the before/after, what the cited tests actually proved, and how the capabilities were re-opened.
3. **Automated test `test_the_reopened_rows_cite_the_correction_adr` in `tests/test_claims.py`**:
   Verify that `specs/pro-edit/tasks.md` and the evidence file strictly preserve the correction record.
4. **Gate pass & ledger update**:
   Run `scripts/verify.sh` and update `specs/pro-grade-program/tasks.md`.
