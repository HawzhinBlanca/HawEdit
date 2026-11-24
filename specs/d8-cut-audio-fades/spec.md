# Spec — ~30 ms audio fades at cuts (D8 / d8-cut-audio-fades)

EARS acceptance criteria. Each criterion names its automated test(s) in `tests/test_silence.py`, `tests/test_assembly.py`, and `tests/test_render.py`.

- **AC1** WHEN `silence_trim_filter` or `assembled_splice_filter` splices two or more intervals, THE shared fade helper SHALL emit `30 ms` `qsin` `afade` out/in filters (clamped to half-segment duration for segments `< 60 ms`) at every internal cut boundary without altering segment length.
  `test_silence_trim_filter_generates_valid_ffmpeg_filtergraph`,
  `test_assembled_splice_filter_constructs_trim_and_concat`,
  `test_cut_audio_fade_clamps_safely_on_short_segments`

- **AC2** WHEN two non-silent audio segments are spliced via `silence_trim_filter` or `assembled_splice_filter` through `ffmpeg`, THE total audio duration SHALL remain identical (`<= 1 ms` PCM delta, passing `assert_encoded_span`), AND the peak sample amplitude inside `±1 ms` of the cut SHALL drop by at least `10×` compared to an unfaded cut.
  `test_cut_audio_fades_eliminate_splice_boundary_discontinuity_without_av_drift`

- **AC3** WHEN `render_clip` encodes a single-span or multi-span clip with two-pass linear `loudnorm`, THE Pass 1 measurement (`measure_audio_loudness`) and Pass 2 encode (`render_clip`) SHALL apply matching `30 ms` boundary fades (including clip start/end edges in `render_clip`) while keeping `loudness_pass2` compliant with EBU R128 targets.
  `test_render_clip_cut_fades_preserve_two_pass_loudness_and_span`
