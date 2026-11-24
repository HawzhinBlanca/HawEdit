# Spec — Phone-readable captions off faces, tables, and burned-in teaser label (D5 / d5-phone-readable-captions)

EARS acceptance criteria. Each criterion names its automated test(s) in `tests/test_captions.py` or `tests/test_caption_layout.py`.

- **AC1** WHEN `VIRAL_THEME` and `VIRAL_FONT_SIZE` render a 2–3-word Sorani caption on a `1080x1920` frame, THE rendered ink bounding height SHALL be at least `68 px` (about twice the `35 px` ink height of `64 pt` `REPORT_THEME`), the outline SHALL be `>= 6.0 px`, every popup SHALL stay within `<= 3` words and `<= 20` characters, and the baseline SHALL sit in the lower-middle safe zone (`margin_v >= 440 px`, clearing bottom UI chrome).
  `test_viral_captions_reach_phone_readable_ink_size_outline_and_safe_zone`

- **AC2** WHEN `render_assembled_reel` or `pipeline.py` builds ASS subtitles for social/podcast reels, THE system SHALL apply `VIRAL_THEME`, `VIRAL_FONT_SIZE`, and `POPUP_MAX_WORDS` (`2–3` words) rather than `64 pt` full-sentence `REPORT_THEME`.
  `test_assembled_reel_and_pipeline_emit_phone_readable_popup_captions`

- **AC3** WHEN `ProtectedContentRegion` carries `ProtectedRegionKind.TABLE_OBJECT`, `SOURCE_ON_SCREEN_TEXT` (e.g. a burned-in `"لەم پۆدکاستەدا:"` teaser pill), or `SPEAKER_FACE` intersecting the lower-middle caption band during a cue's time window, THE `plan_caption_layout` planner SHALL relocate only the intersecting cue(s) to `TOP` or `MID_UPPER` without altering canonical Kurdish speech text.
  `test_caption_layout_protects_table_objects_teaser_label_and_time_scoped_faces`

- **AC4** WHEN a rendered 9:16 video clip contains a tracked face, table-prop region, or persistent lower burned-in teaser label intersecting the lower caption band, THE ASS passed to `render_clip` SHALL relocate overlapping caption events out of the bottom band so rendered caption ink does not cover those protected regions.
  `test_captions_avoid_detected_teaser_pill_and_table_regions_in_rendered_frames`

- **AC5** WHEN `kurdish-viral-karaoke.png`, `kurdish-hook-card.png`, and `kurdish-caption-fixture.png` are rendered after owner approval, THE renders SHALL match the updated goldens and fail `shaping=simple`.
  `test_the_render_matches_viral_karaoke_golden`,
  `test_the_render_matches_hook_card_golden`,
  `test_the_render_matches_caption_over_fixture_video_golden`,
  `test_golden_files_match_their_pinned_digests`
