# The validator's answer had no specified effect

Hawa asked why this project uses Qwen ASR at all. Answering it surfaced a gap in the frozen
blueprint: **§3 Stage 1 never says what the validator's reading does to the canonical text.**

```
BLUEPRINT.md:128
Escalation: compute mean token log-probability per segment from CTC posteriors. Route the bottom
quartile, and any segment where LLM-7B and CTC-3B disagree materially, to the validator. Never
escalate on duration or word-count heuristics.
```

Route it there — and then what? Replace the canonical words, merge with them, record it alongside?
The sentence stops. `select_for_validation` is implemented and tested (D-015, D-109) and has **no
consumer**, so nothing implements any of the three readings either.

## What Qwen is actually for

Not transcription. The canonical read is `omniASR_LLM_7B_v2` for words plus `omniASR_CTC_3B_v2` for
timings, and Kurdish invariant #5 pins every word timing to CTC Viterbi. `registry.py` gives
`rzgar/qwen3-asr-sorani-kurdish-ckb-v1` the role `asr_validator`, and §7 lists it as *"Validator on
disagreement / hard spans"*. It is a second opinion on the spans the canonical pair found hardest.

It has never run: transformers 4.57.6 has no `qwen3_asr` module (BLOCKED #16).

## The rule, and why it is one-directional

**The validator's reading is evidence, never a replacement.** It may flag a span; it may never
rewrite one. Three things enforce that, two of which already existed:

1. **Invariant #1.** `transcript.raw.json` is *exactly as canonical ASR emitted*, write-once,
   digest-verified. A validator reading written into it would make "canonical" mean whichever model
   was written there last.
2. **§7's roles, checked by the type.** `AsrProvenance.__post_init__` resolves `canonical` against
   `canonical_asr` and `validated_by` against `asr_validator`. Measured:

   ```
   validator as canonical           WrongRole: … is §7's 'ASR validator' (role 'asr_validator')
   canonical as validator           WrongRole: … is §7's 'Canonical ASR' (role 'canonical_asr')
   emissions model as canonical     WrongRole: … is §7's 'ASR confidence + emissions'
   the legitimate pairing           ACCEPTED
   ```

   True already; held by no test until now.
3. **Disagreement routes to a human.** §2 puts a human QC gate before output, always. A disputed
   span gets a `qc.flags` entry, which already blocks rendering through `assert_renderable`
   (D-195). Not a merge.

Hawa's assessment — that the Sorani checkpoint is weaker on Kurdish than the champion LoRA they
trained — is recorded **as an assessment**. Nothing in this repo measures it: no CER, no WER, no
side-by-side on Kurdish audio, and the labelled set that could produce one is BLOCKED #1. The rule
does not depend on it. A second opinion is only safe to overwrite with if it is *better*, and
escalation hands it precisely the hardest spans, where being wrong costs most. Evidence-only is
correct either way, which is why it does not wait on BLOCKED #1.

M6.1 settled the identical question for TimeLens2 — *"intervals as evidence, never as cuts"*. Same
shape, one stage over.

## BLOCKED #16 was asking the wrong question

It said: one package, licence unread, and therefore Hawa's call. Measured 2026-08-12, from the
authoritative sources rather than inferred:

* **`transformers` ships the loader now.** `src/transformers/models/qwen3_asr/` is **absent in
  v5.12.0 and present in v5.13.0**, checked tag by tag. Installed: **4.57.6**. Latest: **5.15.0**.
* **The checkpoint ships no remote code** — no `.py`, no `auto_map` in `config.json` — so
  `trust_remote_code=True` is not a third option. There is nothing to execute.
* **`qwen-asr` 0.0.6** declares `license: Apache-2.0` as author-declared free text with **no
  `License ::` classifier**, and its declared Homepage and Repository both point at
  `github.com/Qwen/Qwen3-ASR`, which **404s**. It requires **ten** packages including **`flask`**
  and **`gradio`**, and pins `transformers==4.57.6` and `accelerate==1.12.0` — the latter a
  **downgrade** from the 1.14.0 installed.

So it was never a licence question. It is a `transformers` major-version bump, which is a real
decision — the champion LoRA path, `peft==0.19.1` and the WSL runtime are all built against 4.57.6,
and the WSL runtime is keyed on a source fingerprint — but a different and much smaller one than
adding a web server to the dependency set.

## Mutation audit — 3/3, three times over

Each mutation loosens one `resolve_role` call to `ASR_ROLES`, the union that already exists in the
registry and reads like the natural refactor, and carries the import it needs so it is a real
program rather than a `NameError`.

```
baseline: GREEN (1643 passed, 86 warnings in 141.44s)

CAUGHT   any ASR model may be recorded as the canonical one
         by 1: test_a_model_cannot_take_the_asr_role_it_is_not_section_7s_model_for[…]
CAUGHT   any ASR model may be recorded as the validator
         by 1: test_a_model_cannot_take_the_asr_role_it_is_not_section_7s_model_for[…]
CAUGHT   the canonical role check becomes a mere registry lookup
         by 2: test_a_model_cannot_take_the_asr_role_it_is_not_section_7s_model_for[…],
               test_a_scene_detector_cannot_be_transcript_provenance

file restored byte-identical: True
3/3 caught
suite after restore: GREEN
```

It was run three times because the first two runs overlapped other background work, and the result
is only reported here because all three agree exactly.

## Two background jobs mutating source at once, and how it was caught

A sweep over `gemini.py` was killed mid-mutation and **left the file on disk with a Vertex location
check replaced by `pass`**. It was caught by a routine `git status` before staging — BLOCKED #12's
rule earning its keep — and restored from HEAD.

Worse, I then started a second audit while that sweep was still running. Each mutated its own file
while the other ran the whole suite, so results were contaminated in both directions: false HELDs
from the other job's mutation, and a false UNHELD from a mutation restored underneath it. **The
gemini sweep's output is discarded entirely** rather than reported with a caveat.

The root cause of the repeat was my own inference, three times: an empty output file plus a
momentary gap in `ps` is *not* evidence a background job has died — output is block-buffered until
exit, and `ps` misses the gaps between subprocess spawns. **The completion notification is the only
reliable signal.** Same class as this session's two `pgrep` false positives.

The harness now takes a lock, refuses to start while another sweep holds it, and restores its target
on normal exit, on exception and on SIGTERM — so a killed sweep cannot leave a deleted refusal on
disk for someone else to commit.
