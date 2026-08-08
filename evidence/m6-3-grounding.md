# TimeLens2 grounds real scenes, and its clock would have moved the wrong boundary

> Measured on `transformers` 4.57.6 (the pin, D-055), hawapc01 `cuda:0`, bfloat16.

`MCG-NJU/TimeLens2-4B` behind §3 Stage 5's evidence contract, closing M6.3's model. §3 Stage 5:
*"TimeLens2-4B returns intervals containing relevant visual evidence. It does not produce
editorial cuts."*

## It loads through the shared loader with no arguments at all

Unlike VideoChat3, which needed three workarounds:

```
Qwen3VLForConditionalGeneration  |  missing_keys: NONE  |  peak 8.53 GiB
tie_word_embeddings: true at BOTH config levels  |  transformers_version: 4.57.3
```

`tie_word_embeddings` agreeing at the top level and in `text_config` is exactly what D-054 found
VideoChat3 contradicting itself about, so `assert_fully_loaded` passes here for a real reason
rather than by luck.

## Two obstacles, both measured before any adapter was written

**1. It is the only §7 visual checkpoint shipping `do_resize: false`.** Its processor will not
resize, and its patch grid is computed by integer division, so a frame height that is not a
multiple of `patch_size × merge_size` = 32 produces a grid narrower than the tensor. The fixture
is 640x**360**:

```
RuntimeError: shape '[1, 4, 2, 3, 11, 2, 16, 20, 2, 16]' is invalid for input of size 5529600
```

22 rows — 352 px — against 360. Loud, but it names a tensor shape and the remedy is not guessable
from it. `align_to_patch_grid` uses the checkpoint's **own** `smart_resize`, so the target is the
library's arithmetic rather than ours: **640x360 -> 640x352**. It is a no-op for the three
checkpoints that declare `do_resize: true`, so `load_window_images` now takes the processor
everywhere and no adapter has to know which kind it has.

**2. Its answers are on the window's clock.** This is D-058's trap one layer worse, because an
interval moves a *boundary* rather than labelling a moment.

## The grounding, per scene

Query `a red number 2 on a blue background`, each of the fixture's three scenes read separately:

```
3 windows in 18.8 s, peak VRAM 8.53 GiB
  s0:w0 [0..1400]     -> nothing
  s1:w0 [1400..2800]  -> nothing
  s2:w0 [2800..4162]  -> [(2800, 3600)]  'evidence for: a red number 2 on a blue background'
                                          confidence=None
```

Correct: the blue "2" is scene 2, and the model both declines the other two and localises it
inside the right one. `confidence` is `None` because TimeLens2 returns spans and nothing else —
0.0 there would be a measurement it never made.

## The clock, and what an unshifted interval does to a real clip

Shown only scene 2 — 2800..4162 ms — the model answered `[[0.0, 0.8]]`. Unshifted that reads
0..800 ms, a span inside the **first** scene of the episode. Put through the real selector and the
real fusion:

| Anchored sentence | | overlaps | selector | final clip | extended by |
|---|---|---|---|---|---|
| 0..400 ms | shifted | False | `None` | 0..**600** | `tail` |
| 0..400 ms | **unshifted** | True | 800 | 0..**800** | **`timelens_interval_end`** |
| 0..600 ms | shifted | False | `None` | 0..800 | `tail` |
| 0..600 ms | unshifted | True | 800 | 0..800 | `tail` |
| 0..1000 ms | either | — | `None` | 0..1200 | `tail` |

At an anchor of 0..400 the unshifted interval makes the clip **200 ms longer and records visual
evidence as the reason** — for footage 2.8 seconds away. Kurdish invariant #2 holds throughout,
because it constrains direction and not relevance; that is the same sentence M6.1 was written
about, and this is the same defect arriving through the offset instead of through `max()`.

