# Impact Map — Two-Pass Linear Loudnorm (Task T3.1)

## Symbols Touched

1. **`src/hawedit/render.py`**:
   - `LoudnessStats`: New frozen dataclass for loudnorm metrics.
   - `measure_audio_loudness(source: Path, in_ms: int, duration_ms: int, binary: Path | None = None) -> LoudnessStats`:
     Extracts pass 1 audio metrics from ffmpeg null-muxer pass.
   - `audio_filter(measured: LoudnessStats | None = None, linear: bool = False) -> str`:
     Extended signature. When `measured` is None, behaves identically to legacy `audio_filter()`.
   - `RenderResult`:
     Gains `loudness_pass1: LoudnessStats | None = None` and `loudness_pass2: LoudnessStats | None = None`.
   - `render_clip`:
     When `deliverable=True` (or explicit `two_pass_loudnorm=True`), performs Pass 1 measurement, applies linear filter in Pass 2, extracts Pass 2 output metrics, and attaches both to `RenderResult`.

2. **`src/hawedit/clip.py`**:
   - `Output`:
     Gains optional `loudness: dict[str, Any] | None = None` storing both pass 1 and pass 2 records.
     Preserves `slots=True`, strict validation in `__post_init__`, and lossless JSON roundtrip in `to_dict` / `from_dict`.

3. **`src/hawedit/pipeline.py`**:
   - Stage 6 delivery integration:
     When `rendered.loudness_pass1` is present, updates `clip.output` with the two-pass loudness dictionary so it is permanently serialized in `editing.json`.

4. **`tests/test_render.py` & `tests/test_pipeline.py`**:
   - New unit tests verifying `measure_audio_loudness`, linear string formatting, execution in `render_clip`, and EBU R128 compliance.
   - Existing tests retain default working render flags without regressions.
