# Strict Fail-Stop Rule — Zero Silent Fallbacks

> **MANDATORY POLICY**: If ANY step, model, probe, alignment, tracking, shaping, boundary calculation, or gate check fails, execution MUST IMMEDIATELY STOP (ALL STOP). No silent fallbacks, no degraded substitutions, no guessing.

## Core Directives

1. **No Silent Degradation to Static Crops**:
   - If dynamic speaker/face tracking is requested (`--face-reframe` or `Reframe.SPEAKER_TRACKED` / `Reframe.FACE_TRACKED`), and the tracker fails or produces no focus points, the pipeline MUST immediately raise `RenderError` / exit non-zero.
   - It is strictly forbidden to quietly switch to a static centre crop.

2. **No Faked or Uniform Word Timestamps**:
   - All word boundaries used for karaoke subtitles and sentence boundaries MUST originate from verified Viterbi forced alignment on acoustic model emissions (§4.2).
   - If forced alignment fails, the pipeline MUST halt immediately. Never estimate or uniformly distribute word intervals.

3. **No Unshaped or Fallback Font Captions**:
   - Subtitle burning MUST strictly use `shaping=complex` with HarfBuzz and FriBidi verified at deploy/runtime (§4.3).
   - Fonts must be explicitly supplied from a verified directory (`fontsdir`) and checked for 100% Kurdish character coverage (`ڕ ڵ ۆ ێ چ ژ پ گ ە ه ھ ک ی`).
   - If any character lacks a glyph or shaping fails, HALT immediately. Never fall back to host system fonts or unshaped text.

4. **No Incomplete Sentence Renders (Kurdish Invariant #2)**:
   - A clip MUST NEVER start or end mid-sentence.
   - Invariant assertion `final_in <= anchor_in` and `final_out >= anchor_out` must pass on every single clip.
   - If a sentence is incomplete or boundary conditions fail, REJECT the candidate and HALT. Never ship a partial thought.

5. **No Silent Encoder Substitution**:
   - When hardware acceleration (NVENC) is requested, the system MUST verify NVENC availability at the exact target dimensions (`1080x1920`).
   - If NVENC fails or is absent, RAISE an explicit error. Do NOT silently substitute `libx264`.

6. **No Unjudged / Un-QC'd Publication**:
   - Every clip must clear Stage 4 editorial judging (meaning fidelity >= 0.90, misleading edit risk <= 0.05, hook score >= 0.75) and human QC before delivery artifacts are published.
   - Never bypass editorial validation.

7. **Subprocess & IO Safety**:
   - Any non-zero exit code or stderr output from `ffmpeg`, `ffprobe`, or model runners must immediately terminate the workflow and surface the full trace.
