# Impact map
- v8.delivery_pack._sentences_for_v8_srt and write_client_delivery_pack serve both branches of compile_v8_episode and the single-clip CLI. build_srt enforces time bounds and preserves original display text.
- DefaultV8SubtitleRenderer.render_subtitles already calls chunk_viral_kurdish_words with DirectorScript.caption_beats. Sidecar delivery should use identical groups.
- studio_ui.options, validOptions and applyOptions govern speaker identity in the job request and restored form. web._build_v8_episode_config propagates them to compile_v8_episode.
- v8.tiktok_subs renders CTA through Skia and libass. Both engines require layout verification.
