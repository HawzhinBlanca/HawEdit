# Plan — candidate spans that can become clips

## The defect in one line

Path A is asked for "every moment that could stand alone as a short social clip" and told
**nothing about how long a clip is**, so Gemini returns 1.1-second spans — and the §2 gate then
correctly refuses them for being fragments. The system is refusing what it asked for.

## Approach: seeds, then growth

**Stage 3 candidates become seeds rather than final spans.** The span that reaches Stage 4 is
grown from the seed outward to complete sentence boundaries until it reaches the target
duration. This attacks both measured failures at once:

- **Eligibility.** Today a candidate is eligible only if a complete sentence lies *wholly
  inside* it. On ep01 that was 1 of 15, because its sentences run 10.2 s median against ~5 s
  candidates. Growing outward inverts the containment problem instead of loosening the predicate.
- **Misleading-edit risk.** ep10's best candidate scored hook **0.90** and misleading **0.85** at
  5.3 s. A five-second cut of a conversation is close to definitionally not self-contained.
  Growing it to a full argument is the thing most likely to drop that score.

**Two layers, because a prompt is a request.** The prompt gets the target range (AC-1), *and*
the returned spans get measured against it (AC-2). This repo has learned twice that a model or
tool accepting an instruction is not one honouring it — `encoder_available` exists for exactly
that, and D-249 measured `-crf` being silently ignored by NVENC. A prompt-only fix would be
untested faith.

**Growth, not refusal, for short candidates.** Refusing everything under the minimum would throw
away the 0.90-hook material we know is in ep10. A candidate that cannot reach the minimum even
after growth is recorded ineligible with that reason (AC-4) and costs no billed call.

**`_complete_sentences_within` is not touched.** Its docstring says it is shared with
`_rejected_candidates` so the reason in the artifact is the reason the code acted on. Growth
happens around a seed instead of by loosening that predicate, so the shared meaning survives.

## Files and symbols

| file | change |
|---|---|
| `src/hawedit/path_a.py` | the target range in `_PROMPT`; compliance measured on the response |
| `src/hawedit/pipeline.py` | `_sentence_run_for_candidate` grows around a seed; the range constants |
| `tests/test_path_a.py`, `tests/test_pipeline.py` | prompt assertion, growth, eligibility, non-regression |
| `DECISIONS.md` | ADR: the target range, its owner and date, and why it is not derived |

## Divergence from BLUEPRINT

**None — but the number is not in it either.** `BLUEPRINT.md` states no clip duration anywhere;
its only fixed duration is `max_speech_duration_s=38` for VAD input (line 107). The 20–55 s
figure I have been quoting comes from `.claude/skills/pro-kurdish-reel/SKILL.md` line 18, an
operator runbook, not from §3. So a target range is a **decision**, exactly like D-253's
thresholds, and it needs the owner's number and an ADR rather than a derivation from a skill
file. I had been citing it as §3 in earlier messages; that was wrong.

## Risks

- **Cost.** §3 bills video at ~300 tokens/sec, so growing 5 s → 30 s is roughly 6× the video
  tokens on every judged candidate. At `--judge-top-n 5` that is the dominant per-run cost.
- **Every stored verdict becomes incomparable.** The five ep10 verdicts describe 5.3 s spans;
  after this they would describe grown ones. Not a regression, but the old numbers stop being a
  baseline.
- **It may not work.** The hypothesis — that misleading-edit risk falls when a fragment becomes
  an argument — is inferred from five verdicts on one episode plus one on another. It is the
  best-supported explanation available, not a proven one. The plan is built so the answer is
  measurable either way: AC-2 records compliance, and re-running ep10 gives a direct
  before/after on the same footage.
- ep01 and ep10 disagree 4× on sentence length because of ASR punctuation density. Growth keyed
  to sentences will therefore behave differently per episode; that upstream cause is out of
  scope here and stays recorded as the segment-packing finding.

## Decisions, settled by the owner 2026-08-27

1. **Target range 30–90 s.** Not the runbook's 20–55 s and not my recommendation — Hawa chose
   the wider, longer window deliberately, for the best odds that a grown span contains a whole
   argument rather than a fragment. That is the mechanism this whole change rests on, so
   favouring context over cost is coherent. Two consequences to hold onto: it is the most
   expensive option (~300 tokens/sec of video, so a 30 s floor is roughly 6× a 5 s seed on every
   judged candidate), and a 30 s *minimum* is a real eligibility bar — a seed that cannot reach
   30 s on complete sentence boundaries becomes ineligible where today it might have been judged.
   T5 measures whether eligibility rises or falls overall.
2. **Over-long candidates are left alone.** A 90 s+ candidate is a real clip; trimming it to hit
   a number would invent an edit nobody asked for, and the judge already scores self-containment
   and hook, so it can say if the span is too long. Note ep01 has a 105 s sentence — a seed
   inside it grows to that one sentence and exceeds the maximum, and that is accepted rather
   than cut.

Approved-by: Hawa (in chat, 2026-08-27) — 30–90 s, over-long left intact.
