# Two gates, one evidence file

> Observed 2026-08-28 on hawapc01, twice, with two different symptoms and one cause.

## What happened

`scripts/verify.sh` writes its JUnit report to a fixed path, `.gate/last-test-run.xml`, and
`hawedit.gate` then grades that file. Nothing locks it. Two gate runs overlapping in time write
the same path, and the grader reads whatever the interleaving left behind.

This is easy to trigger without meaning to: the Stop hook runs a full gate whenever the agent ends
a turn, so a backgrounded `scripts/update-ledger.sh` still in flight at that moment guarantees two
concurrent runs.

## Symptom 1 — the report and the terminal disagreed

`update-ledger.sh reframe-composition T1`:

```
3277 passed, 1 warning in 637.15s
==> test evidence
REFUSED: 29 failed, 0 errored out of 3277 collected.
```

pytest reported no failures; the report it was supposed to have written recorded 29, all in
`tests/test_vertex_acceptance.py`, all `ssh-keygen` exiting **3221225794** (`0xC0000142`,
STATUS_DLL_INIT_FAILED — the Windows loader failing to start a process under memory pressure).

**This was first written off as a transient flake, and that was only half right.** The
`ssh-keygen` failures were real, but they belonged to a *different run*: the Stop hook's gate,
racing a 1080p ffmpeg render for memory, failed 29 tests and wrote them to the XML. The ledger's
own gate passed and produced the terminal output. The grader then read the other run's evidence.

## Symptom 2 — the report was not XML at all

`update-ledger.sh pro-edit T2`:

```
3295 passed, 1 warning in 538.42s
==> test evidence
REFUSED: .gate/last-test-run.xml is not readable as a JUnit report
         (junk after document element: line 1, column 418950).
         The test step wrote something, but not evidence.
```

Two processes writing the same file concurrently left a complete document followed by the tail of
another. Same race, and this time it could not be mistaken for anything else.

## Why this is worth keeping

**The gate was right both times.** It refused to flip a ledger row on evidence it could not trust,
which is exactly what `.gate/` exists for — D-093's whole point is that the claim and the evidence
must be the same artifact. A grader that read the terminal instead would have flipped both rows on
a report it never saw.

It also means a green terminal is not a green gate, and the two can disagree for reasons that have
nothing to do with the code under test.

## What was changed in response

Nothing in the harness yet, and that is a deliberate note rather than an omission: the fix is
either a lock or a per-run report path, and both are edits to enforcement surface that deserve
their own decision rather than being folded into a feature commit.

What changed is the agent's discipline: **do not leave a gate running across the end of a turn**,
because the Stop hook will start a second one. Both incidents came from backgrounding a ledger
flip and then ending the turn while it was still in flight.
