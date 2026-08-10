# A blocker could resolve invisibly

> Measured 2026-08-10 on hawapc01 against `ba52888`.

`BLOCKED.md` is the file that decides whether work is allowed to stop. `tests/test_claims.py` reads
it to check that every `BLOCKED` row in the ledger points at something still in the way — a test
written because M2.4 sat behind a resolved #5 for two days.

## Its resolution vocabulary was one word, and the file uses two

```
19 entries; the current rule calls these live:
  [1, 3, 4, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19]

bold markers used in headings, and which entries use them:
  ANSWERED   [10]                <- NOT recognised as a resolution
  RESOLVED   [2, 5, 6, 7, 8, 11] <- RESOLVED

entries marked ANSWERED: ['10']
  #10: current rule says live=True
    what it says happened to the blocker: as **#11**, because it is a different question from
    this one and answering this one exposed it.

BLOCKED numbers cited anywhere in PROGRESS.md: [1, 2, 3, 4, 5, 7, 9, 11, 13, 14, 15, 16, 17, 18, 19]
  is #10 cited? False
```

So the guard has been blind to one entry's resolution since 2026-08-08. Nothing cites #10, which is
luck: a `BLOCKED` row pointing at it would have passed the very test written to prevent that.

## The fix

`_BLOCKED_RESOLUTIONS = {RESOLVED, ANSWERED}`, enforced both ways — a heading marker outside the set
fails, and a declared word no heading uses fails too, so the set describes this file instead of
predicting it. A third word becomes a deliberate edit in a diff.

`ANSWERED` counts as not-live because `README.md` defines this file as *"What needs Hawa"*: #10's
question was answered by Hawa, the answer sits in `models/sources.json`, and the obstacle that
survived it was filed as #11 — itself resolved.

## Proof

```
baseline green: True

RED  the vocabulary forgets ANSWERED again (the defect: #10 reads as live)
RED  a heading resolves with an undeclared word
RED  the vocabulary declares a word no heading uses
RED  #10's ANSWERED marker is dropped, so it becomes live with nothing recording why
RED  an unmarked entry is treated as resolved, so #1 stops reading as live
RED  a PROGRESS row cites the answered #10 as its live blocker

6/6
restored and green: True
```

**The first pass was 5/6, and the survivor was my own bad mutation.** It made a ledger row cite the
answered #10, but anchored inside **M5.5**, whose status is `PARTIAL` — a row
`test_every_blocked_row_points_at_a_live_blocked_entry` never examines, since it only reads rows
marked `BLOCKED`. Re-anchored inside **M0.12** and caught. Third such mutation this session, after
D-137's retry ceiling and D-141's `revisions.json`.

## The two live entries this machine could have settled, re-measured

```
#3  hawedit-credentials --check
      GEMINI_API_KEY: not set
      exit 1

#4  HF_TOKEN present in the environment: False
      metadata HTTP 200 | gated: auto
      download HEAD: 401 -> still gated
```

Both still Hawa's. Twelve entries remain live once #10 stops counting: #1, #3, #4, #9, #12, #13,
#14, #15, #16, #17, #18, #19.

## And one of my own measurements was wrong

Checking #3 I first ran `… --check 2>&1 | tail -6; echo "exit=$?"` and read `exit=0` — which is
**`tail`'s** exit status, not Python's, so it looked as though `--check` returned success with no key
and contradicted `README.md`'s *"exits non-zero if unusable"*. Re-run without the pipe it exits
**1**. The README was right; the pipe was the defect. Recorded because "verify your own tool output"
is a rule here and this is what breaking it looks like.

Gate: `VERIFY OK — hawedit gate green`, 1422 tests.
