# `from_dict` defers to a gate that does not check that field

> Measured 2026-08-13 on HawaPC01 against `3b83897`, by reading the three functions and
> confirming the range check exists on exactly one of the two routes.

`Boundary` has two construction routes and one documented validator between them.

`src/hawedit/boundary.py:266-267` — the construction route, which does check:

```python
if confidence is not None and not 0.0 <= confidence <= 1.0:
    raise ValueError(f"confidence must be within [0, 1], got {confidence}")
```

`Boundary.from_dict` — the rehydration route, which deliberately does not, and says so:

```python
"""Rebuild from §5 JSON. Does **not** validate — call the render gate explicitly."""
```

That is a reasonable division of labour, and the docstring names where the checking is supposed to
happen. The problem is that it does not happen there. `assert_boundary_invariant`
(`boundary.py:152-181`) is the render gate the docstring points at; it raises
`BoundaryInvariantViolated` in three places, and **none of them concerns `confidence`**:

```
$ grep -n "def assert_boundary_invariant" -A 30 src/hawedit/boundary.py | grep "confidence\|raise"
  167-        raise BoundaryInvariantViolated(
  175-        raise BoundaryInvariantViolated(
  181-        raise BoundaryInvariantViolated(
  (no line matching 'confidence')

$ grep -rn "confidence" src/hawedit/boundary.py | grep -E "raise|<|>"
  266:    if confidence is not None and not 0.0 <= confidence <= 1.0:
  267:        raise ValueError(...)
```

So a `Boundary` rebuilt from a §5 sidecar carrying `confidence: -3.0` — or `5.0` — passes every
check the design names for it. The value round-trips through `to_dict()` unchanged.

## What this is and is not

It is **not** a live wrong-cut: `confidence` does not participate in choosing `final_in_ms` or
`final_out_ms`, and BLUEPRINT §5 consumers that re-check it (`Editorial.__post_init__`,
`clip.py:210-214`) would still refuse a shipped clip. It is a documented contract pointing at a
checker that does not perform the check, which means the guarantee "the render gate validates a
rehydrated boundary" is true for the anchor arithmetic and false for this field.

The cheap fix is one conjunct in `assert_boundary_invariant`, making the docstring's promise true.
The cheaper non-fix is amending the docstring to say which fields the gate covers. Either is a
decision, not a bug fix, and belongs in a spec.

## Provenance and a caution about the batch this came from

Surfaced by an automated guard-revert sweep of `src/hawedit/` that returned 18 "confirmed"
findings against only 2 refuted — a discrimination ratio far weaker than the same harness's
earlier run over `scripts/` (18 of 24 refuted). Spot-checking three of the eighteen found their
titles overstate severity: `reframe.py`'s `sample_fps` and `smoothing` findings are written as
live defects ("the wrong crop centre is burned into the encode") when
`OpenCvFaceTracker.__init__` already refuses both at construction — those are *guards with no
test*, which is a real and useful class, but not the same claim.

This file records the one item in that batch that survived independent checking as a genuine
inconsistency rather than a coverage gap.

## Not measured

Which callers use `Boundary.from_dict` in production rather than in tests, and therefore whether
an out-of-range confidence can reach a sidecar in a real run; whether `to_dict`/`from_dict` is used
on any path that re-renders. The other 17 findings in the batch were not independently verified.
