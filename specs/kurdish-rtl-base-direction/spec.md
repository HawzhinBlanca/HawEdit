# Spec — Kurdish caption base direction

EARS criteria. Each names the test that will be cited in `tasks.md`. All tests live in
`tests/test_captions.py`.

- **AC1** WHEN `build_ass` or the width probe emits a Style line, THE system SHALL set its
  `Encoding` field to `-1`.
  `test_every_style_line_requests_auto_base_direction`
- **AC2** WHEN any caption Dialogue line is emitted, THE system SHALL begin its text with
  U+200F so a line that starts with a Latin word or a digit is still laid out right-to-left.
  `test_every_dialogue_text_starts_with_a_right_to_left_mark`
- **AC3** WHEN caption text is verified or measured, THE readers SHALL ignore the leading
  U+200F and report the same words as before.
  `test_caption_readers_ignore_the_leading_right_to_left_mark`
- **AC4** WHEN a Sorani sentence is rendered in `WORD_HIGHLIGHT`, THE first spoken word's
  pixels SHALL lie to the right of the last spoken word's pixels.
  `test_word_highlight_renders_the_first_word_rightmost`
- **AC5** WHEN a sentence ends with a full stop, THE full stop SHALL be drawn at the left end
  of the line in `LINE`, `VIRAL_POPUP` and `RTL_WORD_HIGHLIGHT`.
  `test_sentence_final_full_stop_renders_at_the_left_end`
- **AC6** WHEN a Sorani sentence starts with a Latin word, THE Latin word SHALL be drawn at
  the right end of the line.
  `test_a_line_starting_with_a_latin_word_is_still_right_to_left`
- **AC7** WHEN the renderer's libass does not honour the base direction, THE golden comparison
  SHALL fail.
  `test_the_render_matches_the_golden_reference`,
  `test_the_render_matches_viral_karaoke_golden`,
  `test_the_render_matches_hook_card_golden`,
  `test_the_render_matches_caption_over_fixture_video_golden`,
  `test_golden_files_match_their_pinned_digests`
