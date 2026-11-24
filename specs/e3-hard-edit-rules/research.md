# Research: E3 — Hard Edit Rules & `render_critic.py` Wire-or-Delete Audit

## 1. Goal & Scope
Phase E3 (`specs/pro-grade-program/gemini-task-sheet-2026-11-18.md`) mandates:
1. Enforce hard edit rules in code:
   - Never cut inside a word,
   - Maintain `30–200 ms` padding at cut edges,
   - Satisfy output duration bounds.
2. **Audit `src/hawedit/render_critic.py`** (callers, overlap with `sanity_gate.py`, `measure.py`, `delivery.py`, and `agent.py`), and decide concretely to **wire or delete** it without adding a third critic.

Round 1 covers **research + specification/planning only** (`AGENTS.md` §Workflow 1–2).

---

## 2. Audit of `render_critic.py` & Overlapping Modules

### 2.1 Callers and dependents of `src/hawedit/render_critic.py` (`L1-1002`)
Grep across `src/`, `tests/`, and `scripts/` found:
- **Production pipeline call sites (`2`):**
  - `src/hawedit/pipeline.py:2539-2559` (`_render_episode_single_clip`)
  - `src/hawedit/pipeline.py:4627-4647` (`run_pipeline`)
  - Both construct `RenderedSequenceContext(render_path=render_path, duration_ms=int(measurement.video.duration_ms), fps=fps, source_video_path=source, expected_sha256=measurement.file.sha256, sentences=tuple(selected), assembly_spans=assembly_spans)` and call `inspect_rendered_sequence(..., claim_all_clear=True)`.
- **Sibling `src/` importers (`2`, both currently having `0` `src/` callers):**
  - `src/hawedit/visual_repair.py:25-32, 372` (VE-12 bounded visual repair)
  - `src/hawedit/episode_package.py:19` (`CritiqueInspectionResult`, VE-13 episode packaging)
- **Non-importing string reference (`1`):**
  - `src/hawedit/workflow_recovery.py:448, 611-612` (`"render_critic"` in `ALL_STEPS` and `STEP_DIRECT_DEPENDENCIES`)
- **Manual verification script (`1`):**
  - `scripts/verify_real_reel_renders.py:54-57, 340-351`
- **Active tests (`5` files, `11+` tests):**
  - `tests/test_render_critic.py` (`9` tests at `:35, 198, 257, 274, 294, 316, 332, 375, 446`)
  - `tests/test_robustness_audit.py:272-310` (`RB-11`, `RB-12`)
  - `tests/test_visual_repair.py`, `tests/test_episode_package.py`, `tests/test_workflow_recovery.py`

### 2.2 What `render_critic.py` actually executes vs. skips in `pipeline.py`
Both `pipeline.py` call sites leave `planned_shots=()`, `caption_plan=None`, `timing_timeline=None`, `landing_beat_ms=None`, `setup_boundary_ms=None`, `llm_critique_verdict=None`, and `injected_observations=None` unset. Consequently:
- **Checks #3–#7 and #9 (`render_critic.py:629-782, 920-940`) never execute in production.**
- **Only two checks execute in production today:**
  1. **Check #0 (`render_critic.py:370-585`)**: File existence, SHA-256 verification, `cv2` video open, `abs(actual_dur - expected_dur) > 1000 ms`, and sampling 1 frame per window at `mid_ms` checking `mean_lum < 1.0` — which internally contradicts `TemporalCritiqueWindow`'s own `frame_count >= 2` motion invariant (`render_critic.py:164-168`).
  2. **Check #8 (`render_critic.py:783-918`)**: Kurdish narrative-join integrity (`mid_clause_starters` and `_is_dangling_fragment`) on `sentences` / `assembly_spans`.

