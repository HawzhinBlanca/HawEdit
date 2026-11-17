# Plan — Kurdish caption base direction

Read `research.md` first (one page). Frames: `captures/grid_*.png`.

## Approach

Tell libass the truth about the text: it is right-to-left.

1. **Style `Encoding = -1`** in the three Style writers. This alone corrects word order in
   `WORD_HIGHLIGHT` and full-stop placement in every style.
2. **U+200F as the first character of every Dialogue text.** Needed because `-1` auto-detects
   from the first strong character, so a line starting with a Latin word is still laid out
   left-to-right. With both, that case renders correctly.
3. **Readers strip one leading U+200F** so verification and measurement see the same words.

No new dependency. No new caption style. `RTL_WORD_HIGHLIGHT`'s position maths stays as it is.

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/captions.py` | `style_row` (`:228`), `plate_style_row` (`:253`) | final field `1` → `-1` |
| `src/hawedit/captions.py` | `measure_rendered_caption_width` (`:953`) | probe Style `1` → `-1`; probe text gets the same U+200F |
| `src/hawedit/captions.py` | Dialogue writers (`:1845, 1855, 1886, 1906, 1918`) | text prefixed with U+200F through one shared constant |
| `src/hawedit/captions.py` | `verify_caption_text` (`:2421`), `verify_caption_glyphs` (`:2520`), `verify_caption_geometry` (`:2566`) | ignore one leading U+200F |
| `src/hawedit/measure.py`, `src/hawedit/sanity_gate.py` | `_parse_ass_dialogue_cues`, `check_subtitles` | no change expected (they read timings); covered by AC3 |
| `tests/test_captions.py` | `:2193` literal, digest pins `:543-551` | follow the new bytes |
| `tests/golden/*.png` (4 files) | — | re-rendered, **only with your approval below** |
| `DECISIONS.md` | new `D-334` | supersedes D-269 clause 1 (keeping the reversed karaoke byte-identical) |

## Tests (one per criterion in `spec.md`)

AC1–AC3 are text assertions. AC4–AC6 are pixel assertions on a rendered frame, using colour
or a with/without difference, so they do not depend on glyph shapes:

- AC4: at a time inside the second word, the already-highlighted colour's centre is right of
  the not-yet-highlighted colour's centre.
- AC5: render with and without the final `.`; the differing pixels sit left of the rest.
- AC6: the Latin word's pixels (rendered alone to find them) sit at the right end.

AC7 is the existing four golden comparisons against re-rendered references.

## Divergence and ADR

Implements §4.3; no divergence from `BLUEPRINT.md`. D-269 clause 1 is reversed openly in D-334,
with the before/after frames as its measurement.

## Risks

- **CI's Linux ffmpeg is unverified** for `Encoding = -1`. If it differs, AC4–AC7 fail there
  and the fix is not done. No fallback is planned in advance.
- **Goldens change.** Anti-cheat forbids editing a golden to match buggy output. The committed
  references *are* the buggy output (`captures/grid_line.png`, `grid_word_highlight.png`), so
  this plan replaces them once, in one commit, under `.codystem-allow-self-edit`, with the old
  and new frames kept in `captures/`.
- **Single-writer rule.** This checkout was created by another agent last night. I assume no
  other agent is writing to it; say so if one is.
- Not covered: Latin words falling back to a larger bold font; changing the podcast default
  style; any ASR or selection work.

## Owner actions folded into this approval

1. **Replace the four golden PNGs** as described above.
2. **Remove from the checkout** what the desktop app copied in when this session moved here:
   the folder `hawedit/` (a duplicate clone, 2,169 files) and three files at the root
   (`HawEdit-reality-check-2026-11-17.md`, `HawEdit-10x-kurdish-design-2026-11-17.md`,
   `HawEdit-caption-rtl-evidence.png`). Both reports are already in the vault under
   `Research/`. They make the tree dirty, which the reproducible-build tests refuse.

Approved-by: Hawa — in chat, 2026-11-17, "Approve plan" (covers the golden replacement and the checkout cleanup above; recorded by Claude Code on the owner's instruction)

## Learned while implementing (2026-11-17)

- **Order.** Encoding -1 changes the rendered pixels, so the goldens had to move in the same
  change as T1, not after T3. The four ledger rows stay as written; they can only flip together.
- **One reader the impact map missed.** `sanity_gate.check_subtitles` counts characters per
  line with its own tag pattern; the mark would have added one. Its pattern now drops U+200F.
- **Tests moved to the new bytes** (all Style ending `1` → `-1` or the Dialogue prefix):
  `test_captions.py` — `test_the_default_theme_is_byte_identical_to_what_shipped_before_it_existed`,
  `test_a_custom_theme_round_trips_every_field`,
  `test_build_ass_emits_kurdish_top_for_overlapping_events`,
  `test_build_ass_with_speaker_metadata_and_turns`,
  `test_mobile_caption_layout_preserves_canonical_sorani`,
  `test_a_theme_reaches_the_rendered_style_row` (negative assertion kept meaningful);
  `test_broadcast_studio.py` — `test_broadcast_subtitles_respect_vertical_margin_safe_zone`,
  `test_build_ass_margin_v_override`, `test_build_ass_broadcast_studio_formatting`.
- **The edit sentinel is a tracked file.** `.codystem-allow-self-edit` is committed (since
  `a530ab2`), so the enforcement surface is permanently unlocked in this repo. I removed it by
  mistake after the golden copy and restored it from HEAD; it is unchanged in this branch.
- **Blocked on the owner: the VEX source binding.** `security/wsl-asr-vex.json` pins
  `package_digest(src/hawedit)`. Any source change moves it, so
  `tests/test_vex.py::test_checked_in_policy_binds_current_lock_and_assets_and_closes_report`
  fails (`18fe2dd7…` pinned, `2484425d…` now). D-333's addenda show the owner approving each
  re-pin. I did not move it. Until it is re-pinned the gate cannot be green and no row can flip.
- **Not run:** a baseline gate on the untouched tree. I started one and stopped it at about 9%
  after 12 minutes, because it would have delayed every edit by more than an hour.
- **Still wrong after this change:** inside each `WORD_HIGHLIGHT` word the highlight colour
  fills from the left edge, i.e. from the end of the Sorani word (seen in the new fixture
  golden). Word order and punctuation are fixed; the fill direction is not. Recorded in D-334.
