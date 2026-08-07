# M2.4 — one rendered clip

**Date:** 2026-08-07 · **Blueprint ref:** §9 M2, §3 Stage 6, §4.3 · **Decision:** D-027

§9's M2 is "Vertical slice: transcript → BM25 → Gemini → manual boundary → one rendered clip",
and its point is to prove the concept end to end rather than to prove any one stage. Gemini is
blocked (`BLOCKED.md` #3), so the manual boundary substitutes for it — which is what §9's own
wording anticipates.

## The artifact

| | |
|---|---|
| file | `evidence/m2-4-rendered-clip.mp4` (50 KB) |
| still | `evidence/m2-4-frame.png` |
| dimensions | 1080 × 1920 |
| duration | 2.2 s — `final_in` 300 ms to `final_out` 2500 ms |
| captions | `ڕۆژنامەوانی کوردی`, burned in, `shaping=complex` |
| reframe | `static_centre` — **not** speaker-tracked |
| encoder | libx264 |
| ffmpeg | n8.0.1-48-g0592be14ff (libass + HarfBuzz + FriBidi) |

The source is `tests/fixtures/kurdish-speech-3cuts.mp4`, the same fixture §3 Stage 0 is tested
against. The boundary comes from `fuse_boundary` on anchors 500–2500 ms, so `final_in` was
extended backward by the fusion rule and Kurdish invariant #2 holds by construction.

## What was verified, and how

Dimensions and duration are probed off the encoded file. Neither says anything about captions,
so the caption check is separate and is the one that matters:

**Captions are burned into the pixels.** The same frames were rendered a second time with the
subtitle filter removed. A frame from each was decoded to raw RGB and compared byte by byte.
If libass had drawn nothing — wrong filter order, a `fontsdir` that resolves to nothing, an ASS
file it parses and finds nothing drawable in — the frames would be identical and the clip would
be valid, playable and caption-free. They differ.

**The captions are shaped, not merely present.** The same clip was rendered again with
`shaping=simple`, which draws Arabic-script letters in isolated forms: visibly broken text that
still looks like text to anything counting non-black pixels. The shipped render and the simple
render differ, so the comparison above is a check on shaping and not on ink. This is §4.3.2's
warning — a build can accept the option and lack the library — tested at the burn-in rather
than only at §4.3.6's golden frame.

## What this clip is not

**It is not reframed.** §3 Stage 6 says vertical reframing tracks the active speaker from
diarization plus face detection. Neither runs: Community-1 is a gated repo (`BLOCKED.md` #4)
and no face detector is wired up. The crop is a static centre crop, `RenderResult.reframe`
carries `static_centre`, and `Reframe.SPEAKER_TRACKED` exists as a value this module cannot
produce — so every clip rendered before that lands is distinguishable from every clip rendered
after, without anyone having to remember which was which.

**It is not NVENC.** §6 puts NVENC on hawapc01. Asking for it here raises rather than falling
back to x264, because a throughput figure quietly measured on the wrong encoder is worse than
no figure — the same trap §3 Stage 1 sets out for published RTF numbers.

**It was not discovered.** A human chose the boundary. Stage 3 does not exist and Stage 4 has
no credentials, so nothing in this clip is evidence about candidate quality, hook scores or
§8.2's metrics.

## Reproduce

```bash
bash scripts/fetch-ffmpeg.sh
.venv/bin/python -m pytest tests/test_render.py -q
```
