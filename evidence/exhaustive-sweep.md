# Two rows called a sweep "exhaustive"; it covered five of seven inputs

> Measured 2026-08-09 on hawapc01 against `81358c7`.

M2.2 and M6.2 both cite `test_the_invariant_holds_across_every_combination_of_soft_inputs` as
evidence for Kurdish invariant #2, and both call it **exhaustive** over the soft inputs. It swept
five of `BoundaryInputs`' seven optional fields:

| field | in the old sweep |
|---|---|
| `vad_onset_ms` | yes |
| `shot_cuts_ms` | yes |
| `speaker_turn_start_ms` | yes |
| `speaker_turn_end_ms` | yes |
| `timelens_interval_end_ms` | yes |
| `natural_silence_ms` | **no** |
| `media_duration_ms` | **no** |

`natural_silence_ms` is the one that matters. D-070 wired it into the runner three iterations ago
as §3's fourth out-point signal — and did not extend the sweep that two ledger rows cite as proof
the invariant holds. That omission is mine, and the adversarial pass found it, not me.

## Extended, and measured

5⁷ = **78,125** combinations, up from 3,125:

```
combinations : 78125
boundaries   : 46875
refused      : 31250
violations   : 0
  refusal x31250: anchor_out (112400 ms) is after the media ends...
elapsed      : 0.40s
```

**0 violations.** The 31,250 refusals are exactly two fifths of the space — the two duration
offsets that put the media end before `anchor_out`, which `fuse_boundary` refuses by design
rather than clamping, because clamping an anchor that does not fit would violate the very
invariant being checked. They are counted and their message asserted, not skipped: a refusal that
began happening for some *other* reason must not read as coverage.

**I expected it to hold, and it does.** The 200 ms tail is always present in the out-point `max()`,
so `final_out >= anchor_out + 200` regardless of what `natural_silence_ms` contributes; and
`anchor_out <= media_duration` is enforced before the clamp, so the clamp cannot pull `final_out`
below `anchor_out`. This change makes a false claim true and covers an input added this week. It
did not find a bug, and saying otherwise would be the overstatement this whole exercise is about.

## The sweep's own breadth is now asserted

The test asserts `built == 46_875` and `refusals == {"ValueError": 31_250}`, summing to 5⁷. That
is the part with unique value: shrinking `offsets` from five values to four is **CAUGHT**
(`AssertionError` at the count), and nothing else in the suite would have noticed a field quietly
dropped from the product — which is precisely how the claim went stale the first time.

## What the sweep is worth, measured rather than assumed

The adversarial pass claimed the sweep catches nothing the surrounding unit tests do not. Checked
directly — each invariant-breaking mutation run against the whole file, and against the whole file
with the sweep deselected:

```
baseline whole-file: GREEN
baseline no-sweep  : GREEN

caught with or without the sweep   anchor_in is dropped from the in-point candidates
caught with or without the sweep   the out point takes the earliest candidate instead of the latest
caught with or without the sweep   the media clamp no longer requires anchor_out to fit inside the media
caught with or without the sweep   the natural_silence candidate is dropped
```

Confirmed: for all four, the sweep is **defence-in-depth, not the sole catcher**. So the word
"exhaustive" was doing more rhetorical work in the ledger than the test does in the suite. It is
kept — a 0.4 s combinatorial check over an invariant the blueprint calls non-negotiable is cheap
insurance against a mutation nobody thought to write a unit test for — but the ledger rows now say
what it is rather than leaning on the adjective.

## What this does not close

`media_duration_ms` is swept only as `ANCHOR_OUT + offset`. Values between 0 and `anchor_out`, and
the `<= 0` refusal, are covered by dedicated unit tests rather than by the product. Sweeping the
duration independently of the anchor would multiply the space again for cases whose behaviour is
already pinned, so it was not done.

Gate: `VERIFY OK — 1099 passed, 0 skipped`.