Note the middle row: at 0..600 the two agree on 800 ms and disagree only on **why**. The number
coincides and the attribution is still wrong, which is the harder failure to notice — `§8.2`
counts `path_unique_wins` and boundary provenance off exactly that field.

On this 4-second fixture the band of anchors that shows the harm is narrow. On a real episode the
windows are minutes in, so an unshifted span lands anywhere in the first seconds of the file and
the overlap is a coin toss. `BLOCKED.md` #1.

`VisualEvidenceInterval.from_window` does the arithmetic, beside the type rather than in the
adapter, so a second producer — a batch grounder, a rehydrated JSON document — cannot omit it.
D-062.

## The parser defect the real model found on its first run

Asked about the blue "2" while shown the black "0", TimeLens2 answered `[]`. The first draft of
`parse_spans` searched for `[[…]]` with a regex and refused it as malformed — so **the commonest
correct reply would have crashed on the first real episode**, and only on scenes where the query
is absent, which is most of them. It now decodes from the first bracket with `raw_decode`, and
`parse_spans("[]") == ()` is a test.

That is the second time in this project a "found nothing" answer was nearly treated as an error;
`interval_end_for_fusion` already distinguishes absence from an out-point of zero, and the
adapter now matches it.

## What is refused

| Input | |
|---|---|
| `[[1.0]]`, `[[1.0, 2.0, 0.9]]` | refused — reading two of three would be a guess about which |
| `[["start","end"]]` | refused, bounds must be numbers |
| `[[0.0, 0.8], [1.2,` | refused — a truncated array must not read as a shorter answer |
| prose with no bracket | refused — an interval read out of a sentence moves a real boundary |
| `[[0.0, 0.8]] — that is where it appears.` | **accepted**, trailing prose is not a failure |
| an empty query | refused rather than grounded against nothing |
| a span past the window's end | refused; +0.04 s of tail rounding allowed, +0.2 s not |
| frames the processor re-sampled | refused, D-060 at this call site |

## What this row does not claim

**Whole-media grounding was wrong on this fixture, and per-scene was right.** Asked about the
blue "2" over the entire 4162 ms at 1 fps, the model answered `[[1.0, 2.0]]` — the white "1"
scene. Asked about the black "0" it answered `[[0.0, 1.0]]`, correct. Four frames and two temporal
groups is close to no temporal structure for a model benchmarked at 47.7 mIoU on real video, and
Stage 5 grounds *within* a scene window anyway, which is the path measured above. But it means
this fixture cannot say whether the model is accurate — only that the adapter is honest about what
it returns. §8.2's question, `BLOCKED.md` #1.

**The query is not chosen here.** §3 Stage 5 takes the interval as one input among five, and what
to ground against — the anchored sentence, a Path A candidate, the judge's verdict — is Stage 5's
composition. `ground` takes the query and refuses an empty one rather than inventing a default,
so this adapter is not yet wired into `run_pipeline`.

## Gate, and why it was run where it was

**The shared working tree could not produce `VERIFY OK` during this iteration, for reasons outside
this change.** A concurrent session is editing `gemini.py`, `pipeline.py`, `judge.py`,
`transcripts.py` and their tests in the same checkout, and three consecutive gate runs returned
23 failures, then 5, then 3 lint errors — all in its files, none in these. It was also writing a
second TimeLens2 adapter inside `timelens.py` (`TemporalGrounder`, `TimeLensGrounder`) which at
one point left the module non-importable; that work has since been backed out of the tree.

So this change set was proved in a git worktree at `HEAD` plus these files only:

```
ruff check      All checks passed!
ruff format     83 files already formatted
mypy            Success: no issues found in 83 source files
pytest          exit 0   (full suite, excluding tests/test_gate.py)
```

`tests/test_gate.py` reports 9 failures there, and **the identical 9 at plain HEAD in the same
worktree** — they are the worktree running against the main checkout's editable install, not a
regression. Verified by diffing the two failure sets.
