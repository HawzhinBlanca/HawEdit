# A blank named-entity annotation scored 0.0 — the same value as a name transcribed perfectly

> Measured 2026-08-09 on hawapc01 against `ba3ea36`, against a green 1,125 baseline.

`""` is a substring of every string, so `normalize_sorani(entity) not in normalized_hypothesis`
is `False` for a blank entity — it counted as a name that **survived**. In this metric's scale
`0.0` means *found*, so an annotated item with a blank label reported perfect named-entity
accuracy.

Two sibling metrics in one module treated the identical corpus defect oppositely:

```
named_entity_error_rate:                      code_switch_error_rate (the sibling):
  empty hyp, empty entity        -> 0.0         -> ValueError: empty code-switch span …
  real hyp, empty entity         -> 0.0         -> ValueError: empty code-switch span …
  real hyp, whitespace entity    -> 0.0         -> ValueError: empty code-switch span …
  real hyp, real entity present  -> 0.0         -> 0.0
  real hyp, real entity absent   -> 1.0         -> 0.714…
```

## Reachable through the production type, not just by calling the function

```python
CorpusItem(item_id="ne-1", audio_path="a.wav", reference_ckb="سەرۆک لە شار بوو",
           dialect=Dialect.HEWLER, conditions=frozenset({Condition.NAMED_ENTITIES}),
           duration_s=10.0, named_entities=("",))
```

constructs without complaint — `__post_init__` only requires the tuple to be non-empty — and
scores `0.0`. So a labelled item marked as carrying named entities, with one blank label, inflated
§8.1's accuracy silently. This is the third time "unmeasured is None, never 0.0" has been broken in
a metric (D-077 `path_unique_wins`, D-080 `iou_match`/`k`, this).

**The distinction the fix had to preserve:** an *empty tuple* is "nothing was annotated" and
correctly returns `None`. A blank entry *inside* the tuple is malformed data. Those are different
facts and now have different answers — `None` and a refusal.

## The fix is the rule the sibling already had, extracted

`_normalized_annotation(value, kind)` normalizes one annotated span and refuses an empty result.
Both metrics call it. Nothing was invented: the message shape is the sibling's, so its existing
behaviour is unchanged, and a third metric added later has an obvious thing to call.

```
ne empty entity        -> ValueError: empty named entity after normalization …
ne whitespace          -> ValueError: empty named entity after normalization …
ne nothing annotated   -> None
ne real present        -> 0.0
ne near-miss           -> 1.0
cs empty span          -> ValueError: empty code-switch span after normalization …
cs real span           -> 0.0
```

Putting the same check in `CorpusItem.__post_init__` was considered and not taken: the metric is
the last common point every scoring path passes through, and a caller can build an entity tuple
from anywhere. One guard, at the funnel.

## D-008's fourth choice was claimed as tested and was not

D-008 records four definitional choices and closes with *"All four are testable choices, not
conventions to remember: see `tests/test_metrics.py`."* Three were tested. The fourth —
*"Matching is exact after §4.1 normalization … a name 90% right is still the wrong name in a
burned-in caption … Strictness here is deliberate"* — had no test. The behaviour was **already
correct** (`بارزانا` against annotated `بارزانی` scores 1.0); it was simply revertible, and the
mutation replacing exact matching with a 0.34 fuzzy threshold would have made a wrong name score
0.0.

Now pinned in both directions, which matters because either alone is satisfiable by a wrong
implementation:

* a near-miss and a truncation each score `1.0` — strictness holds;
* an Arabic-keyboard `كوردي` against Kurdish `کوردی` still scores `0.0` — so "strict" cannot be
  implemented as byte equality, which the mutation *"strictness becomes byte equality"* confirms is
  caught.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   the blank-annotation refusal is removed (the original defect)
CAUGHT   named entities stop going through the shared guard
CAUGHT   code-switch spans stop going through the shared guard
CAUGHT   an empty tuple starts raising instead of returning None
CAUGHT   exact matching is loosened to a fuzzy near-miss (D-008's fourth choice)
CAUGHT   strictness becomes byte equality, breaking the keyboard-difference control

6/6
```

**It was 5/6 first, and the survivor found a second unprotected guard.** Removing the *code-switch*
refusal — the one implemented correctly all along — left the suite green, because nothing had ever
tested it. So the metric that got this right was exactly as revertible as the metric that got it
wrong; only its behaviour differed, not its protection. One test closed it, and both call sites of
the shared guard are pinned.

Two of the six are caught only by controls: *"an empty tuple starts raising"* and *"strictness
becomes byte equality"* would each pass every refusal test in this file while breaking honest
input.

Gate: `VERIFY OK — 1130 passed, 0 skipped`.
