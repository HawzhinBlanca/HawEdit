# The frame-count guard graded its own parity step and refused a good extraction

> Measured 2026-08-09 on hawapc01 against `7601873`.
> Source: `ZAR38MinTest.mp4` — 640×360 h264, 25 fps, **2313.8 s**.

D-103 got Stage 1 through the whole file. This iteration pointed the visual path at it — Qwen
embedding and reranking, VideoChat3-4B, TimeLens2, all present on this machine — and it stopped after
**three** windows.

## Measured

```
✗ zar38final:s2:w0 planned 36 frames over 17720 ms and ffmpeg produced 34. One frame of tail
  rounding is normal; this is 2. The window likely runs past the end of the media, and an
  embedding of whatever frames existed would describe less footage than the window claims.
```

The message's diagnosis is wrong, and the extracted files prove it, because the trim only shortens the
in-memory tuple:

```
zar38final_s0_w0: 16 files
zar38final_s1_w0: 18 files
zar38final_s2_w0: 35 files      <- ffmpeg delivered 35 of 36
```

35 is one short of the plan — exactly the "tail rounding" the same message calls normal. Then this
function's own even-alignment step (D-060: drop a real frame rather than let the processor pad by
repeating one) removed a second, and the guard compared the **post-trim** count against `plan - 1`:
34 < 35, raise. `s2:w0` sits early in a 2313.8 s file and every frame it asked for existed.

`s0_w0` (16) and `s1_w0` (18) survived only because their deliveries were already even.

**Scope:** any window with an even plan and an odd delivery. `ceil(duration × 2.0)` is even about
half the time, so about half of all windows — which is why the run got through three.

## The fix

Judge what ffmpeg delivered *before* trimming, and trim separately:

```python
extracted = tuple(sorted(dest_dir.glob(...)))   # what the binary wrote
if len(extracted) > window.frame_count:  ...    # the ceiling, on the delivery
if len(extracted) < window.frame_count - 1: ... # the shortfall, on the delivery
paths = extracted                                # what the model is handed
if len(paths) % TEMPORAL_PATCH_FRAMES and len(paths) > TEMPORAL_PATCH_FRAMES: ...
```

**Widening the tolerance to two was rejected.** It is the obvious one-character fix and it is wrong: a
window the media genuinely does not cover *also* comes back two short, and that must stay refused. The
audit pins it — widening to 2 is caught by that control alone.

## Two findings about my own work, from the audit

**A guard I added, then deleted.** I also added a check that the kept count is a whole number of
temporal patches. It survived mutation because it is **unreachable**: after trimming, any count above
`TEMPORAL_PATCH_FRAMES` is even by construction. A guard that cannot fire reads as protection and is
not, so it went, and the property is asserted in a test across every odd delivery instead. This is the
second iteration running where the audit's real catch was my own new guard (D-103's blank reason).

**`len(extracted) > window.frame_count` had no test at all** — §3 Stage 2's 64-frame ceiling was
enforced by a branch nothing exercised, and replacing it with `if False:` left the suite green.
`-frames:v` makes an overshoot unlikely, which is exactly how a check goes unfired for months.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the shortfall check grades the truncated tuple again (the defect)   FAILED=9
CAUGHT   the tolerance is widened to two instead (the wrong fix)             FAILED=1
CAUGHT   more frames than planned is accepted                                FAILED=1
CAUGHT   the parity step stops trimming (D-060 reverted)                     FAILED=3

4/4
```

**The harness itself needed fixing.** A transient Windows file lock made one restore fail and left
`video_input.py` mutated; the backup on hand predated the fix, so the line was restored by hand and the
file verified byte-identical to the verified-green version before committing. Every write now retries
and re-reads to confirm. An audit that can corrupt the tree it audits is worse than no audit.

## Where the run reached next, and what it found

With the fix, the visual path extracted **164** window directories (from 3), indexed and retrieved with
Qwen, loaded VideoChat3-4B — and then hit a real resource wall:

```
CUDA out of memory. Tried to allocate 21.83 GiB. GPU 0 has a total capacity of 23.99 GiB of which
3.59 GiB is free. Of the allocated memory 18.30 GiB is allocated by PyTorch
```

That is not a capacity fact, it is a **divergence from frozen §6**. BLUEPRINT lines 346–347:

```
VIDEO PHASE      GPU 0 → VideoChat3-4B      (segmented)
                 GPU 1 → Embedding / Reranker / TimeLens2  (sequential)
```

`pipeline.py` hands `--visual-device` (default `cuda:0`) to the embedder, the reranker **and** the
VideoChat3 reader, so all three land on GPU 0 while GPU 1 held 1.3 GiB. §6 puts the embedder and
reranker on GPU 1 and reserves GPU 0 for the reader. Recorded as the next item rather than patched
here, because reassigning devices is its own change with its own audit.

Gate: `VERIFY OK — 1202 passed, 0 skipped`.
