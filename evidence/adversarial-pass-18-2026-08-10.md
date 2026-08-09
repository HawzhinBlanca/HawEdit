# Adversarial pass 18: Kurdish font coverage reached neither the alphabet nor the burn

Date: 2026-08-10. Readiness decision: D-163. Upstream decision: D-133.

## Reproduced defect

`normalize_sorani("كوردي")` emits `کوردی`: Kurdish keheh U+06A9 and Farsi yeh U+06CC. Neither
was in `KURDISH_REQUIRED_GLYPHS`, although both occur in `GOLDEN_CAPTION_TEXT`.

The upstream pass subset the shipped Noto Naskh Arabic font to remove only U+06A9 while retaining
Arabic kaf U+0643 and 1,122 other codepoints. The old coverage check accepted it. Rendering the
golden caption through libass changed 15,999 subpixels and split `کوردی` between a detached fallback
glyph and the remaining run; the frame gained ink, demonstrating why a generic "text exists" check
cannot detect this failure.

## Production boundary

The original `assert_font_covers_kurdish` was called only by tests. Installed rendering resolves a
different `fonts_dir`, and `render_clip` never inspected it. The directory-level guard now searches
the exact directory used by libass and requires at least one font covering the complete frozen set.
Render converts `FontCoverageError` to its domain `RenderError`, preserving structured pipeline
reporting.

## Discriminating controls

- the requirement is derived from current normalizer output and explicitly pins `ک` and `ی`;
- the packaged font directory succeeds;
- empty and valid-but-noncovering directories fail with the missing glyph; and
- the real burn path refuses a noncovering directory without publishing output.

Focused verification and the full canonical/exact-SHA gates are recorded after this integration,
not inherited from the upstream measurement.
