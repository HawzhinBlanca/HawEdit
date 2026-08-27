# research — candidate spans are fragments, not clips

## The measurement that started this
Two episodes, full pipeline, live Gemini, `--judge-top-n 5`:

| | ep01 (20 min) | ep10 (75 min) |
|---|---|---|
| candidates returned | 15 | 18 |
| **eligible to judge** | **1** | **5** |
| sentences (§4.2) | 63 | 798 |
| median sentence | 10.2 s | 2.7 s |
| best verdict | hook 0.70, misleading 0.10 | hook 0.90, misleading 0.85 (5.3 s span) |

Judged span durations on ep10: 6.3 s, 22.9 s, 5.3 s, 13.9 s, 1.1 s. The two shortest carry the
two highest misleading-edit risks and are the only two the judge called not self-contained.

## Where the spans come from
**Gemini chooses them, and nothing tells it how long a clip is.**

| symbol | file:line | what it does |
|---|---|---|
| `_PROMPT` | `path_a.py:80` | asks for "every moment that could stand alone as a short social clip" — **no duration guidance of any kind** |
| `_CANDIDATE_SCHEMA` | `path_a.py:66-73` | requires `in_ms`, `out_ms`, `score`, `reason_ckb` |
| span validation | `path_a.py:254` | only `out_ms > in_ms`; **no minimum duration** |
| `_complete_sentences_within` | `pipeline.py:932` | eligibility: a complete sentence must lie **wholly inside** the candidate |
| `_sentence_run_for_candidate` | `pipeline.py` | longest contiguous eligible run, or `()` |
| `fuse_boundary` | `boundary.py:344` | §5 already grows the *final* span outward (`vad_onset`, `shot_cut`, `tail`) — but only after a candidate is already eligible |

So a 1.1 s span is a valid Path A answer, and the fragments the gate refuses are fragments the
system asked for.

## The duration number is NOT in the frozen spec
`BLUEPRINT.md` states no clip duration anywhere — the only duration it fixes is
`max_speech_duration_s=38` for VAD (line 107), which is about ASR input, not output. The
"20–55 s" figure comes from `.claude/skills/pro-kurdish-reel/SKILL.md`, an operator runbook
committed in this session, not from §3.

**Consequence: a target duration is a decision, not a derivation.** It belongs to Hawa with an
ADR, exactly like `MIN_HOOK_SCORE` / `MAX_MISLEADING_EDIT_RISK` in D-253. Deriving it from a
skill file and presenting it as §3 would be inventing a requirement.

## Risks
- **A prompt instruction is a request, not a guarantee.** This repo's own lesson twice over
  (`encoder_available`, D-249's `-crf`): a model accepting an instruction is not a model
  honouring it. Any prompt change needs a post-hoc check on what actually came back.
- Growing spans changes what the judge reads, so **every recorded verdict becomes incomparable**
  with ones taken before the change. The five ep10 verdicts are evidence about 5.3 s spans.
- `_complete_sentences_within` is shared with `_rejected_candidates` deliberately (its docstring
  says so) — the reason written into the artifact must be the reason the code acted on. Changing
  eligibility must move both or neither.
- Longer spans cost more per Stage 4 request: §3 bills video at ~300 tokens/sec, so a 5 s → 30 s
  change is roughly 6× the video tokens on every judged candidate.
- ep01 and ep10 disagree by 4× on sentence length, so any fix keyed to sentence count will
  behave differently per episode. The cause is ASR punctuation density, which is upstream and
  not fixed here.

## Answers to
§3 Stage 3 (Path A discovery) · §5 boundary fusion · D-185 (candidate/sentence granularity
mismatch, first measured) · D-253 (the gate that made the fragments visible) ·
`specs/judge-top-n` (which surfaced the strong-but-unsafe material).
