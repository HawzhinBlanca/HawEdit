# The largest scene window a 3090 Ti can read through VideoChat3-4B is 8 frames

> Measured 2026-08-09 on hawapc01 — NVIDIA GeForce RTX 3090 Ti, **23.99 GiB** — against `223980e`,
> with `MCG-NJU/VideoChat3-4B` (weights resident: **8.68 GiB**) and the real frames the 38-minute run
> extracted (`work/.../frames/zar38final_s37_w0`, 64 files).

D-105 freed 7.86 GiB by putting Stage 2's indexing on GPU 1 per §6, and the reader still failed on one
window. Lowering §3's frame ceiling to make it pass would be picking a threshold, which the hard rules
forbid. So this measures the number, through the real `VideoChat3Reader` class, one model load reused
for every attempt.

## Measured

```
device: NVIDIA GeForce RTX 3090 Ti, 23.99 GiB total     weights resident: 8.68 GiB

 frames  window_ms  peak GiB   result
      4       2000     12.00   OK
      6       3000     16.00   OK
      7       3500     18.58   OK
      8       4000     21.57   OK          <- 90 % of the card
      9       4500     16.33   OOM, wanted a further  6.91 GiB
     10       5000     18.07   OOM, wanted a further  8.53 GiB
     11       5500     19.99   OOM, wanted a further 10.32 GiB
     12       6000     22.09   OOM, wanted a further 12.28 GiB
     16       8000        —    OOM, wanted 21.83 GiB
     24      12000        —    OOM, wanted 49.11 GiB
     32      16000        —    OOM, wanted 87.31 GiB
     48      24000        —    OOM, wanted 196.44 GiB
```

**Eight frames.** §3 Stage 2 plans up to `MAX_FRAMES_PER_WINDOW = 64` — an **8× gap** on the machine §6
names.

## The demand is quadratic, which is why no small adjustment helps

The requested allocations fit `n²` almost exactly:

```
48 → 196.44        196.44 / 87.31 = 2.25   (48/32)² = 2.25
32 →  87.31         87.31 / 49.11 = 1.78   (32/24)² = 1.78
24 →  49.11         49.11 / 21.83 = 2.25   (24/16)² = 2.25
16 →  21.83         21.83 / 12.28 = 1.78   (16/12)² = 1.78
12 →  12.28
```

Attention over the vision tokens. Halving the window buys a **quarter** of the memory, so the gap
between 8 and 64 is not a tuning margin — it is a factor of 64 in demand.

**One reading that looks anomalous is not.** The 64-frame attempt reported "wanted 10.91 GiB", smaller
than the 48-frame attempt's 196.44. That is the *first allocation to fail*, not the total need: peak was
already 15.42 GiB, so a 10.91 GiB request had nowhere to go. Extrapolating the fit, a 64-frame window
needs on the order of 350 GiB. Read the raw numbers, not the headline.

## What is not being changed here, and why

`MAX_FRAMES_PER_WINDOW` stays **64**. It is §3's number, BLUEPRINT is frozen, and quietly lowering it
to make a run pass is precisely the "weaken the check to make something pass" move the hard rules
forbid. To stop that happening by accident, this measurement records the constant canonically, so
D-098's check now holds the code to §3's 64 — a future "fix" that edits it has to amend the record.

Truncating a planned 64-frame window to 8 frames at read time would be worse: D-104's guard exists
because "an embedding of whatever frames existed would describe less footage than the window claims",
and reading 8 of 64 frames is that failure with the numbers changed.

So the honest resolution is that **windows must be planned small enough for the reader**, which moves
the cap into `plan_scene_windows` and changes what a window *is* — on hawapc01, 4-second windows rather
than up to 32-second ones, and several times as many of them. That is a design change with consequences
for retrieval and cost, and it gets its own iteration and its own audit rather than being bolted on at
the end of this one. Recorded as `BLOCKED.md` #17 with these numbers.

Gate: `VERIFY OK — 1207 passed, 0 skipped`.
