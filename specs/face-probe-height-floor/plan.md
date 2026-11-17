# Plan — face probe height floor (resolves BLOCKED #26)

Research: `research.md`. Criteria: `spec.md`. Callers and tests: `impact-map.md`.

## Decision to record as D-335

In `measure.probe_face_tracking`, a detection is a face only if its box is at least
`MIN_FACE_HEIGHT_SHARE = 0.05` of the frame height (96 px on a 1920 frame). Smaller boxes are
dropped after each cascade call, so the profile fallback still runs when the frontal cascade
returned only undersized boxes.

Why 0.05:

- It is the number `delivery.py` Clause 7b already uses for "the opening frame has a subject".
- Measured today, every false box on caption text is 48-58 px (2.5-3.0 %). The floor is 1.65x
  the largest of them.
- Measured in D-258, real faces are 11.6-28.5 % of frame height. The floor is less than half
  the smallest of them.

This is judgment between two measurements, not a fitted threshold: the false-box sample is four
boxes from one font family, and the real-face sample is three episodes from August.

## Considered and not chosen

- **Ignore boxes inside the caption band.** Every false box seen is already under the floor, so
  it adds nothing on today's evidence. It would also need to know whether captions were drawn
  at the bottom or moved to the top, and a real face can sit in that band.
- **Raise `minNeighbors` or change the cascade.** That changes sensitivity to real faces, and
  there is no real footage on this machine to measure the effect.
- **Swap the probe to YuNet.** Better detector, but `models/face_detection_yunet.onnx` is not in
  this checkout and it is a larger change with its own ADR.
- **Only change the test.** The probe would still certify caption text as a face.

## Tasks (one at a time, test-first, gate after each)

**T1 — the floor.** Write the three `tests/test_measure.py` tests of AC1-AC3 first, using the
patterns already in the repo: a blank 1080x1920 clip from `cv2.VideoWriter`
(`test_measure.py:153`) and a fake `cv2.CascadeClassifier` that tells frontal from profile by
its path (`test_reframe.py:1132`). Watch AC1 and AC3 fail. Then add `MIN_FACE_HEIGHT_SHARE` and
one local helper in `probe_face_tracking` that replaces the three duplicated `detectMultiScale`
calls and drops undersized boxes. Append D-335 to `DECISIONS.md`.

**T2 — the test that relied on the accident.** Change
`test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance` to assert AC4:
the clip still claims `face_tracked`, the render is a `StageSkipped` naming
`face_tracking_unsubstantiated`, measured 0.0. Remove `SPEAKER_AMBIGUOUS_RENDER_SHA256` only if
nothing else uses it after that. Give the same treatment to any test listed as "changes" in
`impact-map.md`. Mark BLOCKED #26 resolved by D-335 (text added, nothing deleted).

Not in scope: Clause 7b's own `0.05` literal, the tracker's detector (`reframe.py`), the cover
and sanity-gate detectors, and adding a real-face fixture.

## Needs your explicit approval (approving this plan approves all three)

1. **A test's expectation changes from "published" to "refused".** That is what you chose in
   chat ("Fix the measurement"); it is listed here so it is not a quiet edit.
2. **Security review re-pin.** Editing `src/hawedit/measure.py` moves the source digest, so
   `security/wsl-asr-vex.json` and `tests/test_vex.py` must be re-pinned to the new digest, as
   was done for D-334. `reviewed` stays 2026-10-15; the already-past `expires` is not extended.
3. **Commits on `fix/kurdish-rtl-captions`**, not pushed: these spec files, then one commit per
   task.

## What "done" will and will not mean

After T2 the gate should be green for the first time on this branch. Only then can rows flip:
two here and the four still open in `specs/kurdish-rtl-base-direction/tasks.md`. Each flip
re-runs the full gate (about 46 minutes on this machine), so six flips are about five hours of
machine time. CI on a Linux runner has still not run any of this.

Approved-by: Hawa — in chat, 2026-11-17, "Approve plan" (covers the test expectation change, the security review re-pin and the unpushed commits above; recorded by Claude Code on the owner's instruction)
