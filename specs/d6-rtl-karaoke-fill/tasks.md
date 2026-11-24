# Tasks ledger — d6-rtl-karaoke-fill
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-348; single-pass rgb24 word-box probe (_measure_word_boxes) and two-layer animated \clip sweep in build_ass   (tests: test_word_highlight_style_emits_rtl_clip_karaoke_without_kf, test_karaoke_timings_cover_the_silence_between_words, test_word_highlight_clip_passes_caption_integrity)
- [x] T2  Pixel proofs of RTL intra-word sweep, mixed-script direction, and multi-line/top-band bounds   (tests: test_word_highlight_sweeps_right_to_left_inside_each_sorani_word, test_word_highlight_mixed_script_sweeps_each_word_in_its_script_direction, test_word_highlight_multiline_and_top_band_clip_bounds)
- [x] T3  Update existing \kf/event-count caller tests and re-render owner-approved kurdish-caption-fixture.png golden   (tests: test_ass_pixel_wrapping_uses_selected_font_size, test_ass_generic_popup_width_uses_selected_font_size, test_the_revised_ass_actually_changes_style, test_the_render_matches_caption_over_fixture_video_golden, test_simple_shaping_fails_caption_over_fixture_video_golden, test_golden_files_match_their_pinned_digests)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
