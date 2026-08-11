# The inclusive edge of §3 Stage 5's only stated number, and a test named after a document it never read

M2.2 is `DONE` with 40 tests and has never had its own adversarial pass. Six plausible defects
in `fuse_boundary` — each one that ships a *wrong clip* rather than raising, since the
belt-and-braces `assert_boundary_invariant` already catches everything that violates invariant
#2 — run one at a time against a baseline verified green first:

```
CAUGHT    the VAD lead-in is added instead of subtracted            (2 tests)
CAUGHT    the out point is no longer clamped to the media duration  (8 tests)
CAUGHT    the clamp also erases which signal reached past the end   (1 test)
SURVIVED  a shot cut exactly at anchor_in stops being a candidate
SURVIVED  a shot cut exactly at the window edge stops being a candidate
CAUGHT    the tail is dropped from the out candidates               (8 tests)

4/6 caught by the suite as it stands
```

## The two survivors are not the same kind of thing

Measured on the real `fuse_boundary`, anchor `10000..14000`:

```
== the OUT side: a cut exactly at the window edge ==
  cut at anchor_out+399 = 14399: final_out 14399 by 'shot_cut'
  cut at anchor_out+400 = 14400: final_out 14400 by 'shot_cut'
  cut at anchor_out+401 = 14401: final_out 14200 by 'tail'
    difference at the edge: 200 ms of delivered clip, and the attribution with it

== the IN side ==
  cut at anchor_in-400 = 9600: final_in 9600 by 'shot_cut'
  cut at anchor_in-401 = 9599: final_in 10000 by None
    difference at the edge: 400 ms

== a cut exactly AT anchor_in ==
  only cut at anchor_in itself: final_in 10000 by None
  with an earlier cut too (9700): final_in 9700 by 'shot_cut'
```

**The window edge is real and was held by nothing.** §3 Stage 5 says *"preceding shot_cut
within 400 ms"* and *"following shot_cut within 400 ms"*; "within 400" includes 400, the code
is right, and changing `<=` to `<` on either edge left the whole suite green — worth 200 ms of
clip on the out side and 400 ms on the in side.

**The at-the-anchor survivor is a no-op, proved rather than excused.** `anchor_in` is seeded
into `in_candidates` first, so a cut at exactly `anchor_in` ties with it and `min` returns the
seed: the point and the attribution are identical whether the candidate is present or not, as
the measurement above shows. It is documented, not counted, and the audit keeps mutating it to
confirm it *stays* a no-op.

## The larger finding: the test named after the blueprint never opened it

```python
def test_the_constants_are_the_ones_section_3_stage_5_states() -> None:
    assert VAD_LEAD_IN_MS == 120
    assert TAIL_MS == 200
    assert SHOT_CUT_WINDOW_MS == 400
```

Three literals typed into the test. §3 Stage 5 is named in the function's own title and is never
read, so editing a constant and its literal together leaves the suite green — and `BLUEPRINT.md`
is the frozen document these constants implement. The same shape as D-168's licence column: the
correspondence was true, and accountable to nothing.

It now parses the SOFT ADJUSTMENT block:

```
    final_in  = earliest of { anchor_in,  vad_onset − 120 ms,
                              preceding shot_cut within 400 ms,
                              speaker_turn_start }
    final_out = latest   of { anchor_out + 200 ms tail, natural silence,
                              following shot_cut within 400 ms,
                              speaker_turn_end }
```

Non-vacuity is structural rather than a magic number: the window is stated **twice**, once per
edge, and both must be found and must agree. A regex matching nothing fails there instead of
asserting nothing.

## Mutation audit — 7/7 lint-clean

```
CAUGHT  the following-cut window becomes exclusive      test_a_cut_exactly_on_the_window_still_extends_the_out_point
CAUGHT  the preceding-cut window becomes exclusive      test_a_cut_exactly_on_the_window_still_extends_the_in_point
CAUGHT  SHOT_CUT_WINDOW_MS drifts from the blueprint    (2 tests)
CAUGHT  the blueprint states two different windows      test_the_constants_are_the_ones_section_3_stage_5_states
CAUGHT  VAD_LEAD_IN_MS drifts from the blueprint        test_the_constants_are_the_ones_section_3_stage_5_states
CAUGHT  TAIL_MS drifts from the blueprint               (7 tests)
CAUGHT  the blueprint's stated tail changes, not the constant
                                                        test_the_constants_are_the_ones_section_3_stage_5_states
SURVIVED  NOT COUNTED — a cut exactly at anchor_in (the proved no-op)

files restored byte-identical: True
7/7 caught lint-clean
```

**Both directions of drift are held for all three constants** — code moving away from the
blueprint, and the blueprint moving away from the code. Each edge test reddens exactly one test,
which is the one written for it.

## The floor went down by one, deliberately and visibly

The new `test_the_constants_are_the_ones_section_3_stage_5_states` subsumes a separate
shot-cut-window test written earlier in this iteration, so that one was merged away rather than
left as a duplicate to keep a number up. The gate refused the shrink exactly as designed:

```
REFUSED: only 1561 tests passed against a floor of 1562 … If the removal is intentional, lower
the floor in the same commit that removes them — a shrinking suite must be a visible edit, not
a quieter green run.
```

**Nothing that shipped was lowered.** The committed floor at `6eefbb4` is **1558**; the 1562 was
written by an intermediate run of my own that counted the test since merged. This commit takes
the committed floor 1558 → **1561**, which is a ratchet up.
