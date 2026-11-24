# Sorani hook, caption and review acceptance

- WHEN an automatic headline proposes an unfinished phrase, THE compiler SHALL use a complete qualifying source clause or reject the candidate before export. Evidence: test_local_ranker_can_only_select_measured_source_excerpts.
- WHEN a short caption can borrow time without crossing the clip boundary or group limit, THE renderer and delivery pack SHALL extend or combine the display while keeping source word highlight timing. Evidence: test_paced_captions_keep_highlights_and_respect_speech_and_clip_boundaries, test_unpunctuated_reel_has_timed_phrase_sidecar and test_sidecar_rejects_cues_past_rendered_end.
- WHEN a reviewer evaluates finished renders, THE blind page SHALL hide algorithmic rank and export decisions bound to video SHA-256. Evidence: test_write_client_review_html_self_contained_rtl_badges_and_downloads and the private Chromium ballot exercise.
