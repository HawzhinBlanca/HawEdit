# The report did not say what the transcript omits

> Measured 2026-08-09 on hawapc01 against `f9794c0`, on the real 38-minute run's own report.

D-103 made `transcript.raw.json` state every region canonical ASR could not turn into timed words,
precisely so a short transcript could never be mistaken for a complete one. This checks whether that
fact reaches the document an operator actually reads.

## Measured

```
the raw artifact for that media:
  226754..227070   ms (316 ms)  AlignmentInfeasible: 15 frames cannot emit 15 tokens
  1985346..1985694 ms (348 ms)  AlignmentInfeasible: 17 frames cannot emit 16 tokens
  total speech with no transcription: 664 ms

the emitted run report:
  mentions "unaligned"          : False
  mentions segment_confidence   : False
  transcript section keys       : media_id, source_sha256, text_ckb, words
```

The report's `transcript` section is the **normalized** transcript. `unaligned` and
`segment_confidence` live on the raw, so neither can appear there. 664 ms of Kurdish went unmentioned
in a report whose module docstring opens with *"§1: fail visible, not silent"* — the same shape as
D-100, where the statuses were right and what a human reads was not.

## The change

`PipelineRun.transcript_gaps`, populated where the raw is in hand, and reported as each gap's bounds,
duration and reason plus a `speech_without_transcription_ms` total. Two entries are readable; five
hundred are not, which is why the total is there as well as the list.

**The empty case is reported rather than omitted.** A report that mentions gaps only when there are
some makes their absence unreadable — "nothing was dropped" and "this build does not check" would look
identical. It is also the mutation that would let the positive test pass while every real run said
nothing.

## What was rejected

Making `complete` false when speech was dropped. `complete` means every stage ran and the CLI's exit
code follows it, so redefining it would turn a stage-level fact into a content-level one and conflate
"a stage did not run" with "some speech could not be aligned". Whether a run that drops speech should
*fail* is a decision about exit-code semantics for whatever scripts this, and it is named rather than
taken. The number is in the report either way.

## Mutation audit

```
baseline FAILED=0
CAUGHT   the gaps never reach the run (the defect)
CAUGHT   the total is hardcoded to zero
CAUGHT   the reason is emitted empty
CAUGHT   the duration is negated
GREEN    control: a no-op edit must not go red

5/5
```

Gate: `VERIFY OK — 1225 passed, 0 skipped`.
