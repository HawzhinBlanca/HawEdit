# A recorded threshold could drift from the decision that justifies it, with the suite green

> Measured 2026-08-09 on hawapc01 against `3efd912`, against a green 1,170 baseline.

D-084 pinned one constant to its record — `MINIMUM_HOURS` against D-009 — after measuring that 3.0
could become 1.0 unnoticed. This asks the same question of every constant, because the failure looked
like a class rather than a case.

## Measured — what notices a drift, and why

Changing the constant alone, nothing else:

```
DEFAULT_PAUSE_MS          500 -> 800           GREEN, nothing noticed
NVENC_MIN_FRAME       (145,49) -> (64,64)      GREEN, nothing noticed
DEFAULT_DISAGREEMENT_CER 0.15 -> 0.25          RED, 2 tests — behaviour only
MINIMUM_HOURS             3.0 -> 1.0           RED, 1 test — the record pin D-084 added
```

Two of the four are completely unprotected, and each is instructive for a different reason.

**`NVENC_MIN_FRAME → (64, 64)` is exactly the value D-045 records as the historical defect** — the
probe size that made `encoder_available` report a working NVENC unavailable on the one machine §6 puts
it on. Restoring the bug's own number changed nothing the suite could see, because `test_render.py`
asserts the *relation*:

```python
assert ENCODER_PROBE_SIZE[0] >= NVENC_MIN_FRAME[0]
assert ENCODER_PROBE_SIZE[1] >= NVENC_MIN_FRAME[1]
```

which holds at 1080×1920 against any small pair. The relation is the right assertion, and it cannot
pin the recorded measurement. Stated plainly: drifting this constant has no behavioural effect today,
because the probe runs at the output size regardless — what would rot is D-045's recorded measurement
of what NVENC actually refuses, which is the number a future reader would reach for.

**`DEFAULT_PAUSE_MS → 800` was invisible for a reason worth naming.** Every pause test passes
`pause_ms=DEFAULT_PAUSE_MS`:

```python
sentences = segment_sentences(aligned, pause_ms=DEFAULT_PAUSE_MS)
```

so the tests follow the constant wherever it goes and never assert what it is. Symbolic use reads as
coverage and measures nothing — the same shape as D-094's substring assertion and D-095's `skipped=0`
reports. This one *does* change behaviour: it decides where a transcript with no punctuation is split.

## The fix

**One test, not one pin per constant.** Every `<constant> = <value>` a decision states in a code span
must equal what the code holds; later statements supersede earlier ones. Only 4 such statements existed
(D-009, D-014, D-015, D-045), so D-098 restates three more in canonical form, quoting the entries that
gave them in prose only — `MATERIAL_GAIN_RATIO = 0.10` (D-010's "≥10% relative reduction"),
`DEFAULT_IOU_MATCH = 0.5` (D-020's "IoU ≥ 0.5"), `RETRIEVE_K = 50` (D-090's "§3's depth of 50") — plus
`DEFAULT_TOLERANCE_MS = 50`, which had **no decision at all** and lived only in a code comment.

**A behavioural pin for the pause threshold**, since a record check proves the number is recorded and
not that it is in force: a 500 ms gap must split and a 499 ms gap must not, with literal values.

Two self-inflicted findings while writing this, both kept in the record because they are the same
class of error the check exists for:

* The `>= 7` floor on the number of discovered statements **fired for real**: the first run of the test
  found 4 and refused to pass on a scan that examined almost nothing.
* D-098's own prose spelled the placeholder in the real form, so the check read its own documentation
  as a statement about a constant named `NAME`. The document was reworded rather than the check
  special-cased.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   DEFAULT_PAUSE_MS drifts from D-014                       FAILED=2
CAUGHT   NVENC_MIN_FRAME back to D-045's historical bug value     FAILED=1
CAUGHT   MATERIAL_GAIN_RATIO drifts from D-098's record           FAILED=2
CAUGHT   the discovery regex matches nothing                      FAILED=1
SURVIVED the `>= 7` floor is removed                              FAILED=0

4/5
```

The survivor is not a hole, and saying so precisely matters. Removing a tripwire is unobservable while
the thing it guards against has not happened: with the regex intact and the values matching, the floor
has nothing to fire on. Any test that would catch its removal would be asserting the same property
twice, which is the redundancy D-079 warns inflates a finding count. Mutation 4 is the proof the floor
works — the two together are the pair that matters, and the repo's standard is single-mutation
auditing, so this is recorded as a neutral survivor in D-078's sense rather than as protection.

`NVENC_MIN_FRAME` is caught by exactly one test — the new record check — which is the whole point:
nothing else in the suite can see that number change.

Gate: `VERIFY OK — 1172 passed, 0 skipped`.
