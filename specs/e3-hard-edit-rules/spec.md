# Specification: E3 — Hard Edit Rules (`validate_edl`) & Wired `render_critic.py`

## Overview
Establish a single authoritative hard-edit-rules validator `validate_edl(...)` checked in code both **before rendering** in `pipeline.py` and **during inspection** in `render_critic.py`, plus fix the zero-post-cut-padding bug in `silence.py` and re-wire `render_critic.py` cleanly without introducing a third critic.

## Hard Constants
- `MIN_CUT_PADDING_MS = 30`
- `MAX_CUT_PADDING_MS = 200`
- `DEFAULT_MIN_REEL_DURATION_MS = 30_000` (profile-overridable via `EffectiveConfiguration` / policy after owner `[HAWA]` sign-off on `30–55 s` vs `30–90 s` `D-254`)
- `DEFAULT_MAX_REEL_DURATION_MS = 90_000` (with explicit strict/viral bound parameter `max_duration_ms`, e.g., `55_000` when configured)

## EARS Acceptance Criteria

### E3-R1: Never cut inside a word
- **WHEN** `validate_edl(plan, words=..., ...)` inspects every retained segment `[seg_start_ms, seg_end_ms]` (outer start/end and every internal splice boundary), **THE** validator **SHALL** reject with `EditRuleViolationError` (fail-stop) if any cut timestamp `cut_ms` falls strictly inside any aligned spoken word (`word.start_ms < cut_ms < word.end_ms` for words with `word.end_ms > word.start_ms`), or if an excised silence interval overlaps any aligned word (`silence.py` / `timing_continuity.py` parity).
- **Mapped tests (`tests/test_edit_rules.py`):**
  - `test_validate_edl_rejects_outer_cut_inside_word`
  - `test_validate_edl_rejects_internal_splice_inside_word`

### E3-R2: Maintain 30–200 ms padding at cut edges (and fix `silence.py` 0 ms post-cut bug)
- **WHEN** `validate_edl()` checks padding at outer reel edges (`seg.start_ms` before first contained word `w_first.start_ms`; `seg.end_ms` after last contained word `w_last.end_ms`) and both sides of every internal cut between adjacent retained segments, **THE** validator **SHALL** require every active cut margin `margin_ms` to lie inside `[MIN_CUT_PADDING_MS, MAX_CUT_PADDING_MS]` (`[30, 200]` ms), rejecting `< 30 ms` under-padded cuts and `> 200 ms` dead-air overhangs cleanly with exact offending interval + `margin_ms` in the error report.
- **WHEN** `plan_silence_tightening()` (`src/hawedit/silence.py`) plans an internal cut across a long silence `[gap_start, gap_end]`, **THE** planner **SHALL** reserve symmetric/bounded edge padding of at least `30 ms` and at most `200 ms` on **both** `gap_start` and `gap_end` sides (e.g., `cut_start = gap_start + edge_pad_ms`, `cut_end = gap_end - edge_pad_ms` instead of leaving `0 ms` before `gap_end`), preserving valid word clearances (`margin_ms >= 30 ms`).
- **Mapped tests (`tests/test_edit_rules.py` & `tests/test_silence.py`):**
  - `test_validate_edl_rejects_under_padded_cut_below_30ms`
  - `test_validate_edl_rejects_over_padded_cut_above_200ms`
  - `test_validate_edl_accepts_boundaries_within_30_to_200ms`
  - `test_plan_silence_tightening_keeps_at_least_30ms_padding_on_both_sides`

### E3-R3: Output duration bounds enforcement
- **WHEN** `validate_edl()` inspects an edit plan's total output duration (sum of retained output segments after silence tightening / assembly), **THE** validator **SHALL** fail immediately with `EditRuleViolationError` whenever `output_duration_ms < min_duration_ms` or `output_duration_ms > max_duration_ms`.
- **WHEN** `_grown_sentence_run()` or pre-render assembly in `pipeline.py` prepares a `VisualEditPlan` for rendering (`pipeline.py:2398`, `pipeline.py:4476`), **THE** pipeline **SHALL** validate the finalized EDL with `validate_edl()` before invoking `render_clip()` so out-of-bounds, word-clipped, or mis-padded plans never enter rendering.
- **Mapped tests (`tests/test_edit_rules.py` & `tests/test_pipeline_edl_gate.py`):**
  - `test_validate_edl_rejects_duration_below_min_bound`
  - `test_validate_edl_rejects_duration_above_max_bound`
  - `test_pipeline_aborts_before_render_when_validate_edl_fails`

### E3-R4: Wire and repair `render_critic.py` without adding a third critic
- **WHEN** `pipeline.py` runs `inspect_rendered_sequence()` (`pipeline.py:2539-2559` and `pipeline.py:4627-4647`), **THE** pipeline **SHALL** populate `RenderedSequenceContext` with `edit_plan` (and `caption_plan` when present) so `render_critic.py` enforces `validate_edl()` in addition to its existing physical + Kurdish narrative-join checks (`claim_all_clear=True` fails if `validate_edl()` fails).
- **WHEN** `render_critic.py` builds `TemporalCritiqueWindow` frames during Check #0 (`render_critic.py:164-168, 370-585`), **THE** critic **SHALL** sample at least `frame_count >= 2` distinct frames per window (e.g., start/end or spaced interior samples) so window invariants and motion/black-frame inspection agree cleanly while keeping existing standalone `tests/test_render_critic.py` contracts green.
- **Mapped tests (`tests/test_render_critic.py` & `tests/test_edit_rules.py`):**
  - `test_render_critic_rejects_claim_all_clear_on_edit_rule_violation`
  - `test_render_critic_samples_multi_frame_temporal_windows`
  - Existing 9 tests in `tests/test_render_critic.py` + `tests/test_robustness_audit.py` (`RB-11`, `RB-12`) remain green without relaxing assertions.
