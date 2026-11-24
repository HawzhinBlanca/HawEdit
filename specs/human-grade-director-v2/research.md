# Research — `human-grade-director-v2` (True Broadcast & Human-Level Content-Aware Editing)

Date: 2026-11-21
Branch: `gemini/number-one` (base commit `72180dc`)
Evidence basis: real visual + pixel + audio forensic audit on `D:\HawEdit-media\reels\run-2026-11-20-ai-c10\` (5 reels) and `D:\HawEdit-media\reels\run-2026-11-20-cooking-30m-c10\` (`cooking-verbal-2` + 3 Stage-4-passed clips hitting `66.7%` teaser precision).

## Forensic Root Causes Observed Directly on Real Reels

1. **31-microsecond `per_shot_boxes` double-cut race (`src/hawedit/render.py:1164, 1180`):**
   - On `ai-c10/topic-14` (`in_ms=1,553,802`), FFmpeg timebase rounding placed frame `40273` (`CUT #5`) at `pts_time=57.117969 s`. `_interpolated()` (`x`, line `1023`) switched `2 ms` early (`57.116 s`), while `per_shot_boxes` (`y_center_expr` line `1164` and `sendcmd` `w/h` line `1180`) switched at `57.118000 s` — `31 µs` too late — causing `frame 1404 diff=72.8` followed by `frame 1405 diff=51.2` (`double_cuts_count=1`, the sole double cut across all 6 delivered reels).
   - **Fix:** Apply the identical `-2 ms` (`-0.002 s` / `-2 ms`) snap to `per_shot_boxes` `y_center_expr` and `sendcmd` `w/h` boundaries so `x`, `y`, `w`, and `h` transition on the exact same video frame.

2. **High-crest-factor audio forcing `loudnorm` out of linear mode (`src/hawedit/render.py:166, 322, 415`):**
   - Real measurement on `cooking/verbal-8` (`295,618..342,046 ms`): `input_i=-19.06 LUFS`, `input_tp=+1.5 dBTP` (crest `20.56 dB > 13.0 dB` linear headroom). FFmpeg `loudnorm=I=-14:TP=-1:linear=true` silently fell back to dynamic mode and stopped at `-14.7..-15.0 LUFS`, failing `verify_delivery` (`±0.5 LU`) on `cooking/verbal-5` (`hook=0.83`, Gold `G05`) and `cooking/verbal-8` (`hook=0.76`).
   - Additionally, `ai/verbal-1` hit `true_peak_violation (-0.6 > -0.7 dBTP)` because `--profile default` ran single-pass dynamic `loudnorm`.
   - **Measured proof on `cooking/verbal-8`:** Appending transparent broadcast peak control (`acompressor=threshold=-22dB:ratio=3:attack=8:release=100:makeup=3,alimiter=limit=-3.0dB:attack=5:release=50:level=disabled`) to `SPEECH_CHAIN_FILTERS` + enabling two-pass linear `loudnorm` produced **`output_i=-13.96 LUFS, output_tp=-1.68 dBTP, output_lra=2.3 LU, normalization_type='linear'`** (`0.04 LU` from target!).

3. **Leaning-speaker edge clipping & zero-face cutaway stagnation (`src/hawedit/reframe.py`):**
   - Visual inspection of `ai/verbal-3 CUT #4 PRE` and `cooking/verbal-2 CUT #3 POST` showed a speaker leaning sharply left/right mid-shot while `stabilize()` waited for `settle_ms=600 ms` across a `crop_w // 10` dead zone, clipping half the face near the frame edge.
   - Inside multi-shot clips containing genuine zero-face cutaway shots (cooking pans/hands/B-roll), `OpenCvFaceTracker.track()` held the previous shot's speaker `x`, cropping empty counter space instead of framing visual motion (`detect_motion_focus_points`).

4. **Hook card forehead overlap, orphan 1-word captions, Western digits, and non-content-aware zoom (`src/hawedit/captions.py`, `src/hawedit/caption_polish.py`, `src/hawedit/render.py`):**
   - On `ai/topic-14` and `ai/verbal-2` `FIRST 0.000s`, `title_ckb` wrapped at `max_chars=20` (`POPUP_MAX_CHARS`), forming a tall 4-line box that overlapped the speaker's forehead/hair (`MarginV=120`). Wrapping at `30` chars (sleek 2-line card) and checking frame-0 face top (`face_intervals`) eliminates forehead overlap while keeping `GOLDEN_HOOK_CARD` (`face_intervals=None`) 100% byte-identical.
   - On `ai/verbal-4`, `لێی` rendered as a 1-word orphan flash; on `ai/verbal-3`, `3 گۆشە 4` showed unnormalized Western digits in RTL text.
   - `eased_push_schedule` pulsed blindly at a fixed cadence instead of scaling zoom intensity by `SentenceAudioMetrics.excitement_score` and `verdict.payoff_at_ms`.
