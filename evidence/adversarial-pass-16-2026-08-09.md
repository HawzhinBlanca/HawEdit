# Adversarial pass #16 — the end-to-end runner

> Run 2026-08-09 on hawapc01 against `7269dd0`.
> Target: **M2.7**, DONE — 9,594 characters of claims, the largest surface never attacked as a row.

Several of its amendments were mutation-audited when they landed (D-070, D-071, D-072, D-110, D-111,
D-115, D-116). The mutations below target the *original* D-032 claims nobody has re-attacked.

```
CAUGHT  an incomplete run exits 0
CAUGHT  an incomplete run exits 2, the code a refusal uses
MISSED  a run with skipped stages calls itself complete
MISSED  a run with no visual windows calls itself complete
MISSED  a run with no candidates calls itself complete
MISSED  Stage 5 fuses against cuts from nowhere on this video
CAUGHT  the window plan ignores the cuts Stage 0 found

3/7
```

## `complete` was never True

`complete` is what the exit code derives from and it has eleven conjuncts. Three could each become
`True` with 1,302 tests green. The cause is not a missing assertion here or there:

```
full_run.complete   False
  skipped           ['visual_index', 'discovery']
  ingest OK   transcript OK   index OK   visual_windows OK
  candidates NO
  boundary OK   clip OK   editorial OK   render OK   delivery OK
```

Even the six-stage `full_run` is incomplete, so **no test in the suite ever reached the True branch**,
and a conjunct was indistinguishable from a no-op.

The suite now has one:

```
run_pipeline(… discover=…, visual_composer=…, judge=…)
  complete   True
  skipped    ()
  candidates 1
```

Built through the real runner rather than by fabricating `RenderResult` and `Delivery`, so it cannot
drift from the product. Each conjunct is then removed from that run with `replace()`.

## Eight, not four

```
bare run exit code   1                          the cell says 1 — correct
blocked stages       8  ['transcript', 'index', 'visual_index', 'discovery',
                         'editorial', 'boundary', 'render', 'delivery']
the cell says        "the four blocked stages"
```

True when D-032 wrote it. Stage 2's visual half, boundary, render and delivery arrived later. The same
class as M1.6's "five repositories" — a count nobody re-derived.

## Stage 5's cuts, and why the assertion is on the input

§3 Stage 5 takes the **latest** of its out-point signals. On the only media here, natural silence is
the end of the VAD speech region — the whole file. Through the real runner, with an anchor 300 ms
before the 2800 ms cut:

```
anchor          2000..2500
final           1834..4162
out_extended_by natural_silence
```

`fuse_boundary` on its own does distinguish — `(1400, 2800)` gives 2800/`shot_cut`, `(9000, 9500)`
gives 2700/`tail` — but through the runner natural silence is always later, so the cut cannot decide
the result on this fixture. The test therefore asserts that what Stage 5 was handed equals what
Stage 0 measured off the file: two values from different places, not a request echoed back.

## Two of my own mistakes, caught by controls

The "constant cuts" mutation first used `(1_400, 2_800)` — the fixture's actual cuts — so it could not
change behaviour and its SURVIVED measured nothing. With `(9_000, 9_500)` it is a real survivor.

And the first three `complete` tests were built on a synthetic run that was already incomplete for
unrelated reasons, so each removal proved nothing. The control failed, which is the only reason I
found out. A control that cannot fail is not a control.

```
after: 7/7
```

No production code changed.

Gate: `VERIFY OK — 1307 passed, 0 skipped`.
