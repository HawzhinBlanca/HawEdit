# Path B reads scenes, and the model's clock is not the media's

> **Rate superseded, 2026-08-08 (D-063/D-065).** The run below is at a sampling rate
> `SceneWindow` now **refuses**: all four §7 visual checkpoints declare `fps: 2`, and above it the
> processor discards frames. The index was re-measured at 2 fps — rank-1/rank-2 rerank margin
> 0.005644 (4 fps) -> 0.015441 (3 fps) -> **0.027870** (2 fps), reranking still reversing
> retrieval. This run is no longer reproducible from the code that produced it. See
> `evidence/m5-1-declared-sampling-rate.md`.

> Measured on `transformers` 4.57.6 (the pin, D-055), hawapc01 `cuda:0`, bfloat16.

`MCG-NJU/VideoChat3-4B` behind `path_b.VideoUnderstanding`, closing M5.4. §3 Stage 3:
*"Path B — visual. `VideoChat3-4B` over scenes, plus embedding/rerank retrieval."*

## It runs, and it reads the right scene each time

Three windows of the fixture, each read separately, through the real `discover_visual`:

```
STAGE 2 — the score Path B ranks by
  rank 1: kurdish-speech-3cuts:s0:w0  rerank=0.055600
  rank 2: kurdish-speech-3cuts:s1:w0  rerank=0.049956
  rank 3: kurdish-speech-3cuts:s2:w0  rerank=0.022751
  Stage 2 peak VRAM: 8.16 GiB

STAGE 3 PATH B — MCG-NJU/VideoChat3-4B reading each scene
  read 3 scenes in 59.5s
  Path B peak VRAM: 11.99 GiB

  rank 1  kurdish-speech-3cuts:s0:w0  0..1400 ms      score=0.055600
    subject     0.000s A red number 0 is centered on a black background
  rank 2  kurdish-speech-3cuts:s1:w0  1400..2800 ms   score=0.049956
    subject     1.400s A red number "1" is centered on a white background
  rank 3  kurdish-speech-3cuts:s2:w0  2800..4162 ms   score=0.022751
    subject     2.800s A red number "2" appears on a blue background
```

0 on black, 1 on white, 2 on blue — the fixture's three scenes, each identified from the window
it was shown. All six SV6D dimensions came back on every window.

**The score is not the model's.** §3 pairs the reader with "embedding/rerank retrieval", so
`score_window` is supplied by the caller and the numbers above are Stage 2's reranker scores,
carried through. Asking a describer for a relevance score would have produced one, in [0, 1],
about nothing. The rerank values reproduce `evidence/m5-2-reranker.md` exactly, which is a
second confirmation of the metadata change below.

## The clock, which is the part that could ship wrong

VideoChat3 computes a frame's time as `video_start_time + index / fps` and then validates
`video_start_time < duration`. For the fixture's second window that offset is 1.4 s against a
1.4 s clip — **its own validator rejects the offset it would need**. There is no way to tell
this checkpoint that a window starts partway through a media, so every time it cites is
window-relative, and it cited `0.0` on every dimension of every window.

`assert_sv6d_within_window` compares against **media-absolute** milliseconds. So without a
shift:

```
  s0:w0 [0..1400]    model said 0.0 s -> shifted 0.000s | unshifted 0 ms inside window: True
  s1:w0 [1400..2800] model said 0.0 s -> shifted 1.400s | unshifted 0 ms inside window: False
  s2:w0 [2800..4162] model said 0.0 s -> shifted 2.800s | unshifted 0 ms inside window: False
```

**The first window agrees and every other one does not** — which is exactly the shape of defect
that survives an end-to-end run, because the first window is the one anyone checks.

Two failure modes, and only one is loud. A window-relative time outside the absolute range
raises. A window-relative time *inside* it does not: a window running 1000–3000 ms with the
model citing 1.5 s is truly 2500 ms, the unshifted label reads `1.500s`, and 1500 lands inside
1000..3000. The invariant accepts it and the label is off by the window's start with nothing
reporting it. `tests/test_video_reader.py` pins that case as an explicit
*accepted, and wrong* assertion, because it is the reason the invariant cannot be the only guard.

**Why the shift is arithmetic and not a prompt instruction.** Telling the model its window
starts at 1.4 s and asking it to add the offset gets a number that is right most of the time.
The wrong ones are the silent case above.

**Why the time is a field and not prose.** `parse_timestamps_ms` cannot tell a moment from a
duration — "slow push-in over 3s, starting 5:04" cites both — so rewriting times found inside
free text would corrupt the durations. The prompt asks for `dimension | seconds | text` and the
label is built here. A description carrying a second time is refused, since that one is on the
clip's clock and nothing downstream marks which clock a number is on. Measured: 0 of 18 real
lines did this.

## Two things in `video_input.py` that VideoChat3 broke, and the second was ours

### `duration` had to become an identity (D-056)

VideoChat3's metadata type asserts `fps × duration == total_num_frames` and refused Stage 2's
metadata outright:

```
ValueError: fps * duration must be equal to total_num_frames, but got 5.6 != 6
```

