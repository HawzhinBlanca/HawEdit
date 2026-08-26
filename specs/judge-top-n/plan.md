# Plan — judge the top N candidates

## Approach

Stage 3 ranks candidates by discovery score; Stage 4 judges rank #1 and the run lives or dies on
that single sample. Measured twice: 26 candidates → 1 judged → hook 0.20, and 18 candidates → 1
judged → hook 0.20. Nothing establishes rank #1 is the *best* candidate — `_candidate_priority`
orders by discovery rank and knows nothing about editorial quality.

**Judge up to N in priority order, ship the best that clears the gate.**

Three pieces:

1. **Split `_automatic_sentence_selection`.** Its loop already walks candidates in priority order
   and returns at the first with eligible sentences. The per-candidate half becomes
   `_sentence_run_for_candidate`; the caller owns the loop. A candidate with no complete
   contiguous run is skipped **before** any billed call (AC-2) — D-185 measured that this is
   common, not rare.

2. **The Stage 4 block becomes a loop body.** Keyframes → `JudgeRequest.for_survivor` →
   `judge.judge` → `_assert_verdict_matches_request`, per candidate. Every existing refusal path
   keeps its structured skip; an operational failure on candidate 3 must not discard verdicts 1
   and 2.

3. **Selection consults the same thresholds D-253 enforces.** `MIN_HOOK_SCORE` /
   `MAX_MISLEADING_EDIT_RISK` / `self_contained` decide which verdicts are shippable; the best
   surviving `hook_score` wins. **The gate stays the final authority at the artifact boundary** —
   selection picking a clip does not exempt it from `assert_renderable`.

**Every verdict is persisted as it arrives** (AC-5), before the render decision. Today a refused
render discards a billed call: `work/ep10/stage4/` holds an empty keyframe directory and nothing
else, so the 18-candidate run has no record of what Gemini actually said.

**The refusal names every score** (AC-4). "No candidate passed" without the numbers costs the
operator another billed run to learn what was close.

## Cost

Each judged candidate is one billed call — §3's table puts Stage 4 at ~$0.36–0.72 with video.
N is a spend multiplier, so it is a flag with a cap, and `--judge-top-n 1` reproduces today's
behaviour and today's cost exactly (AC-6).

## Files and symbols

| file | change |
|---|---|
| `src/hawedit/pipeline.py` | split the selector, loop Stage 4, `--judge-top-n`, richer refusal |
| `tests/test_pipeline.py` | the N-way tests, including "best passing wins, not first" |

## Divergence from BLUEPRINT
None. §3 Stage 3 discovers candidates and §3 Stage 4 judges them; nothing in the frozen document
says only one is judged. §5's "rejection is a first-class outcome … your only measure of recall"
is better served, not worse: AC-8 separates *not eligible* from *judged and below threshold*.

## Risks
- **Cost is the real one.** N=5 is five billed calls per run, and a run that finds nothing
  shippable still pays for all of them.
- Changing which clip ships even when rank #1 passes: with `--judge-top-n 1` the behaviour is
  unchanged, so the change is opt-in by value.
- The loop must not weaken `_assert_no_existing_artifacts`' ordering — it exists so a re-run
  cannot pay Gemini and then collide with an artifact that already exists (AC-7).

## Decisions, settled by the owner 2026-08-26
1. **Default N = 5.** Roughly $2–$3.50 a run at §3's Stage 4 rates. Both failed runs judged
   exactly one candidate and both scored 0.20; five samples is enough that one bad rank #1
   cannot sink a run, without open-ended spend.
2. **Best passing verdict wins, by `hook_score`.** All N are judged and the strongest ships.
   First-passing would have been cheaper but ships in discovery-rank order — which is precisely
   the ordering that produced both 0.20s, so it would spend more calls to reach the same answer.

Approved-by: Hawa (in chat, 2026-08-26) — N=5, best hook wins.
