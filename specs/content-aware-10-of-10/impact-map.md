# Impact Map — Content-Aware 10/10 Short-From-Long Program

## Lane A (`D-356` — Multimodal Acoustic Discovery)
- **New:** `src/hawedit/audio_signals.py` (`SentenceAudioMetrics`, `analyze_sentence_audio`, `evaluate_teaser_overlap`, `TeaserOverlapReport`).
- **Modified:**
  - `src/hawedit/path_a.py` (`discover_verbal`, `PathADiscovery.discover`, `_numbered_sentences`): optional `audio_metrics: Sequence[SentenceAudioMetrics] | None = None` (default `None` preserves all existing callers).
  - `src/hawedit/topic_segmenter.py` (`discover_topics`): optional `audio_metrics: Sequence[SentenceAudioMetrics] | None = None` + viral duration preference curve (`35–65 s` peak, default backward-compatible).
- **Callers checked:** `src/hawedit/pipeline.py`, `tests/test_path_a.py`, `tests/test_topic_segmenter.py`, `tests/test_c1_sentence_number_discovery.py`, `tests/test_c4_topic_segmentation_candidates.py`.

## Lane B (`D-357` — ReframeAnything & Fast GPU Encode)
- **Modified:**
  - `src/hawedit/reframe.py` (`OpenCvFaceTracker.track`, new helpers `_intra_shot_speaker_switch`, `detect_motion_focus_points`): adds intra-shot rolling-window active-speaker switching (`>= 5 s` wide shots, `>= 2.0 s` dwell), downscaled Haar (`<= 960 px` width rescaled cleanly), and zero-face motion-saliency helper. Existing single-face and 2-frame dropout tests unaffected.
  - `src/hawedit/render.py` (`resolve_encoder`): explicit `auto | h264_nvenc | libx264` resolver (fail-stop when `h264_nvenc` explicitly requested and unavailable; explicit provenance when `auto` picks `NVENC` or `X264`).
- **Callers checked:** `src/hawedit/pipeline.py`, `tests/test_reframe.py`, `tests/test_render.py`, `tests/test_broadcast_studio.py`.

## Lane C (`D-358` — Caption Polish & E3-Safe Dead-Air Tightening)
- **New:** `src/hawedit/caption_polish.py` (`CaptionPolishResult`, `deduplicate_micro_stutters`, `polish_clip_sentences`).
- **Modified:**
  - `src/hawedit/silence.py` (`plan_silence_tightening`, `_identify_filler_words`): only runs `detect_restarts=True` when `filler_tokens is not None` (explicit `--excise-fillers`); clamps pure silence cuts so both adjacent word boundaries keep `[30, 200] ms` padding satisfying E3 `validate_edl`.
- **Callers checked:** `src/hawedit/pipeline.py`, `tests/test_silence.py`, `tests/test_edit_plan.py`, `tests/test_e3_hard_edit_rules.py`.

## Lane D (`D-359` — Pipeline Wiring & Broadcast Scorecard)
- **Modified:**
  - `src/hawedit/pipeline.py`: wires `analyze_sentence_audio` into Stage 3, `--encoder` (`auto` default for desktop/episode runs or explicit flag) into `_render_episode_single_clip` and single-clip render, zero-face `Reframe.BLURRED_FILL` fallback when non-face action occurs, and `--polish-captions` on chosen clips only.
  - `src/hawedit/measure.py`: adds `BroadcastScorecard` / `evaluate_broadcast_scorecard` into `MeasuredMedia` / `.measured.json`.
- **Callers checked:** `tests/test_pipeline.py`, `tests/test_measure.py`, `tests/test_a2_one_command_reels.py`, `tests/test_a4_studio_pipeline_runner.py`, `tests/test_claims.py`.
