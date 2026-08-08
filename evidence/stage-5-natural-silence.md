# Stage 5 fused three of §3's five out-point signals, and the fourth was already computed

> Measured 2026-08-09 on hawapc01 against `2847efb`, real Silero VAD on the real fixture.

`fuse_boundary` has always had a `natural_silence` branch:

```python
if inputs.natural_silence_ms is not None:
    out_candidates.append((inputs.natural_silence_ms, "natural_silence"))
```

`pipeline.py` never set it. One construction site in the whole of `src/` (`BoundaryInputs(` at
what was line 853), and it passed `shot_cuts_ms`, `vad_onset_ms`, the TimeLens pair and
`media_duration_ms` — so the branch was unreachable from the runner and the fused out point was
**three of §3's five signals**: the 200 ms tail, a following shot cut, and
`timelens_interval_end`.

§3 Stage 5, verbatim:

```
final_out = latest   of { anchor_out + 200 ms tail, natural silence,
                          following shot_cut within 400 ms,
                          speaker_turn_end, timelens_interval_end }
```

## The silences were already being computed

This is the part that makes it a wiring defect rather than a missing feature.
`_pauses_between(ingested)` runs at what was line 703 and derives the gaps between Stage 0's VAD
speech regions; the result goes to `segment_sentences(vad_pauses=…)` for §4.2 and nowhere else.
The measurement Stage 5 needed had been taken in the same function, a hundred and fifty lines
earlier, and spent once.

## What "natural silence" is, decided from the measurement rather than assumed

Stage 0's real VAD on `tests/fixtures/kurdish-speech-3cuts.mp4`:

```
duration_ms 4162
speech regions: 2
       0 ..   1790 ms  (1.790s)
    1954 ..   4180 ms  (2.226s)
pauses: ((1790, 1954),)
```

Two candidate readings, and the fixture separates them:

**The end of the speech region containing `anchor_out`** — where sound actually stopped. This is
what shipped. `anchor_out` is a *transcript* time (a word's end, from §4.2's Viterbi alignment);
VAD measured when the audio went quiet, independently. When the audible tail runs past the last
aligned word, §3's "end on natural silence" means exactly this point.

**The onset of the next speech region** — the far side of the pause. Rejected: it reaches across
an entire silence to butt against the next utterance, which lengthens every mid-episode clip and
clips the following speaker's first phoneme. On this fixture it would put a sentence-0 clip at
1954 ms instead of 1790 ms.

The shipped reading needs **no threshold** — every value it returns is a measured region edge —
and it cannot run into the following region by construction, because a region's end precedes the
next region's start. It is the exact mirror of the existing `_vad_onset_for_anchor`, which takes
the *start* of the region holding the first anchor.

`None` when `anchor_out` is not inside a speech region: the clip already ends in silence, so
there is nothing to extend to. A number there would be indistinguishable from a measurement, and
§8.2 reads which signal moved the boundary.

## Two numbers, and why the second one is the test that proves it

With the stock fixture transcript, sentence 0's last word ends at 1700 ms:

| signal | value |
|---|---|
| tail (`anchor_out + 200`) | **1900 ms** ← wins |
| natural silence (region end) | 1790 ms |

So on the stock timings the fix changes nothing, which is correct and is why that case is the
**control**, not the proof. Ending the same word at 1500 ms — the ordinary situation the signal
exists for, an audible tail running past the last aligned word — inverts it:

| signal | value |
|---|---|
| tail | 1700 ms |
| natural silence | **1790 ms** ← wins |

Both are asserted on the fused artifact (`run.clip.boundary.final_out_ms` and
`out_extended_by`), through a real `run_pipeline` call over the real media with real VAD, not on
inputs echoed back.

**The control is a genuine discriminator.** Reading natural silence as the next speech onset
gives 1954 ms and `out_extended_by == "natural_silence"` for the stock transcript, so the control
fails for the wrong definition while the positive test passes for both. A positive test alone
would have certified either.

## An edge the fixture exposed for free

VAD region 2 ends at **4180 ms** on a **4162 ms** file — the model reports speech 18 ms past the
end of the media. `fuse_boundary`'s existing `media_duration_ms` clamp absorbs it, and this is
now a second reason that clamp is load-bearing rather than defensive. It also means no value
this helper returns can push a render past the end of the source.

The invariant is safe independently of all of it: the 200 ms tail is always present in the
`max()`, so `final_out >= anchor_out + 200 > anchor_out` whatever this signal returns.

The uncaptioned-speech guard is also unaffected — it filters unselected *words*, not VAD
regions, and word 2 starts at 2000 ms, past the 1790 ms extension.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   the signal is never passed at all (the original defect)
CAUGHT   natural silence read as the NEXT speech onset, across the pause
CAUGHT   returns the region START instead of its end
CAUGHT   an anchor inside a pause invents an edge instead of returning None
CAUGHT   boundary.py stops offering the natural_silence candidate

5/5
```

The second and the last are the ones worth having. The second is the design decision above,
pinned so a later reader cannot "simplify" it into the wrong reading. The last mutates
`boundary.py` rather than `pipeline.py`, which confirms the tests cover the whole chain from
Stage 0's VAD to the emitted boundary rather than just the argument being present.

## What is still missing, and why it is not this row

`speaker_turn_end` — §3's fifth out-point signal — needs `pyannote/speaker-diarization-community-1`,
which measures **401** from this machine (`BLOCKED.md` #4). Four of five now, with the fifth
absent for a stated reason rather than by omission. The in-point set is unaffected by this
change: `natural silence` appears only in `final_out`.

Gate: `VERIFY OK — 1075 passed, 0 skipped`.
