# Plan — Brand Kit: Lower-Third, Logo, End Card, Progress Bar (Task T2.13)

## Status
Approved-by: User Review Policy (/goal make canon)

## Goal
Implement a complete, production-grade Brand Kit for HawEdit's Stage 6 rendering pipeline, encompassing:
1. **Lower-Third Speaker Labels**: Per-episode metadata mapped to diarization speaker turns, rendered in Kurdish Sorani via libass with `shaping=complex` (`Noto Naskh Arabic` / `Vazirmatn`).
2. **Logo Watermark**: Semi-transparent channel/creator logo overlay positioned in an un-occluded corner with configurable opacity, scale, and safe margins.
3. **2-Second End Card**: Outro sequence with Kurdish call-to-action ("سەبسکرایبی چەناڵی یوتیوب بکەن") and channel handle.
4. **Dynamic Progress Bar**: Seamless bottom-edge progress indicator advancing from 0% to 100% across the video's duration.
5. **ADR in `DECISIONS.md`**: Formalize the Stage 6 rendering divergence as ADR D-268.

## Proposed Tasks

### Task 1: Core Brand Kit Domain Models (`src/hawedit/brand.py`)
1. Create `SpeakerBio`, `ProgressBarConfig`, `EndCardConfig`, and `BrandKit` dataclasses with strict field validation (positive dimensions, valid 0..1 opacity, valid positioning strings, and non-empty strings).
2. Implement `logo_overlay_filter(...)` and `progress_bar_filter(...)` to generate deterministic FFmpeg filter strings.
3. Provide `BrandKit.from_dict(...)`, `BrandKit.to_dict(...)`, and `BrandKit.from_json(path)` with fail-stop error handling if files are missing or malformed.
4. Write comprehensive unit tests in `tests/test_brand.py`.

### Task 2: Lower-Third Speaker Tags via ASS Subtitles (`src/hawedit/captions.py`)
1. Extend `build_ass(...)` to accept `speaker_turns: Sequence[tuple[int, int, str]] | None = None` and `speaker_metadata: dict[str, SpeakerBio] | None = None`.
2. Introduce `SpeakerTag` style in ASS header: 
   - Positioned cleanly with safe margins, high-contrast dark outline, and semi-transparent background box.
3. Add dialogue events with `\fad(300,300)` for active speaker turns matching `speaker_metadata`.
4. Add unit and visual tests in `tests/test_captions.py` verifying correct Sorani glyph shaping and zero collision with speech captions.

### Task 3: Video Filter Integration & End Card in `src/hawedit/render.py`
1. Extend `render_clip(...)` with `brand_kit: BrandKit | None = None`.
2. When `brand_kit.logo_path` is specified:
   - Validate logo file existence (fail-stop if missing).
   - Append logo scaling, opacity, and overlay filter to the video filter complex.
3. When `brand_kit.progress_bar.enabled` is True:
   - Append `drawbox` progress bar filter to the video filter complex.
4. When `brand_kit.end_card.enabled` is True:
   - Append a 2.0-second outro card with call-to-action text and logo, updating duration math and contract assertions.
5. Add integration tests in `tests/test_render.py`.

### Task 4: Pipeline Wiring & CLI Support in `src/hawedit/pipeline.py`
1. Add CLI flags:
   - `--brand-kit PATH`
   - `--speaker-metadata PATH`
   - `--logo PATH`
   - `--progress-bar`
   - `--end-card`
2. Integrate into `render_clip_candidates` and record brand kit settings in `PipelineRun` output contract and `RunEventLog`.
3. Add tests in `tests/test_pipeline.py`.

### Task 5: ADR D-268 in `DECISIONS.md`
1. Record Architectural Decision Record `## D-268 · Brand kit overlays in Stage 6 render: lower-third, logo, end card, progress bar`.

### Task 6: Gate Verification & Ledger Update
1. Run `bash scripts/verify.sh` to ensure all linting, type-checking, formatting, and unit tests pass.
2. Ratchet test floor and update `specs/brand-kit/ledger.log` using `scripts/update-ledger.sh`.
