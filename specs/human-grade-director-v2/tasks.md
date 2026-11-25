# Tasks ledger — human-grade-director-v2
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Snap `per_shot_boxes` `y_center_expr` and `sendcmd` `w/h` transitions `-2 ms` early matching `_interpolated()` (D-360)   (tests: test_crop_filter_per_shot_boxes_snaps_two_ms_early_matching_focus_x)
- [x] T2  Add transparent broadcast compressor + peak limiter to `SPEECH_CHAIN_FILTERS` and `two_pass_loudness` support in `render_clip()` (D-360)   (tests: test_speech_chain_linear_loudnorm_tames_high_crest_audio)
- [x] T3  Implement acoustic-driven `content_aware_push_schedule()` scaling push depth by `SentenceAudioMetrics` excitement and `payoff_at_ms` (D-360)   (tests: test_content_aware_push_schedule_boosts_excited_and_payoff_spans)
- [x] T4  Add edge-danger fast smooth-follow (`edge_guard_px`, `edge_settle_ms`) to `stabilize()` preventing leaning-speaker edge clipping (D-361)   (tests: test_stabilize_edge_guard_follows_leaning_speaker_without_dead_zone_jitter)
- [x] T5  Add per-shot zero-face cutaway motion-saliency framing in `OpenCvFaceTracker.track()` (D-361)   (tests: test_face_tracker_frames_zero_face_cutaway_shot_via_motion_saliency)
- [x] T6  Add face-aware 30-char 2-line hook card placement, zero-orphan chunk merging, and acoustic-energy karaoke micro-pop in `build_ass()` preserving `GOLDEN_HOOK_CARD` (D-362)   (tests: test_build_ass_face_aware_hook_card_orphan_merge_and_excited_pop)
- [x] T7  Add deterministic Sorani digit normalization (`normalize_sorani_digits`) in `caption_polish.py` preserving exact CTC timestamps (D-362)   (tests: test_normalize_sorani_digits_preserves_timestamps_and_rtl_order)
- [x] T8  Wire director v2 upgrades end-to-end in `pipeline.py` and verify real multi-genre `ai` + `cooking-30m` reels in `evidence/human-grade-director-v2-2026-11-21.md` (D-363)   (tests: test_pipeline_wires_director_v2_audio_camera_and_captions)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh on integration branch)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Multi-genre reels (`ai` + `cooking`) visually verified with 0 double cuts, linear -14 LUFS, non-overlapping hook cards, and zero edge clips
