# Tasks ledger — kurdish-rtl-base-direction
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [ ] T1  ADR D-334; Style Encoding -1 in the three Style writers   (tests: test_every_style_line_requests_auto_base_direction)
- [ ] T2  Leading U+200F on every Dialogue text; readers ignore it   (tests: test_every_dialogue_text_starts_with_a_right_to_left_mark, test_caption_readers_ignore_the_leading_right_to_left_mark)
- [ ] T3  Pixel proofs of reading order   (tests: test_word_highlight_renders_the_first_word_rightmost, test_sentence_final_full_stop_renders_at_the_left_end, test_a_line_starting_with_a_latin_word_is_still_right_to_left)
- [ ] T4  Re-render the four goldens and their digests, owner-approved   (tests: test_the_render_matches_the_golden_reference, test_the_render_matches_viral_karaoke_golden, test_the_render_matches_hook_card_golden, test_the_render_matches_caption_over_fixture_video_golden, test_golden_files_match_their_pinned_digests)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
