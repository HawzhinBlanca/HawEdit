# Plan: Face-Aware Caption Placement (Task T2.7)

Approved-by: Hawa

## Overview
Implement face-aware caption band placement in `src/hawedit/captions.py`: detect when a tracked subject's face overlaps the default bottom caption band, and dynamically move the caption event to the top band (`KurdishTop`, `alignment=8`, `margin_v=240`) so subtitles never obscure the speaker's face.

## Architecture
1. In `src/hawedit/captions.py`:
   - Define constants:
     - `DEFAULT_BOTTOM_CAPTION_BAND: Final = (1300, 1650)`
     - `DEFAULT_TOP_CAPTION_BAND: Final = (200, 520)`
     - `DEFAULT_TOP_MARGIN_V: Final = 240`
   - In `build_ass`:
     - Accept `face_intervals: Sequence[tuple[int, int, int, int]] | None = None` where each tuple is `(start_ms, end_ms, top_y, bottom_y)`.
     - Emit both `Kurdish` (default bottom) and `KurdishTop` (top-aligned) in `[V4+ Styles]`.
     - In event emission loop, check if any face interval within `[event_start, event_end]` intersects `DEFAULT_BOTTOM_CAPTION_BAND`. If so, assign style `KurdishTop`; otherwise `Kurdish`.
2. In `tests/test_captions.py`:
   - Test collision logic with mock face intervals.
   - Verify ASS output contains `KurdishTop` for overlapping sentences.
   - Verify pixel extent of rendered ink via FFmpeg + libass.
