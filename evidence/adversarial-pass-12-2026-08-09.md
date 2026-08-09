# Adversarial pass #12 — captions timed to the clip

> Run 2026-08-09 on hawapc01 against `d1676a5`.
> Target: **M3.5**, DONE — never attacked, and its own cell calls its origin *"the most serious
> defect found so far"*.

`build_ass` used to write source-absolute timestamps into a stream ffmpeg had already cut at
`clip.in_ms`. Measured then: **0 bytes** differed between a captioned and an uncaptioned render of a
1.6 s clip taken from source 2000 ms — a valid, playable, entirely caption-free MP4, with Kurdish
invariant #4 absent from every clip not starting near zero.

## Every mechanism held

```
CAUGHT  the ASS carries source-absolute timestamps again (the defect)
CAUGHT  a sentence starting before the clip is captioned anyway
CAUGHT  a sentence running past the end of the clip is captioned anyway
CAUGHT  an ASS with no Dialogue line at all is accepted
CAUGHT  an ASS whose captions all fall outside the clip is accepted
CAUGHT  full containment required instead of partial overlap
CAUGHT  the burn no longer checks the file it is handed
CAUGHT  libass wraps the captions instead of our own line breaks

8/8
```

Five tests catch the headline regression, and one of them is a pixel test — so the row's claim that
*"the existing pixel test is the right test"* is supported.

## Where they are proved is the gap

Removing the shift and running only the files that drive the real renderer:

```
tests/test_render.py + tests/test_pipeline.py     0 failures, exit 0
```

Every catcher lives in `tests/test_caption_timing.py`, whose pixel proof builds the ffmpeg command by
hand. `render_clip` — the function the product calls — and `run_pipeline` both stayed green.

This is not a defect in those tests. `test_render.py` hands `render_clip` an ASS built by
`build_ass((_sentence(),))` with no offset, and `_sentence()` is **0..1600 in clip time** — its
docstring says "whose word timings sit inside the clip's own window". A renderer test *should* be
handed an already-clip-relative file. The effect is that the composition never reaches the product's
encoder:

```
§4.2 source-time sentences -> build_ass(clip_in_ms=clip.in_ms) -> render_clip -> pixels
                                                                  ^ never assembled in one test
```

And `run_pipeline`'s fixture clip starts at ~100 ms, where an unshifted caption still overlaps the
window and libass draws something regardless.

M3.5's own cell describes exactly this trap one level down: *"its fixture cuts at 300 ms with words
at 0–1600, the one input where the bug is invisible."*

## What was added

One test through `render_clip` at 2000 ms, decoded against an uncaptioned render of the same span,
and a control that the **unshifted** file is refused at the burn rather than encoded bare.

2000 ms is derived: `_sentence()` is 1600 ms long, so an unshifted caption falls entirely outside a
clip starting at 2000 and `assert_captions_within_clip` can refuse it. At 500 ms — the offset this
file's existing clip uses — the same mistake still overlaps and draws.

```
after: removing the shift fails
  tests/test_render.py::test_the_composed_path_burns_captions_into_a_clip_from_mid_media
```

8/8 before and after; the count did not change because nothing was broken. What changed is which
function the proof runs through.

Gate: `VERIFY OK — 1288 passed, 0 skipped`.
