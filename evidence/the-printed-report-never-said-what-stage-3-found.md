# The printed report never said what Stage 3 found

D-111's finding, one representation over. That entry fixed `report["discovery"]` reading `null`
whether Stage 3 produced candidates or was never attempted, and stated the rule this file is
about — *"a stage reporting nothing about itself is the silent case"*. It fixed the **JSON**. The
**printed** report, which is what the documented invocation produces, said nothing about Stage 3
at all.

The asymmetry is the tell: a *skipped* discovery printed a `SKIPPED discovery: …` line, and a
discovery that *succeeded* printed nothing.

## The measurement

The full composed pipeline, run on the real 38-minute file with the champion adapter — Stage 0 and
Stage 1 both reused, Stage 2 and Path B live:

```
hawedit.pipeline "…\ZAR38MinTest.mp4" --work-dir …\champion --media-id zar38champion \
    --omni-asr --omni-asr-adapter '//wsl$/Ubuntu/home/ai/cortex_champion_model' \
    --visual --visual-query "two or more people talking to each other in conversation" \
    --visual-max-frames 8
```

The entire printed report, 14 lines, straight from Stage 2's survivors to §4.2's sentences:

```
media   zar38champion
stage 0 2313800 ms · 138 shot cut(s) · 547 speech region(s) · diarization: not run
stage 2 641 scene window(s) · 4873 frame(s) at 2.0 fps · 7 reranked survivor(s)
§4.2    185 sentence(s)
SKIPPED editorial … SKIPPED boundary … SKIPPED render … SKIPPED delivery …
```

The same run with `--json`:

```json
"discovery": {"skipped": false, "stage": "discovery", "candidates": 7, "by_path": {"visual": 7}},
"candidates": [ … 7 … ],  "rejected": [],  "rejected_by_path": {"visual": 0}
```

**Computed, carried, and reported in one representation but not the other.** Among those 7 is
`zar38champion:s54:w4` at 1040287–1043818 ms — the window D-182 recovered — so the stage the
operator cannot see is the one producing the run's actual output.

## The fix

One line in `_print_report`, placed between Stage 2 and §4.2 where it belongs in pipeline order:

```
stage 3 7 candidate(s) [visual 7] · 0 rejected [visual 0]
```

Read off `_discovery_ran()` — the same helper `to_dict` uses — rather than recounted, so the two
reports of one run cannot disagree about what it did. That is a guard, not a convenience, and it
has its own mutation below.

**Rejections are printed even at zero.** §5 makes rejection first-class and calls that set *"your
only measure of recall"*; the set was computed, so `0` is a measurement rather than an absence, and
a line that appeared only when something had been rejected could not be told from one that never
ran — D-110's reasoning, which `to_dict` already applies to the same two fields.

## Mutation audit — 5/5 lint-clean

```
baseline: GREEN
baseline lint: clean

CAUGHT   Stage 3 goes unreported again when it succeeds
CAUGHT   the per-path split is dropped, leaving a bare total §8.2 cannot partition
CAUGHT   the rejection count is dropped — §5's only measure of recall
CAUGHT   the count is recounted in the printer instead of read from _discovery_ran
CAUGHT   a run that never reached Stage 3 invents a result line from an empty tuple

file restored byte-identical: True
5/5 caught lint-clean
suite after restore: GREEN
```

**The audit caught a test of mine that measured nothing.** The per-path split test first asserted
only that each path's *name* appeared in the output — and the **rejection** split prints the same
names, so deleting the candidate split entirely left `visual` in the line and the test stayed
green. It now asserts each path's *count* (`verbal 1`, `visual 1`), which the all-zero rejection
split cannot satisfy. First run 3/5, after fixing that test and making one mutation lint-clean,
5/5.

The control is the last mutation's target: a run with no Stage 3 producer must still print exactly
what it printed before — one `SKIPPED discovery` line and no `stage 3` line invented from an empty
tuple.
