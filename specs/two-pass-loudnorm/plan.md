# Plan — Two-Pass Linear Loudnorm (Task T3.1)

## Work Breakdown

### Task T1: First-Pass Loudness Measurement & Filter Generation (`src/hawedit/render.py`)
- Implement `LoudnessStats` frozen dataclass with `.to_dict()` and `.from_dict()`.
- Implement `measure_audio_loudness(source: Path, in_ms: int, duration_ms: int, binary: Path | None = None) -> LoudnessStats`.
- Update `audio_filter(measured: LoudnessStats | None = None, linear: bool = False) -> str` to inject measured parameters when provided.
- Update `RenderResult` to hold `loudness_pass1` and `loudness_pass2`.
- Update `render_clip` to invoke `measure_audio_loudness` and apply linear normalization when `deliverable=True`.

### Task T2: Output Contract Schema & Pipeline Binding (`src/hawedit/clip.py` & `src/hawedit/pipeline.py`)
- Add optional `loudness: dict[str, Any] | None = None` to `Output` in `src/hawedit/clip.py`.
- Update `Output.to_dict()` and `Output.from_dict()` for strict validation and serialization.
- In `src/hawedit/pipeline.py`, attach two-pass loudness records from `RenderResult` to `clip.output.loudness` before editing JSON serialization.

### Task T3: Unit Tests & Verification
- Unit test: `test_measure_audio_loudness_parses_json_stats` (verifying ffmpeg null-muxer parsing).
- Unit test: `test_audio_filter_linear_formatting` (verifying exact filter string).
- Unit test: `test_loudnorm_runs_linear_with_measured_inputs` (verifying two-pass linear render).
- Unit test: `test_contract_records_two_pass_loudness` (verifying contract JSON preservation).
- Full gate verification with `bash scripts/verify.sh` and ledger update.
