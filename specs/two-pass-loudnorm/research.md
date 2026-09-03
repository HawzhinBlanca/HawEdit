# Research — Two-Pass Linear Loudnorm (Task T3.1)

## Context & Problem
In `BLUEPRINT.md` §3 Stage 6, audio normalization is specified to EBU R128 broadcast standards (`DELIVERY_LUFS = -14.0`, `DELIVERY_TRUE_PEAK_DB = -1.5`).
Currently, `src/hawedit/render.py:211-221` uses single-pass dynamic loudnorm:
```python
def audio_filter() -> str:
    return (
        f"loudnorm=I={DELIVERY_LUFS:g}:TP={DELIVERY_TRUE_PEAK_DB:g}:LRA=11,"
        f"aresample={DELIVERY_AUDIO_RATE}"
    )
```
In single-pass mode, FFmpeg dynamically estimates loudness and adjusts gain over a short lookahead buffer. While fast, dynamic mode introduces noticeable dynamic range pumping on spoken Kurdish dialogue and cannot guarantee exact integrated loudness across short speech segments.

As identified in `specs/pro-grade-program/tasks.md` row 102 (Task T3.1):
> **T3.1 P1 Two-pass linear loudnorm.** First pass measures (`print_format=json`), second applies `measured_*` with `linear=true`. Record both passes in the contract.
> Proof required:
> A: `test_loudnorm_runs_linear_with_measured_inputs`.
> B: `ebur128` on the re-render: I within ±0.5 LU, TP ≤ −1, LRA recorded; media-tier test on speech, not a sine.
> C: T1.2.

## FFmpeg Loudnorm Mechanism
FFmpeg's `loudnorm` filter supports two distinct modes:
1. **Pass 1 (Analysis)**:
   ```bash
   ffmpeg -hide_banner -loglevel info -ss <in_s> -t <duration_s> -i <source> \
     -vn -sn -dn -af "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" -f null -
   ```
   This passes only audio through the filter to the null muxer at high speed (~60× realtime). It writes a JSON block to stderr containing:
   - `input_i`: integrated loudness of input in LUFS
   - `input_tp`: true peak of input in dBFS
   - `input_lra`: loudness range of input in LU
   - `input_thresh`: loudness threshold of input in LUFS
   - `target_offset`: gain offset in LU
   - `output_i`, `output_tp`, `output_lra`, `output_thresh`

2. **Pass 2 (Linear Normalization)**:
   ```bash
   loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:offset=<target_offset>:linear=true:print_format=json,aresample=48000
   ```
   When supplied with the measured input statistics and `linear=true`, FFmpeg applies static linear gain scaling across the entire span, eliminating volume pumping while ensuring True Peak compliance.

## Integration Architecture
1. **`measure_audio_loudness`**:
   - New function in `src/hawedit/render.py`.
   - Subprocess invocation of `ffmpeg` with `-vn -sn -dn -af loudnorm=...:print_format=json -f null -`.
   - Parses stderr JSON and validates all required numeric fields.
2. **`LoudnessStats` & `audio_filter`**:
   - `LoudnessStats` frozen dataclass with `input_i`, `input_tp`, `input_lra`, `input_thresh`, `target_offset`, `output_i`, `output_tp`, `output_lra`, `output_thresh`, `normalization_type`.
   - `audio_filter(measured: LoudnessStats | None = None, linear: bool = False) -> str`.
3. **`render_clip` & Deliverable Profile**:
   - If `deliverable=True` (or `two_pass_loudnorm=True`): runs Pass 1, computes `LoudnessStats`, applies linear filter in Pass 2, and records `loudness_pass1` and `loudness_pass2` in `RenderResult`.
   - If `deliverable=False`: preserves existing single-pass dynamic filter for fast working renders and test backwards compatibility.
4. **Contract Recording (`Output.loudness`)**:
   - `Output` in `src/hawedit/clip.py` gains optional `loudness: dict[str, Any] | None = None`.
   - In `src/hawedit/pipeline.py`, when `rendered.loudness_pass1` is available, `clip.output.loudness` records both pass 1 and pass 2 statistics.
