# Tasks ledger — d7-latin-fallback-font
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-349; DEFAULT_CAPTION_FONT = "Vazirmatn" across captions.py defaults and fail-stop Latin glyph guard in assert_ass_fonts_cover_kurdish   (tests: test_default_caption_font_is_vazirmatn_and_covers_kurdish_and_latin, test_ass_font_binding_refuses_host_latin_fallback_for_mixed_text, test_a_theme_reaches_the_rendered_style_row, test_mobile_caption_layout_preserves_canonical_sorani)
- [x] T2  Pixel proof that Latin words render at matched height/weight inside mixed Sorani lines   (tests: test_mixed_sorani_and_latin_render_at_matched_height_and_weight)
- [x] T3  Re-render the four golden references with owner approval and pin updated SHA-256 digests   (tests: test_the_render_matches_the_golden_reference, test_simple_shaping_fails_the_golden_test, test_the_render_matches_viral_karaoke_golden, test_the_render_matches_hook_card_golden, test_the_render_matches_caption_over_fixture_video_golden, test_golden_files_match_their_pinned_digests)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
