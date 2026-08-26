# Impact map — judge the top N candidates

## `_automatic_sentence_selection` — `pipeline.py:991` — **split**

Returns on the first candidate with eligible sentences. The per-candidate half becomes
`_sentence_run_for_candidate`; the loop moves to the caller.

| caller | site | covered by |
|---|---|---|
| `run_pipeline` | `pipeline.py:1604` | `tests/test_pipeline.py` auto-select suite |

## `_candidate_for_judging` — `pipeline.py:893` — **unchanged**

Still used when sentences were supplied explicitly (`--sentences`), where there is exactly one
span to judge. Only the `--auto-select` path loops.

| caller | site | covered by |
|---|---|---|
| `run_pipeline` | `pipeline.py:1648,1650` | `tests/test_pipeline.py` |

## Stage 4 block — `pipeline.py:1658-1706` — **becomes a loop body**

Keyframe extraction, `JudgeRequest.for_survivor`, `judge.judge`,
`_assert_verdict_matches_request` and the `sv6d` backfill all move into a per-candidate helper.
Every existing refusal path (`KeyframeError`, `GeminiUnavailable`, `JudgeUnusable`,
`NotRoutable`, `RequestTooLarge`) must keep its current structured-skip behaviour.

## `build_parser` / `_build_and_run` — gains `--judge-top-n`

| caller | site | covered by |
|---|---|---|
| `pipeline.main` | `pipeline.py:2406` | CLI suite |
| `durable.main` | `durable.py:47` | `test_durable.py::test_run_durable_reports_the_same_thing_a_direct_call_would` |
| `durable_workflow._run_pipeline_step` | `durable_workflow.py:137` | same |

## `Clip.assert_renderable` / `EditorialBelowThreshold` — `clip.py` — **unchanged, new caller**

The thresholds move from being only a render-time refusal to also being the selection predicate.
The gate itself does not change; a second caller consults it earlier. **D-253 stays the final
authority** — selection choosing a clip does not exempt it from the gate at the artifact
boundary.

## Gap found

No test today asserts that more than one candidate can be judged, because nothing could. The
`--auto-select` suite covers "a candidate was chosen", not "the best passing candidate was
chosen".
