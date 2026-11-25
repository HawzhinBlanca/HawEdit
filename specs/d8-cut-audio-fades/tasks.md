# Tasks ledger — d8-cut-audio-fades
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-351; shared audio_cut_fade_filters helper wired into silence_trim_filter and assembled_splice_filter   (tests: test_silence_trim_filter_generates_valid_ffmpeg_filtergraph, test_assembled_splice_filter_constructs_trim_and_concat, test_cut_audio_fade_clamps_safely_on_short_segments)
- [x] T2  Wire cut fades into measure_audio_loudness, render_clip, and render_assembled_reel with PCM discontinuity & loudness proofs   (tests: test_cut_audio_fades_eliminate_splice_boundary_discontinuity_without_av_drift, test_render_clip_cut_fades_preserve_two_pass_loudness_and_span)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
