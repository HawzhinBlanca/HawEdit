# Tasks: E3 — Hard Edit Rules (`validate_edl`) & Wired `render_critic.py`

## Round 1 (Spec Commit)
- [x] T0.1 Audit `render_critic.py`, `sanity_gate.py`, `measure.py`, `agent.py`, `visual_repair.py`, `episode_package.py`, `workflow_recovery.py`, `assembly.py`, `edit_plan.py`, `boundary.py`, `silence.py`, `timing_continuity.py`, `clip.py`, `content_type.py`, `delivery.py`, `pipeline.py`, `tests/test_render_critic.py`, `tests/test_robustness_audit.py`, `tests/test_claims.py`, and `tests/test_vex.py`.
- [x] T0.2 Author `research.md`, `spec.md`, `plan.md`, `impact-map.md`, and `tasks.md` with concrete wire recommendation for `render_critic.py`.

## Round 2 (Implemented on `gemini/lane-5` — Ledgers Flipped by Lead `update-ledger.sh`)
- [x] T1 (`E3-R1`..`E3-R4`): Create `tests/test_edit_rules.py` covering word-split rejection, `< 30 ms` and `> 200 ms` edge-padding rejection, valid `[30, 200]` ms bounds + physical clamps, duration min/max rejection, `silence.py` dual-side padding, `pipeline.py` pre-render fail-stop, Stage 5 padding bounds, and `render_critic` rejection + multi-frame window sampling.
- [x] T2 (`E3-R1`..`E3-R3`): Implement `MIN_CUT_PADDING_MS = 30`, `MAX_CUT_PADDING_MS = 200`, `EditRuleViolationError`, `EdlValidationResult`, `pipeline_edl_duration_bounds`, `pipeline_edl_padding_bounds`, and `validate_edl()` in `src/hawedit/edit_plan.py`.
- [x] T3 (`E3-R2`): Fix `plan_silence_tightening()` in `src/hawedit/silence.py` (`_two_sided_keep_ms`) so both sides of silence cuts keep `[30, 200]` ms padding when `target_gap_ms >= 60` (and symmetric `target_gap_ms // 2` split for explicit small synthetic gaps).
- [x] T4 (`E3-R4`): Wire `validate_edl()` and `>= 2` frame-per-window Check #0 sampling into `src/hawedit/render_critic.py`.
- [x] T5 (`E3-R3`, `E3-R4`): Wire pre-render `validate_edl()` fail-stop and complete `RenderedSequenceContext` context into `src/hawedit/pipeline.py`.
- [x] T6 (Docs): Record `D-354` in `DECISIONS.md` and `M9.42` in `PROGRESS.md`, keeping `tests/test_claims.py` green.
