# Stage 4 was billed, and two GPU models loaded, before the run refused to overwrite

> Measured 2026-08-09 on hawapc01 against `4c7ad00`.

`run_pipeline` refuses to overwrite a previous run's delivery artifacts. It did so from beside
the render step — **~180 lines after the billed Stage 4 `generateContent`**, and after Stage 2
and Stage 3 had put Qwen and VideoChat3 on the GPU. So a re-run into a used work directory paid
Google, spent GPU time, and then raised with nothing to show for it.

The condition was knowable the whole time. It depends on `work_dir`, the media id and the
sentence selection, and on nothing that any model produces.

## The ordering, by line number at `4c7ad00`

```
731  _prepare_selection(...)          explicit selection validated
739  discover / visual_composer       <- Qwen embed + rerank, VideoChat3  (GPU)
778  auto-select                      selection settled in the other mode
814  judge.judge(request)             <- BILLED generateContent
939  clip_id = f"{identifier}-s..."
993  FileExistsError                  <- the refusal
```

Two facts decide the fix. `select_sentences` is **not** always known at entry: `--auto-select`
settles it at 778, after Stage 3 has ranked candidates. But both 731 and 778 are still ahead of
the billed call at 814, so there is a real window in both modes.

## The fix, and why it is two call sites of one function

One guard, `_assert_no_existing_artifacts`, called where the answer first becomes knowable:

* **after 731** — explicit selection. Saves the GPU work *and* the billed call.
* **after 778** — `--auto-select`. Saves the billed call; the GPU work is what produced the
  selection, so it cannot be saved in that mode.
* **before the first write** — kept, at zero cost, so a file that appeared while the models were
  running is still caught.

Those are three different moments, not three copies of a rule. The rule itself exists once.

`clip_id` and the five artifact paths now derive from `_clip_id` and
`_delivery_artifact_paths` — one derivation each, read by both the guard and the writer. A guard
that computes a path a second way is a guard that can pass while the write collides, and that is
the obvious way this fix goes wrong.

## Measured

Planting one artifact and running with an explicit selection and a counting judge stub:

```
FileExistsError: refusing to overwrite existing delivery artifact(s):
  …\work\billed-s0-s0.ass. Use a new work directory for a new run.
billed judge calls: 0
```

The same with `--auto-select` and no explicit selection: **0 calls**. Without the second call
site this case reaches the judge — the first guard sees an empty selection, returns, and nothing
re-checks once auto-selection has named sentence 0.

**The artifact of this fix is a request that never happened**, so the assertion is on the call
count, not on the exception alone.

## The control

`test_a_clean_work_directory_still_reaches_the_judge` runs the identical call with nothing
planted and asserts the judge is reached **exactly once**. A guard that refused every run — or
one hoisted to a point where `select_sentences` is always empty — passes both refusal tests and
fails this one.

It earned its place immediately: the first version failed because the stub returned
`a_verdict(...)` with `candidate_id="fixture-0"` against a request for `"v1"`, and
`_assert_verdict_matches_request` rejected it. That refusal is the pipeline's own guard against a
judge adapter returning a verdict for different footage, and it only fires on a run that actually
reaches Stage 4 — so the control was proved to be reaching the judge before it was proved to
pass.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   the early guard is removed (back to refusing after the billed call)
CAUGHT   the auto-select guard is removed (--auto-select pays again)
CAUGHT   the guard no-ops instead of raising
CAUGHT   the guard checks a different suffix set than the run writes
SURVIVED the guard derives clip_id differently from the writer

4/5
```

**The survivor, honestly.** Mutating `_clip_id` changes the guard and the writer together —
that is the point of the shared derivation — so those four tests cannot see it. It is still
behaviour-changing, and the full suite does catch it: dropping `select_sentences[-1]` makes
`(0,)` and `(0, 1)` produce the same name, and three pre-existing tests fail, led by
`test_distinct_selections_do_not_overwrite_each_others_deliveries`. Verified by running the whole
suite under the mutation rather than assuming.

So **4/5 targeted, 5/5 at the gate**, and the fifth is caught by the test that already owns that
property. No test was added to pin the filename format, because the format is a naming
convention rather than a requirement, and a test that hardcoded it would fail on an intentional
rename while catching nothing this fix is about.

## What this does not fix

Delivery is still not atomic. This guard refuses a *colliding* run up front; it does not make a
run that fails halfway leave the work directory clean, so a crashed render can still strand a
partial `.ass` or `.mp4` that forces a new work directory. That is a separate defect and is not
claimed here.

Gate: `VERIFY OK — 1079 passed, 0 skipped`.
