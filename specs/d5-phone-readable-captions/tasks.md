# Tasks ledger — d5-phone-readable-captions
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-350; phone-readable VIRAL_FONT_SIZE (128), VIRAL_THEME (outline 6, margin_v 450), POPUP_MAX_CHARS (20), and assembly/pipeline wiring   (tests: test_viral_captions_reach_phone_readable_ink_size_outline_and_safe_zone, test_assembled_reel_and_pipeline_emit_phone_readable_popup_captions, test_the_viral_theme_clears_the_platform_caption_bar, test_the_viral_font_size_is_set_from_measured_ink_not_from_the_point_number)
- [x] T2  ProtectedRegionKind.TABLE_OBJECT, temporal ProtectedContentRegion bounds, and plan_caption_layout protection of tables/teaser label/faces   (tests: test_caption_layout_protects_table_objects_teaser_label_and_time_scoped_faces)
- [x] T3  Frame-level protected-region probe + pipeline wiring + pixel proof avoiding teaser pill and table regions   (tests: test_captions_avoid_detected_teaser_pill_and_table_regions_in_rendered_frames)
- [x] T4  Re-render owner-approved VIRAL_THEME goldens and update pinned SHA-256 digests   (tests: test_the_render_matches_viral_karaoke_golden, test_the_render_matches_hook_card_golden, test_the_render_matches_caption_over_fixture_video_golden, test_golden_files_match_their_pinned_digests)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