### 2.3 Overlap with `sanity_gate.py`, `measure.py`, `delivery.py`, and `agent.py`
| Module | Production Callers (`src/`) | Scope & Overlap |
|---|---|---|
| `render_critic.py` (`L1-1002`) | `pipeline.py:2539-2559, 4627-4647` | Post-render sequence inspection, `assert_verdict_grounded()` (`:238-265`), `injected_observations` (`:629-661`), Kurdish dangling-clause check (`:783-918`). |
| `sanity_gate.py` (`L1-417`) | **0 `src/` callers** (only `scripts/verify_real_reel_renders.py` & `tests/test_sanity_gate.py`) | `SanityGate` (`check_subtitles`, `check_audio_compliance`, `check_face_presence`, `check_narrative_integrity`). Largely duplicates `measure.py` + `delivery.reconcile_delivery()`. |
| `measure.py` (`L1-1235`) | `pipeline.py`, `delivery.py` | Authoritative Level B FFmpeg/ffprobe/MediaPipe artifact measurement (`measure_clip`, `probe_container`, `probe_audio_dynamics`, `probe_scene_cuts`, `probe_face_tracking`, `probe_caption_ink`, `probe_vmaf`). |
| `delivery.py` (`L407-667`) | `pipeline.py:2527-2537, 4614-4624`, `candidate_publication.py:243-250` | `reconcile_delivery()` enforces 11 physical media/contract clauses before critic runs. |
| `agent.py` (`L486-600`) | `run_quality_checks`, `TOOL_NAMES`, `build_agent` | Zero-parameter agent wrapper reading `report.json` / `events.jsonl`. |

### 2.4 Concrete Wire-or-Delete Decision on `render_critic.py`: **WIRE (Consolidate, Do Not Delete, Do Not Add a 3rd Critic)**
- **Why NOT delete `render_critic.py`:**
  1. It is already wired into both production paths in `pipeline.py` and tracked in `PROGRESS.md:1281` (`M9.35`), `README.md:713`, `workflow_recovery.py:448, 611-612`, `visual_repair.py`, and `episode_package.py`.
  2. Deleting it would destroy 11+ existing tests (`test_render_critic.py`, `test_robustness_audit.py` RB-11/RB-12) or violate anti-cheat test-preservation discipline.
  3. Its Check #8 (`mid_clause_starters` / `_is_dangling_fragment`) and `assert_verdict_grounded()` / `injected_observations` schema (`render_critic.py:238-265, 629-661`) already implement the defect-grounding contract required by E2 (`validate_edl` + `view_frames`), preventing a third critic from being invented.
- **How to WIRE it cleanly:**
  1. Implement the single authoritative `validate_edl(...)` function (for both pre-render fail-stop in `pipeline.py` and post-render verification in `render_critic.py`, reusable by E2 later).
  2. Wire `edit_plan` (and available `caption_plan` / `timing_timeline` / contact-sheet context) into `RenderedSequenceContext` at `pipeline.py:2539-2559` and `pipeline.py:4627-4647`, and add an E3 hard-edit-rules check inside `render_critic.inspect_rendered_sequence()` backed by `validate_edl()`.
  3. Fix Check #0's 1-frame `mid_ms` vs `TemporalCritiqueWindow` `frame_count >= 2` contradiction (`render_critic.py:164-168, 370-585`) so `inspect_rendered_sequence()` does not sample a single frame while claiming multi-frame motion inspection.
  4. Leave physical FFmpeg/audio/container measurement in `measure.py` + `delivery.reconcile_delivery()`, and keep the redundant unwired `sanity_gate.py` quarantined/unwired (`README.md:627`) rather than wiring a competing critic (candidate for follow-up deprecation once E2 settles).

---

## 3. Audit of Existing EDL / Word-Boundary / Padding / Duration Code

Grep and line-by-line inspection across `assembly.py`, `edit_plan.py`, `boundary.py`, `silence.py`, `timing_continuity.py`, `clip.py`, `content_type.py`, `delivery.py`, and `pipeline.py` uncovered concrete gaps for all three E3 rules:

