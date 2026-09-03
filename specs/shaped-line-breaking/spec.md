# Spec: Shaped-Width Line Breaking (Task T2.9)

## Acceptance Criteria (EARS Format)

- **AC-1 (Shaped Line Wrapping)**:
  WHEN candidate words are evaluated by `wrap_caption_lines` and `max_width_px` is specified,
  THE system SHALL measure the rendered ink width through libass at PlayRes and break lines
  such that line ink width does not exceed `max_width_px`.

- **AC-2 (Shaped Popup Event Chunking)**:
  WHEN candidate words are evaluated by `chunk_caption_events` and `max_width_px` is specified,
  THE system SHALL measure the rendered ink width through libass at PlayRes and close the event
  before rendered ink width exceeds `max_width_px`.

- **AC-3 (Single Oversized Word Invariant)**:
  WHEN a single word has a rendered ink width exceeding `max_width_px`,
  THE system SHALL assign that word to its own line or popup event without dropping, truncating,
  or breaking the word mid-shaping.

- **AC-4 (Pixel Overflow Prevention)**:
  WHEN a long-ligature Kurdish phrase that would overflow margin boundaries under character-count
  rules is processed with shaped-width breaking,
  THE system SHALL wrap it so that the rendered ink bounding box remains within the safe canvas margins.
