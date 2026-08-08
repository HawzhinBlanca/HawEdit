# The frames we extract are not the frames the model reads

> Measured on `transformers` 4.57.6 (the pin, D-055), hawapc01 `cuda:0`, bfloat16.

Found while starting M6.3, by reading `MCG-NJU/TimeLens2-4B`'s `video_preprocessor_config.json`
and noticing a field none of the four §7 visual adapters had ever looked at. Every one of them
declares:

```
do_sample_frames: true      fps: 2      min_frames: 4
```

So the processor **re-samples whatever it is handed**, and no code in this project knew.

## The artifact, read back off `video_grid_thw`

`WindowFrames.count` is what we hand over. `video_grid_thw[0][0] × temporal_patch_size` is what
the vision tower received. Measured on `Qwen3-VL-Embedding-2B` with synthetic frames so lengths
the fixture cannot supply are reachable:

| extracted | rate | processor asks for | model saw | |
|---|---|---|---|---|
| 6 | 4 fps | 4 | **4** | dropped 2 — **M5.2's shipped index** |
| 64 | 4 fps | 32 | **32** | dropped 32 — half of §3's own 64-frame ceiling |
| 12 | 3 fps | 8 | **8** | dropped 4 |
| 3 | any | 4 | **4** | duplicated the last frame |
| 5 | 2 fps | 5 | **6** | duplicated the last frame |
| 4 | 1 fps | 8 | 4 | same |
| 64 | 1 fps | 128 | 64 | same |
| 30 | 1 fps | 60 | 30 | same |

Two independent rules, and they pull in opposite directions:

1. **Above the declared rate the sampler asks for fewer frames than exist** and takes a
   `linspace` subset. It never asks for more than exist — it caps — so there is no VRAM
   doubling, only loss.
2. **Any count that is not a whole number of temporal patches is padded by repeating the last
   frame.** An odd count gains a frame that was never filmed.

The exact condition for handing over precisely what is read: the count is a multiple of
`temporal_patch_size` **and** either the rate is at or below the declared `fps` **or** the count
is at most `min_frames`. That second branch matters — above 2 fps this checkpoint will not look
at more than 4 frames of a scene however many are extracted, which is why a 1400 ms window is
legal at 3 fps (4 frames) and illegal at 4 fps (6 frames).

## Why nothing saw it

The embedding comes out 2048-d with |v| = 1.0000 either way. And the timestamps are still
computed from the rate *we* supplied, so `assert_timestamps_span_window` — the guard written for
exactly this class of defect — passes. Measured: 6 frames at 4 fps produce stamps `(0.2, 1.0)`,
which is `linspace(0, 5, 4) = [0, 2, 3, 5]` over 4 fps, paired and averaged. Correct arithmetic
about the four frames that survived, silent about the two that did not.

This is `extract_window_frames`'s own objection — *"its embedding is indistinguishable from an
honest window's"* — one layer further in, past that guard.

It also overrides §3 Stage 2's ceiling from the far side. `visual_index` enforces 64 frames and
~1 fps together *"because either alone is satisfiable while the pair is broken"*. A 16 s scene at
4 fps satisfies both and the model sees 32 frames.

## The guard fires on the run that produced M5.2's evidence

Not a synthetic reproduction — the same script, unchanged:

```
VideoInputError: kurdish-speech-3cuts:s0:w0 was extracted as 6 frames at 4.0 fps and the model
received 4: the processor dropped 2. It asks for max(min_frames=4, fps=2 x 6/4.0) frames, caps
that at what exists, and pads up to a whole 2-frame temporal patch. Nothing downstream can see
this — the embedding comes out the right shape either way. To hand over exactly what is read,
the count must be a multiple of 2 **and** either the rate must be at or below 2 fps or the count
at most 4: above the declared rate this checkpoint will not look at more than 4 frames of a
scene, however many are extracted.
```

## How much it moved — the whole index rebuilt at 3 fps

3 fps is not a preference. For a 1400 ms scene, 1 fps yields one frame (`extract_window_frames`
refuses it), 2 fps yields three (odd — padded), and 3 fps yields four (clean). It is the only
legal rate for this scene length, derived rather than chosen.

Same query, same models, same weights. Only the frames that actually arrive differ:

| | 4 fps — 6 handed over, **4 read** | 3 fps — 4 handed over, **4 read** |
|---|---|---|
| rerank s0 | 0.055600 | 0.054432 |
| rerank s1 | 0.049956 | **0.038991** |
| rerank s2 | 0.022751 | **0.026656** |
| rank 1 → rank 2 margin | 0.005644 | **0.015441** |

**s1 moved by 0.011.** D-051 rejected a bfloat16 shortcut whose error was 0.0032 on the grounds
that it was 57% of the margin it was deciding. The two frames that never arrived move a single
score by **three and a half times that error**, and by twice the entire margin D-051 was
measured against.

