# Research — Content-Aware 10/10 Short-From-Long Program

Date: 2026-11-20
Baseline commit: `51835ba` (`gemini/number-one`)
Host: `HawaPC01` (`Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual RTX 3090 Ti 24 GB)

---

## 1. Competitive & Academic Landscape (2025–2026)

### 1.1 OpusClip (`ClipAnything` + `ReframeAnything` + Dynamic Layout)
- **Multimodal Curation (`ClipAnything`):** Evaluates transcript semantics alongside audio energy/sentiment patterns and visual cues across diverse genres (podcasts, cooking, tutorials, vlogs, panels) rather than transcript-only slicing.
- **Genre-Aware Framing (`ReframeAnything` & Dynamic Layout):** Automatically selects Fill (single speaker), Split / Multi-way stacked layout (rapid multi-speaker exchanges), or preserved wide/screenshare composition (`BLURRED_FILL` / top-bottom split) when no single talking head fills the shot.
- **Active Speaker Detection (ASD):** Audio-visual speaker attribution prevents staring at a silent listener during 2-person wide shots.
- **Post-Production Ecosystem:** Word-level dynamic captions, one-click dead-air / filler cleaning, AI B-roll insertion, and cloud GPU rendering (2–5 min typical turnaround).
- **Hard Weaknesses for Sorani Kurdish (`ckb`):** No native Sorani Kurdish ASR, broken/weak RTL Arabic-script karaoke sweep direction, cloud upload latency + recurring cost, opaque "Virality Score" that routinely outputs filler clips.

### 1.2 OpenShorts (`mutonby/openshorts`, MIT)
- **Architecture:** Local Faster-Whisper transcription + PySceneDetect + Gemini Flash/Pro transcript-only highlight selection + MediaPipe/YOLOv8 face tracking + Remotion/FFmpeg vertical composition (with 2-person split layout) + NVENC GPU rendering (~50 s per 8-min video on NVIDIA GPUs).
- **Hard Weaknesses for Sorani Kurdish (`ckb`):**
  1. Whisper exhibits severe Sorani Kurdish WER (~40–65% on conversational podcasts), producing unreadable captions and broken LLM clip selection.
  2. Transcript-only highlight discovery misses vocal excitement, laughter bursts, and visual action.
  3. Remotion/Canvas captions are LTR-first and lack HarfBuzz `shaping=complex` RTL karaoke precision.
  4. Face tracking struggles on profile angles, occlusions, and non-talking-head action shots (e.g., cooking pans/hands).

### 1.3 SOTA Research (TalkNet / Light-ASD / Multimodal Highlight Detection)
- **Active Speaker Detection:** TalkNet (ACM MM) and Light-ASD (CVPR) demonstrate that combining temporal lip/lower-face motion cues with acoustic activity / speaker identity vastly outperforms static largest-face heuristics on multi-speaker wide shots.
- **Multimodal Highlight Detection:** Combining semantic boundaries (LLM + TextTiling) with lightweight acoustic excitement signals (RMS energy z-score, vocal bursts/laughter, delivery rate) consistently improves human-editor recall over text-only selectors without requiring multi-GB VLMs.
- **Short-Form Retention Editing:** Top-performing 9:16 shorts pair tight `35–65 s` narrative arcs, dead-air tightening with click-free audio crossfades (30 ms), crisp zero-flash camera cuts, active-speaker framing, and error-free kinetic word-by-word captions.

---

## 2. HawEdit Baseline Audit (`51835ba` on `RO1PmSoqmCM`)

### 2.1 Existing Unfair Advantages (Already Proven & Gated at 6,688/6,688 Tests)
1. **Best-in-class Sorani ASR & Word Sync:** Custom fine-tuned `omniASR_LLM_7B_v2` LoRA v12 + CTC-3B forced alignment (`5,951` words, `0` unaligned on 40-min `RO1PmSoqmCM`).
2. **Broadcast Sorani RTL Karaoke (D5/D6/D7):** 128 pt Vazirmatn, HarfBuzz `shaping=complex`, true RTL `\clip` gold-to-white sweep, mixed-script Latin fallback, silence-capped sweep duration (`600–900 ms`), `16.54:1–17.26:1` measured contrast.
3. **Zero-Flash Frame-Exact Cuts & Per-Shot Active Speaker (`1b1a421`, `2ef15c0`):** `0` double-cuts across all `37` camera cuts in Pass 6 (`6/6` reels); `9/9` Speaker-2 tracking on `verbal-2` and `7/7` Speaker-1 tracking on `verbal-1`.
4. **Honest Pairwise Editorial Selection (C1/C4/C5 + E3):** Sentence-numbered Path A + clean-room MIT TextTiling + `gemini-4-carbon` multimodal judge + Swiss pairwise ranking + E3 hard edit rules + `reconciled=true`.
5. **Broadcast Audio (D8):** Two-pass linear EBU R128 loudness (`-13.8` to `-14.5 LUFS`, `-0.8` to `-1.2 dBTP`) + symmetric 30 ms `qsin` boundary fades.

### 2.2 Measured Gaps Separating Pass 6 From True 10/10 Superiority Over OpusClip & OpenShorts

| # | Gap Measured on Real Pass 6 Footage / Codebase | Root Cause Found in `src/hawedit/` | Concrete Fix |
| --- | --- | --- | --- |
| G1 | **Text-only Stage 3 discovery** misses vocal energy, laughter bursts, and punchy delivery pacing; no automated teaser-overlap benchmark against `cooking`/`ep54` gold spans (`evidence/teaser-gold-timestamps.md`). | `path_a.py` and `topic_segmenter.py` never read Stage 0 `audio.wav` acoustic energy or speaking rate; Path A allows `88 s` meanders instead of favoring `35–65 s` viral arcs. | New `audio_signals.py` (<2 s CPU on `audio.wav`) feeding compact acoustic tags into `path_a.py` + `topic_segmenter.py` + viral sweet-spot scoring + `evaluate_teaser_overlap()`. |
| G2 | **Long uncut 2-person wide shots & non-face action shots (`cooking`):** `OpenCvFaceTracker.track()` locks one speaker per shot (missing mid-shot speaker handoffs inside uncut wide shots); zero-face shots (e.g., cooking pans/hands) raise `RuntimeError("zero faces detected")` in `pipeline.py:2003` instead of using existing `Reframe.BLURRED_FILL` / motion saliency! | `reframe.py` computes cluster scores once per shot; `pipeline.py:2002` fails hard on zero faces instead of routing to `Reframe.BLURRED_FILL` when non-face action is present. | Rolling-window intra-shot active-speaker switching (`>= 2.0 s` dwell hysteresis + hard cut step) in `reframe.py`; motion-saliency & `Reframe.BLURRED_FILL` support for zero-face shots; downscaled Haar (`<= 960 px`) for ~4× faster CPU tracking. |
| G3 | **65-minute CPU render time for 6 reels (`4,284 s` total vs OpenShorts' ~50 s / 8 min):** `_render_episode_single_clip` (`pipeline.py:2616`) never passes `encoder=`, silently defaulting to CPU `libx264` even though `encoder_available(Encoder.NVENC)` is `True` on HawaPC01's RTX 3090 Ti. | No explicit `--encoder auto|h264_nvenc|libx264` plumbing into `_render_episode_single_clip` / `render_clip`. | Add explicit `--encoder` (`auto` probes `h264_nvenc` once and records exact chosen encoder in provenance; explicit `h264_nvenc` fails-stop if unavailable). |
| G4 | **Burned-in ASR typos & stutters on chosen reels** (`تۆپ تۆپ تۆپ`, `چیت سکۆدس`, `نابزانی`, `تێئەگە`, `ما ئێ فەیبوو فایف`). | B6 rightly disabled slow 40-min full-episode validation, leaving zero lightweight clip-only proofreading for the 5–6 final chosen 60 s clips. | New `caption_polish.py` — clip-only audio-grounded Sorani display-caption polisher via `gemini-4-carbon` with strict 1-to-1 timestamp preservation, stutter deduplication, immutable `raw.json`, and `<= 25%` edit-distance safety guard. |
| G5 | **Broken dead-air silence tightening:** Passing `--silence-threshold-ms 1000` failed E3 `validate_edl` on 6/6 Pass 6 reels (`segment end padding 0 ms outside [30, 200] ms`) because `silence.py:368` ran `_identify_filler_words(..., detect_restarts=True)` even when `filler_tokens is None`, chopping Kurdish emphatic repeats (`زۆر زۆر`) with `0 ms` gap. | `plan_silence_tightening` conflated dead-air trimming with restart excision. | Decouple `detect_restarts` so it runs ONLY when `filler_tokens is not None` (explicit `--excise-fillers`), and clamp cut boundaries to strict `[30, 200] ms` word padding so dead-air tightening passes E3 100%. |
| G6 | **Single-genre proof only (`ai` podcast, no teaser):** `cooking` (`k_jxP903t5w`, 17 gold teaser regions) has not been processed end-to-end; `.measured.json` lacks a unified pass/fail broadcast quality scorecard (`double_cuts`, `speaking_face_share`, `LUFS/dBTP`, `contrast`). | Missing unified scorecard in `measure.py` and unrun second genre (`cooking`). | Add deterministic `broadcast_scorecard` in `measure.py` and run real end-to-end production on BOTH `ai` (`RO1PmSoqmCM`) and `cooking` (`k_jxP903t5w`) with teaser-overlap scoring. |
