# §8.1's coverage grid certified itself, and the hours floor answered to nothing

> Measured 2026-08-09 on hawapc01 against `0347df5`, against a green 1,131 baseline.

## First, a negative result worth recording

Three separate violations of *"unmeasured is None, never 0.0"* had been found in metrics (D-077
`path_unique_wins`, D-080 `iou_match`/`k`, D-083 the blank named entity). Three in one module family
stops looking like coincidence, so every metric was swept rather than waiting for a fourth.

**No fourth instance exists.** All fifteen public metric functions answer the unmeasured case
correctly:

```
named_entity_error_rate(hyp, ())        -> None
code_switch_error_rate(hyp, ())         -> None
misleading_edit_rate(())                -> None
sentence_completeness_rate(())          -> None
recall_at_k((), ())                     -> None
recall_at_k_by_path((), ())             -> {}     (the mapping signal, D-077)
path_unique_wins((), ())                -> {}
pairwise_preference(())                 -> {}
cer / normalized_cer / spacing_free_cer -> ValueError: empty reference …
cost_per_source_hour(_, 0.0)            -> ValueError: source_hours must be positive …
wallclock_per_source_hour(_, 0.0)       -> ValueError: source_hours must be positive …
temporal_iou((0,0),(0,0))               -> ValueError: span (0, 0) has no length
```

And the branches are **protected**, not merely correct — which was the real question, since all
three earlier instances looked right until mutated:

```
baseline: GREEN
CAUGHT   named_entity_error_rate returns 0.0 when nothing was annotated
CAUGHT   code_switch_error_rate returns 0.0 when nothing was annotated
CAUGHT   recall_at_k returns 0.0 when there is no gold winner
CAUGHT   misleading_edit_rate returns 0.0 when nothing shipped
CAUGHT   sentence_completeness_rate returns 0.0 when nothing shipped
CAUGHT   recall_at_k_by_path returns a zero per path instead of {}

6/6
```

The class is closed. Nothing was changed for it, because there was nothing to change.

## What the same pass did find: the grid certified itself

`tests/test_corpus.py` contains **zero** references to `BLUEPRINT.md`. It compared the `Dialect` and
`Condition` enums against literal sets typed into the test file:

```python
assert {d.value for d in Dialect} == {"hewler", "slemani", "mukriyan"}
assert {c.value for c in Condition} == {"formal_news", "casual_podcast", …}
```

`tests/test_registry.py` has parsed §7 out of the frozen blueprint from the beginning and asserts
set equality both ways. §8.1 never got that treatment, while M0.6's row claims *"(3 dialects × 7
conditions)"* implements §8.1's list. If §8.1 gained a category, the enum and the test would agree
with each other and both be wrong.

§8.1's coverage line parses cleanly:

```
'Several hours across: **Hewlêr · Slemani · Mukriyan · formal news · casual podcast ·
 Kurdish–English and Kurdish–Arabic code-switching · noisy environments ·
 overlapping speakers · named entities and political terminology.**'

dot-separated items: 9
```

**Nine items against a seven-member enum, and that gap is the whole reason the mapping is
explicit.** "Kurdish–English and Kurdish–Arabic code-switching" is *one* §8.1 phrase covering *two*
enum members. That is precisely the shape of §4.1's single "Numerals" row covering three numeral
systems — the shape that made M0.3 claim five collisions were handled when four were (D-076).
Comparing `len(items)` to `len(Condition)` would have reproduced that error exactly.

So each §8.1 phrase is mapped to the set of members it covers, and set equality is asserted both
ways: a category §8.1 adds has no mapping and fails; an enum member no §8.1 phrase covers fails too.

## And the hours floor answered to nothing

`MINIMUM_HOURS = 3.0` is D-009's recorded judgment — *"the smallest quantity 'several' honestly
describes"*. `grep -rn MINIMUM_HOURS tests/` returned **no matches**: the constant was referenced by
no test at all, so the code could drift from its own decision record. Changing 3.0 → 1.0 left the
whole suite green.

The value is now parsed out of D-009's heading rather than retyped in the test, so changing the floor
requires amending the record — which is the point of recording it.

```
floor 3.0 -> 1.0
FAILED tests/test_corpus.py::test_the_hours_floor_matches_the_decision_that_records_it
```

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   a §8.1 phrase loses its mapping
CAUGHT   the code-switch phrase maps to only one of its two members
SURVIVED the blueprint parse is replaced by a retyped literal list
CAUGHT   §8.1 gains an eighth condition (the case this exists for)
CAUGHT   §8.1 gains a fourth dialect

4/5   plus the hours-floor drift above, caught
```

The two blueprint mutations are the ones that matter — they are the scenario the change exists for,
and both now fail where before they were invisible.

**The survivor is the same neutral class as D-078's.** Replacing the parse with a retyped literal
list changes nothing observable while `BLUEPRINT.md` is frozen; it would only diverge if §8.1
changed, which the freeze forbids. Reported rather than papered over with a test about
implementation.

**BLUEPRINT.md is frozen and was touched in this audit.** Two mutations edit it to simulate §8.1
growing, which is the only way to measure the property. It is restored in a `finally` and verified
two ways: `sha256 before=b7e05d219be4e527 after=b7e05d219be4e527 IDENTICAL`, and
`git status --porcelain BLUEPRINT.md` empty afterwards.

## What was left alone

The two literal-set tests are kept alongside the parsed ones. They are not redundant: the parsed
test checks enum *membership* against §8.1, while the literal tests pin the enum's `.value` strings,
which the serialized corpus manifest depends on. Removing them would also have required lowering the
test-count floor, which the hard rules forbid doing casually.

Gate: `VERIFY OK — 1134 passed, 0 skipped`.
