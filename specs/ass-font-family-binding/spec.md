# Specification — ASS font-family binding

Parent: true-10/10 AC-2 and BLUEPRINT §4.3.4.

1. WHEN a caption burn uses an ASS style, THE renderer SHALL require that style's declared font
   family to match a name-table family of a regular font inside the supplied fonts directory.
2. WHEN the matching font lacks any required Kurdish glyph, THE renderer SHALL refuse even if an
   unrelated covering font is present beside it.
3. WHEN a Dialogue event names an undefined style, THE renderer SHALL refuse before ffmpeg.
4. WHEN a Dialogue payload contains an inline `\\fn` family override, THE renderer SHALL refuse
   before ffmpeg rather than relying on host fallback or incompletely reproducing libass resolution.
5. WHEN the shipped ASS and shipped font are used, THE guard SHALL accept the exact shipped font.
6. WHEN the ASS style format is malformed, ambiguous, or unreadable, THE renderer SHALL refuse with
   a bounded domain error before encoding.

Evidence tests:

- shipped family positive control;
- requested non-covering family beside an unrelated covering font;
- missing family, undefined style, malformed style format, and inline override refusals; and
- `render_clip` wiring regression proving the ASS-aware guard is the production call.