The retrieval side moved too, and the honest run is the stronger demonstration of §3 Stage 2:

```
retrieval order: [s1, s2, s0]   0.387250 / 0.374038 / 0.326896
rerank order:    [s0, s1, s2]   0.054432 / 0.038991 / 0.026656
reranking CHANGED the order: True   (a complete reversal)
retrieval similarities carried through untouched: True
Stage 2 peak VRAM 8.16 GiB
```

At 4 fps the reranker's reordering was one swap. At the honest rate it reverses retrieval
outright — so M5.2's central claim, *"the model is doing something rather than echoing
retrieval"*, holds more firmly than the evidence that was recorded for it.

Path B re-read all three scenes at 3 fps as well: same three descriptions (0 on black, 1 on
white, 2 on blue), 49–60 s, 11.99 GiB peak, and every SV6D time still shifted onto the media's
clock — 0.000s, 1.400s, 2.800s.

## What this invalidates, stated per file rather than in general

| Evidence | Status |
|---|---|
| `m5-2-video-timestamps.md` — the `(0.0, 0.1)` vs `(0.5, 2.5)` measurement | **stands.** 4 frames at 1 fps arrive intact |
| `m5-2-video-timestamps.md` — the three-scene distance table (0.186 / 0.224 / 0.220) | **superseded.** Measured on 4 fps windows, so on 4 of 6 frames |
| `m5-2-embedder.md`, `m5-2-reranker.md` — the index and rerank numbers | **superseded** by the 3 fps table above |
| `m5-2-sampling-rate.md` — the 1 / 2 / 4 fps cosine comparison | **superseded, and see below** |
| `m5-4-path-b.md` — the clock finding and the parser | **stands.** Re-run at 3 fps, same conclusions |

### D-052's anomaly has a candidate explanation now

That file recorded a non-monotonicity it could not account for: *"1 vs 2 fps (0.117) is further
than 1 vs 4 fps (0.057)"*, and concluded *"whatever is happening is not a smooth function of
frame count"*. It was not. Over the same 4162 ms span, the model actually received:

| arm | extracted | **read** |
|---|---|---|
| 1 fps | 4 | 4 |
| 2 fps | 8 | 8 |
| 4 fps | 16 | **8** |

The 4 fps arm was eight frames, not sixteen — the same *count* as the 2 fps arm, from different
moments. A comparison labelled 1-vs-4 was really 4-frames-vs-8, which is why it did not behave
like a rate sweep. D-052's *conclusion* is untouched and is now overdetermined: an index must not
mix rates, and mixing them also means mixing how much of each window the model ever saw.

## The guards, and the mutation audit

`assert_frames_reached_model` reads the count back off the batch and refuses a mismatch in either
direction, naming both branches of the remedy. `window_batch` is now the single function all
three adapters tokenise a window through, so the three checks that took three iterations to
find — `video_metadata` at the top level, the timestamps off the decoded prompt, the frame count
off `video_grid_thw` — cannot be written one-at-a-time again. Two of the three were originally
found by adding a check to one call site and discovering the others had never had it.

Ten guards reverted one at a time, whole suite run, file restored, against a baseline verified
green first:

```
CAUGHT  the frame-arrival check itself
CAUGHT  the temporal-patch multiplier in the count
CAUGHT  window_batch calling the frame guard
CAUGHT  window_batch calling the timestamp guard
CAUGHT  the media-clock shift in build_sv6d
CAUGHT  duration as the identity VideoChat3 demands
CAUGHT  the derived last-stamp floor
CAUGHT  the second-clock refusal
CAUGHT  the moment-outside-the-clip refusal
CAUGHT  deterministic decoding

10/10 caught
```

## Carried to M6.3, so it is not rediscovered

`MCG-NJU/TimeLens2-4B` is the only §7 visual checkpoint shipping **`do_resize: false`**, so its
frames must arrive already a multiple of `patch_size × merge_size` = 32 in both dimensions. The
fixture is 640×**360** and 360 is not, which raises before any generation:

```
RuntimeError: shape '[1, 4, 2, 3, 11, 2, 16, 20, 2, 16]' is invalid for input of size 5529600
```

— the processor computing a 22-row patch grid, 352 px, for a 360 px frame. Loud, at least. The
model card's own example resizes via `process_vision_info` before the processor sees anything,
which is what that config field means. Recorded here rather than left for M6.3 to hit again.

Also confirmed for M6.3: TimeLens2 is a plain `Qwen3VLForConditionalGeneration` with
`tie_word_embeddings: true` at both config levels and `transformers_version: 4.57.3`, so it needs
none of VideoChat3's three workarounds — it loads through the shared loader with defaults and
reports `missing_keys: NONE`.
