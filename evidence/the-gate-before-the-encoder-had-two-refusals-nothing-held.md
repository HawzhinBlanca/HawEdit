# The gate before the encoder had two refusals nothing held

A guard-revert sweep over `clip.py` — the module whose dict *is* the §5 client sidecar, and whose
`assert_renderable()` is the gate `render_clip` calls before it starts an encoder. D-149's method:
every `raise` located by parsing rather than by grep, replaced one at a time with `pass` at the same
indent, `ruff format`ed, the whole suite run each time against a baseline verified green first, file
restored byte-identical after each.

```
baseline: GREEN (1633 passed)
clip.py: 15 refusals

held 11/15, unheld 4, gate-only 0
  UNHELD 314: output durations must be positive seconds
  UNHELD 352: qc.flags must be a tuple of non-empty strings
  UNHELD 473: clip has no editorial block: it was never judged
  UNHELD 479: clip has no output block — no title, crop target or caption style

file restored byte-identical: True     suite after restore: GREEN
```

**No production code changed.** All four refusals were already there and already correct. What was
missing was anything that would notice their removal.

## `assert_renderable` was half-covered

```python
if self.qc is None:                                   # held, by 11 tests
if not (self.qc.auto_pass or self.qc.human_reviewed): # held, by 3
if self.editorial is None:                            # HELD BY NOTHING
if self.output is None:                               # HELD BY NOTHING
```

Its docstring says *"§8.3 requires this on every shipped clip"*, and the two halves nobody held are
the judge's. A clip with no editorial block has no meaning-fidelity and no misleading-edit score —
the number §8.2 calls the one that matters for a media organisation — and a clip with no output
block has no title, crop target or caption style to render with. Either could have reached ffmpeg
if the check were refactored away, with the whole suite green.

The two that *were* held are the QC ones, and that is the shape worth noticing: the guards written
under "audit finding #3" got tests, and the two added beside them in the same function did not.

## The sweep's third outcome

This harness reports `GATE` separately from `HELD`: a mutation whose only failures are
`test_gate.py`'s four subprocess tests has been caught by the real `verify.sh`'s lint or typecheck
step, not by anything behavioural. Three times earlier in this session a lint-dirty mutation sat in
a CAUGHT list next to a genuine defender and read as coverage. **On `clip.py` there were none** —
`gate-only 0` — so the 11 held are all held by named tests.

## Each new test carries its control

* the unjudged clip asserts `qc.auto_pass` **first**, so it cannot pass on the QC refusal one line
  above the one under test, and the same fixture with its editorial block renders;
* the output-block test asserts `editorial is not None` for the same reason;
* the duration test accepts §5's own `(15, 30, 60)` after refusing `(0,)`, `(-15,)` and
  `(15, 0, 60)`, so it measures the sign and not a constructor that refuses everything;
* the `qc.flags` test accepts `("needs_review",)` and the empty tuple that honestly means
  "nothing flagged".

The flags test also covers a case worth naming: `flags="not a tuple at all"` must be refused, and
the `isinstance(self.flags, tuple)` half is what does it. Without that half, `any(...)` would
iterate the string **character by character** and accept it, because every character of a non-empty
string is itself a non-empty string.

## Mutation audit — 4/4, lint-clean

```
baseline: GREEN (1637 passed, 86 warnings in 146.87s)

CAUGHT   line 314: a non-positive output duration is no longer refused
         by 1: test_a_non_positive_output_duration_is_refused
CAUGHT   line 352: qc.flags stops having to be a tuple of non-empty strings
         by 1: test_qc_flags_must_be_a_tuple_of_non_empty_strings
CAUGHT   line 473: a clip the judge never scored becomes renderable
         by 1: test_a_clip_that_was_never_judged_is_not_renderable
CAUGHT   line 479: a clip with no title or crop target becomes renderable
         by 1: test_a_clip_with_no_output_block_is_not_renderable

file restored byte-identical: True
4/4 caught
suite after restore: GREEN
```

Each mutation replaces the `raise` alone — the sweep's own form — so the surrounding `if` survives
and ruff stays quiet. Every guard is caught by exactly the one test written for it, and by no gate
test.

## Where the sweeps stand

| module | refusals | held | found |
|---|---|---|---|
| `delivery.py` | 12 | 12 | — |
| `credentials.py` | 10 | 6 | a refusal that named the state it had already created (D-191) |
| `render.py` | 11 | 8 | a failed encode nothing would have missed (D-194) |
| `clip.py` | 15 | 11 | two halves of the pre-encoder gate (this) |

Every module that builds or ships the deliverable has now been swept once.
