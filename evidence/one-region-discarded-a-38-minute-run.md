# One 316 ms region discarded a 38-minute run

> Measured 2026-08-09 on hawapc01 against `95f5140`.
> Source: `ZAR38MinTest.mp4` — h264 640×360, 25 fps, AAC 44.1 kHz stereo, **2313.8 s**.

D-102 got the OmniASR runtime provisioned, which let Stage 1 run on real Kurdish for the first time.
It ran, and then it threw everything away.

## Measured

```
Stage 0 -> 547 speech regions, 2076.5 s of speech in 2313.8 s of media (89.7 %)
           shortest: 316, 316, 316, 316, 348, 348, 380, 380, 380, 380, 412, 444 ms
             <250ms 0    250-375 6    375-500 11    500-1000 67    >=1000 463
Stage 1 -> LLM-7B and CTC-3B loaded (17,968 MiB on each of two 3090 Tis), regions transcribed, then:

hawedit.forced_alignment.AlignmentInfeasible: 15 frames cannot emit 15 tokens: CTC needs at
least 17 frames (one per token, plus a blank between each repeated pair). Aligning anyway would
invent timings, and a wrong word boundary becomes a clip that starts mid-word …

exit 2, no transcript written
```

The guard is right and stays. A 316 ms region is ~15 frames at these models' framing, and the model
emitted 15 tokens for it — more text than the audio can carry. Refusing to align that is invariant #5
working as designed.

**What was wrong is the blast radius.** Both producers built their results the same way:

```python
results = tuple(
    (segment, self.backend.transcribe_segment(segment.path, segment.duration_s))
    for segment in prepared
)
```

One raise inside a generator expression discarded a finished Stage 0 — 74 MB of extracted audio, a
51 MB proxy, 547 cut regions — plus every other region's GPU inference. **6 of 547** regions sit in
that duration band, so a 38-minute file failing this way is ordinary, not exotic.

## The fix

`transcribe_prepared_segments`, shared by the local producer and the WSL worker, because the identical
generator existed in both and D-102 had just finished paying for duplicated invocation logic. A region
that raises becomes an `UnalignedSpeech(start_ms, end_ms, reason)` and the loop continues.

The precedent is this repo's own, in `MeasurementSession.measure`:

> A raised exception becomes a recorded failure rather than an aborted run: §8.1 wants a long-audio
> failure *rate*, and a run that dies on the first 62-second file produces no rate at all.

**The record goes in the artifact.** `transcript.raw.json` ships to the client, and a reader cannot
tell speech the model refused from silence that was never there:

```json
"unaligned": [
  { "start_ms": 1000, "end_ms": 1316,
    "reason": "AlignmentInfeasible: 15 frames cannot emit 15 tokens" }
]
```

No text is kept for a failed region: text the audio cannot support is exactly what invariant #5 exists
to keep out of the canonical file. The honest record is the span and the reason.

Verified on the artifact rather than the objects: the field serialises, round-trips through
`from_json`, and a pre-D-103 transcript with no such key still reads (`.get`, because refusing to read
an old canonical artifact to satisfy a new field breaks invariant #1 from the other side). A clean run
emits `"unaligned": []` and is otherwise unchanged.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the failure aborts the run again (the defect)                    FAILED=3
CAUGHT   failures are collected and then dropped from the artifact       FAILED=1
CAUGHT   a nothing-aligned run writes an empty transcript                 FAILED=1
CAUGHT   only AlignmentInfeasible is recorded, others still abort         FAILED=3
CAUGHT   every region is reported as unaligned (over-strict)              FAILED=6
CAUGHT   an unaligned gap may carry a blank reason                        FAILED=1

6/6
```

Two of these are worth naming. **The over-strict direction** is caught by the clean-run control alone
— without it, "report every region as unaligned" satisfies every other test here and would silently
empty every transcript this project produces. And **the blank-reason mutation survived the first
audit**: I had written that guard and no test exercised it, which is precisely the absence-of-a-check
this iteration is about, found in my own change an hour after writing it.

## What this does not claim

Nothing here measures accuracy. The transcript's *quality* on real Sorani needs the labelled corpus
(`BLOCKED.md` #1) and human judgement; this is about a run completing and stating what it omits.

Gate: `VERIFY OK — 1197 passed, 0 skipped`.
