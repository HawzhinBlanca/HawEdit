# Actual Impact Map

See the ten-pair raw Serena record/hash in research.md; not a provisional grep map.

- measure_rendered_caption_width: wrap_caption_lines, chunk_caption_events,
  compute_rtl_word_positions (full/prefix/word) and its positive/cache test.
- wrap_caption_lines: build_ass, delivery.build_srt and caption tests. SRT uses
  char-only wrapping; preserve it without requiring rendering tools.
- chunk_caption_events: six build_ass style branches and popup/word/time/gap/
  order/long-word/pixel-limit tests. Forward selected rendering context in each.
- compute_rtl_word_positions: two build_ass branches and RTL order tests; keep
  existing positional arguments, add optional keyword-only canvas height.
- build_ass: pipeline/review/rendered-caption callers and all caption goldens.
  Defaults/char-only text and timing remain unchanged; pixel checks use actual
  selected font/canvas instead of the helper's unrelated default.
- _default_fonts_dir/find_ffmpeg/subtitle_filter: reuse actual local resolution
  and complex-shaping filter. No font/encoder fallback or alternate renderer.

Whole tests/test_captions.py and tests/test_delivery.py plus new named native
regressions, strict static checks and exact frozen full gate are required.
