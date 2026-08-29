# The champion ships, at rank eight

> Measured 2026-08-28/29 on hawapc01. `ep29-chunk50min.mp4` — ZAR Podcast episode 29, 2560x1440,
> 50 minutes, the owner's own channel. Live `gemini-2.5-pro`.

**This file replaces `the-champion-transcribed-and-shipped-nothing.md`, which was wrong.** The
correction is the point of the record, so it is kept in full below rather than quietly rewritten.

## What was claimed, and why it was wrong

The first run of the champion transcript judged five candidates, none passed, and it was written
up as *"the base decoder shipped a clip, the champion shipped none."* Every number in that
sentence was accurate. The conclusion was not.

`--judge-top-n` defaults to **5**, a cost ceiling set in D-254. The champion run found **13**
candidates and scored the first five. Re-running the identical transcript at `--judge-top-n 12`
produced a **passing clip at rank 8**:

| rank | length | hook | misleading-edit | self-contained | fidelity |
|---|---|---|---|---|---|
| 1 | 56.3 s | 0.70 | 0.10 | yes | 1.00 |
| 2 | 36.6 s | 0.60 | 0.10 | yes | 1.00 |
| 3 | 45.9 s | 0.70 | **0.40** | yes | 0.90 |
| 6 | 32.3 s | **0.90** | 0.10 | **no** | 1.00 |
| 7 | 34.3 s | **0.90** | 0.20 | **no** | 1.00 |
| **8** | **63.8 s** | **0.75** | **0.10** | **yes** | **1.00** | ← shipped |

Delivered: 64.1 s, hook 0.75, misleading 0.10, self-contained, meaning fidelity 1.00, cultural
landing 0.95, `adapter: lora:22b2c9eed5a67425`, eleven visual changes, −14.0 LUFS, full five-file
delivery set.

**The comparison that produced the wrong conclusion was between a base run judging 5 of 11 and a
champion run judging 5 of 13.** It was read as a fact about the decoder. It was a fact about a
cost default.

## What is actually established

**A default tuned for cost can hide a shippable clip.** D-254 set `--judge-top-n` at 5 because
each judged candidate is a billed Stage 4 request at roughly $0.36–0.72 with video. That reasoning
stands. What was not known then is that the winner can sit at rank 8, so "this episode has no clip
worth shipping" is only true *of the candidates that were scored*. The run's own skip message says
"N candidate(s) were judged and none cleared §2's editorial thresholds", which is exact — the
inference beyond it was the error.

**Misleading-edit risk has real range, and the 0.10 "floor" was an artefact of small samples.**
Fifteen consecutive verdicts scored exactly 0.10, and D-257 raised the ceiling from 0.05 to 0.10
on that evidence. Since then the metric has produced **0.20** twice and now **0.40**. D-257's
change was right — at 0.05 nothing could ever ship — but the reasoning that "0.10 is the floor"
was drawn from too few samples, which is the same error made with `TARGET_FACE_HEIGHT_SHARE` and
corrected by the next source that arrived.

**The strongest hooks are the least complete thoughts.** Both 0.90-hook candidates failed on
`self_contained`; the winner scored 0.75 and passed. That is the tension §2's gate exists to
arbitrate, and it arbitrated it.

## What is still not established

**Whether the champion transcribes more accurately than the base decoder.** On the same episode
the base run's best was hook 0.90 self-contained and the champion's is hook 0.75. That is one
episode, judged by a model that is demonstrably not reproducible across calls — Path A returned
13 candidates on one run and 10 on the next from the identical transcript. Settling it needs a
reference transcript to score against, which is `BLOCKED.md` #1.

The champion is mandatory because the owner's canon says so (D-260), and this run shows that
mandate does not cost the pipeline its output.
