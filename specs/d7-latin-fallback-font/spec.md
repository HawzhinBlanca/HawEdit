# Spec — Latin fallback font in Sorani captions (D7 / d7-latin-fallback-font)

EARS acceptance criteria. Each criterion names the automated test(s) that verify it in `tests/test_captions.py`.

- **AC1** WHEN `build_ass` or any caption layout/measurement helper is called without an explicit `font_name`, THE system SHALL default to `DEFAULT_CAPTION_FONT` (`"Vazirmatn"`), which is bundled in `assets/fonts/Vazirmatn.ttf` (OFL-1.1).
  `test_default_caption_font_is_vazirmatn_and_covers_kurdish_and_latin`

- **AC2** WHEN a mixed Sorani-and-Latin sentence (e.g. `"OpusClip زۆر باشە."` or `"ئێمە لە 2026 OpusClip بەکاردەهێنین."`) is rendered with default settings, THE ratio of the Latin word's ink bounding height to the Sorani word's ink bounding height SHALL be within `[0.85, 1.15]` (eliminating the `~1.48x–1.51x` host fallback mismatch).
  `test_mixed_sorani_and_latin_render_at_matched_height_and_weight`

- **AC3** WHEN `assert_ass_fonts_cover_kurdish` inspects an ASS file whose Dialogue text contains ASCII Latin letters (`A–Z`, `a–z`) while binding to a directory font that lacks Latin glyphs (e.g. `NotoNaskhArabic-Regular.ttf`), THE system SHALL raise `FontCoverageError` rather than allowing silent host-font fallback.
  `test_ass_font_binding_refuses_host_latin_fallback_for_mixed_text`

- **AC4** WHEN `Vazirmatn` renders `GOLDEN_CAPTION_TEXT` through production `subtitle_filter`, THE `shaping=complex` render SHALL match the owner-approved updated goldens and `shaping=simple` SHALL fail `compare_golden_render`.
  `test_the_render_matches_the_golden_reference`,
  `test_simple_shaping_fails_the_golden_test`,
  `test_the_render_matches_viral_karaoke_golden`,
  `test_the_render_matches_hook_card_golden`,
  `test_the_render_matches_caption_over_fixture_video_golden`,
  `test_golden_files_match_their_pinned_digests`
