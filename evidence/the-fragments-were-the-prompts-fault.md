# The fragments were the prompt's fault

> Measured 2026-08-27 on hawapc01, live `gemini-2.5-pro`, `--gemini --auto-select
> --judge-top-n 5`, cached canonical transcripts so Stage 1 was not repeated.
> ep10 = `ep10-0zC2bd03stw.mp4` (ZAR Podcast episode 10, 4,480,494 ms).
> ep01 = `01-MmQ9XPggSig.mp4` (ZAR Podcast episode 1, 1,222,374 ms).
> `specs/candidate-span` T5.

## The hypothesis

D-254, D-255 and D-256 all rest on one claim: **misleading-edit risk falls when a fragment
becomes an argument.** It was inferred from five verdicts on ep10 plus one on ep01. The plan
committed to recording the answer either way.

## Before and after

Same episodes, same judge, same thresholds.

| | ep10 before | ep10 after | ep01 before | ep01 after |
|---|---|---|---|---|
| Path A candidates | 18 | 11 | 15 | 13 |
| candidate spans | 1.1 – 22.9 s | 42.5 – 135.1 s | ~5 s typical | in range |
| spans inside the 30–90 s target | not measured | **11 of 11** | not measured | **13 of 13** |
| eligible to judge | 5 | 5 | **1 of 15** | 5 |
| judged spans | 1.1 – 22.9 s | 32.0 – 81.1 s | 9.4 s | 48.8 – 101.6 s |
| **misleading-edit risk** | 0.00, 0.10, **0.85**, 0.20, **0.90** | 0.10 ×5 | 0.10 | 0.10 ×5 |
| self-contained | 3 of 5 | 4 of 5 | 1 of 1 | 4 of 5 |
| best hook | 0.90, not self-contained | 0.80, self-contained | 0.70 | **0.90, self-contained** |
| shipped a clip | no | no | no | no |

ep01 after, verdict by verdict:

| candidate | span | duration | hook | misleading | self-contained | fidelity | cultural |
|---|---|---|---|---|---|---|---|
| **verbal-2** | 723,554–825,182 | 101.6 s | **0.90** | 0.10 | yes | 1.00 | 0.90 |
| verbal-3 | 79,138–127,934 | 48.8 s | 0.50 | 0.10 | yes | 1.00 | 0.80 |
| verbal-4 | 248,258–306,494 | 58.2 s | 0.30 | 0.10 | no | 0.90 | 0.80 |
| verbal-5 | 723,554–825,182 | 101.6 s | 0.80 | 0.10 | yes | 1.00 | 1.00 |
| verbal-6 | 128,642–196,414 | 67.8 s | 0.50 | 0.10 | yes | 1.00 | 0.80 |

## Confirmed, and by a mechanism the plan did not predict

**The risk collapsed.** ep10's two catastrophic scores — 0.85 and 0.90, both on the shortest
spans — are gone, and across both episodes nothing scored above 0.10.

**T3 and T4 did not cause it. T2 did.** The compliance figures are the proof: **11 of 11** on
ep10, **13 of 13** on ep01 — 24 of 24 Path A spans arrived inside 30–90 s.
`_grown_sentence_run` returns the ungrown seed whenever
`candidate.out_ms - candidate.in_ms >= minimum`, so a candidate already in range never grows.
Growth fired **zero times** on either episode, and T4's refusal never triggered once. The entire
measured improvement came from telling the model how long a clip is.

That is worth stating plainly because the plan argued the opposite. It called the prompt "a
request, not a guarantee", cited `encoder_available` and D-249's silently-ignored `-crf`, and
built growth as the half that does not depend on a model honouring an instruction. On both
episodes the model honoured it completely and the independent half was never needed. The
measurement layer is what proved that — a prompt-only change with no compliance count would have
left the mechanism unknown.

**ep01 was the strongest case for growth and it still did not fire.** That episode is where 14 of
15 candidates had no complete sentence wholly inside them, with sentences at a 10.2 s median
against ~5 s candidates. Once Path A was told the target, the containment problem disappeared at
source: eligibility went from **1 of 15** to 5, without a single candidate being grown.
`_grown_sentence_run`, `_complete_sentences_overlapping` and the minimum-span refusal are
unit-tested and unexercised on real footage.

## The finding this run actually produced

**D-253's 0.05 misleading-edit ceiling is unreachable on real conversational footage.**

**Ten of ten** post-fix verdicts came back at exactly **0.10** — five on ep10, five on ep01,
across spans of 32 to 102 seconds in nine different parts of two unrelated episodes. ep01's
pre-fix verdict was also 0.10. The metric demonstrably moves: ep10's before-run produced 0.00,
0.10, 0.20, 0.85 and 0.90. So 0.10 is not a constant the judge always emits — it is the floor it
settles on for a well-formed excerpt of a conversation.

A ceiling of 0.05 therefore refuses every clip this pipeline can cut from this kind of source,
regardless of quality.

**ep01 `verbal-2` is the case in point.** Hook **0.90**. Self-contained. Meaning fidelity 1.00,
cultural landing 0.90. Its own Kurdish title is *"ئایا توێکاریی جەستەی مردوو حەرامە؟"* — is autopsy
religiously forbidden? — arguing that what many take to be prohibited is medical science that
identifies cause of death and hereditary disease, and can save the rest of a family. That is a
real social clip with a real hook, and it is refused on one hundredth of a point of policy.

The ceiling is Hawa's number, set 2026-08-27 (D-253). This evidence does not change it. It
records that the threshold, not the footage, is now what stands between this system and a
delivered clip.

## Also observed

- **Two of five billed calls scored identical footage.** ep01's `verbal-2` and `verbal-5` were
  judged on exactly the same span, 723,554–825,182 ms, because two different Stage 3 candidates
  anchored to the same complete sentence run. `_judgeable_plans` deduplicates candidates, not
  spans. At §3's Stage 4 rates that is roughly $0.36–0.72 spent to score the same seconds twice,
  and it cost this run one of its five samples.
- **A single slow response discards a whole run.** ep01's first attempt failed at Stage 4 with
  `GeminiUnavailable: the billed generateContent result is ambiguous and was not retried without
  provider idempotency — HTTP 0: The read operation timed out` against the transport's 120 s
  ceiling. Refusing to retry an ambiguous billed call is correct. Losing every subsequent
  candidate because the first one timed out is not obviously correct: no verdict was persisted,
  and the identical re-run then succeeded.
- **Both grown spans on ep01 exceed the 90 s maximum** at 101.6 s, which is D-254's
  "over-long candidates are left intact" working as decided rather than a defect.
- **Path A is not reproducible across calls at temperature 0.** A second discovery call on ep10's
  transcript minutes later returned a different candidate set — overlapping spans, different
  boundaries, 10 rather than 11. Recorded as observed behaviour, not as a conclusion about the
  API. A per-candidate before/after is therefore unavailable; the distributions are.
- **Stage 1 remains the weakest link.** ep10 escalated 1,063 of 1,572 segments (68%) at mean
  logprob −9.877; ep01 escalated 277 of 306 (91%) on materially disagreeing LLM and CTC arms
  despite a healthier −5.375. Every editorial judgement above rests on that text, and the
  segment-packing finding upstream is still unfixed.
