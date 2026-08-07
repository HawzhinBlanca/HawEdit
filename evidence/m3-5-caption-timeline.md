# M3.5 — captions were being scheduled on the wrong timeline

`src/hawedit/captions.py` · `src/hawedit/render.py` · `src/hawedit/pipeline.py` ·
`tests/test_caption_timing.py` (13 tests) · D-041

## The defect

`render.py`'s own docstring names this exact failure mode and then did not check for it:

> A burn-in has many silent failure modes — the wrong filter order, a font directory that
> resolves to nothing, **an ASS file libass parses but finds nothing to draw in** — and every
> one of them produces a valid, playable, caption-free clip.

`build_ass` wrote **source-absolute** timestamps. `render_clip` burns them into a stream ffmpeg
has already cut with `-ss clip.in_ms`, where t=0 is the start of the clip. The two timelines
were never the same one.

## Measured

A 1.6 s clip taken from source 2000 ms, whose sentence is spoken at source 2000–3600 ms —
the ordinary case for any clip from the middle of an episode:

```
ASS Dialogue line: Dialogue: 0,0:00:02.00,0:00:03.60,Kurdish,,0,0,0,,ڕۆژنامەوانی …
bytes differing between captioned and uncaptioned render: 0
captions drawn: False
```

**Zero bytes.** The clip is 1.6 s long; the caption was scheduled to appear at 2.0 s, past its
end. libass drew nothing, ffmpeg exited 0, and the output is a valid, playable MP4 with no
captions — Kurdish invariant #4, the whole §4.3 surface, absent with no error anywhere.

The worse the clip's offset, the more complete the failure. A clip at 84.6 s into an episode
would have had every caption scheduled a minute and a half past its own end.

## Why the existing test did not catch it

`tests/test_render.py` compares a captioned render against an uncaptioned one on decoded
pixels, which is precisely the right test. Its fixture cuts at 300 ms with words at 0–1600 —
the two timelines overlap by 1.3 s, enough to draw something, so the comparison passed. The
test measured the right thing on the one input where the bug is invisible.

`tests/test_caption_timing.py` now runs the same comparison on a clip that starts two seconds
in. Against the code as it stood, it fails at 0 bytes.

## The fix, in two places

1. **`build_ass(..., clip_in_ms, clip_duration_ms)`** subtracts the offset. The `\kf` karaoke
   spans are *durations* and were always correct; only the two absolute stamps on each
   `Dialogue` line ever needed it. A sentence starting before the clip or ending after it is
   refused — it is speech the clip does not contain.
2. **`assert_captions_within_clip` runs at the burn**, on whatever file arrives. A fix applied
   only where the file is written is not a fix (D-038): a hand-written ASS, a file from an
   older run, or the next caller who forgets would all reintroduce it. `render_clip` refuses
   an ASS with no `Dialogue` line, and one whose events all fall outside `[0, duration]`.

Partial overlap passes — something is on screen, so it is not the silent case.

## The committed artifact

`evidence/m2-4-rendered-clip.mp4` was rendered from the 300 ms fixture, so its captions are on
screen but run to the wrong end time by 300 ms. The clip is a demonstration of the RTL stack,
not client output, and its own evidence file records what it was for. It has not been
re-rendered, and this note is here so nobody later reads its timing as correct.
