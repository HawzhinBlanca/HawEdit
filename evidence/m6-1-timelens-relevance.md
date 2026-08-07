# M6.1 — TimeLens2 intervals: the relevance the invariant never checked

`src/hawedit/timelens.py` · `src/hawedit/boundary.py` ·
`tests/test_timelens.py` (23 tests) · D-038

## The gap

§3 Stage 5 writes the out-point as `final_out = latest of { anchor_out + 200 ms tail, natural
silence, following shot_cut within 400 ms, speaker_turn_end, timelens_interval_end }`, and
opens the same section with a warning:

> **TimeLens2-4B returns intervals containing relevant visual evidence. It does not produce
> editorial cuts and cannot locate a speech-only idea without transcript timing.**

`boundary.py` honoured the second sentence from the start — the interval is one of five soft
signals and may only extend outward, so a visual model can never truncate a Kurdish sentence.
It could not honour the first, because what reached fusion was `timelens_interval_end_ms`: a
bare integer. A number cannot be asked which interval produced it.

"Latest" then reads, to any implementer, as `max()` over what the model returned for the
episode.

## The measurement

```
anchored sentence      : 10000..14000 ms  (4.0 s)
naive max(end)         : final_out = 305000 ms -> clip is 295.0 s
relevance-first        : final_out = 16000 ms -> clip is 6.0 s
invariant #2 satisfied by the naive answer: True
```

Two intervals from one episode — a gesture at 12 s and applause at 5:02. Under `max()`, a clip
anchored on a four-second Kurdish sentence ends at 5 minutes 5 seconds. **Kurdish invariant #2
passes**: `final_out >= anchor_out` is satisfied, generously. The arithmetic is right, the
render gate is green, and the clip runs from one sentence into five minutes of unrelated
footage.

The invariant constrains the *direction* a soft signal may move a boundary. Nothing
constrained *relevance*.

## The fix, and where it had to go

`interval_end_for_fusion` filters by overlap with the anchored sentence before taking the
latest end — §3's own words, since the model reports evidence *contained in* an interval and
an interval sharing no footage with the idea is evidence about a different moment.

That alone would not have been enough. This codebase has twice fixed a defect at one call site
and left its sibling untouched, so the check also lives at the point of consumption:
`BoundaryInputs` now carries `timelens_interval_start_ms`, and `fuse_boundary` refuses an end
without a start, a start without an end, a backwards interval, and an interval that does not
overlap the anchor. A caller building inputs by hand can no longer reintroduce this.

## What this does not cover

- **No magnitude cap.** An interval overlapping the anchor by one millisecond and ending far
  later is still eligible. §3 caps shot cuts at 400 ms and says nothing about TimeLens2, and
  inventing a threshold would be redesigning a frozen section. Whether one is needed is a
  §8.2 question against the labelled set (M7.2, blocked on annotators).
- **The model has not run.** `MCG-NJU/TimeLens2-4B` is `BLOCKED.md` #2 (GPU) and #6 (weights).
  These are the types it will return; no interval in this repository came from it.
