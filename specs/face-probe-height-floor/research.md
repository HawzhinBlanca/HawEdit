# Research — face probe height floor (BLOCKED #26)

2026-11-17. HawaPC01, Windows 11, `.venv` CPython 3.12.10, opencv-python-headless 4.12.0,
ffmpeg 8.1.1-full, tree `b1cba30`. Serena did not connect, so symbols were found with grep.
No code or test was changed. Probe scripts and raw output are in `captures/`.

## What the code does today

- `measure.probe_face_tracking` (`src/hawedit/measure.py:509`) samples the delivered MP4 at
  5 frames/s and runs OpenCV Haar cascades: frontal, then profile, then mirrored profile, each
  with `scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)`. **Any** returned box makes the
  sample count as "face detected". The largest box feeds `median_face_height_share`,
  `median_y_center_share` and `first_frame_face_share`.
- 30 px on a 1920-high frame is 1.6 % of the height. Nothing bounds a box from below.
- Only caller: `measure_clip` (`measure.py:1157`), called from `pipeline.py:2511, 4598`, the
  measurement CLI (`measure.py:1212`) and the subprocess in `candidate_publication.py:107`.
- Only reader of the face fields: `delivery.reconcile_delivery` (`delivery.py:541-598`).
  Clause 7 publishes a `face_tracked` clip only if `face_detected_share` >= 0.90 (>= 0.50 under
  3 s). Clause 7a checks the speaking share. Clause 7b already refuses an opening frame whose
  face is under **0.05** of frame height, but only when `min_face_share` is set.
- Stage: this is the independent measurement of a §3 Stage 6 render, feeding the §2 delivery
  gate (D-263 clause 7: "If `crop_target` is `face_tracked`, face detected share must be >= 90%").

## Measured today: what the detector returns when there is no face

| Input (1080x1920, no face in any frame) | Samples | Samples with a box | Box height |
|---|---|---|---|
| Test render at `0ea5158` (before D-334) | 10 | 5 | 58 px = 3.02 %, centre 78.3 % down |
| Same render at `b1cba30` (after D-334) | 10 | 1 | 53 px = 2.76 %, centre 78.4 % down |
| Golden `kurdish-caption-fixture.png` | 1 | 1 | 53 px = 2.76 %, centre 78.4 % down |
| Three other goldens | 3 | 0 | none |
| 144 caption-only clips on black: 12 Sorani sentences x 6 caption styles x font 64 and 108 | 2,160 | 1 | 48 px = 2.50 %, centre 78.8 % down |

Every false box is a frontal-cascade hit on caption text, 48-58 px tall (2.5-3.0 % of frame
height), centred inside `DEFAULT_BOTTOM_CAPTION_BAND` (1300-1650 px = 68-86 % down). Eight
samples with a box out of 2,184, four distinct boxes: a small sample, all from the two bundled
fonts. The caption-only clips show black alone rarely triggers it; the fixture's own picture
under the caption is what makes the hit repeat.

## Measured today: what the test suite's renders measure

A logging wrapper around the real probe (`captures/whatif.py.txt`) recorded 113 probe calls
from 95 tests in 19 test files. 64 measured no box. 48 measured a share of 0.0476-0.1 from one
box 2.71-2.76 % tall. One measured 1.0 from a faked 80 px box (4.17 %). **No call saw a box at
or above 5 %.** Limit: my run used a long temp path that broke Stage 0 ingest in at least 8
`test_review_candidate_cache.py` tests (they pass with the default temp folder), so those never
reached the probe and the run's total failure count was not captured.

## Already measured: how tall a real face is

D-258 (2026-08-27, same cascades, 60 samples per source, 718 detections): face height
**28.5 %**, **16.2 %** and **11.6 %** of frame height on three real episodes. `render.py`
then frames toward `TARGET_FACE_HEIGHT_SHARE = 0.15` with `MAX_VERTICAL_ZOOM = 1.5`. The tracker
itself drops source detections under `MIN_FACE_AREA = 2_000` px² (`reframe.py:57`).
**Not re-measured today:** no real footage exists on this machine any more.

## Risks and gaps

- No test runs the real probe on pixels and checks its numbers. `tests/test_measure.py` builds
  `FaceTrackMeasurement` by hand; `tests/test_pipeline.py` reaches the probe only through whole
  pipeline runs.
- `tests/fixtures/` holds one clip and it has no face. The "real face is counted" path cannot
  be tested against the real cascade in this repo, before or after this work.
- `tests/test_pipeline.py::test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance`
  expects a faceless render to be published as `face_tracked` (BLOCKED #26). Its pinned digest
  `SPEAKER_AMBIGUOUS_RENDER_SHA256` (`6ceba45f…`) no longer matches the render (`77bec008…`).
- 49 logged probe calls would measure lower under a floor; none changes a test's outcome
  (`impact-map.md`).
- Vault note `Projects/HawEdit road to number one 2026-09-08`: this Haar probe found a face in
  only 56 % of samples on real episode ep29, against Clause 7's 90 %. A floor cannot fix that
  and is not meant to; replacing Haar is separate work.
- Any change under `src/hawedit/` moves `package_digest`, so `security/wsl-asr-vex.json` and
  `tests/test_vex.py` need an owner-approved re-pin again (as in D-334's addendum).

## Answers to

BLUEPRINT §2 (delivery bundle), §3 Stage 6 ("Vertical reframing tracks the active speaker from
diarization plus face detection"); D-263 clause 7; D-258; `specs/reconciliation-gate` AC-7;
`specs/first-frame-gate` CRIT-4; BLOCKED #26. No ADR defines what counts as a face in the
delivery measurement, so this needs a new one (D-335).
