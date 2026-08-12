# Whether a human reviewed the clip could leave the sidecar in silence

`Qc.to_dict` could stop emitting `flags` and `human_reviewed` — the review reasons, and whether a
human looked at the clip at all — and the **whole suite stays green**. Proven by deleting each one.

## Why a round-trip test did not catch it

`clip.py` pairs `to_dict` with `from_dict` for every block, and
`test_the_clip_round_trips_through_json` has always asserted `from_dict(to_dict(x)) == x`. That
catches a dropped field only when the field's value differs from what `from_dict` supplies in its
absence.

`a_clip()` leaves four optional fields at exactly their defaults. Measured, by deleting each emitted
key in turn and rebuilding:

```
--- Editorial: 9 keys ---
  payoff_at_ms         INVISIBLE — rebuilt object is unchanged, value None
--- Output: 6 keys ---
  hashtags_ckb         INVISIBLE — rebuilt object is unchanged, value []
--- Qc: 3 keys ---
  flags                INVISIBLE — rebuilt object is unchanged, value []
  human_reviewed       INVISIBLE — rebuilt object is unchanged, value False

keys whose removal no round-trip could notice: 4
```

This is the third instance of one defect. **D-101**: `Clip.to_dict` hardcoding
`DiscoveryPath.VERBAL.value` left five test files green, because `a_clip()` builds a verbal clip and
the round-trip compared "verbal" against "verbal". **D-181**: `AsrProvenance.adapter` was absent from
the hand-enumerated dict, and the delivered clip would have named stock weights whichever weights
read the words. Both were found by hand, one field at a time.

## Two of the four were held elsewhere

D-033's `test_the_projection_carries_both_fields_section_3_names_and_section_5_lacked` asserts
`payoff_at_ms` and `hashtags_ckb` explicitly, so those two were covered — by a test written for a
different reason, which is luck rather than design, but covered.

**`Qc.flags` and `Qc.human_reviewed` were held by nothing at all.** §2's diagram puts a human QC gate
before output *always*; `human_reviewed` is the field that records whether that happened. A sidecar
that stopped carrying it would read back as `False` for every clip a human had in fact approved.

## The fix is the round-trip that already existed, on a fixture that can fail it

`a_fully_populated_clip()` sets every optional field in all five blocks to a non-default value —
`payoff_at_ms=87_400`, `hashtags_ckb=("#کوردی", "#هەواڵ")`,
`Qc(auto_pass=False, flags=("low_confidence",), human_reviewed=True)`, `speaker="SPK_02"` — and the
round-trip runs against that, whole-clip and per-block so a failure names which block lost the
field.

A second test keeps the fixture honest: it asserts no field in it still carries its default. Without
that, a future edit could return the fixture to `a_clip()`'s values and the round-trip would go green
by **losing** coverage rather than gaining it. A check that stops measuring is worse than one that
fails.

## My first attempt was wrong, and the audit is what said so

The first version was a cleverer property: delete each emitted key in turn, and require the
round-trip to notice. It passed, it read well, and **it could not detect the defect it named**. It
iterated the keys `to_dict` *emits* — so a key that stopped being emitted was never examined at all.

The mutation audit said so unambiguously:

```
CAUGHT   Editorial stops emitting payoff_at_ms
         by 1: test_the_projection_carries_both_fields_section_3_names_and_section_5_lacked
CAUGHT   Output stops emitting hashtags_ckb
         by 1: test_the_projection_carries_both_fields_section_3_names_and_section_5_lacked
SURVIVED Qc stops emitting flags
SURVIVED Qc stops emitting human_reviewed
CAUGHT   the fixture falls back to the defaults, so the property measures nothing
         by 2: test_no_key_of_the_shipped_sidecar_can_vanish_unnoticed, …

3/5 caught
```

Two mutations survived, and the two that were caught name a **pre-existing** test rather than the
new one. The new test appeared in exactly one row — the mutation against its own fixture. It was
guarding itself and nothing else.

## Mutation audit — 5/5 after the rewrite

```
baseline: GREEN (1639 passed, 86 warnings in 142.50s)

CAUGHT   Editorial stops emitting payoff_at_ms
         by 2: test_the_fully_populated_clip_round_trips_through_json,
               test_the_projection_carries_both_fields_section_3_names_and_section_5_lacked
CAUGHT   Output stops emitting hashtags_ckb
         by 2: (same two)
CAUGHT   Qc stops emitting flags
         by 1: test_the_fully_populated_clip_round_trips_through_json
CAUGHT   Qc stops emitting human_reviewed
         by 1: test_the_fully_populated_clip_round_trips_through_json
CAUGHT   the fixture falls back to the defaults, so the property measures nothing
         by 1: test_the_fully_populated_clip_leaves_no_field_at_its_default

files restored byte-identical: True
5/5 caught
suite after restore: GREEN
```

The fifth mutation is the one that matters most in a year's time: it attacks the **test**, not the
code, by returning the fixture to the defaults. That is the failure mode this whole entry is about,
and it is now itself caught.

## And the gate caught what a per-file run did not — again

`pytest tests/test_clip.py` passed 40/40 on a file ruff and mypy both reject: `Any` used in an
annotation without importing it, then a `union-attr` error once that was fixed, because
`clip.editorial` is `Editorial | None`. Both surfaced as the audit's **baseline** going red on
`test_gate.py`'s four subprocess tests — 15 minutes to learn something `ruff check` and `mypy` answer
in twenty seconds.

That is twice in two iterations. The habit is now: **`ruff check` + `mypy` over the whole tree before
launching any audit**, not a per-file `pytest`.
