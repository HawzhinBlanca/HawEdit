# Research — Director Remediation

## Grounding & Root Cause Analysis

Following `specs/pro-grade-program/reality-check-2026-09-13.md` and `AGENTS.md`:

### 1. Gate Failures & Skipped Test
- **Root Cause 1**: `src/hawedit/web.py` had uncommitted modifications introducing fake showcase clips and scores. Because `test_build.py` refuses dirty trees and `test_vex.py` binds committed source digest, any dirty tree fails 5 tests in the gate.
- **Root Cause 2**: `tests/test_cover.py:250` contained `pytest.skip("ep29 clip not available")` pointing to ephemeral `work/ep29-VbX8UWwl1c4-s25-25/...`. Under T1.11, skipped tests violate the zero-skip floor.
- **Fix**: Point `test_select_cover_frame_on_ep29_extracts_face_thumbnail` to the committed fixture `tests/fixtures/kurdish-speech-3cuts.mp4` without skips, and clean up `src/hawedit/web.py`.

### 2. Studio Mock Sham (Item 1 & Item 2)
- **Root Cause**: `JobManager._run_job_stages` in `src/hawedit/web.py` does not call `run_pipeline`. It sleeps 40 ms 7 times. It also hardcodes `is_ep29` checks returning literal 99.8/99.5 scores.
- **Fix**: Wire `JobManager` to invoke `run_pipeline` in a thread, capture events (`StageSkipped`, `StageCompleted`), and produce real bundles with `measured.json`. Remove all hardcoded `/media/ep29` and mock scoring.

### 3. VisualEditPlan Contract (Item 3)
- **Root Cause**: `VisualEditPlan` is generated after `publish()` and swallowed inside `suppress(Exception)`. Render consumes raw parameters, not the plan.
- **Fix**: Build `VisualEditPlan` *before* render. Pass `plan` to render. Add `plan` to `ArtifactBundle.suffixes()`. Refuse publish if plan is missing.

### 4. Provenance Gate (Item 4)
- **Root Cause**: `work/assets/` contains orphan audio (`music_tension_bed.wav`, SFX) mixed without provenance.
- **Fix**: Quarantine unvetted audio. Enforce that any auxiliary asset passed to render has a `.provenance.json` sidecar.

### 5. Join Critic (Item 5)
- **Root Cause**: `render_critic.inspect_rendered_sequence` is never called in production. It does not inspect join words.
- **Fix**: Call critic before publish. Pass join words. Reject joins ending in `DANGLING_CONJUNCTIONS_CKB` or starting mid-clause.

### 6. Excision by Default & Restarts (Item 6)
- **Root Cause**: `excise_fillers=False` by default. No restart/repetition detection exists.
- **Fix**: Default `excise_fillers=True`. Detect n-gram repetitions within 2 seconds and false starts in `silence.py`. Ensure excision cuts sync with punch-ins.

### 7. Speaking Face Share (Item 7)
- **Root Cause**: Face share is measured over all frames indiscriminately. Delivery threshold is 0.90.
- **Fix**: Intersect face detections with active diarization speech intervals. Compute `speaking_face_share`. Raise threshold to 0.98.

### 8. Caption Word Order (Item 12)
- **Root Cause**: Manual ASS files or inline style tags in `KINETIC_POP` flipped BiDi chunks in HarfBuzz.
- **Fix**: Use `RTL_WORD_HIGHLIGHT` / unified chunk formatting ensuring RTL token sequence is strictly preserved. Add regression test.
