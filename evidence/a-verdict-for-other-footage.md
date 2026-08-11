# The one CLI refusal nothing held, on today's only Stage 4 route

`main()` refuses fourteen argument combinations, and `run_pipeline` refuses one more: a supplied
verdict whose span is not the selected sentence anchors. Eleven mutated one at a time against a
baseline verified green first:

```
CAUGHT   --transcript and --omni-asr both given
CAUGHT   --omni-asr-runtime without --omni-asr
CAUGHT   --gemini and --vertex-project both given
CAUGHT   cloud judging together with --verdict
CAUGHT   cloud discovery with no Stage 1 source
CAUGHT   --sentences with no Stage 1 source
CAUGHT   --verdict with no Stage 1 source or no --sentences
CAUGHT   --visual with no Stage 1 source
CAUGHT   --visual-query without --visual
CAUGHT   --qc-pass without a selection
SURVIVED the supplied-verdict span check

10/11 caught by the suite as it stands
```

The argument refusals are exemplary, and one of the tests catching them is
`test_every_refusal_in_the_source_has_a_case` — derived from the source, so a new refusal cannot
arrive uncovered. That test reads the arg-parsing block; the surviving check lives in
`run_pipeline`, outside its reach.

## Why it matters here and now

`--verdict` is the **only** Stage 4 route available while `BLOCKED.md` #3 stands — no
`GEMINI_API_KEY`, no `~/.hawedit/credentials.json`. It is the path a real run takes today.

`JudgeVerdict.__post_init__` cannot catch a mismatch: it requires
`clip_in_ms <= payoff_at_ms <= clip_out_ms`, which a verdict for a *different* clip satisfies
perfectly. The verdict is internally valid and externally wrong.

Measured on the §5 block that ships, with the shipped code and then with the check removed:

```
a matching verdict yields an editorial block: True
  payoff   : 2100

a verdict scored for a different span, through the shipped code:
  refused: supplied verdict scores 900000..904000 ms but the selected sentence anchors are
           exactly 100..4100 ms. Persisted and live verdicts must identify the same footage.

what such a verdict would have carried into §5's editorial block:
  {"hook_score": 0.8, "self_contained": true, "meaning_fidelity": 0.9,
   "misleading_edit_risk": 0.05, "cultural_landing": 0.8, "narrative_role": "payoff",
   "judge": "gemini-2.5-pro", "sv6d": null, "payoff_at_ms": 902000}
```

`payoff_at_ms: 902000` inside a clip running 100..4100 ms — §5's payoff marker pointing 898
seconds past the end — with every editorial score reached on footage the clip does not contain.

## What the audit found about my own first attempt

Three mutations, then two more after re-running the format-dirty ones through `ruff format` so
they measured behaviour rather than layout:

```
CAUGHT   the defect restored: the span check is gone      <- ONLY the new guard
SURVIVED only the in-point is compared                    <- a gap my first test did not close
SURVIVED the check applies to live judge verdicts too
CAUGHT   the check refuses every supplied verdict         (many tests, incl. the positive control)
```

**The second is a real finding against my own work.** The first refusal test moved both ends of
the span at once, so comparing only `clip_in_ms` still caught it — leaving unheld the case an
operator is most likely to produce by hand: the right start and the wrong end. The test now moves
each end separately, and that mutation is caught by it alone:

```
CAUGHT   only the in-point is compared, so a wrong out-point passes   <- ONLY the new guards
```

**The third survivor is recorded, not counted.** A control I wrote for the `judge is None` clause
turned out to measure nothing: with discovery driving the run, `boundary` is `StageSkipped` and
`anchors` is `None`, so that path never reaches the check at all — measured, the judge answered
`(0, 1700)` and no anchors existed. The clause is defence in depth whose state I could not
construct, the same category as D-166's sibling assertion and D-170's blank clause. The vacuous
test was **removed** rather than kept, as D-174's was.

## Result

**2 of 3 counted mutations caught by the new guard alone**, the third (refuse-everything) caught
broadly by the positive control and by every existing test that supplies a matching verdict. No
production code changed — the check was correct, and both halves of it are now held.
