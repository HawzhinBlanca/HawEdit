# The delivery block could not catch the exception introduced one commit earlier

D-165 (the previous iteration) added `UndeliverableOrder` and had `build_srt` raise it. The
delivery block that calls `build_srt` catches an explicit tuple:

```python
except (DeliveryError, RenderError, OSError) as exc:
```

`UndeliverableOrder` is a `ValueError`. So is `DeliveryError`. They are **siblings**, not parent
and child — so the new exception was not in the tuple and could not be caught by it.

## Measured against the real tuple, not inferred from the class names

```
DeliveryError MRO      : ['DeliveryError', 'ValueError', 'Exception', 'BaseException']
UndeliverableOrder MRO : ['UndeliverableOrder', 'ValueError', 'Exception', 'BaseException']
issubclass(UndeliverableOrder, DeliveryError): False

delivery handler: ESCAPES -> no cleanup, no named gap
```

The last line is the tuple copied verbatim from `pipeline.py` with the exception raised against
it. What escaping costs, from the block's own comments:

* the `for path in (...): path.unlink(missing_ok=True)` cleanup that keeps the delivery set
  **all-or-none** — D-072's whole subject, "four fifths of a delivery set that looked whole";
* the `StageSkipped(..., blocked_by=...)` that reports the gap by name;
* and it propagates out of a stage written to refuse gracefully.

## Reachability, stated honestly

**It was latent, not live.** `build_ass` runs first, on the *same* `selected` sentences, and its
handler catches `ValueError` — so an undeliverable sequence is refused there and the delivery
block is never reached with one. The pipeline could not hit this today.

That is an **ordering guarantee, not an exception contract**. It survives only while `build_ass`
precedes `build_srt` and keeps its broad `except ValueError`; the delivery block's own comment
records that these statements were already reordered once (D-072), for a different reason.

Recorded rather than dressed up: no wrong output shipped, and a defect I introduced one commit
earlier was reachable by an innocuous edit.

## The fix, and the guard that would have caught it

The handler now names the type. The durable half is
`test_the_delivery_handler_catches_everything_its_builders_refuse_with`, which reads the `except`
clause **out of `pipeline.py` by AST** — the tuple actually protecting the five writes, not a copy
of it elsewhere — and requires every type the three builders raise for bad input to appear in it.

## Mutation audit — 1/1 on the defect, and two results I will not count

```
baseline green: True
CAUGHT    the defect restored: the handler drops UndeliverableOrder
           red (1): test_the_delivery_handler_catches_everything_its_builders_refuse_with
CAUGHT    the handler drops DeliveryError instead                    [LINT DIRTY]
CAUGHT    the handler is widened to bare Exception                   [LINT DIRTY]
SURVIVED  the sibling control is dropped
3/4
```

**The one that matters is clean.** Restoring the exact defect — the handler without
`UndeliverableOrder`, import removed so nothing lints dirty — reddens the new test and nothing
else. That is the bug this commit fixes, caught by the guard written for it.

**Two catches are not trustworthy and are not claimed.** Dropping `DeliveryError` orphans its
import, and the bare-`Exception` mutation does not satisfy ruff either; both reddened the
gate-as-subprocess tests, so those results partly measure ruff (D-148, D-150). They also reddened
real tests — `test_a_refused_edl_leaves_no_partial_delivery_set` — so the coverage is probably
genuine, but "probably" is not a measurement and they are recorded as contaminated.

**The survivor is honest and stays.** The sibling assertion is *documentation, not a control*:
deleting it measures nothing because the state it would catch — one of the two subclassing the
other — cannot be constructed. `sentences.py` cannot import `DeliveryError` without a cycle, since
`delivery.py` imports `sentences`. Counting it as a guard would be the "mutating a test in
isolation" mistake this loop keeps finding (D-149, D-155, D-156, D-157, D-161, D-162); the
comment beside it now says what it is.
