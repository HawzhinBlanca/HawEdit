# Twelve of fourteen CLI refusals were held by nothing

> Measured 2026-08-10 on hawapc01 against `3765add`, Python 3.11 in `.venv`, ffmpeg 8.1.1-full.

`_run_from_args` opens with fourteen refusals for flag combinations that cannot work — the block
D-147 found a *wrong* rule in, and where D-148's `governance flags apply only with a Gemini or
Vertex route` lives.

## Measured

Each refusal deleted whole by its AST line span — so the file still lints and typechecks, and the
result is about the tests rather than about ruff — against a baseline verified green first, whole
gate suite each time:

```
14 argv refusals found by AST
baseline green: True

held: 2   unheld: 12
  UNHELD  --transcript and --omni-asr are mutually exclusive Stage 1 sources
  UNHELD  --omni-asr-runtime and --wsl-distro require --omni-asr
  UNHELD  --gemini and --vertex-project are mutually exclusive cloud routes
  UNHELD  cloud judging and --verdict are mutually exclusive Stage 4 sources
  UNHELD  cloud discovery requires --transcript or --omni-asr
  UNHELD  --sentences requires --transcript or --omni-asr
  UNHELD  --verdict requires a Stage 1 source and --sentences
  UNHELD  --visual requires --transcript or --omni-asr
  UNHELD  --qc-pass requires --sentences or --auto-select
  UNHELD  --auto-select requires --transcript or --omni-asr
  UNHELD  --timelens and --face-reframe require --sentences or --auto-select
  UNHELD  governance flags apply only with a Gemini or Vertex route

restored and green: True
```

The two that held — `--visual-query requires --visual` and the `--auto-select` producer test — were
given tests by D-147 and D-148 this session.

## The test that looked like coverage

`test_the_cli_refuses_flags_whose_prerequisites_are_absent` ran `--sentences 0`, `--qc-pass` and
`--confidential` and asserted `main([source, *flags]) == 2`. Exit 2 is the code for **every**
exception the function catches. With the `--sentences` guard deleted:

```
exit code with the guard DELETED: 2
what it actually said: ✗ ffmpeg.EXE failed (3199971767): [in#0] moov atom not found
                         [in#0] Error opening input: Invalid data found when processing input
```

`source.mp4` was an empty `touch()`ed file, so the run reached Stage 0 and ffmpeg refused it. The
test was asserting that an empty MP4 breaks the demux — and spending an ffmpeg subprocess per case
to assert it.

## The replacement

Thirteen cases, one per triggerable refusal, each verified to reach *its own* refusal before being
written down:

```
[2] work_dir=False two Stage 1 sources
      ✗ --transcript and --omni-asr are mutually exclusive Stage 1 sources
[2] work_dir=False an OmniASR runtime flag without the runtime
      ✗ --omni-asr-runtime and --wsl-distro require --omni-asr
[2] work_dir=False both cloud routes
      ✗ --gemini and --vertex-project are mutually exclusive cloud routes
[2] work_dir=False two Stage 4 sources
      ✗ cloud judging and --verdict are mutually exclusive Stage 4 sources
[2] work_dir=False cloud discovery with nothing to discover in
      ✗ cloud discovery requires --transcript or --omni-asr
[2] work_dir=False a selection with no transcript
      ✗ --sentences requires --transcript or --omni-asr
[2] work_dir=False a verdict with no selection
      ✗ --verdict requires a Stage 1 source and --sentences
[2] work_dir=False Path B with no transcript
      ✗ --visual requires --transcript or --omni-asr
[2] work_dir=False a query with no retrieval
      ✗ --visual-query requires --visual
[2] work_dir=False passing QC on nothing
      ✗ --qc-pass requires --sentences or --auto-select
[2] work_dir=False auto-select with no producer
      ✗ --auto-select needs a Stage 3 producer that can actually produce: …
[2] work_dir=False Stage 5 with nothing selected
      ✗ --timelens and --face-reframe require --sentences or --auto-select
[2] work_dir=False ZDR governance with nothing sent
      ✗ governance flags apply only with a Gemini or Vertex route
[2] work_dir=False CONTROL: a legal argv
      ✗ [Errno 2] No such file or directory: 'no-such.json'
```

`work_dir=False` throughout: a refusal about argv must land before any work. The control breaks
none of the fourteen rules and gets past all of them, far enough to fail on the transcript file it
names — without it, a `_run_from_args` that refused *everything* would pass every case above.

The set is bound to the source by AST: `_argv_refusals()` reads every `ValueError` raised directly
in `_run_from_args`, and the coverage test compares that set against the case table **both ways**.

## The fourteenth refusal cannot fire

`--auto-select requires --transcript or --omni-asr` is unreachable: `--auto-select` needs a producer
that can produce, and both producers need a Stage 1 source of their own, so an argv reaching it
always has one. Recorded in `_PRE_EMPTED_REFUSALS` with the guard that pre-empts it, and proved by
running the argv that would reach it. Not deleted — the unreachability is a property of the block's
order, and this is where a change to that order shows.

## Proof

```
baseline green: True

RED  × 14   every argv refusal, deleted whole by its AST line span
RED         the runner makes the work directory before validating argv
RED         a case is dropped, so one refusal stops being covered
RED         the pre-empted list swallows a reachable refusal

17/17
restored and green: True
```

## What each assertion buys — measured, after a wrong prediction

I predicted the message assertion was what caught a deleted guard. It is not:

```
guard deleted, message assertion present: red
guard deleted, message assertion removed: red
    the only failure: test_every_refusal_in_the_source_has_a_case
```

The **binding** catches a deleted guard — the case then names a refusal the source no longer
raises. The message assertion catches something else: a guard whose *condition* is wrong rather
than absent. Inverting `--qc-pass`'s condition:

```
condition inverted, message assertion present:
    test_the_cli_refuses_a_combination_that_cannot_work[passing QC on nothing] FAILED
condition inverted, message assertion removed:
    that failure disappears
```

Two independent nets for two different failure modes.

## Three survivors first time, and two were my own bad mutations

The audit was 15/18 before this. One survivor was a real gap: `_PRE_EMPTED_REFUSALS` could absorb a
*reachable* refusal and excuse it from needing a case — one line, and a live guard leaves coverage.
The two lists are now asserted disjoint.

The other two removed an assertion from the new tests *alone*, with the source intact. Neither
changes behaviour on an unmutated source, so neither measures anything: a test's discriminating
power only shows against a defect. Replaced by the differential above and by a source mutation only
the work-directory assertion can catch — making the runner `mkdir` the work directory before
validating argv, so every refusal still fires with its own message while the run has already
prepared state.

Fifth bad mutation of mine this session, after D-137, D-141, D-144 and D-147. Mutating a test in
isolation asks whether it is redundant today, not whether it is load-bearing.

Gate: `VERIFY OK — hawedit gate green`, 1466 tests (floor 1453 → 1466).
