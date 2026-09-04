# Ledger Audit Evidence: Correction of Pro-Edit T6 and T7

```yaml
commit: dd82e2051afb64ca00c929f7811b2f9dbcf126b4
media_sha256: n/a
host: HAWAPC01
command: pytest tests/test_claims.py -k test_the_reopened_rows_cite_the_correction_adr
date: 2026-09-04T18:50:00Z
decision: D-262
blueprint_ref: §3 Stage 3, Stage 6
```

## 1. Audit Finding & Context

During the systematic repository audit (`specs/pro-grade-program/research.md` §6.2), two rows in `specs/pro-edit/tasks.md` were identified as having been flipped to `[x]` based on automated tests that proved negative or mock conditions rather than actual product capability:

1. **`pro-edit` T6 (Assembly)**:
   - Flipped on 2026-08-29 in commit `d79501e`.
   - Cited tests:
     - `test_an_assembled_reel_is_judged_as_one`
     - `test_the_verdict_is_recorded_against_the_assembly`
     - `test_editorial_thresholds_apply_to_the_assembly`
   - **What the tests proved**: In-memory sentence concatenation, timestamp arithmetic, and synthetic JSON serialization under `MockEditorialJudge`.
   - **What did NOT exist**: Zero media rendering, zero FFmpeg video splicing filtergraphs, no frame extractions, and zero callers in `src/`. Real `GeminiJudge` refused any frameless Stage 4 request (`gemini.py:~415`).

2. **`pro-edit` T7 (Speaker tracking)**:
   - Flipped on 2026-08-29 in commit `9152e59`.
   - Cited test: `test_an_unavailable_diarizer_never_claims_speaker_tracking`.
   - **What the test proved**: That when diarization is unavailable, the contract output does not falsely emit the `speaker_face` label.
   - **What did NOT exist**: Actual speaker-to-face audiovisual tracking (`SpeakerSubjectTracker` protocol in `reframe.py` was an empty abstract stub without concrete implementation).

## 2. In-Place Correction Protocol (HANDOFF.md §1.6)

Per `HANDOFF.md` §1.6 ("A wrong record is corrected in place, keeping the wrong claim"):
- The original claims and commit citations for T6 and T7 are preserved in `specs/pro-edit/tasks.md` and `specs/pro-edit/ledger.log` to preserve historical integrity.
- Formal in-place correction annotations are added directly beneath rows T6 and T7 citing ADR **`D-262`**.

## 3. Re-Opened Capabilities in Pro-Grade Master Plan

Both capabilities were re-opened in `specs/pro-grade-program/tasks.md` with explicit, verifiable definitions of done:

- **Assembly re-opened as Task T4.9 (Cold-open assembly)**:
  - Requires: pay-off sentence first, then setup, media concatenated via FFmpeg splice filtergraph, ASS captions regenerated on the assembled timeline, punch-ins re-timed, and the assembly judged with frames extracted directly from the assembled render.
  - Status: Completed and verified with Level C evidence in `specs/cold-open-assembly/`.
- **Speaker tracking re-opened as Task T2.1 (Active-speaker reframe)**:
  - Requires: Diarization turns (`--diarize`, pyannote Community-1) plus speaker-to-face association (pixel-motion energy or audiovisual ASD model) with crop tracking the active speaker and holding on ambiguity.
  - Status: Tracked in `specs/pro-grade-program/tasks.md` awaiting HuggingFace diarization token clearance (`BLOCKED.md` #4).
