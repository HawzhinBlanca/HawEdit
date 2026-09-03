# Impact Map: Caption Legibility Measurement & Adaptive Background Plate (Task T2.8)

## Modified Files
- `src/hawedit/captions.py`:
  - Functions: `parse_ass_colour`, `relative_luminance`, `contrast_ratio`.
  - Constants: `DEFAULT_PLATE_COLOUR = "&H80000000"`, `DEFAULT_PLATE_PADDING = 16.0`.
  - Class `CaptionTheme`: added `plate_style_row(...)` method for `border_style=3` bounding plates.
  - Function `build_ass`: added `plate_intervals: Sequence[tuple[int, int]] | None = None` parameter, emitting `KurdishPlate` / `KurdishTopPlate` styles and mapping events appropriately.
- `src/hawedit/measure.py`:
  - Added `measure_caption_events_contrast(...)` producing per-event contrast tables.
- `tests/test_captions.py`:
  - Unit tests for colorimetry and ASS plate rendering.

## Invariants & Safety
- Default styling without `plate_intervals` remains 100% identical.
- When a plate is requested, libass's native `border_style=3` handles the bounding geometry automatically with zero external dependencies.
