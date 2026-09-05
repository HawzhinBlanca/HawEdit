# Impact Map — Brand Kit (Task T2.13)

## Affected Modules & Callers

### 1. `src/hawedit/brand.py` (NEW)
- **Role**: Primary domain module for Brand Kit data models and filter generators.
- **Exports**:
  - `BrandKitError`
  - `SpeakerBio`
  - `ProgressBarConfig`
  - `EndCardConfig`
  - `BrandKit`
  - `logo_overlay_filter`
  - `progress_bar_filter`
- **Callers**:
  - `src/hawedit/captions.py` (reads `speaker_metadata`)
  - `src/hawedit/render.py` (applies video filter chains)
  - `src/hawedit/pipeline.py` (CLI parsing and workflow coordination)
  - `tests/test_brand.py` (unit tests)

### 2. `src/hawedit/captions.py`
- **Symbols Modified**:
  - `build_ass(...)`:
    - Add optional parameters `speaker_turns: Sequence[tuple[int, int, str]] | None = None` and `speaker_metadata: dict[str, SpeakerBio] | None = None`.
    - Emit `SpeakerTag` style in ASS header when `speaker_metadata` is provided.
    - Emit lower-third dialogue events with `\fad(300,300)` for speaker turns matching metadata.
- **Callers**:
  - `src/hawedit/pipeline.py:render_clip_candidates`: Passes `speaker_turns` and `brand_kit.speaker_metadata` to `build_ass`.
  - `tests/test_captions.py`: Existing tests remain unaffected (new parameters optional). New tests verify lower-third rendering.

### 3. `src/hawedit/render.py`
- **Symbols Modified**:
  - `render_clip(...)`:
    - Add optional parameter `brand_kit: BrandKit | None = None`.
    - Chains logo watermark and progress bar filters into `stream_filter_args` when configured.
    - Adjusts output duration when `brand_kit.end_card` is active.
- **Callers**:
  - `src/hawedit/pipeline.py:render_clip_candidates`: Passes `brand_kit` to `render_clip`.
  - `tests/test_render.py`: Existing tests remain unaffected. New tests verify brand filter integration.

### 4. `src/hawedit/pipeline.py`
- **Symbols Modified**:
  - `add_arguments(...)`: Add `--brand-kit`, `--speaker-metadata`, `--logo`, `--progress-bar`, `--end-card`.
  - `run_pipeline(...)`: Parse brand kit options and pass to downstream rendering.
  - `PipelineRun`: Records brand kit metadata in output manifest and run events.
- **Callers**:
  - CLI entrypoints (`hawedit.pipeline`).
  - `tests/test_pipeline.py`.

### 5. `DECISIONS.md`
- New ADR `## D-268 · Brand kit overlays in Stage 6 render: lower-third, logo, end card, progress bar`.
