# Impact map
- v8.delivery_pack._sentences_for_v8_srt and write_client_delivery_pack serve both branches of compile_v8_episode and the single-clip CLI. build_srt enforces time bounds and preserves original display text.
- DefaultV8SubtitleRenderer.render_subtitles already calls chunk_viral_kurdish_words with DirectorScript.caption_beats. Sidecar delivery should use identical groups.
- studio_ui.options, validOptions and applyOptions govern speaker identity in the job request and restored form. web._build_v8_episode_config propagates them to compile_v8_episode.
- v8.tiktok_subs renders CTA through Skia and libass. Both engines require layout verification.

## 2026-11-25 native-review qualification

The owner asked to fix unfinished hooks and fast captions and validate three unseen complete Sorani episodes. Source review maps `compile_v8_clip` to `DefaultV8SubtitleRenderer`, both subtitle renderers, and the delivery pack. The shared pacing pass preserves the cut clock and speech highlights while merging nearby short groups or extending their display within the clip. The final automated headline uses complete measured source clauses when available. The pack reads the final rendered headline. Explicitly supplied director scripts retain their authored hooks.

`write_blind_review` is called by the client gallery and by the opt-in cross-episode review. Reviewer codes, pace ratings and posting decisions supplement the existing MP4-bound ballot. Private rights and editorial acceptability are distinct. No benchmark assets should be used for external publishing without permission.

## 2026-11-25 raw benchmark follow-up

A locally generated title that has no qualifying match may use an eligible source phrase. Filler tails stay ineligible. `compile_v8_clip` reports a missing title as a reel-quality rejection before it encodes. The existing reserve path in `compile_v8_episode` advances automatically, and explicit ranges continue to fail on quality errors.
