# Adversarial pass 29 — every refusal in `src/`, and which the suite never reaches

`tests/test_credentials.py` opens with this project's own thesis: *"the tests that matter are
refusals"*. Four consecutive iterations then found one refusal apiece that no test reached
(D-175, D-176, D-177, and the `--check` gap inside D-176). Rather than keep finding them one at
a time, this pass measures the whole refusal surface at once.

## Method, and why not `coverage`

`coverage` is not installed, and installing it would change what the gate's environment
contains — D-139 fixed that deliberately, with a hash-pinned lock. For a one-off measurement
that trade is not worth making, and the standard library answers the same question: a
`sys.settrace` line tracer whose local trace function returns `None` for every file outside
`src/hawedit`, so per-line tracing only ever runs on the code being measured. The raise
statements themselves come from `ast`, with the enclosing function recorded.

**Caveat recorded rather than hidden:** tests that run the gate or a script in a **subprocess**
are not traced, so a refusal reached only there reads as unreached. The number below is an upper
bound on the gap, not a defect count.

## The measurement

```
modules the tracer saw executing: 46
raise statements in src/hawedit : 438
never executed by the suite     : 125
```

Distribution, largest first: `asr.py` 14, `pipeline.py` 10, `asr_worker.py` 9,
`editorial_bench.py` 8, `transcripts.py` 8, `gemini.py` 7, `reframe.py` 7, `judge.py` 6,
`visual_pipeline.py` 6, then a long tail.

**125 is not 125 defects, and the pass does not claim it is.** Much of it is legitimately
unreachable here: `OmniAsrBackend` and `WslOmniAsrProducer` need weights and a WSL runtime
(`BLOCKED.md` #4, #16), `gemini.py` needs a key (#3), and several are `SystemExit` inside
`if __name__ == "__main__"` blocks. What the number is good for is *finding the reachable ones*,
and the top of `pipeline.py`'s list is one.

## The standout: a guard that runs constantly and has never once refused

```
  line 1240  executed: True    the call site
  line 738   executed: True    def _assert_verdict_matches_request
  line 740   executed: True    the candidate_id comparison
  line 741   executed: False   the candidate_id raise
  line 745   executed: True    the span comparison
  line 749   executed: False   the span raise
```

`_assert_verdict_matches_request` runs on every judged run. **Both of its comparisons execute
and neither of its two refusals ever fires.** It is the only thing between a judge adapter's
answer and §5's editorial block — and D-177 measured exactly what a verdict for other footage
carries there: `payoff_at_ms` outside the clip, with every editorial score reached on footage the
clip does not contain.

It is the adapter-side twin of the check D-177 closed one iteration earlier, and it was in the
same state: correct, load-bearing, and accountable to nothing.

## The guards

Three tests drive Stage 4 with an adapter whose verdict is built by an injected factory:

* a verdict carrying **another candidate's id** must be refused;
* a verdict carrying **another span** must be refused — separately, because an adapter that
  answers the right candidate over the wrong seconds passes the identifier check completely;
* the **control**: an adapter answering the request it was given must be accepted, without which
  both tests above pass for a pipeline that refuses every adapter verdict and Stage 4 is unusable
  while looking guarded.

## A mutation left on disk, and why the tree is checked before staging

This pass's first audit run was killed when the session ended, and its `finally` never ran. It
left mutation 4 — *the guard refuses every adapter verdict* — sitting in `src/hawedit/pipeline.py`:

```diff
-    if verdict.candidate_id != request.candidate_id:
+    if True:
```

`git add <file>` stages the file **as it is on disk**, which is precisely what BLOCKED #12
records carrying a reversal into main under someone else's message. Caught by diffing the tree
against `HEAD` before staging anything, and restored with `git checkout --`. Recorded because the
hazard is real and the habit is the only thing that catches it.

## Mutation audit — 4/4 lint-clean

`ruff format` runs on the mutated file before the suite, so a reflowed condition measures
behaviour rather than layout — the correction D-177 needed twice.

```
baseline: lint+format clean, suite green

CAUGHT  the candidate-identity refusal is gone      <- ONLY the new guards
          test_a_judge_returning_another_candidates_verdict_is_refused
CAUGHT  the span refusal is gone                    <- ONLY the new guards
          test_a_judge_returning_another_span_is_refused
CAUGHT  the guard is never called                   <- ONLY the new guards
          test_a_judge_returning_another_candidates_verdict_is_refused
          test_a_judge_returning_another_span_is_refused
CAUGHT  the guard refuses every adapter verdict     (5 tests, incl. the positive control)

file restored byte-identical: True
4/4 caught lint-clean
```

**Three of the four are caught by the new guards and nothing else** — the two refusals
separately, and the call site that reaches them. The fourth is the control direction, caught
broadly by every existing test that drives a judge, which is what makes the first three
meaningful rather than satisfiable by a pipeline that refuses everything.

## What this pass did not do

It fixed one of the 125. The rest are recorded here as a map rather than a backlog: the
reachable ones are worth future iterations, and the unreachable ones stay unreachable until
`BLOCKED.md` #3, #4 and #16 clear. Naming the number without claiming it as defects is the
point — a bare "125 unreached refusals" would be exactly the kind of uncounted-list claim this
project keeps finding in its own documents.

