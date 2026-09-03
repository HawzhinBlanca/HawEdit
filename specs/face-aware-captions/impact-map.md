# Impact Map: Face-Aware Caption Placement (Task T2.7)

## Modified Files
- `src/hawedit/captions.py`:
  - Export `DEFAULT_BOTTOM_CAPTION_BAND` and `DEFAULT_TOP_CAPTION_BAND`.
  - Add top-aligned style generation to `CaptionTheme` (`style_row`).
  - Update `build_ass` to accept `face_intervals: Sequence[tuple[int, int, int, int]] | None = None` and select `KurdishTop` for overlapping events.
- `tests/test_captions.py`:
  - Add geometry unit tests for collision detection and ASS style assignment.
  - Add pixel test verifying rendered ink for top vs bottom placements.

## Invariants & Safety
- Default behavior without `face_intervals` remains 100% backward compatible (emits bottom `Kurdish` style).
- Word highlights and karaoke timing tags (`\kf`) remain intact regardless of style placement.
