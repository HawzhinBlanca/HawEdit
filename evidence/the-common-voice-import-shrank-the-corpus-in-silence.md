# The Common Voice import shrank the corpus in silence

`import_common_voice` states the rule itself, in the refusal it raises for a clip missing from the
durations file:

> Every item needs a real duration; **skipping it silently would quietly shrink the corpus**, and
> defaulting it would fabricate a measurement.

Ten lines above that refusal, it skipped rows silently.

## The asymmetry

Two importers live in this file and only one obeys the rule:

| | skip | recorded? |
|---|---|---|
| `import_cortex_speech` | a record no human confirmed | **yes** — `unconfirmed += 1`, and the count reaches the manifest: *"…{unconfirmed} unconfirmed record(s)"*, with the comment *"Skipped, and counted"* |
| `import_common_voice` | a row with no sentence or no clip path | **no** — bare `continue` |

## The measurement

Reproduced by **executing** the importer on a Common Voice-shaped TSV — four rows, two of them
unusable (one empty `sentence`, one whitespace-only):

```
rows in the TSV        : 4
items in the corpus    : 2
rows dropped in silence: 2

provenance note : Read speech from volunteer contributors. No §4.4 dialect labels and none
                  of §8.1's recording conditions — …

  manifest mentions 'skip': False
  manifest mentions 'drop': False

VERDICT: the corpus shrank and no artifact records it
```

**The TSV is constructed, not downloaded.** There is no Common Voice `ckb` release on this machine
(M0.16 is BLOCKED), and that is stated rather than glossed. It is adequate here because the defect
is in the *shape* of the code — a skip no artifact records — and the reproduction is by execution
rather than by reading. It is weaker evidence than this project's usual real-media standard, and
that is why the finding was **deferred for six iterations** rather than reported when first spotted.

**Why it matters:** corpus size is the denominator of §8.1's hours-of-coverage. A corpus that is
quietly two rows smaller reports a coverage figure that is quietly wrong, and nothing in the
artifact says which rows went or how many.

## The fix

`unusable` is counted and carried into the `Provenance` note, mirroring `unconfirmed` exactly:

```
Read speech from volunteer contributors. 2 row(s) skipped as unusable — no validated
sentence, or no clip path — so this corpus is 2 of 4 rows read. Reported even at zero: …
```

**Reported even at zero**, which is D-110's rule and the reason for the control test: a line that
appears only when something was skipped cannot be told from an import that does not count skips at
all. The **denominator** is carried too — `2 of 4 rows read` — because a count without a total says
how many were lost but not out of what.

## Mutation audit — 3/3 lint-clean

```
baseline: GREEN
baseline lint: clean

CAUGHT   the skip goes back to being silent
CAUGHT   the count is reported but the total is not, so the shrink has no denominator
CAUGHT   the line appears only when something was skipped

file restored byte-identical: True
3/3 caught lint-clean
suite after restore: GREEN
```

The third mutation is the control's own target: it keeps the counter, keeps the total, and only
hides the line on a clean import — which is precisely the version that looks correct in review.
