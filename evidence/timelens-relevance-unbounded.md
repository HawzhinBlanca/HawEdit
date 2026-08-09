# One millisecond of overlap made evidence "about the clip", and shipped a 2.56× clip

> Measured 2026-08-09 on hawapc01 against `9aced24`, against a green 1,134 baseline.

M6.1's row claims two things. They have different verdicts.

## Half one: "intervals as evidence, never as cuts" — true, and untested

§3 Stage 5's formula is explicit about the asymmetry:

```
final_in  = earliest of { anchor_in, vad_onset − 120 ms,
                          preceding shot_cut within 400 ms, speaker_turn_start }
final_out = latest   of { anchor_out + 200 ms tail, natural silence,
                          following shot_cut within 400 ms,
                          speaker_turn_end, timelens_interval_end }
```

`timelens_interval_end` appears in `final_out` and nowhere in `final_in` — TimeLens says where a
moment *ends*, it does not decide where a clip *starts*. Adding the interval's start to the in-point
candidate set left the **entire suite green**. Now pinned: that mutation fails exactly one test.

The test carries a control asserting the out point still moves to the interval, so it cannot pass for
a `fuse_boundary` that ignores TimeLens altogether. This half needed no judgment — the blueprint
states the formula.

## Half two: "only where they are about the clip" — false, and it ships

`interval_for_fusion` keeps any interval that `overlaps(anchor_in, anchor_out)` and ends after the
anchor. Overlap means *any* intersection:

```
anchor      : 10000..14000 ms  (a 4.0s sentence)
evidence    : 13999..305000 ms 'applause five minutes later'
overlap     : 1 ms
relevance gate -> ACCEPTED
fused clip  : 10000..305000 ms = 295.0s  extended by 'timelens_interval_end'
```

Asserted on the artifact rather than the library — through the real `run_pipeline` on the fixture:

```
CLIP SHIPPED: 0..4100 ms = 4.10s
  anchor 100..1700 = 1.60s, extended by 'timelens_interval_end' on 1 ms of overlap
```

A 1.60-second anchored sentence shipped as a 4.10-second clip, 2.56× longer, and the recorded reason
is `timelens_interval_end`. §8.2 calls misleading output the error class that matters most for a media
organisation, and this is misattribution as well as over-length: the clip's own provenance blames a
signal that had one millisecond of contact with it.

## The runner's mitigation is real, and misses the case the feature invites

The uncaptioned-speech guard does refuse the expansion when unselected **words** fall in the swallowed
span. Verified with a second sentence at 2000 ms:

```
boundary SKIPPED: soft boundary expansion 0..4100 ms would include unselected speech
                  beginning with 'لە' at 2000..2400 ms
```

Which is why the shipping case above uses a single-sentence transcript. Applause, music, silence and
untranscribed tails contain no words — and "applause five minutes later" is precisely such a span. The
guard protects against swallowing *other people's speech*, not against reaching five minutes into
untranscribed audio.

## Not fixed, because the bound is a threshold and §3 gives none

§3 bounds the shot-cut signal explicitly — *"following shot_cut within 400 ms"* — and says nothing of
the kind for `timelens_interval_end`. Three defensible rules, each failing differently:

1. **Minimum overlap fraction of the anchor.** Rejects applause; also rejects a genuine reaction shot
   that begins just as the sentence ends, which is the commonest real case Stage 5 exists for.
2. **Maximum extension window**, symmetric with §3's only stated window. But TimeLens exists to find
   ends *beyond* a 400 ms neighbourhood, so this risks neutering the stage.
3. **Cap relative to the anchored sentence's own length.** Scales with content instead of fixing a
   constant, and needs the multiple chosen.

All three are thresholds; the question is empirical and there is no labelled Sorani footage here to
settle it. Recorded as `BLOCKED.md` #15 with the failure modes, and M6.1 demoted to PARTIAL.

`test_one_millisecond_of_overlap_currently_qualifies_as_relevant` pins the measurement so the gate
cannot be read as bounding reach, with a control that an interval with **no** overlap is still refused
— otherwise the test would also pass for a gate that had stopped working. Second time this loop has
committed a test asserting a defect, after D-081's dead VAD branch; the alternative is code that reads
as though the bound exists.

## A correction to my own survey

I had named M2.1 as this iteration's target because its pass-#2 findings were unverified (that agent's
baseline was red). I verified them first: **M2.1 is clean.** Its central claim — Kurdish invariant #3
enforced at the index boundary — is triply guarded, and its whole-set removal does redden the cited
file. Re-measured here against a green baseline:

```
both invariant #3 guards removed -> FAILED tests/test_index.py::test_an_index_refuses_a_raw_transcript
```

That agent had also written that reporting its two individually-surviving guards as gaps "would be a
threefold overstatement" — the redundancy instruction added to the pass prompt after D-079 worked as
intended. So the target moved to M6.1 on measurement, not on plan.

Gate: `VERIFY OK — 1136 passed, 0 skipped`.
