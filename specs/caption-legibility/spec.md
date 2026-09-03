# Spec: Caption Legibility Measurement & Adaptive Background Plate (Task T2.8)

## Acceptance Criteria (EARS Format)

- **AC-1 (Relative Luminance & Contrast Calculation)**:
  WHEN supplied with sRGB color channels or ASS color strings,
  THE system SHALL calculate standard WCAG 2.1 relative luminance and contrast ratio (e.g. 21.0:1 for white against black).

- **AC-2 (Legibility Threshold Evaluation)**:
  WHEN comparing subtitle text color against caption-band background luminance,
  THE system SHALL detect when contrast falls below the 4.5:1 threshold.

- **AC-3 (Plate Style Assignment)**:
  WHEN a caption event is specified with plate requirement (or when `plate_intervals` covers the event),
  THE system SHALL emit the dialogue line using a plate style (`border_style=3`, `outline=16.0`, `back_colour="&H80000000"`).

- **AC-4 (Pixel Separation on Bright Background)**:
  WHEN a plate style event is rendered through libass over a white background,
  THE plate region SHALL render darkened pixels behind the text, preventing text washout.
