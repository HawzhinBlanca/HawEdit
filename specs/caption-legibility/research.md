# Research: Caption Legibility Measurement & Adaptive Background Plate (Task T2.8)

## 1. Grounding & Spec
Per `specs/pro-grade-program/tasks.md` Task T2.8:
> **T2.8** | **P2** | **Caption legibility measurement.** Contrast between text colour and the band's median luminance per caption event; below 4.5:1 add the plate. Nothing measures legibility; a dark source would fail silently. Proof required: A: contrast function tests. B: per-event contrast table for s25-25. C: T1.2 clause (min contrast).

In `src/hawedit/captions.py`:
- Captions currently default to outline/shadow styling (`border_style = 1`).
- On light, bright, or visually noisy video scenes (e.g. guest wearing white/light clothing, bright studio lighting, outdoor daylight), yellow/white text loses legibility without a backing plate.
- Standard WCAG 2.1 AA legibility requires a minimum contrast ratio of 4.5:1 for standard text.

## 2. Colorimetry & Luminance Mathematics
1. **Relative Luminance ($L$)**:
   Converts sRGB channels $[0, 255]$ to linear RGB:
   $C_{\text{lin}} = C / 12.92$ if $C \le 0.04045$ else $((C + 0.055) / 1.055)^{2.4}$
   $L = 0.2126 \times R_{\text{lin}} + 0.7152 \times G_{\text{lin}} + 0.0722 \times B_{\text{lin}}$.
   - Pure White `#FFFFFF`: $L = 1.0$.
   - Viral Yellow `&H0000E5FF` (`#FFE500`): $L \approx 0.773$.
   - Pure Black `#000000`: $L = 0.0$.
2. **Contrast Ratio ($CR$)**:
   $CR = \frac{\max(L_1, L_2) + 0.05}{\min(L_1, L_2) + 0.05}$.
   - Black vs White: $21.0:1$.
   - White vs Light Grey ($L=0.58$): $1.67:1$ (fails $4.5:1$ threshold).
3. **Adaptive Plate Addition**:
   When measured contrast in the caption band during a dialogue event is $< 4.5:1$:
   Assign the dialogue event to a plate style (`border_style=3`, `outline=16.0`, `back_colour="&H80000000"`), which renders a semi-transparent black backing plate directly behind the text.
   Against the dark plate ($L \approx 0.02$), contrast ratio is restored to $\ge 11:1$, guaranteeing flawless readability.

## 3. Architecture
- `src/hawedit/captions.py`:
  - `parse_ass_colour(colour: str) -> tuple[int, int, int]`
  - `relative_luminance(r: int, g: int, b: int) -> float`
  - `contrast_ratio(lum1: float, lum2: float) -> float`
  - `CaptionTheme.plate_style_row(...)` for `border_style=3`
  - `build_ass(...)` accepts `plate_intervals: Sequence[tuple[int, int]] | None = None`
  - When an event interval matches `plate_intervals`, apply `KurdishPlate` (or `KurdishTopPlate`).
- `src/hawedit/measure.py`:
  - `measure_caption_event_contrast(...)` computes the per-event contrast ratio table.
