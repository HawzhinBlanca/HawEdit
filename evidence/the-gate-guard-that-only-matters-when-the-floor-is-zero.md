# The gate guard that only matters when the floor is zero

> Measured 2026-08-10 on hawapc01 against `c47ae49`, Python 3.11 in `.venv`.

M0.1 — *"Package skeleton + gate script; gate refuses a no-op command instead of printing green"* —
is **DONE**, 12,279 characters of claims, and the largest row never attacked as a whole. It is also
the row everything else rests on.

## The sweep

Each of the gate's nine refusals disabled in turn, against a baseline verified green first, whole
suite each time, with lint checked per mutation so a mutation that only breaks ruff is visible as
such:

```
baseline green: True

CAUGHT    a missing report is accepted
CAUGHT    a stale report from an earlier run is accepted
CAUGHT    a report collecting 0 tests is accepted
CAUGHT    failures are only refused when there are errors too
SURVIVED  a suite that skipped every test is accepted
CAUGHT    a count below the committed floor is accepted
CAUGHT    the floor stops ratcheting, so growth is never recorded
CAUGHT    a tool from outside this interpreter's environment is accepted
SURVIVED  a report with no testsuite element is accepted as evidence

7/9
restored and green: True
```

## The real gap

`gate.py` carries this, with the reason in a comment above it:

```python
if evidence.passed == 0:
    raise NoTestEvidence(... "A suite that skips itself is not a passing suite.")
```

> A report of 700 collected, 0 failures, 0 errors and 700 *skipped* cleared every check this
> function had, and `verify.sh` printed VERIFY OK with zero test bodies executed.

Replacing it with `passed < 0` left all 1,503 tests green. Every existing test supplies a non-zero
floor, and at a non-zero floor the **floor** check refuses first, so the guard never gets a turn.
The state where it is the only refusal left is a floor of 0 — what `read_floor` returns for a
missing or empty file. Measured with the guard neutered:

```
floor missing (0)    ACCEPTED — collected 700, skipped 700, passed 0
floor = 1503         refused by the floor
```

Unmutated, the gate refuses in every floor state. So the guard is correct; it was simply never
exercised where it is load-bearing.

## The fix

Three states, all of which `read_floor` reads as 0 — floor file **missing**, **empty**, and
**whitespace-only** — each asserting the premise (`read_floor(floor) == 0`) before asserting the
refusal, so the test cannot pass because the floor quietly refused instead.

The control is the other half: a healthy report of 700 collected with **one** legitimate skip must
be accepted at a zero floor *and* ratchet the floor to **699** — what actually ran. A gate that
refused every zero-floor run, or every report with any skip in it, passes all three refusal cases
and fails this one. It also re-pins D-095's collected-versus-passed distinction from the other
side.

## The second survivor is a bad mutation

Removing `if not suites:` accepts nothing. `total()` sums an empty list, `collected` becomes 0, and
the next guard refuses. Measured:

```
still refused, by the next guard: check testpaths, a stray -k filter, or a collection error.
```

Only the message changes. Pinning it would fail on an intentional rewording and catch nothing —
D-072's rule. Recorded, not pinned. Seventh bad mutation of mine this session after D-137, D-141,
D-144, D-147, D-149 and D-155.

## Proof

```
8/9 after
```

the ninth being that bad mutation. No production code changed — `gate.py` is byte-identical.

Gate: `VERIFY OK — hawedit gate green`, 1507 tests (floor 1503 → 1507).
