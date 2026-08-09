# The gate's own self-poisoning fix was described at length and held in place by nothing

> Measured 2026-08-09 on hawapc01 against `e689297`, against a green 1,164 baseline.

`gate.py` records the bug and its fix in the code:

> Ratcheting on `collected` while gating on `passed` made the gate poison itself â€” one legitimately
> skipped test (a symlink a Windows account may not create) collected 873 and passed 872, so the
> first run raised the floor to 873 and every run after it was refused for missing a bar the
> previous run invented. Two floors, one job, and they disagreed on any host with a skip.

## Measured

Substituting `collected` for `passed` in the ratchet, counts read from a JUnit report rather than
from a summary line:

```
baseline: collected=1164 skipped=0 failures=0 errors=0 passed=1164
mutated:  collected=1164 skipped=0 failures=0 errors=0 passed=1164
```

The suite genuinely ran and genuinely did not notice. Two reasons, and the second is the interesting
one:

* Every ratchet test used a report with `skipped=0`, where `passed == collected` by construction. The
  tests were correct and could not tell the two numbers apart â€” the same shape as D-095, D-098 and
  D-126.
* **This host skips nothing.** So the defect is invisible precisely here and fires on a machine where
  something legitimately skips â€” a box without the pinned ffmpeg, or CI if the golden render ever
  starts skipping. A regression would land on somebody else's machine.

What it does, run directly against the 873/872 numbers from `gate.py`'s own comment:

```
a host with one skip: collected=873 skipped=1 passed=872
  floor after run 1 (correct, ratchets on passed): 872
  run 2 on the SAME report: accepted

  if the ratchet had written `collected` instead: floor=873
  run 2 on the SAME report: REFUSED â€” only 872 tests passed against a floor of 873
```

The gate refuses the very run that set its bar. Computed and discarded, not never-computed: `passed`
is a property and is correct; nothing checked which number reached the file.

## The fix

Three tests, and the middle one is the point:

* **The idempotence property** â€” a green run must never leave the gate refusing an identical one.
  This needs no knowledge of which number is right: a ratchet on `collected` fails it and a ratchet
  on `passed` cannot. It is the failure exactly as it happened.
* The direct assertion, on the **artifact** â€” the committed floor file reads 872, not 873.
* The control â€” with no skips the floor must reach the full count, so "ratchet on `passed`" is not
  read as "ratchet lower than collected", which would stop the gate noticing deletions.

## A structural change tried and backed out

I first bound `ran = evidence.passed` and used it at both sites, on the reasoning that one name makes
"gate on one, ratchet on the other" unexpressible. It is not: `ran = evidence.collected` is the same
one-word edit, so the rename only moves the single point. It also broke
`test_the_readme_describes_the_gate_floor_as_tests_that_passed`, which asserts the literal
`if evidence.passed < floor:` in the source to keep the README's wording honest (D-069).

The audit settled it. **Mutation 3 below is caught by that source-text test alone** â€” so the rename
would have paid a real protection for a cosmetic gain. `gate.py`'s diff in this commit is comment-only.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the ratchet writes `collected` (the defect gate.py describes)      FAILED=2
CAUGHT   the ratchet writes `collected` on every run, not only growth       FAILED=2
CAUGHT   the gate compares `collected` instead (the other half of the pair) FAILED=1
CAUGHT   the ratchet never fires (growth is never recorded)                 FAILED=4
CAUGHT   the floor is ratcheted one below what ran (over-lax)               FAILED=4

5/5
```

The last is the over-lax direction: a floor one below what ran leaves room for a test to vanish
between two green runs, which is the whole purpose of the ratchet. It is caught by four tests, so
unlike D-097/088/090/091 the new control is not the only witness here â€” the existing ratchet tests
already covered downward drift. What they could not see was *which of two equal numbers* was being
written.

Gate: `VERIFY OK â€” 1167 passed, 0 skipped`.
