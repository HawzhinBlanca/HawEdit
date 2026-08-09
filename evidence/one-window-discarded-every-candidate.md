# One window discarded every candidate

> Measured 2026-08-09 on hawapc01 against `889468d`.
> Source: `ZAR38MinTest.mp4`, the real 38-minute Sorani file.

D-117 gave Stage 2 a bounded query, and the composed run reached VideoChat3 for the first time on
real media. It then produced nothing:

```
Stage 0 demux 38 min -> 641 windows planned, extracted and embedded
                     -> 50 retrieved -> 7 survivors -> reader
window 1 of 7:
  ✗ the model returned no usable line for ['subject', 'aesthetics', 'camera', 'editing',
    'narrative', 'retention']. §3 Stage 3 fixes the schema at six dimensions
result: 0 candidates, after roughly 40 minutes of work
```

The model's actual output for that window, verbatim:

```
subject | 0.0 - 3.5 | A logo with white and orange shapes and text on a blue background
aesthetics | 0.0 - 3.5 | Blue background with white and orange shapes and text
camera | 0.0 - 3.5 | Static shot
editing | 0.0 - 3.5 | No cuts or transitions
narrative | 0.0 - 3.5 | No narrative
retention | 0.0 - 3.5 | The logo and its design elements
```

Six dimensions, in order, pipe-delimited, with times. `SV6D_PROMPT` asks for *"the number alone, no
unit"*; this is a **range**. Reproduced through the parser: 6 lines in, 0 matched, all six refused.

## Is the format the defect? No — measured, not assumed

Twelve of the run's own cached windows, read back through the real checkpoint:

```
cached window dirs from the real run: 641
weights resident on cuda:0: 8.39 GiB

ZAR38MinTest_s0_w0     8 frames  4.00s  6/6 parseable  [point]
ZAR38MinTest_s112_w1   7 frames  3.50s  6/6 parseable  [point]
ZAR38MinTest_s122_w4   7 frames  3.50s  6/6 parseable  [point]
…
windows read      : 12
shape of the time : {'point': 12}
lines parseable   : 72/72
```

The prompt's contract holds on real footage. The range is the exception, and widening `_LINE` to
take one would mean deciding whether the moment is the start, the end or the middle of it — a
guessed answer to a question the model did not answer. §3's *"reject output where a claim has no
timeline evidence"* stays.

(Every one of the twelve cited **0.0**, which is M5.4's already-recorded shortfall — temporal
discrimination within a scene is unmeasured — not a new finding.)

## What was changed

`read_scenes` records the refusal and keeps going. `UnreadableScene` carries the window, its bounds
and the reason; `discover_visual` returns `PathBDiscovery(candidates, unreadable)`; the composer's
result carries it into the emitted report, empty case included.

The exactness guard was kept rather than relaxed: "candidates == survivors" became "candidates ∪
unreadable == survivors", so a scene still cannot vanish between the reranker and Stage 4, and a
*model* that omits a window is still refused — the omission and the refusal are different facts now.

`discover_visual` still raises when **nothing** was readable: some readings is a partial answer with
its gaps named; none at all is a result reported for no work.

## The audit caught the defect surviving

```
first run

GREEN — SURVIVED  the reader aborts on the first refusal again (the defect)
RED   a run where nothing was readable reports a result
RED   the refusals never leave discover_visual
RED   an invented refusal for a window never sent is accepted
RED   a window both read and refused is accepted
RED   the composer stops accounting for refused survivors
RED   the empty refusal list is omitted from the report
RED   a refusal with a blank reason is accepted

7/8
```

Every test written for it used a fake reader that builds `SceneReadings` itself, so the method that
actually changed was never driven. **The function is tested, the trip to it is not** — D-105, D-108
and D-112 again, caught here by the audit rather than by a later pass.

Closed by driving the real `read_scenes` through this file's existing stub processor, with the
recorded range output as one of three answers, plus a control that a clean run reports nothing
unreadable:

```
RED  the reader aborts on the first refusal again (the defect)
…
8/8
```

Gate: `VERIFY OK — 1264 passed, 0 skipped`.
