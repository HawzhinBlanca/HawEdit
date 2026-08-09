# Â§6 spreads the video phase across two GPUs; the code ran it on one

> Measured 2026-08-09 on hawapc01 (2Ã— RTX 3090 Ti, 23.99 GiB each) against `099fa3c`.
> Source: `ZAR38MinTest.mp4` â€” 640Ã—360 h264, 25 fps, 2313.8 s.

D-136 got the visual path from 3 windows to 164, and it then died on VideoChat3. BLUEPRINT Â§6 is
explicit and frozen:

```
VIDEO PHASE      GPU 0 â†’ VideoChat3-4B      (segmented)
                 GPU 1 â†’ Embedding / Reranker / TimeLens2  (sequential)
```

`pipeline.py` handed `--visual-device` (default `cuda:0`) to all three:

```python
QwenVisualEmbedder(embed_dir, device=args.visual_device),
lambda read: QwenVisualReranker(rerank_dir, read, device=args.visual_device),
lambda read, score: VideoChat3Reader(reader_dir, read, score, device=args.visual_device),
```

## Measured, before and after

```
before   GPU 0: 18.30 GiB allocated,  3.59 GiB free   (embedder + reranker + reader together)
         GPU 1:  1.30 GiB                             (idle but for TimeLens2's later turn)
         âœ— CUDA out of memory. Tried to allocate 21.83 GiB.

after    GPU 0: 10.44 GiB allocated, 12.18 GiB free   (the reader alone)
         âœ— CUDA out of memory. Tried to allocate 21.83 GiB.
```

**7.86 GiB freed on GPU 0**, Stage 2's indexing moved to GPU 1 â€” exactly what Â§6 asks for â€” and the
run still fails. The packing was a real divergence with a measurable cost, and it was not the whole
cause. Recording it that way rather than as a fix that worked.

## The fix

`--index-device` (default `cuda:1`) for Stage 2's embedding and reranking; `--visual-device` keeps the
Path B reader on GPU 0. Both assignments come from Â§6, so nothing was chosen. `--timelens-device` was
already `cuda:1`.

`build_parser` was extracted from `main` so the defaults are assertable â€” a comment claiming Â§6 is not
Â§6 being followed, and the test now reads the parsed values.

**A refusal, because these are two-GPU defaults.** On a one-GPU machine `cuda:1` previously died inside
torch with a device-ordinal message naming neither the stage nor the remedy. It now refuses up front,
names which stage wanted which device, and gives the flag to pass. The control is that available
devices are *accepted*: a check that refused every CUDA device would satisfy the refusal test and stop
the machine Â§6 was written for from running at all.

## The audit caught my own test

The first version asserted the parsed defaults. Reverting either Qwen model to `--visual-device` left
the suite **green** â€” a default nothing reads is not an assignment, which is D-126's substring failure
wearing new clothes. The composer construction was extracted into `build_visual_composer` so the
wiring itself is assertable, and the test now checks which device each of the three models receives:

```
baseline FAILED=0
CAUGHT   the embedder goes back onto the reader's GPU (half the defect)
CAUGHT   the reranker goes back onto the reader's GPU (the other half)
CAUGHT   the index default is cuda:0 again, so the flag exists and changes nothing
CAUGHT   a device the machine does not have is accepted
CAUGHT   a bare `cuda` is treated as an index

5/5
```

The first two are caught by the wiring test alone.

## A hypothesis I checked and dropped

Â§6 calls the reader "(segmented)", and I suspected the code pushed every window through one forward.
It does not â€” `read_scenes` is one call per window, docstring: *"One call per window rather than one
model batch: Â§3 calls segmentation mandatory"*. The 21.83 GiB is **one window**. Checking beat
assuming, which is the whole reason step 2 exists.

## What remains, measured rather than guessed

```
largest survivor windows, by frames on disk:
  64  zar38final_s37_w0        <- exactly MAX_FRAMES_PER_WINDOW
  63  zar38final_s82_w0
  62  zar38final_s55_w1 / s55_w0 / s40_w0
```

One 64-frame window through VideoChat3-4B's preprocessing wants 21.83 GiB beside its own 10.44 GiB of
weights: 32.3 GiB against a 23.99 GiB card. Â§3 Stage 2's 64-frame ceiling and this checkpoint's memory
appetite are in tension on a 3090 Ti â€” which is a fact about the pair, not a bug in either.

Lowering the frame cap would be picking a threshold, and the hard rules forbid that. The next step is
to **measure** the largest window this GPU can actually read and record that number with the hardware
and checkpoint that produced it.

Gate: `VERIFY OK â€” 1206 passed, 0 skipped`.
