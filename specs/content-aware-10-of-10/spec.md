# Specification — Content-Aware 10/10 Short-From-Long Program

## EARS Acceptance Criteria

### Lane A — Multimodal Acoustic Discovery & Teaser Benchmark (D-356)
- **AC-A1 (Acoustic Profiling):** WHEN Stage 0 `audio.wav` and Stage 2 `sentences` are provided, THE system SHALL compute per-sentence `rms_z`, `peak_burst_count`, `speech_rate_wps`, and `pause_before_ms` deterministically on CPU in pure Python/NumPy without external model weights.
- **AC-A2 (Content-Aware Discovery Fusion):** WHEN `audio_profile` is supplied to Path A (`discover_verbal`) or C4 (`discover_topics`), THE system SHALL annotate high-energy / burst / fast-delivery sentences in the Path A prompt and boost C4 candidate scores for acoustic excitement and `35–65 s` viral target duration without breaking existing text-only callers.
- **AC-A3 (Teaser Overlap Benchmark):** WHEN a list of discovered or delivered spans and gold teaser source spans are passed to `evaluate_teaser_overlap`, THE system SHALL return deterministic `precision`, `recall`, `f1`, and per-gold-region hit coverage (`iou` / overlap seconds).

### Lane B — ReframeAnything & Fast GPU Encode (D-357)
- **AC-B1 (Intra-Shot Active Speaker Switching):** WHEN an uncut 2-person wide shot lasts `>= 5 s` and the secondary speaker dominates lower-face mouth motion (`>= 1.6×` and `>= 2.0` energy) for `>= 2.0 s` continuously, THE `OpenCvFaceTracker` SHALL switch focus cleanly to the active speaker with an instant hard cut step (`<= 2 ms` step -> frame-exact zero-flash crop) instead of locking onto the opening speaker for the whole shot.
- **AC-B2 (Non-Face Action Framing):** WHEN `OpenCvFaceTracker` detects zero faces across a clip (e.g., cooking/demo footage), THE camera resolver SHALL explicitly select `Reframe.BLURRED_FILL` (when non-face fallback is enabled or content is non-talking-head) rather than silently centre-cropping or failing mid-episode, and SHALL record `reframe="blurred_fill"` in provenance.
- **AC-B3 (Explicit Encoder Selection & Fast Detection):** WHEN `--encoder auto` is selected, THE system SHALL probe `h264_nvenc` once and record the exact chosen encoder (`h264_nvenc` or `libx264`); WHEN `--encoder h264_nvenc` is explicitly requested and unavailable, THE system SHALL fail-stop with `RenderError` (zero silent fallback). Downscaled Haar detection (`<= 960 px` width) SHALL map face bounding boxes back to full source pixel coordinates within `<= 2 px`.

### Lane C — Clip-Only Sorani Caption Polish & E3-Safe Dead-Air Tightening (D-358)
- **AC-C1 (Audio-Grounded Clip Caption Polish):** WHEN `polish_clip_captions` runs on a chosen clip's sentences (display layer only), THE system SHALL deduplicate obvious CTC micro-stutters (`< 120 ms` identical consecutive tokens like `تۆپ تۆپ تۆپ`) and apply 1-to-1 timestamp-preserving Sorani spelling corrections from a multimodal client, NEVER mutating `raw.json` and rejecting any response that alters word count beyond guardrails or drifts `> 25%` character distance.
- **AC-C2 (E3-Safe Dead-Air Tightening):** WHEN `plan_silence_tightening` runs with `filler_tokens=None` (pure dead-air tightening without `--excise-fillers`), THE system SHALL NOT invoke `detect_restarts` on emphatic Kurdish repeats (`زۆر زۆر`) and SHALL enforce `[30, 200] ms` word padding on every cut edge so 100% of tightened intervals clear `validate_edl`.

### Lane D — Pipeline Integration & Broadcast Scorecard (D-359)
- **AC-D1 (End-to-End Wiring):** WHEN `hawedit.pipeline` runs with `--encoder auto` / `--polish-captions` / `--silence-threshold-ms 1100`, THE pipeline SHALL wire Stage 3 acoustic signals, intra-shot active speaker + non-face `BLURRED_FILL`, clip-only caption polish, safe silence tightening, and NVENC/x264 encoding end-to-end with zero regressions.
- **AC-D2 (Broadcast Quality Scorecard):** WHEN `measure_rendered_clip` measures any rendered MP4, THE `.measured.json` sidecar SHALL include a deterministic `broadcast_scorecard` reporting `double_cuts_count`, `zero_double_cuts`, `loudness_ok`, `contrast_ok`, `face_framing_ok`, and `all_passed`.
- **AC-D3 (Multi-Genre Real-Media Proof):** THE integrated system SHALL deliver verified, visually inspected reels on BOTH `RO1PmSoqmCM` (`ai` podcast) and `k_jxP903t5w` (`cooking` show with 17 gold teaser spans), recording wall times, NVENC speedup, teaser-overlap recall, and contact-sheet inspection in `evidence/`.
