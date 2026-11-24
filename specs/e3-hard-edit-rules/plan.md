# Plan: E3 — Hard Edit Rules & Wiring `render_critic.py`

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

## 1. Architecture & Concrete `render_critic.py` Disposition

### Decision: WIRE & CONSOLIDATE `render_critic.py` (Do NOT Delete; Do NOT Add a 3rd Critic)
`render_critic.py` already executes in both `pipeline.py` paths (`:2539-2559`, `:4627-4647`), owns the only Kurdish mid-clause dangling-fragment check (`:783-918`), enforces `assert_verdict_grounded()` (`:238-265`), and anchors `visual_repair.py`, `episode_package.py`, `workflow_recovery.py`, and `11+` active tests (`tests/test_render_critic.py`, `tests/test_robustness_audit.py` `RB-11`/`RB-12`). Deleting it wastes working invariants and breaks existing modules; adding another critic violates E2/E3 consolidation rules.

Instead:
1. **Single Authoritative `validate_edl()` (`src/hawedit/edit_plan.py`)**:
   - Implement `EdlValidationResult` + `EditRuleViolationError(ValueError)` + `validate_edl(plan, *, words=..., min_padding_ms=30, max_padding_ms=200, min_duration_ms=..., max_duration_ms=...)` directly alongside `VisualEditPlan` in `edit_plan.py` (zero new module bloat; immediately reusable by E2's future `validate_edl` tool).
   - Also expose a thin helper `validate_edl_segments(...)` or accept `VisualEditPlan` / `SourceTimeMapping` / explicit retained intervals + `words` so `delivery.py`, `pipeline.py`, `render_critic.py`, and E2 review callers share one exact code path (`ponytail`).
   - Checks enforced:
     1. **No word splits:** Neither any retained interval boundary `[start_ms, end_ms]` nor any excised gap splits a spoken word (`w.start_ms < cut_ms < w.end_ms` or excised-interval overlap with `[w.start_ms, w.end_ms]`).
     2. **Edge padding `[30, 200]` ms:** Every outer edge (`seg.start_ms -> first_word.start_ms` and `last_word.end_ms -> seg.end_ms`) and both sides of every internal splice cut maintain `30 <= pad_ms <= 200` ms.
        - **Boundary reconciliation note:** Existing `boundary.py` tests test `fuse_boundary()` with optional `None` soft signals (`0 ms` when absent) or `SHOT_CUT_WINDOW_MS = 400`. Rather than breaking `boundary.py`'s existing low-level unit contracts, `pipeline.py` clamps/applies bounded edge padding (`[30, 200]` ms) before building `VisualEditPlan` (respecting surrounding non-included words when selecting cut points, and rejecting tight exterior gaps `< 30 ms` or failing cleanly in `validate_edl()`), while `boundary.py` stays backward-compatible or gets explicit bounded helper support.
     3. **Output duration bounds:** Total output timeline duration must satisfy `min_duration_ms <= total_output_duration_ms <= max_duration_ms` (default resolved cleanly from `EffectiveConfiguration` / policy; see `[HAWA]` question below on `30–55 s` vs `30–90 s` `D-254`).

2. **Fix `silence.py` Zero-Padding Bug (`src/hawedit/silence.py:377-379, 408-410`)**:
   - Today `plan_silence_tightening()` puts the entire `target_gap_ms` at `gap_start` and sets `cut_end = gap_end`, leaving **`0 ms`** between the splice cut and the next spoken word!
   - Update gap allocation to retain padding on **both** sides (`post_pad = max(30, min(target_gap_ms // 2, 200))`, `pre_pad = max(30, min(target_gap_ms - post_pad, 200))` bounded so `pre_pad + post_pad` respects `30..200 ms` per side when tightening gaps `>= DEFAULT_SILENCE_THRESHOLD_MS`), reusing `timing_continuity.py` overlap awareness if words are supplied.

3. **Wire Pre-Render Gate + `render_critic.py` Context in `pipeline.py` & Fix Check #0**:
   - Before calling `render_clip()` in `_render_episode_single_clip` (`pipeline.py:2398`) and `run_pipeline` (`pipeline.py:4476`), build the exact `VisualEditPlan` / word sequence and run `validate_edl(...)` fail-stop (zero silent fallback, zero wasted GPU render).
   - At `pipeline.py:2539-2559` and `pipeline.py:4627-4647`, pass `edit_plan` (and `caption_plan` when constructed) into `RenderedSequenceContext`.
   - Extend `RenderedSequenceContext` and `inspect_rendered_sequence()` in `src/hawedit/render_critic.py` to run `validate_edl()` when `edit_plan` (with words/sentences) is provided, failing `claim_all_clear=True` if any E3 rule is violated.
   - Fix Check #0 (`render_critic.py:164-168, 370-585`) so `TemporalCritiqueWindow` consistently samples `frame_count >= 2` distinct frames per window (start & end of window) rather than a single `mid_ms` frame.
   - Keep `sanity_gate.py` unwired (no 3rd critic); keep physical FFmpeg/container checks in `measure.py` + `delivery.reconcile_delivery()`.

## 2. Files to Create or Modify in Round 2 (After Approval)
| Action | File | Purpose |
|---|---|---|
| Edit | `src/hawedit/edit_plan.py` | Add `MIN_CUT_PADDING_MS = 30`, `MAX_CUT_PADDING_MS = 200`, `EditRuleViolationError`, `EdlValidationResult`, `validate_edl()` |
| Edit | `src/hawedit/silence.py` (`:377-379, 408-410`) | Split retained gap across both `cut_start` and `cut_end` so both sides keep `[30, 200]` ms padding |
| Edit | `src/hawedit/render_critic.py` | Accept optional `edit_plan` / `words` on `RenderedSequenceContext`, call `validate_edl()`, fix Check #0 multi-frame sampling (`frame_count >= 2`) |
| Edit | `src/hawedit/pipeline.py` (`:2398`, `:2539-2559`, `:4476`, `:4627-4647`) | Pre-render `validate_edl()` fail-stop + pass `edit_plan`/`caption_plan` to `RenderedSequenceContext` |
| Create | `tests/test_edit_rules.py` | Unit tests covering `E3-R1`..`E3-R4` + pre-render fail-stop |
| Edit | `tests/test_silence.py` (or `tests/test_edit_rules.py`) | Regression test ensuring `plan_silence_tightening` never emits `0 ms` post-cut edge margin |
| Edit (integration) | `DECISIONS.md` (`D-354`), `PROGRESS.md` | Record ADR `D-354` (hard edit rules constants & `render_critic.py` consolidation); ensure constants match `tests/test_claims.py:883-940` |
| Coordinate | `security/wsl-asr-vex.json`, `tests/test_vex.py` | Re-pin or wait for A3 VEX parking (`tests/test_vex.py:140-163`) |

## 3. Verification Plan (Round 2)
1. `.venv\Scripts\python.exe -m pytest tests/test_edit_rules.py tests/test_render_critic.py tests/test_robustness_audit.py tests/test_silence.py tests/test_boundary.py tests/test_edit_plan.py tests/test_delivery.py tests/test_claims.py -q`
2. `& "C:\Program Files\Git\bin\bash.exe" scripts/verify.sh --fast`
3. Confirm no existing `tests/test_render_critic.py` or `RB-11`/`RB-12` assertions were relaxed or skipped.

## 4. Open Questions (`[HAWA]` / Owner Confirmation Before Round 2)
1. **Duration bounds reconciliation (`clip.py` `D-254` vs social target vs `content_type.py`):** Should `validate_edl()` enforce `[30_000, 90_000]` ms per `D-254`/`clip.py:287-288`, `[30_000, 55_000]` ms per `GEMINI.md` reel pacing, or `EffectiveConfiguration` profile bounds (`content_type.py`: `15_000`–`30_000` ms min)?
2. **Tight neighboring speech (`< 30 ms` gap outside selected sentence):** When an unselected adjacent source word sits `< 30 ms` away from the start/end of a selected clip (making `>= 30 ms` exterior silence impossible without overlapping that neighboring word), should `validate_edl()` reject the candidate clip outright (fail-stop) or allow an explicitly bounded exterior snap while keeping `[30, 200]` ms mandatory on all planned cuts/tightened gaps?
