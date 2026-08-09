# §4.4 was enforced on the property and never on the report a reader receives

> Measured 2026-08-09 on hawapc01 against `beb2ba3`, against a green 1,161 baseline.

M0.9's row says "per-dialect always reported alongside the aggregate", and
`normalized_cer_by_dialect`'s own docstring says "§4.4: never report the aggregate without these".
`bench.py:466` writes `report.to_json()` to a file — that file is what a human reads when deciding
which model becomes canonical.

## Measured

Deleting `normalized_cer_by_dialect` from `ModelReport.to_dict()`:

```
suite:            1161 passed, 0 failed        <- nothing noticed
tests/test_bench: 20 passed                    <- nothing noticed
```

The emitted artifact, before and after, on a run where the two dialects genuinely diverge:

```
HONEST                                   FIELD DROPPED
  normalized_cer            : 0.15         normalized_cer            : 0.15
  normalized_cer_by_dialect : {              normalized_cer_by_dialect : (absent)
      "hewler":   0.04,
      "mukriyan": 0.26 }
```

`0.15` across "Sorani", from two dialects measuring **0.04 and 0.26** — a 6.5× spread the aggregate
hides, on the number §8.1 uses to promote a model.

Computed and discarded, not never-computed: the property is correct, the breakdown is computed on
every call, and the only thing missing was any check that it reaches the file.

## Why the existing tests were blind

`test_the_report_serialises_to_json` asserted `"hewler" in payload`, which looks like exactly the
right check. With the field deleted the string still occurred **seven** times:

```
    "hewler": 0.016666666666666666,      <- coverage.hours_by_dialect
    "hewler/casual_podcast",             <- coverage.missing_cells
    "hewler/code_switch_en",
    "hewler/code_switch_ar",
    "hewler/noisy",
    "hewler/overlapping_speakers",
    "hewler/named_entities",
```

A substring assertion against a whole document is satisfied by any block that happens to mention the
word. The per-model accuracy section was gone; the coverage section carried the test.

`test_the_report_never_gives_only_an_aggregate` asserted on the **property**, which was never the
thing at risk. Between them the two tests read as full coverage of §4.4 and left the artifact
unguarded — the same shape as D-086 and D-088: correct, and blind.

## The fix

Assert on parsed key paths in the emitted JSON, and record the **whole** emitted schema rather than
the one field this pass happened to name — `to_dict` is a hand-written key list, so any field can
vanish from a written §8.1 report the same way. Adding a field now means editing a recorded set,
which is a visible line in a diff, the same trade `scripts/test-count.floor` already makes.

The fixture carries the teeth: the two dialects are deliberately far apart, so the aggregate genuinely
misleads and the breakdown genuinely informs. A run where both dialects score the same passes whether
or not the field survives — which is how this got here.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the breakdown is dropped from the artifact (the defect)              FAILED=4
CAUGHT   the key is emitted only when non-empty (the plausible wrong fix)     FAILED=1
CAUGHT   an unrelated field vanishes from the artifact (the class, not case)  FAILED=1
CAUGHT   an unmeasured dialect is scored 0.0 instead of omitted               FAILED=6
CAUGHT   every dialect reports the aggregate (present but meaningless)        FAILED=7

5/5
```

The two single-test catches are the ones doing real work:

* **"emitted only when non-empty"** is the plausible wrong fix, and it is caught *only* by the
  unlabelled-corpus control. An interim corpus has no §4.4 labels, so `{}` is the honest value — and
  on an artifact an absent key reads as *not applicable* while an empty object reads as *we looked and
  the data carries no labels*. Omitting it would satisfy every other test here and reintroduce the
  unqualified aggregate for exactly the corpus most likely to be quoted first.
* **"an unrelated field vanishes"** is caught only by the recorded schema, which is the difference
  between fixing this field and fixing the class.

The `0.0` mutation is worth naming: it puts a fabricated score on a dialect with no items, which is
the hard rule "unmeasured is None, never 0.0" — caught by six tests, two of them new.

Gate: `VERIFY OK — 1164 passed, 0 skipped`.