A 1400 ms window at 4 fps yields 6 frames; `4.0 × 1.400 = 5.6`. Before changing a function two
shipped models already call, the cost was measured on `Qwen3-VL-Embedding-2B` — same frames,
both forms of `duration`:

| Window | `duration` as window | as frames/fps | prompt stamps | embedding |
|---|---|---|---|---|
| 4162 ms @ 1 fps, 4 frames | 4.1620 | 4.0000 | `(0.5, 2.5)` both | **byte-identical** |
| 1400 ms @ 4 fps, 6 frames | 1.4000 | 1.5000 | `(0.2, 1.0)` both | **byte-identical** |

Inert for the model that was already reading it, required by the one added next. The reranker
scores above reproducing M5.2's to six decimals is the same fact measured a third way.

### The timestamp guard was rejecting correct prompts (D-057)

`assert_timestamps_span_window` required the last stamp to reach half the window. That number
was calibrated on Qwen3-VL, which merges frames in **pairs**. VideoChat3 merges **four** and
resamples first, so six frames of a 1400 ms window become one temporal group stamped at their
midpoint — `(0 + 5/4) / 2 = 0.625`, printed `0.6`, which is 42.9% of the window. The guard
rejected all three of the fixture's windows for being correct.

The bar is now derived from the frames rather than assumed: a stamp is a frame index over the
sampling rate, so the largest a correct processor can write is `(count-1)/fps` and the smallest
is that halved — one group covering everything. Any finer grouping puts it higher, so it is a
floor for every grouping at once, less half of the last printed digit.

| Window | frames | fps | floor | real stamp | at 24 fps |
|---|---|---|---|---|---|
| s0:w0 | 6 | 4.0 | 0.5750 | 0.600 | 0.1000 |
| s1:w0 | 6 | 4.0 | 0.5750 | 0.600 | 0.1000 |
| s2:w0 | 5 | 4.0 | 0.4500 | 0.500 | 0.0833 |

The defect it exists to catch scales every stamp by `fps / 24`, so the separation is 5.4–6× and
`tests/test_video_input.py` pins both directions at the same frame count and rate. This is a
threshold being replaced by a derivation, not relaxed: it still refuses `(0.0, 0.1)` on the
4162 ms window it was originally written for.

## The prompt, and the wording that failed

The first wording asked for `name: text` and *"every line must cite a timestamp"*. The same
model, the same frames:

| Window | Result |
|---|---|
| s0, s1 | a `0.0s:` prefix on every line — a timestamp, and always zero |
| s2 | **no timestamp at all** on any of six lines |

That is output §3 requires be rejected, from the model §3 names. The pipe-delimited form with
the time in a field of its own returned **18 of 18** lines parseable, on all three windows, with
no second time anywhere in the description text.

## Negative controls, on real strings

```
  cites a moment outside the clip: REFUSED — SV6D subject cites 9999.0 s of a 1.400 s clip
  no time field at all:            REFUSED — the model returned no usable line for ['subject']
  a second clock inside the text:  REFUSED — description carries its own timestamps [1200] ms
```

The first is M5.3's `9999s` caught one layer earlier — before the shift can move it somewhere
plausible. The second is the failed prompt wording above, kept as a test.

## Mutation audit, run before the claim rather than after (D-053's lesson)

Each guard reverted in turn, the whole suite run, the file restored:

```
  CAUGHT  the media-clock shift in build_sv6d
  CAUGHT  duration as the identity VideoChat3 demands
  CAUGHT  the derived last-stamp floor
  CAUGHT  the second-clock refusal in the description
  CAUGHT  the moment-outside-the-clip refusal
  CAUGHT  video_metadata passed at the top level
  CAUGHT  deterministic decoding
  CAUGHT  the missing-dimension refusal

8/8 mutations caught by the suite
```

The first run of this audit reported 8/8 against a suite that was **already red** — four
pre-existing failures from the same edits, so every mutation "failed" for reasons that had
nothing to do with the mutation. The number was meaningless until the baseline was green. Both
runs are recorded because the first one is the mistake worth remembering: an audit that reports
success without a passing baseline measures the baseline.

## What this row does not claim

**The model cited `0.0` on every dimension of every window.** On this fixture that is not wrong
— each scene is a static single shot with nothing happening at any particular moment — but it
means the shift is *demonstrated* (0.0 → 1.400s → 2.800s) while temporal discrimination *within*
a window is unmeasured. Whether VideoChat3 points at the right moment of a scene where moments
differ needs footage where they do: `BLOCKED.md` #1.

**Whether the readings are good is §8.2's question.** The descriptions are correct about the
frames. Nothing here says they are the descriptions that surface the right clip.

**The episode-length frame-budget defect is closed (D-059).** The 256-frame figure is a
single-call VRAM ceiling. `discover_visual` now packs arbitrary episode windows into deterministic
≤256-frame calls; `VideoChat3Reader` remains stricter and invokes the model once per window. A
30-minute source is no longer refused merely because all of its segmented scenes sum past 256.
