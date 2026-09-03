# Impact Map: Shaped-Width Line Breaking (Task T2.9)

## Modified Files
- `src/hawedit/captions.py`:
  - `measure_rendered_caption_width`: helper to measure text ink bounding width using libass + OpenCV with caching.
  - `wrap_caption_lines`: support `max_width_px` parameter for shaped-width wrapping.
  - `chunk_caption_events`: support `max_width_px` parameter for shaped-width chunking.
  - `POPUP_MAX_WIDTH_PX`: export default popup width limit (~700 px).
  - `DEFAULT_MAX_LINE_WIDTH_PX`: export default line width limit (~850 px).
- `tests/test_captions.py`:
  - Add unit tests verifying shaped-width line wrapping, chunking, single-word preservation, and pixel margin containment.

## Callers and Invariants
- Existing callers of `wrap_caption_lines(words, max_chars=...)` remain 100% compatible.
- Single-word non-truncation invariant (§4.3.5) preserved.
- `build_ass` integrates shaped-width parameters when theme or width is specified.
