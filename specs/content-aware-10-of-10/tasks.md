# Tasks ledger — content-aware-10-of-10
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Audio excitement/burst profiler (`audio_signals.py`) and teaser-overlap evaluator (D-356)   (tests: test_analyze_sentence_audio_detects_energy_peaks_and_rate, test_evaluate_teaser_overlap_computes_precision_recall_and_hits)
- [x] T2  Multimodal acoustic cue injection into Path A and C4 topic segmentation with viral 35-65s duration preference (D-356)   (tests: test_path_a_annotates_high_energy_and_burst_sentences, test_discover_topics_boosts_high_energy_viral_duration_candidates)
- [x] T3  Intra-shot rolling-window active-speaker switching and downscaled fast Haar detection in `OpenCvFaceTracker` (D-357)   (tests: test_opencv_face_tracker_switches_active_speaker_mid_wide_shot, test_downscaled_haar_preserves_full_source_coordinates)
- [x] T4  Non-face visual motion saliency / `BLURRED_FILL` framing and explicit `resolve_encoder` (`auto|h264_nvenc|libx264`) (D-357)   (tests: test_resolve_encoder_explicit_nvenc_fails_stop_and_auto_reports_choice, test_detect_motion_focus_points_tracks_non_face_action)
- [x] T5  Clip-only audio-grounded Sorani caption polisher with stutter deduplication and strict timestamp/edit-distance guards (D-358)   (tests: test_deduplicate_micro_stutters_removes_ctc_stutter_preserving_emphatic_repeats, test_polish_clip_sentences_preserves_timestamps_and_rejects_hallucinations)
- [x] T6  E3-safe dead-air tightening in `silence.py` decoupled from filler/restart excision (D-358)   (tests: test_dead_air_tightening_preserves_kurdish_repeats_and_clears_e3_edl)
- [x] T7  Wire acoustic discovery, NVENC/auto encoder, non-face `BLURRED_FILL`, clip caption polish, and `broadcast_scorecard` into `pipeline.py` and `measure.py` (D-359)   (tests: test_pipeline_wires_audio_signals_encoder_and_caption_polish, test_broadcast_scorecard_flags_double_cuts_and_passes_clean_reel)
- [x] T8  Real multi-genre production on `ai` (`RO1PmSoqmCM`) and `cooking` (`k_jxP903t5w`) with teaser-overlap report and visual inspection in `evidence/content-aware-10-of-10-2026-11-20.md`   (tests: test_broadcast_scorecard_flags_double_cuts_and_passes_clean_reel)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh on integration branch)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Multi-genre reels (`ai` + `cooking`) visually verified & scored in evidence/usable-rate.csv
