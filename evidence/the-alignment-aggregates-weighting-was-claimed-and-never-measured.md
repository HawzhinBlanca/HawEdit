# M0.8 adversarial pass: the weighting rule was stated in three places and tested in none

**Pass 25.** M0.8 — "Alignment-accuracy metric against CTC emissions (§8.1 last metric)" — DONE
since D-131, never adversarially audited. Its cell makes six checkable claims. Each was disabled in
turn against a baseline verified green first.

## Round 1 — 6/7, and the survivor is the one the row argues hardest for

```
baseline green: True
CAUGHT    the 50 ms tolerance the decision log records becomes 100
           red: test_every_value_the_decision_log_states_is_the_value_the_code_holds
CAUGHT    invariant #5 stops being checked when an aligner is declared
           red: test_word_timings_from_a_non_ctc_aligner_are_refused
CAUGHT    words with no declared aligner are accepted at construction
           red: test_a_transcript_with_words_must_declare_an_aligner
SURVIVED  the report averages per item instead of weighting by matched words
CAUGHT    coverage is dropped from the emitted alignment block
           red: test_the_alignment_aggregate_reports_coverage_beside_its_errors
CAUGHT    nothing aligned reports 0.0 instead of None
           red: test_an_unmeasured_alignment_is_none_in_the_report_not_zero
CAUGHT    two tolerances in one report are averaged rather than refused
           red: test_two_tolerances_in_one_report_are_refused_rather_than_averaged

6/7
  SURVIVOR: the report averages per item instead of weighting by matched words
restored and green: True
```

Five of the six claims are held. The sixth is the one `ModelReport.alignment`'s docstring spends
two lines defending — *"a two-word item and a sixty-word one are not equal evidence about
timing"* — and the same sentence appears in the M0.8 cell and in D-131. Stated three times, and
`sum(x * w) / sum(w)` could be replaced with `sum(x) / len(x)` with the whole suite still green.

## Why nothing caught it: the fixture cannot tell the two formulas apart

`_TimedAdapter` shifts **every** item by the same `shift_ms`, and every item in `_timed_corpus()`
carries the same two reference words. So all six items have identical weight and identical error,
and the two formulas are arithmetically the same number:

```
uniform-shift fixture: weighted 30.0000 vs per-item 30.0000 -> same: True
```

Every existing alignment assertion passes under either implementation. That is the loop's own
definition of a test that measures nothing.

## What the difference actually is, on unequal items

Two items — 2 words mistimed by 200 ms, 20 words mistimed by 10 ms — through
`ModelReport.alignment` and out of `to_dict()`:

```
emitted mean_onset_abs_error_ms : 16.1290      (2 words @ 200 ms, 60 words @ 10 ms)
weighted by matched words       : 16.1290
averaged per item               : 105.0000
emitted within_tolerance_rate   : 0.9677
rate averaged per item          : 0.5000
formulas differ                 : True
```

The emitted value tracks the weighted formula exactly, so the **code is right** — this was never a
defect that ships wrong output. It is a claim the suite did not support: any refactor of that
expression would have shipped a §8.1 error figure 6.5x too large with a green gate.

## Round 2 — the first fixture only excluded one of the two wrong answers

`test_the_alignment_aggregate_weights_by_matched_words_not_by_item` runs the real `run_benchmark`
path and asserts on the emitted JSON. The first version used a 2-word item 200 ms out and a
20-word item 10 ms out, both fully covered. It caught per-item averaging — and a new mutation,
**weighting by reference words**, survived it 5/6:

```
SURVIVED  weighting by reference words instead of matched words
```

Not a bad mutation: it changes the emitted number whenever coverage is below 1. With both items
fully covered, `matched_words == reference_words` per item, so the two weightings are the same
arithmetic. The same blindness as the original defect, one level down, in a fixture I had just
written to expose exactly that.

## The fixture that separates all three

The long item now returns only 10 of its 20 reference words (`_UnevenlyTimedAdapter` takes
`(shift_ms, words_returned)`), so coverage is 12/22 and the three candidate weightings give three
different answers. Measured through `ModelReport.alignment` and out of `to_dict()`:

```
emitted mean_onset_abs_error_ms : 41.6667
weighted by matched words       : 41.6667
weighted by reference words     : 27.2727
averaged per item               : 105.0000

emitted within_tolerance_rate   : 0.8333
rate by matched words           : 0.8333
rate by reference words         : 0.9091

matched_words 12  reference_words 22  coverage 0.5455
all three formulas distinct     : True
```

| field | matched words (asserted) | reference words (excluded) | per item (excluded) |
|---|---|---|---|
| `mean_onset_abs_error_ms` | 41.6667 = (200x2 + 10x10) / 12 | 27.2727 | 105.0 |
| `mean_offset_abs_error_ms` | 41.6667 | 27.2727 | 105.0 |
| `within_tolerance_rate` | 0.8333 = 10/12 | 0.9091 | 0.5 |

Matched words is the right weight because each item's mean is a mean *over matched words*.
Weighting by reference words would give a barely-transcribed item the full say its length
suggests — the failure `coverage` is reported beside the errors to expose.

## Round 3 — 7/7

```
baseline green: True
CAUGHT    the survivor: the report averages per item instead of weighting by matched words
CAUGHT    the within-tolerance rate averages per item
CAUGHT    the offset error averages per item
CAUGHT    weighting by reference words instead of matched words
CAUGHT    the fixture's two items become the same length, so the formulas agree again
CAUGHT    the fixture's two items become equally mistimed
CAUGHT    the long item is fully covered again, so matched and reference weighting agree
7/7
restored and green: True
```

The last three are controls on the fixture rather than on the code: each collapses the corpus back
to a shape where two of the three formulas agree, and each reddens. Without them the test could
have gone on passing for the reason the old one did.

## Two process notes

**The baseline check earned its keep.** Round 2's first run reported `baseline not green` naming
`test_nested_full_gate_refuses_instead_of_recursing` and `test_nested_fast_run_is_still_allowed`.
Neither was a regression: those two run the real gate as a subprocess, and my new helper's
docstring was 101 characters, so `ruff` failed inside them with `E501`. Had the sweep not verified
green first, seven mutations would have reported CAUGHT against a suite that was red before any of
them were applied — the exact false result that mutation auditing is supposed to prevent, arriving
through the same lint-contamination door as D-148 and D-150.

**One mutation refused to run rather than report.** Round 3's `ANCHOR?(0)` was mine: the fixture
control still quoted `{"short": 200, "long": 10}` after the adapter had moved to
`(shift_ms, words_returned)` tuples. The probe skipped it and reported `5/5` over what it actually
measured instead of `5/6` or a fabricated catch — same behaviour as D-157's `ANCHOR?(2)`. Re-run
with the anchor corrected: 7/7.