### 3.1 Rule 1 — Never cut inside a word
- **`assembly.py:86-165` (`assemble_spans`) and `:219-250` (`assemble_cold_open`)**: Enforce `sent.complete`, non-empty `sent.words`, `out > in`, and word timing containment within assembled sentences. They do **not** validate arbitrary `VisualEditPlan` / `SilencePlan` / cut intervals across sub-sentence splits.
- **`edit_plan.py:232-320` (`SourceTimeMapping`) and `:324-573` (`VisualEditPlan`)**: Validate segment interval monotonicity inside `[clip_in_ms, clip_out_ms]` only; there is **no** word-overlap check on cut boundaries and **no** `validate_edl()` function.
- **`timing_continuity.py:193-320` (`tighten_with_continuity_protection`)**: Implements `SpeechTruncationError` when excised intervals overlap `[w.start_ms, w.end_ms]` (`:291-298`, with `word_boundary_buffer_ms = 50`), **but has `0` callers in `src/`**.
- **`delivery.py:297-378` (`build_edl`)**: Checks `fps` and `duration_frames >= 1` only; performs zero word-boundary or padding validation.

### 3.2 Rule 2 — 30–200 ms padding at cut edges
- **`boundary.py:151-153, 274-313`**: Defines `VAD_LEAD_IN_MS = 120`, `TAIL_MS = 200`, `SHOT_CUT_WINDOW_MS = 400`, and `assert_boundary_invariant()`. Enforces `final_in_ms <= anchor_in_ms` and `final_out_ms >= anchor_out_ms`, allowing **`0 ms`** padding when VAD/tail signals are `None` and **`> 200 ms`** outward drift when `SHOT_CUT_WINDOW_MS = 400` snaps to a distant shot boundary.
- **`silence.py:36-37, 240-500` (`plan_silence_tightening`)**: Uses `DEFAULT_SILENCE_THRESHOLD_MS = 600` and `DEFAULT_TARGET_GAP_MS = 150`. **Bug at `silence.py:377-379` and `:408-410`:** computes `cut_start = gap_start + target_gap_ms; cut_end = gap_end`, placing all `target_gap_ms` before `cut_start` and leaving **`0 ms` padding** immediately before the post-cut word onset at `gap_end`!
- **`content_type.py:57-94` and `pipeline.py:2849-2850`**: Currently set `silence_threshold_ms = 0` (disabled by default) and `silence_target_gap_ms = 150`; whenever silence tightening is enabled, `silence.py` immediately violates the `>= 30 ms` post-cut padding rule.

### 3.3 Rule 3 — Output duration bounds
- **`clip.py:287-288`**: Defines `MIN_CANDIDATE_SPAN_MS = 30_000` and `MAX_CANDIDATE_SPAN_MS = 90_000` (`DECISIONS.md` `D-254`).
- **`content_type.py:57-94`**: Defines profile `min_clip_ms` (`30_000` PODCAST, `25_000` INTERVIEW, `15_000` NEWS/SOCIAL).
- **`pipeline.py:1354-1356` (`_grown_sentence_run`)**: Allows sentence-completion growth to overshoot the configured max span; no pre-render EDL check clamps or rejects out-of-bounds post-tightening output durations (`VisualEditPlan.total_output_duration_ms`).
- **`pipeline.py:2398` and `:4476`**: Call `render_clip(...)` directly without pre-render `validate_edl()` enforcement of duration bounds, word boundaries, or `30–200 ms` edge padding.

### 3.4 Relevant living doc references
- `DECISIONS.md`: `D-259` (`:13580`), `D-262` (`:13705`), `D-263` (`:13723`), `D-330` (`:16341`), `D-333` (`:16485`), `D-334` (`:16548`), `D-335` (`:16607`).
- `PROGRESS.md`: `M9.27` (`:1273`, `edit_plan`), `M9.35` (`:1281`, `render_critic`).
- `BLOCKED.md`: active blockers include `#1`, `#3`, `#4`, `#14`, `#17`, `#21`, `#25` (`#24` and `#26` RESOLVED); next free number is `#27` (ask `@coordinator` before adding).
- `README.md`: `sanity_gate.py` (`:627`), `delivery.py` (`:671`), `edit_plan.py` (`:706`), `render_critic.py` (`:713`).
- `tests/test_vex.py:27-30, 140-163`: Editing `src/hawedit/*.py` updates `package_digest(src/hawedit)` and requires Lane 1 A3 parking VEX or owner re-pinning `security/wsl-asr-vex.json` + `tests/test_vex.py`.
