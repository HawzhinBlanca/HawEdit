# Plan — Cold-Open Assembly (Task T4.9)

Research: `specs/cold-open-assembly/research.md`
Specification: `specs/cold-open-assembly/spec.md`
Impact Map: `specs/cold-open-assembly/impact-map.md`

Approved-by: Hawa — inherited from the approved autonomy-first execution plan, 2026-08-17

## Architecture & Implementation

### 1. Cold-Open Construction (`src/hawedit/assembly.py`)
- `assemble_cold_open(setup_sentences: Sequence[Sentence], payoff_sentence: Sentence) -> AssembledReel`:
  Places `[payoff_sentence]` as span 0, followed by `setup_sentences` as span 1.
  Uses `assemble_spans` to re-offset word timestamps onto the continuous unified timeline starting at $t=0$.

### 2. Filtergraph Generation & Splicing
- `assembled_splice_filter(spans: Sequence[AssemblySpan], fps: float = 30.0) -> str`:
  Generates FFmpeg filter complex:
  * For each span $i$:
    `[0:v]trim=start_pts={in_s}:end_pts={out_s},setpts=PTS-STARTPTS[v{i}]`
    `[0:a]atrim=start_pts={in_s}:end_pts={out_s},asetpts=PTS-STARTPTS[a{i}]`
  * Splicing via concat:
    `[v0][a0][v1][a1]concat=n={len(spans)}:v=1:a=1[vconcat][aconcat]`
  * Concat output feeds downstream crop/scale/subtitles filtergraph.

### 3. Rendering Pipeline
- `render_assembled_reel(...) -> Path`:
  * Computes 9:16 vertical crop coordinates from face-tracking or centering.
  * Builds ASS subtitles from `reel.assembled_sentences` via `build_ass`.
  * Computes re-timed punch-ins on assembled sentence boundaries via `plan_punch_ins`.
  * Executes FFmpeg encode producing deliverable 1080x1920 MP4 of exact duration `reel.total_duration_ms`.

### 4. Frame Extraction & Multimodal Judging
- `judge_assembled_reel_multimodal(...) -> JudgeVerdict`:
  * Extracts representative keyframes from the rendered assembled MP4 (at $t = 0.5\text{s}, D_{\text{cold-open}}/2, D_{\text{cold-open}} + 1\text{s}, \dots$).
  * Passes `frames` to `EditorialJudge.judge` in `STAGE_4_MULTIMODAL` mode.
  * Enforces `verdict.misleading_edit_risk <= MAX_MISLEADING_EDIT_RISK` (0.10).

## Verification
- Unit and integration tests in `tests/test_assembly.py`:
  - `test_assemble_cold_open_orders_payoff_first`
  - `test_assembled_splice_filter_generates_valid_filtergraph`
  - `test_an_assembled_reel_is_rendered_and_judged_with_its_own_frames` (Required Proof A)
  - `test_misleading_edit_risk_gated_on_assembled_reel`
