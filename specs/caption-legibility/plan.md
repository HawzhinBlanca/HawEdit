# Plan: Caption Legibility Measurement & Adaptive Background Plate (Task T2.8)

Approved-by: Hawa

## Overview
Implement caption legibility measurement and adaptive background plate rendering: measure relative luminance and contrast ratio between subtitle text and video background per caption event, and when contrast falls below 4.5:1, automatically add a backing plate (`border_style=3`, `outline=16.0`, `back_colour="&H80000000"`).

## Architecture
1. In `src/hawedit/captions.py`:
   - `parse_ass_colour(colour: str) -> tuple[int, int, int]`: decode `&HAABBGGRR` or `#RRGGBB` into sRGB.
   - `relative_luminance(r: int, g: int, b: int) -> float`: WCAG 2.1 relative luminance.
   - `contrast_ratio(lum1: float, lum2: float) -> float`: standard contrast ratio.
   - `CaptionTheme.plate_style_row(...)`: generate ASS style with `border_style=3`.
   - `build_ass(...)`: accept `plate_intervals: Sequence[tuple[int, int]] | None = None`. If an event falls within a plate interval, assign style `KurdishPlate` (or `KurdishTopPlate`).
2. In `src/hawedit/measure.py`:
   - `measure_caption_events_contrast(...)`: returns per-event contrast measurements.
3. In `tests/test_captions.py`:
   - Test colorimetry math against known WCAG benchmarks.
   - Test ASS plate style generation and event assignment.
   - Pixel test rendering text with plate over white video background.
