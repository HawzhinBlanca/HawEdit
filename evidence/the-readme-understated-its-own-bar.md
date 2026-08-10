# The README understated its own bar

> Measured 2026-08-10 on hawapc01 against `6f23d29`.

`README.md` is the last document in the loop's step 1(b) list never checked systematically, and the
one a reader meets first.

## It called a resolved blocker undone

```
README.md:257   … Making that job a required status check is a repository setting, and is not done.
BLOCKED.md:260  ## #7 · The hawedit CI job is not a *required* status check — **RESOLVED 2026-08-08**
```

Measured against the live API, not read off the record:

```
$ gh api repos/HawzhinBlanca/HawEdit/branches/main/protection --jq '.required_status_checks'
{"checks":[{"app_id":15368,"context":"gate"}],"contexts":["gate"],"strict":true, …}
```

`gate` is required **and** `strict: true`, so a branch must be up to date with `main` before it can
merge — stronger than the sentence claimed. Every `git push` in this loop prints
`Required status check "gate" is expected.`

## Its `cli.py` row named none of what `cli.py` does

```
hawedit.cli.__all__: ['machine_readable_stdout', 'program_name', 'use_utf8_streams']
exported but not named in the row: ['machine_readable_stdout', 'program_name', 'use_utf8_streams']
```

The row described `use_utf8_streams`'s effect without naming it, omitted `machine_readable_stdout`
(D-119), and omitted `program_name` — added **two commits earlier** by D-142. One drift older than
this loop, one made by it.

## Proof

```
baseline green: True

RED  the README calls the resolved required-check setting undone again (the defect)
RED  the README stops stating the fact #7's resolution rests on
RED  the cli.py row drops program_name (the drift D-142 created)
RED  the cli.py row drops machine_readable_stdout (the drift that predated the loop)
RED  cli.py gains a fourth export the README does not name
RED  BLOCKED #7 is reopened while the README still says it is done
RED  the claims helper reads corrections as claims again (the prose-grep trap)

7/7
restored and green: True
```

**The first pass was 6/7.** The survivor was the mirror: reopening #7 while the README still
claimed the check was in place left the suite green, because the test returned early on a live entry
rather than asserting the opposite. Overstating the bar is the worse direction, so that is the
direction that most needed the assertion.

## The prose-grep trap, four times, fixed structurally

The first version of the fix left `is not done` inside its own correction sentence, and the new test
failed on it — correctly.

| | where the check matched the correction instead of the claim |
|---|---|
| D-121 | `fetch-ffmpeg.sh` *explains* `--fail` in a comment |
| D-139 | the gate workflow *quotes* `-e '.[dev,media]'` to say what it replaced |
| D-141 | the audit report's correction *names* the entry point it had omitted |
| D-143 | the README *quotes* "is not done" while correcting it |

One `claims_only()` helper now strips `**Corrected …**` / `**Amended …**` spans, and both
documentation checks read through it. The convention that causes the trap is worth keeping — quoting
the wrong sentence is what makes the record readable — so what changed is that checks read claims.

**The helper's own first version was wrong too:** it dropped whole paragraphs, which emptied the
audit report's entry-point list, because README puts corrections in their own paragraph while
AUDIT_REPORT and PROGRESS put them mid-bullet after the claim. It cuts at the marker now.

Gate: `VERIFY OK — hawedit gate green`, 1419 tests.
