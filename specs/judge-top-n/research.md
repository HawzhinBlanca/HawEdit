# research — judge the top N candidates

## The defect, measured twice
Stage 3 finds many candidates and Stage 4 judges exactly one. If that one fails the gate the run
ends and the rest are never scored.

| run | candidates | judged | hook | outcome |
|---|---|---|---|---|
| ZAR38 (38 min) | 26 | 1 | 0.20 | shipped (pre-gate) |
| ep10 (75 min) | 18 | 1 | 0.20 | refused by D-253 |

Two episodes, two single samples, two 0.20s. Nothing establishes that rank #1 is the best
candidate — only that it ranked first by `_candidate_priority`, which orders by discovery rank
and never by editorial quality.

## The real symbols
| symbol | file:line | role |
|---|---|---|
| `_candidate_priority` | `pipeline.py:883` | `(best_rank, agreement, in_ms, id)` — discovery order, no editorial input |
| `_candidate_for_judging` | `pipeline.py:893` | picks **one** survivor |
| `_automatic_sentence_selection` | `pipeline.py:991` | loops sorted candidates, **returns on the first** with eligible sentences |
| `_complete_sentences_within` | shared with `_rejected_candidates` | eligibility, per candidate |
| `_prepare_selection` | `pipeline.py:1016` | `(indexes, sentences, anchors)` |
| Stage 4 block | `pipeline.py:1658-1706` | keyframes → `JudgeRequest.for_survivor` → `judge.judge` |
| `_assert_verdict_matches_request` | called at 1703 | verdict span must equal request span |
| `_assert_no_existing_artifacts` | called at 1637 | runs **before** the billed call, keyed to `select_sentences` |

## What makes this more than a loop
- **Selection is per-candidate.** `select_sentences`, `selected`, `selected_anchors`, the
  `clip_id` and the artifact paths are all derived from the one chosen candidate. Judging N means
  deriving a selection per candidate first.
- **`_assert_no_existing_artifacts` is keyed to the selection**, so it can only run once the
  winner is known — but it currently runs *before* the billed call deliberately, so a re-run
  cannot pay Gemini and then collide. That ordering has to be preserved per candidate.
- **Every judged candidate costs a billed call.** §3's table puts Stage 4 at ~$0.36–0.72 per
  request with video. N is a spend multiplier, so it needs a cap and a flag.
- **The verdict is currently discarded when render is refused.** `work/ep10/stage4/` holds only
  an empty keyframe directory; the billed verdict lived in memory and died with the run.

## Risks
- `MergedCandidate` spans and sentence runs do not correspond 1:1 — `D-185` records 7 candidates
  spanning 3.48-3.96 s against sentences with a 6.72 s median, and **0** wholly inside any
  candidate. A candidate can be judged and still yield no cuttable selection.
- Judging N and shipping the best changes which clip ships even when rank #1 passes.
- `_rejected_candidates` records rejection reasons; N-way judging adds a second kind of
  rejection (judged and failed) that §5 calls "your only measure of recall".

## Answers to
§3 Stage 3 / Stage 4 · §5 rejection as a first-class outcome · §8.2 · D-253 (the gate that made
this visible) · D-185 (candidate/sentence mismatch).
