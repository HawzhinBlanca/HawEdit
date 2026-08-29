# The champion transcribed, and shipped nothing

> Measured 2026-08-29 on hawapc01. `ep29-chunk50min.mp4` — ZAR Podcast episode 29, 2560x1440,
> 50 minutes, the owner's own channel. Same source, same flags, same judge (`gemini-2.5-pro`),
> differing only in which decoder drafted Stage 1.

## It ran, for the first time

`adapter: lora:22b2c9eed5a67425` is recorded in the transcript. **This is the first champion
transcript this system has produced.** `--omni-asr-adapter` shipped in D-181 and had never once
executed to completion; five distinct defects were stacked behind it, each visible only after the
previous was fixed:

1. the bundle's UNC path handed to `wslpath`, which answered `/mnt/c/wsl.localhost/…`
2. `peft` absent from the reviewed runtime lock (D-261) — measured in D-181 and never provisioned
3. a misdiagnosis: asking for the tokenizer by name, which changed nothing
4. a profiler installed into the audited runtime, correctly refused by the receipt
5. `CANONICAL_LLM_CARD` ends in `@`, so the derived name `…_v2@_tokenizer` parsed as *card
   `…_v2`, environment `_tokenizer`* — the model card, whose `tokenizer_ref` is that same string.
   `resolve_tokenizer_reference` handed itself back forever; a worker burned 3 h 20 m at 99% of
   one core before it was killed.

Only the fifth was found by measuring rather than reasoning — dumping the spinning frame's locals
showed `ref_card` was the identical object to `card`.

## The transcripts differ

| | base | champion |
|---|---|---|
| adapter | `None` | `lora:22b2c9eed5a67425` |
| words | 6,856 | **6,946** |
| mean logprob | −7.105 | −7.116 |
| §4.2 sentences | 191 | 192 |
| Stage 1 escalated | 372/773 = **48%** | 389/774 = **50%** |

## The verdicts differ, and the champion's are worse

Same footage. Four of five spans are identical to the millisecond, so this is the judge reading
different words about the same pictures.

| span | base | champion |
|---|---|---|
| 56.3 s | hook **0.75**, misl 0.10 | hook 0.70, misl 0.10 |
| 45.9 s | hook 0.60, misl 0.10 | hook 0.70, misl **0.20** |
| 36.6 s | hook **0.85**, misl 0.10 | hook 0.60, misl 0.10 |
| 34.3 s | hook **0.90**, self-contained | hook 0.90, **not self-contained**, misl **0.20** |

**The base decoder shipped a clip. The champion shipped none.** Escalation also rose two points.

## What this actually establishes

**The 0.10 "floor" was not a floor, and D-257 rests on that.** Fifteen consecutive verdicts across
three episodes scored *exactly* 0.10, and the misleading-edit ceiling was raised from 0.05 to 0.10
on that evidence. This run produced **0.20 twice**. The metric does move above 0.10, so the
ceiling now refuses rather than admitting everything — which is the behaviour D-253 wanted. The
reasoning in D-257 was sound on the evidence available; the evidence was incomplete, and fifteen
samples from one judge on three episodes was a smaller distribution than it looked.

**Stage 4 is text-dominated.** Identical spans of identical footage scored differently because the
transcript changed. That makes transcript quality a lever on editorial outcomes rather than a
detail, and it is worth knowing before any effort goes into visual discovery.

## What this does not establish

**Whether the champion is more accurate or merely different.** Lower hooks and higher
misleading-edit risk are consistent with a transcript that is *more* faithful to messy real
speech, and equally consistent with one that is worse on this material.
`evidence/the-champion-adapter-would-have-shipped-the-base-models-words.md` measured 3/3 clips
changed and one base hallucination removed — on a different episode, against a different source.
One episode is not a distribution, which is the mistake already made once with
`TARGET_FACE_HEIGHT_SHARE` and corrected by the next source that arrived.

Deciding between those two readings needs a reference transcript to score against, and that is
`BLOCKED.md` #1 — the labelled Sorani set that does not exist. Until then the champion is
mandatory because the owner's canon says so (D-260), not because this run showed it to be better.
