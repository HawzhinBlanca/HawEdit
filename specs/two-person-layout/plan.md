# Plan — Two-Person Split Screen Layout (Task T2.12)

## Status
Approved-by: Autonomous Canon Mandate (/goal make canon)

## Goal
Provide a stacked top/bottom split screen layout (1080×1920 composed of two 1080×960 panes) when diarization indicates rapid conversational exchanges (turns < 4.0s) between two participants, preventing camera whiplash from rapid alternating jump-cuts/pans.

## Proposed Changes

### Task 1: Rapid Exchange Detection & Split Crop Planning in `src/hawedit/reframe.py`
1. Implement `detect_rapid_speaker_exchange(turns, in_ms, out_ms, *, max_turn_duration_ms=4000, min_turns=3) -> bool`:
   - Checks if candidate interval contains >= 2 distinct speakers alternating turns where average or individual turn duration is < `max_turn_duration_ms`.
2. Implement `compute_two_person_split_crops(source_width, source_height, speaker_centers, *, target_width=1080, pane_height=960)`:
   - Derives the 9:8 aspect ratio crop windows $(x_1, y_1, w_1, h_1)$ and $(x_2, y_2, w_2, h_2)$ centered on Speaker 1 (top pane) and Speaker 2 (bottom pane).
   - Bounds-checks and clamps coordinates to stay strictly within source video dimensions.

### Task 2: Filtergraph & Reframe Execution in `src/hawedit/render.py`
1. Add `Reframe.TWO_PERSON_SPLIT = "two_person_split"` to `Reframe` enum.
2. Implement `two_person_split_filter(...)`:
   - Generates FFmpeg filter chain:
     `[0:v]split=2[top_in][bot_in];`
     `[top_in]crop=...:scale=1080:960[top_p];`
     `[bot_in]crop=...:scale=1080:960[bot_p];`
     `[top_p][bot_p]vstack=inputs=2[v_split]`
3. Wire into `render_clip` when `reframe is Reframe.TWO_PERSON_SPLIT`.

### Task 3: Pipeline Integration & CLI Support in `src/hawedit/pipeline.py`
1. Add CLI flag `--split-screen` / `--two-person-split {auto,never,always}` (default: `auto`).
2. When `auto` and `detect_rapid_speaker_exchange` returns True, activate `Reframe.TWO_PERSON_SPLIT`.
3. Record `reframe: "two_person_split"` in the output contract and run events.

### Task 4: Unit & Integration Tests
1. Add comprehensive tests in `tests/test_reframe.py` and `tests/test_render.py`.
2. Verify gate passes with `scripts/verify.sh`.
3. Update ledgers with `scripts/update-ledger.sh`.

### Task 5: Level B Media Verification
1. Render an exchange from `ep29-chunk50min.mp4` using both standard reframing and two-person split screen.
2. Record comparative metrics in `evidence/two-person-layout.md`.
