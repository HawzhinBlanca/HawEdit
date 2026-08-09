# 547 confidence measurements became one, and §3's escalation rule went inert

> Measured 2026-08-09 on hawapc01 against `a038163`, on the artifacts of the real 38-minute run.

`escalation.select_for_validation` implements §3 Stage 1's rule — escalate any segment in the bottom
log-probability quartile, or where LLM-7B and CTC-3B disagree materially — and it is tested. It also has
**no reference anywhere in `src/` outside its own module**. The interesting question is why.

## Measured

```
asr.py:474   logprobs.append(item.mean_logprob)          # every region's own value
asr.py:482   mean_logprob=sum(logprobs) / len(logprobs)  # one number survives

the real artifact:
  asr.mean_logprob        : -6.523425833753913
  per-segment values      : none — the key did not exist
  regions Stage 0 cut     : 547
```

547 measurements, one survivor. §3's rule ranks segments; a quartile of an average is nothing. The
policy had no caller because its input had been thrown away — **computed and discarded**, not never
computed.

## The change

`RawTranscript.segment_confidence`: `(start_ms, end_ms, mean_logprob)` per transcribed region, on the
media clock. The aggregate is untouched. `from_json` reads pre-D-109 transcripts with `.get`, as D-103
established for `unaligned`.

`SegmentConfidence` refuses a positive `mean_logprob` for the reason `SegmentScore` already gives —
escalation ranks on log probabilities, so a wrong scale silently inverts the quartile and the
*confident* segments would be the ones routed for validation.

## Proven on the real run's geometry

Re-running 38 minutes of OmniASR costs about half an hour of GPU, so the run's own 547 regions were
replayed through the fixed assembly:

```
assembled: 547 per-segment values retained
§3's rule over those values: 136 of 547 escalate     (547 // 4 = 136, the bottom quartile)
  first reason: bottom-quartile confidence (mean logprob -8.523)
before the change, the same call over one aggregate:  0 escalate
```

**What this shows, precisely:** the quartile is computable at all — the count is exactly `n // 4` and the
pre-change case is inert. The confidence values in the replay are spread around the run's own aggregate
rather than being the models' per-segment measurements, so **this is not a finding about which real
segments are weak.** That needs the run repeated, and it is not claimed here.

## Still not wired, and why that is not a cop-out

`select_for_validation` also needs `ctc_text`, and that is **never computed**: the CTC pass produces
frame-level emissions for alignment and nothing decodes them to text, so `SegmentTranscript` carries only
the LLM's `text_raw`. Half of §3's rule now has its input; half does not. Inventing a `ctc_text` to make
the call typecheck would fabricate the disagreement the rule exists to detect — and the validator it
would route to is `BLOCKED.md` #16 in any case.

## Mutation audit

```
baseline FAILED=0
CAUGHT   the collected values are dropped from the artifact (the defect)      FAILED=3
CAUGHT   every segment records the running average (the wrong fix)            FAILED=2
CAUGHT   the bounds stop being the segment's own                              FAILED=2
CAUGHT   a positive log-probability is accepted, inverting the quartile       FAILED=1
CAUGHT   a zero-length segment is accepted                                    FAILED=1

5/5
```

The middle mutation is the one worth naming: recording the running average once per segment satisfies
any "the key exists" test and leaves every segment **tied**, so the quartile stays empty. The control
asserts the values differ from the aggregate and from each other.

The last two **survived the first audit** — both were validation I had just written on
`SegmentConfidence` with no test reaching it. Third iteration running where the audit's real catch was
my own new guard.

Gate: `VERIFY OK — 1223 passed, 0 skipped`.
