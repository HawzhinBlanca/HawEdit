# §8.1's last metric never reached the report

> Measured 2026-08-09 on hawapc01 against `06adf58`.

M0.8 is DONE for *"Alignment-accuracy metric against CTC emissions (§8.1 last metric)"*. The metric is
computed. It was not in the report.

Pass #17 is what pointed here: it found the `None`-versus-0.0 rule held per measurement and unheld in
the aggregate, so the aggregate is where the next metric's gap would live. It was not a gap in a
number — the field did not exist.

## The measurement

Six items with reference timings, a hypothesis shifted 30 ms on every boundary:

```
per item, computed and stored on ItemScore.alignment
  hewler-1  matched 2/2  onset 30.0 ms  offset 30.0 ms  within 1.00 @ 50 ms  coverage 1.00
  hewler-2  matched 2/2  onset 30.0 ms  offset 30.0 ms  within 1.00 @ 50 ms  coverage 1.00

keys in the written model report
  model_id · adapter_impls · scored_items · failed_items · normalized_cer · spacing_free_cer
  normalized_cer_by_dialect · named_entity_error · code_switch_error · mean_rtf · worst_rtf
  long_audio_failure_rate · peak_vram_bytes

any key mentioning alignment          []
'align' anywhere in the whole JSON    False
```

`_score_item` calls `score_alignment` whenever the item has reference timings and the hypothesis has
words, and stores the result on `ItemScore.alignment`. `ModelReport.to_dict()` never read it.

**Computed and discarded**, which is a different fix from never computed: the same shape as D-070's
`natural_silence_ms` and D-109's per-segment `mean_logprob`.

## What the report carries now

```json
{
  "matched_words": 12,
  "reference_words": 12,
  "coverage": 1.0,
  "mean_onset_abs_error_ms": 30.0,
  "mean_offset_abs_error_ms": 30.0,
  "within_tolerance_rate": 1.0,
  "tolerance_ms": 50,
  "scored_items": 6
}
```

Weighted by matched words, the way `_micro_cer` weights by characters. Coverage beside the errors,
because `AlignmentAccuracy` says why. `None` — never a zero — when nothing was aligned, since 0.0 ms
is the best possible score. Two tolerances in one report are refused rather than averaged.

## Proof

```
baseline fails: False

RED  the aggregate is dropped from the report again (the defect)
RED  an unmeasured alignment becomes a perfect zero
RED  coverage is left out of the aggregate
RED  two tolerances are averaged instead of refused
RED  the within-tolerance rate ignores the timings it measures     <- the control

5/5
```

The control is the one that matters: it shifts the hypothesis from 30 ms to 120 ms, past the 50 ms
bar, and requires the rate to move from 1.00 to 0.00 and the mean error to read 120.0 ms. Emitting
constants would satisfy every other assertion.

And the ordinary case is pinned too: the scripted adapter returns no word timings, so no item can be
aligned and the report must say `null` rather than a perfect score — which is the state this project
is in until `BLOCKED.md` #1 supplies timed labels.

## The recorded schema caught the new key

`test_the_emitted_report_schema_is_recorded_field_by_field` (D-094) went red the moment `alignment`
appeared in `to_dict()`. That is the guard working: adding a field to the artifact is a deliberate
edit to a recorded contract, not a silent one.

Gate: `VERIFY OK — 1316 passed, 0 skipped`.
