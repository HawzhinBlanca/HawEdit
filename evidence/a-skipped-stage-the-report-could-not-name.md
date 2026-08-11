# A stage could be skipped and the report would not name it

M2.7's deliverable is *"End-to-end runner: one command over §3, **reporting every stage it could
not run**"*. `PipelineRun.skipped()` is what that sentence means in code, and it was a
hand-written tuple of nine stages sitting beside the dataclass it describes.

## Measured: `delivery` could be deleted from that list with the suite green

```
CAUGHT    skipped() no longer lists visual_index    (3 tests)
CAUGHT    skipped() no longer lists discovery       (3 tests)
CAUGHT    skipped() no longer lists editorial       (2 tests)
SURVIVED  skipped() no longer lists delivery        (0 tests)

3/4 caught by the suite as it stands
```

## What that costs, on the report a reader is handed

The same `PipelineRun`, with the render and delivery stages skipped, under the list as shipped
and with `delivery` removed from it:

```
fields of PipelineRun currently holding a StageSkipped:
  ['render', 'delivery']

with the list as shipped:
  ['render', 'delivery']
  complete: False
  report  : run is INCOMPLETE — 2 stage(s) did not run

with 'delivery' absent from the hand-written list:
  ['render']
  complete: False
  report  : run is INCOMPLETE — 1 stage(s) did not run

  the delivery stage is still skipped : True
  its reason is reachable in the report: False
  blocked_by that no longer reaches a reader: ('§2 delivery set',)
```

**This was never an exit-code defect, and it is recorded that way.** `complete` separately
requires `isinstance(self.delivery, Delivery)`, which a `StageSkipped` fails, so the CLI still
exits 1. What is lost is the *naming*: the count is short by one, the stage is not named, and
`blocked_by=('§2 delivery set',)` — the half a reader acts on — reaches nobody. §1 of that module
is **fail visible, not silent**; an unnamed failure is the silent case.

## Why `delivery` and not the other three

`complete` is eleven conjuncts, and for two stages the evidence it checks is a *different field*:
`visual_index` is covered by `bool(self.visual_windows)` and `discovery` by
`bool(self.candidates)`. Those two are load-bearing in `ordered`, and the suite holds them.
`delivery` has a direct `isinstance` conjunct, so `complete` stayed correct without the list —
which is exactly why nothing noticed the list was wrong.

## The fix: derive it, do not guard it

```python
return tuple(
    (field.name, value)
    for field in fields(self)
    if isinstance(value := getattr(self, field.name), StageSkipped)
)
```

Field declaration order **is** pipeline order, so the derived sequence is the one the list spelled
out — verified, the same `['render', 'delivery']` — and a stage added to the dataclass later
cannot be forgotten here. The defect becomes unconstructible rather than guarded: there is no
list to delete an entry from.

## Mutation audit — 3/3 lint-clean, and a control that must stay green

```
baseline: lint+format clean: True   pytest exit: 0

CAUGHT    the defect restored: the shipped list with delivery deleted from it
            test_a_skipped_stage_in_any_field_is_named_in_the_report
            test_the_report_counts_every_skipped_stage_it_names
CAUGHT    the derivation reports only the first skipped stage            (4 tests)
CAUGHT    the derivation drops the blocked_by it carries                 (3 tests)
green     CONTROL — the shipped list, unchanged (must stay green)        (0 red)

3/3 caught lint-clean
```

The pre-fix text is `git show HEAD:`, not retyped, so the restored defect is byte-for-byte what
shipped. **The control matters as much as the catches:** the complete hand-written list is
behaviourally identical to the derivation, and it stays green — so the new tests pin the
property, not this particular implementation of it.

## Two contaminated runs of mine, discarded rather than counted

The first sweep hand-wrote the pre-fix method and both it and the control came back **lint/format
dirty**, reddening the four gate-as-subprocess tests — measuring ruff, not the report. Rebuilt
from git, they were *still* dirty: restoring the list orphans the new `fields` import and F401
fires. The import is reverted alongside the method now. Third time this pattern has cost a run in
this session (D-148, D-150 record it); the fix is always the same — mutate the state and
everything that only exists to serve it.

## Also probed this iteration and disproved, rather than assumed

* **§8.1's metrics (M0.5) are correct and well held.** `edit_distance` against a breadth-first
  search over the edit graph: **7,225 pairs, 0 mismatches**. `substring_edit_distance` against the
  minimum over every substring: **4,840 pairs, 0 mismatches**. Six plausible defects — substitution
  cost, the deletion branch, the free prefix, the free suffix, the CER denominator, one-sided
  whitespace stripping — were **6/6 caught** by the suite as it stands. Nothing to add there, and
  adding an oracle for its own sake would have been busywork.
