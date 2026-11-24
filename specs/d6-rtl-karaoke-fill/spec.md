# Spec — Right-to-left intra-word karaoke fill (D6 / d6-rtl-karaoke-fill)

EARS acceptance criteria. Each criterion names the automated test(s) that verify it in `tests/test_captions.py` (and updated existing callers/tests).

- **AC1** WHEN `build_ass` emits `CaptionStyle.WORD_HIGHLIGHT`, THE system SHALL emit a Layer 0 unbroken base event in the unspoken colour (`theme.secondary`) and per-word Layer 1 `\clip` animated highlight events in the spoken colour (`theme.primary`), with zero `\kf` override tags.
  `test_word_highlight_style_emits_rtl_clip_karaoke_without_kf`

- **AC2** WHEN two consecutive words in `WORD_HIGHLIGHT` are separated by a silence gap, THE Layer 1 highlight event for the later word SHALL start at that word's own `start_ms` so the sweep holds across the pause rather than drifting ahead of speech.
  `test_karaoke_timings_cover_the_silence_between_words` (in `tests/test_audit_regressions.py`)

- **AC3** WHEN a Sorani word is rendered in `WORD_HIGHLIGHT` and sampled at 25%, 50%, and 75% of its spoken duration, THE mean X coordinate of the highlighted (spoken-colour) pixels inside that word SHALL remain strictly to the right of the mean X coordinate of the unspoken pixels, and the highlighted left boundary SHALL advance leftward across the three samples.
  `test_word_highlight_sweeps_right_to_left_inside_each_sorani_word`

- **AC4** WHEN a mixed Sorani-and-Latin line is rendered in `WORD_HIGHLIGHT`, THE Sorani words SHALL sweep right-to-left internally while an embedded Latin word SHALL sweep left-to-right internally in its spoken turn without breaking RTL word order or cursive joining.
  `test_word_highlight_mixed_script_sweeps_each_word_in_its_script_direction`

- **AC5** WHEN `WORD_HIGHLIGHT` wraps across multiple lines (`\N`) or places captions in the top band (`face_intervals`), THE Layer 1 `\clip` coordinates SHALL match each word's rendered line and band without cross-line clipping or outline fringe.
  `test_word_highlight_multiline_and_top_band_clip_bounds`

- **AC6** WHEN `verify_caption_integrity(..., expected_text=...)` inspects a `WORD_HIGHLIGHT` ASS generated with Layer 0 and Layer 1 events, THE verifier SHALL confirm exact canonical surface text and unbroken Kurdish cursive joining.
  `test_word_highlight_clip_passes_caption_integrity`

- **AC7** WHEN `kurdish-caption-fixture.png` is rendered through production `subtitle_filter` at `t = 0.500 s`, THE render SHALL match the owner-approved updated golden reference and fail under `shaping=simple`.
  `test_the_render_matches_caption_over_fixture_video_golden`,
  `test_simple_shaping_fails_caption_over_fixture_video_golden`,
  `test_golden_files_match_their_pinned_digests`
