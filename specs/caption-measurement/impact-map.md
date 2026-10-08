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

T2 maps were refreshed using actual Serena four definition/reference pairs at
e1f07fe (research.md). The mixed-type optional keyword expansion also impacts
test_chunking_refuses_input_it_cannot_split: its dynamically inferred dict[str,int]
cannot typecheck against the expanded API. Actual Serena definition/reference
pair at the dirty T2 baseline found no code callers (pytest collection remains
the caller). Spell out max_words/max_chars/max_ms=0 with the same three exception
type/message assertions; do not weaken the API, assertion or strict type gate.
Raw: C:/Users/Wareen/HawEditCaptionInvalidLimitsMap-20261008/serena-map.json.
tests/test_caption_context.py adds 29 real-renderer context regressions across
all six styles, both generic popup routes and direct/char-only consumers.
