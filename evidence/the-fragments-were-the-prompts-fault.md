# The fragments were the prompt's fault

> Measured 2026-08-27 on `ep10-0zC2bd03stw.mp4` (ZAR Podcast episode 10, 4,480,494 ms), hawapc01,
> live `gemini-2.5-pro`, `--gemini --auto-select --judge-top-n 5`, cached canonical transcript
> from the 2026-08-26 run so Stage 1 was not repeated. `specs/candidate-span` T5.

## The hypothesis

D-254, D-255 and D-256 all rest on one claim: **misleading-edit risk falls when a fragment
becomes an argument.** It was inferred from five verdicts on this episode plus one on ep01. The
plan committed to recording the answer either way.

## Before and after

Same episode, same judge, same thresholds. Left: 2026-08-26, before any of this work. Right:
2026-08-27, after T2 (the prompt states the range) through T4 (a fragment is refused unbilled).

| | before | after |
|---|---|---|
| Path A candidates | 18 | 11 |
| candidate spans | **1.1 – 22.9 s** | **42.5 – 135.1 s** |
| spans inside the 30–90 s target | not measured | **11 of 11** |
| judged spans | 1.1, 5.3, 6.3, 13.9, 22.9 s | 32.0, 48.9, 53.9, 76.0, 81.1 s |
| **misleading-edit risk** | 0.00, 0.10, **0.85**, 0.20, **0.90** | **0.10, 0.10, 0.10, 0.10, 0.10** |
| self-contained | 3 of 5 | 4 of 5 |
| best hook | 0.90, on a 5.3 s span the judge called not self-contained | **0.80, self-contained, fidelity 1.00, cultural landing 1.00** |
| shipped a clip | no | no |

Verdict-by-verdict, after:

| candidate | span | duration | hook | misleading | self-contained | role |
|---|---|---|---|---|---|---|
| verbal-1 | 990,562–1,071,678 | 81.1 s | **0.80** | 0.10 | yes | aside |
| verbal-2 | 895,170–944,030 | 48.9 s | 0.60 | 0.10 | no | setup |
| verbal-3 | 1,739,714–1,815,742 | 76.0 s | 0.70 | 0.10 | yes | aside |
| verbal-4 | 222,722–276,606 | 53.9 s | 0.60 | 0.10 | yes | aside |
| verbal-5 | 364,802–396,798 | 32.0 s | 0.30 | 0.10 | yes | aside |

## Confirmed, and by a mechanism the plan did not predict

**The risk collapsed.** The two catastrophic scores — 0.85 and 0.90, both on the shortest spans —
are gone, and nothing scored above 0.10. Every verdict in the run returned exactly 0.10.

**T3 and T4 did not cause it. T2 did.** The compliance figure is the proof: **11 of 11** Path A
spans arrived inside 30–90 s. `_grown_sentence_run` returns the ungrown seed whenever
`candidate.out_ms - candidate.in_ms >= minimum`, so a candidate already in range never grows.
Growth fired **zero times** on this episode, and T4's refusal never triggered. The entire measured
improvement came from telling the model how long a clip is.

That is worth stating plainly because the plan argued the opposite. It called the prompt "a
request, not a guarantee", cited `encoder_available` and D-249's silently-ignored `-crf`, and
built growth as the half that does not depend on a model honouring an instruction. On this
episode the model honoured it completely and the independent half was never needed. The
measurement layer is what proved that — a prompt-only change with no compliance count would have
left the mechanism unknown.

**Growth is not thereby useless, and this run cannot say whether it is.** ep01 is the episode
where 14 of 15 candidates had no complete sentence wholly inside them, and it has not been
re-run: its canonical transcript was not kept and Stage 1 measured 73 minutes on this machine.
Growth's value is unmeasured, not disproven.

## The finding this run actually produced

**The 0.05 misleading-edit ceiling may be unreachable on real conversational footage.**

Five of five verdicts came back at exactly **0.10**. Not a spread around 0.10 — the same value
five times, across spans of 32 to 81 seconds in four different parts of a 75-minute episode. The
before-run shows the metric does move: it produced 0.00, 0.10, 0.20, 0.85 and 0.90. So 0.10 is
not a constant the judge always emits; it looks like the floor it settles on for a well-formed
excerpt of a conversation.

If that holds, D-253's ceiling of 0.05 cannot be cleared by any clip cut from this kind of
source, and the pipeline will refuse every episode regardless of quality.

`verbal-1` is the case in point. Hook **0.80** clears the 0.75 floor. Self-contained. Meaning
fidelity 1.00, cultural landing 1.00. It fails on one number: 0.10 against a 0.05 ceiling. It is
the strongest candidate this system has produced, and one hundredth of a point of policy
separates it from shipping.

That ceiling is Hawa's number, set 2026-08-27 (D-253). This evidence does not change it. It
records that the threshold, not the footage, is now what stands between this episode and a clip —
and that one more episode would say whether 0.10 is a floor or a coincidence.

## Also observed

- **Path A is not reproducible across calls at temperature 0.** A second discovery call on the
  same transcript minutes later returned a different candidate set — overlapping spans, different
  boundaries, 10 rather than 11. Recorded as observed behaviour, not as a conclusion about the
  API. It means a before/after on *individual candidates* is not available; the distributions are.
- **Stage 1 escalated 1,063 of 1,572 segments (68%)** at mean logprob **−9.877**, "the models
  disagree materially" — materially worse than ep01's −5.699. The transcript feeding all of this
  is poor, and the segment-packing finding upstream is still unfixed.
- Six stages did not run. The run exited 1, which is the hard stop working as specified.
