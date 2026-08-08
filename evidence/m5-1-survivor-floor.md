# A recorded decision was reversed in code, and I am the one who committed it

> Verified on the working tree of 2026-08-08, gate green at 1067 passed / 0 skipped.

## What happened

`rerank_and_keep` refused an index below §3 Stage 2's survivor floor. It was changed to return
however many windows existed:

```python
survivor_count = min(keep, len(reranked))
```

**That change reached main in my own commit `3c270f7`.** I staged the whole of
`src/hawedit/visual_index.py` to land a rate bound, rather than building HEAD-plus-my-edits as I
had done for `DECISIONS.md` and `PROGRESS.md` in the same commit. A concurrent session's edit was
sitting in that file and went with it. The rule I was following for documents is the rule that
applies to source, and I did not apply it there.

## What it reversed

D-037 clause 4, verbatim:

> **4 · Below the survivor floor the retrieval refuses instead of shortening.** §3 fixes the count
> at 5–10. A three-scene video cannot satisfy it. The alternative considered was returning whatever
> exists; rejected because §8.2 counts Recall@K on this list, and three results in a column that
> says five is a number that does not mean what the column says. `rerank_and_keep` raises and names
> both figures.

The alternative was not merely unconsidered — it was considered and rejected, in writing. No
superseding entry was recorded. Two other things still said the old behaviour at the moment the
code stopped doing it:

| Where | What it said |
|---|---|
| `PROGRESS.md` M5.2 | *"`rerank_and_keep` correctly refuses"* |
| the function's own docstring, two lines above the change | the reranker *"may not … drop below the survivor count"* |

## Reproduced

```
_index_of(3), keep=5
  before: returns 3 hits, ranks 1..3, no error
  after:  VisualIndexError — the index holds 3 windows and 5 survivors were asked for
```

## The fix, and where it sits

Restored, and moved **before** the reranker is asked to run — the previous position was after
retrieval, so a media too short for the slice paid for a GPU scoring pass first. A test proves the
ordering by handing in a reranker that raises if called at all; the refusal still comes out.

The message names the caller's option rather than the function's: *"This media is too short for
Stage 2's survivor slice — the caller decides whether to skip the slice, and says so, rather than
this function shortening it quietly."* `visual_pipeline.VisualComposer` already converts the
refusal into a `VisualPipelineError` naming the media, so the composed path reports it rather than
crashing anonymously.

## Why the short-media case does not justify the relaxation

A three-window index is the **fixture**, not the product. At 2 fps under the 64-frame ceiling a
window is at most 32 s, so a 40-minute Kurdish episode plans roughly 75 windows. The only inputs
that fall below five are test material — and `evidence/m5-2-reranker.md` has said since M5.2 that
the keep-5–10 slice is *"not exercisable on this fixture"* precisely because `rerank_and_keep`
*"correctly refuses"* it.

## The counter-argument, recorded rather than dismissed

§8.2's Recall@K over three candidates is arguably still well defined — the denominator is smaller,
not corrupted — and `VisualDiscoveryResult` already reports `indexed_windows` and `retrieved`, so a
reader could see the shortfall. That is a real argument that D-037 clause 4 may be wrong.

It is not settled here. Settling it needs the labelled set §8.2 scores against, which is
`BLOCKED.md` #1. Until then the recorded decision stands, because "the written decision wins until
someone measures it wrong" is the only rule available when neither side can be measured. D-066.

## What the other session's change got right, and is kept

It added a check that the reranker returns exactly as many hits as it was handed — *"it must score
every retrieved window … none may disappear"*. That is **stronger** than the check it replaced and
is retained unchanged. The revert is only of the count, not of that.

## Mutation audit — and one survivor that is redundancy, not a hole

Baseline verified green first (1067 passed, 0 skipped):

```
CAUGHT   the survivor-floor refusal itself
SURVIVED the keep slice (min(keep, len) would readmit the relaxation)
CAUGHT   the reranker-must-score-every-hit check
```

The survivor is provable rather than lucky. `hits` is `min(k, len(index))`; the restored floor
guarantees `len(index) >= keep`; the equal-length check guarantees `len(reranked) == len(hits)`.
So `len(reranked) >= keep` always, and `min(keep, len(reranked))` and `[:keep]` cannot differ. The
plain slice is kept because it states the contract, and no test was written for it: a test for a
branch that cannot be reached measures nothing, which is the same standard applied to the
`shaping=simple` control in `evidence/rtl-shaping-wrapping.md`.

## The process finding, which outlasts this fix

Two sessions sharing one checkout also share one git index. My commit carried a change I had not
read because `git add <file>` stages the file as it is on disk, not the change I made to it. The
protection is the one already used for shared documents — reconstruct HEAD plus your own edits and
hash-object it — and it applies to source files with exactly the same force.
