# Plan: Shaped-Width Line Breaking (Task T2.9)

Approved-by: Hawa

## Overview
Implement rendered ink width measurement using libass and OpenCV, then integrate shaped-width constraints into `wrap_caption_lines` and `chunk_caption_events` to eliminate Kurdish ligature margin overflow and premature line splits.

## Architecture
1. `measure_rendered_caption_width(text, ...)`:
   - Formats a single Dialogue event in an in-memory ASS buffer.
   - Runs `ffmpeg` with `-f rawvideo -pix_fmt gray` into a pipe.
   - Computes `cv2.boundingRect(cv2.findNonZero(gray))[2]` to get exact ink width in pixels.
   - Uses an LRU cache keyed by `(text, font_name, font_size)` to ensure near-zero latency on subsequent evaluations.
2. `wrap_caption_lines(words, max_chars, *, max_width_px=None, ...)`:
   - If `max_width_px` is specified and `measure_rendered_caption_width` is usable, measures incremental candidate lines. Breaks line when adding the next word exceeds `max_width_px`.
3. `chunk_caption_events(words, ..., max_width_px=None, ...)`:
   - If `max_width_px` is specified and usable, closes event when candidate rendered width exceeds `max_width_px`.
4. Tests:
   - Add unit tests for shaped wrapping, chunking, and pixel margin verification on Kurdish text.
