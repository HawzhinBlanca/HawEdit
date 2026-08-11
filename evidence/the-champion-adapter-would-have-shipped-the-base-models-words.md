# A fine-tuned decoder would have shipped the base model's words under its own name

Found by asking a question the code could not answer: **run Stage 1 with Hawa's own fine-tuned
OmniASR-7B ("champion") instead of the stock one.** `--omni-asr` had no way to load an adapter,
and the three defects below are what appeared while giving it one.

## What the champion actually is

Measured on this machine, not assumed:

| Fact | Value |
|---|---|
| Form | PEFT LoRA adapter, **not** a separate 7B — `r=16`, `alpha=32`, `q_proj`+`v_proj` |
| Size | 79,768,688 B of weights + 1,112 B config, at `/home/ai/cortex_champion_model` |
| Base | `omniASR-LLM-7B-v2`, 31.2 GB, already in the fairseq2 cache |
| Tokenizer | `omniASR_tokenizer_written_v2.model`, shipped inside the bundle |
| Trainer's recipe | `cortex-speech/cortex-speech-app/scripts/cortex_7b_server.py`, proven — its log shows `LoRA applied. Pipeline ready.` |

**The adapter is not cosmetic.** Base and champion were run against the same in-memory
checkpoint, on three real clips cut from `ZAR38MinTest.mp4`, differing only in whether the
adapter was applied. **3/3 clips changed.** The clearest, at 19:15 — the base drops the opening
line entirely and the champion recovers it:

```
base     : هەست دەکەم خۆم ئەی باشە دیموکراسییەک بە هەموو موزاحەفاتێکی …
champion : هەستەکەم درۆم لە گەڵ ناکا هەستەکەم ڕاستیم لە گەڵ ئاکا هەستەکەم خۆم ئەی باشە دیموکراسیەک …
```

At 1:00 the base opens with a hallucinated `سانە` that the champion does not emit, and the
champion writes `بە تایبەتی` / `ڕیزبەندەکان` in written-form orthography.

## The three defects

**1. The reuse key could not tell the two apart.** `run_pipeline` keys Stage 1 reuse on
`f"{module}.{qualname}"` of the producer. Every OmniASR run — stock or adapted — is
`hawedit.asr.WslOmniAsrProducer`. So:

```
run 1: --omni-asr                        -> 1,547 s, transcript stored
run 2: --omni-asr --omni-asr-adapter …   -> 0 s, the STOCK transcript returned
                                            and the run reports the adapter
```

545 segments of words the champion never read, presented as the champion's. This is exactly
D-136's own rule — a transcript "must not be reused by a run that did not make it" — on the axis
that did not exist when D-136 was written.

**2. The artifact hardcoded the base model.** `_assemble_canonical_transcript` wrote
`AsrProvenance(canonical="omniASR_LLM_7B_v2", …)` as a literal, so an adapted transcript claimed
stock provenance in the file that ships to the client.

**3. `peft` was absent from the runtime.** Measured against
`%LOCALAPPDATA%\HawEdit\wsl-asr\venv`: `peft MISSING`, `omnilingual-asr 0.2.0`, `torch 2.8.0`.
The adapter path would have raised `ImportError` **inside WSL, after Stage 0 and 545 WAV cuts**.

## What changed

`--omni-asr-adapter <bundle>` loads base + LoRA through the trainer's proven recipe, and the
adapter becomes part of **both** the reuse key and the artifact:

* `AsrProvenance.adapter` — a new field, `lora:<digest>`, recorded **beside** `canonical`, never
  inside it. Folding the digest into `canonical` was written first and `AsrProvenance` refused it
  with `ModelNotInRegistry`: §7 role-checks that field, and a fine-tune of a §7 model is still
  that model. The cheapest way to make that pass would have been to loosen the §7 check, which is
  the trade this project does not make.
* the digest hashes **config and weights**, so a retrain at the same rank and a re-attachment of
  the same tensors are each a different identity;
* `ClipTranscript.to_dict` names its fields one at a time, so the adapter had to be added there
  too or the delivered clip sidecar would still say stock weights;
* the worker **refuses** a request naming an adapter it cannot apply, rather than transcribing on
  base weights and publishing under the adapter's name;
* `peft==0.19.1` is in the setup script — the version `adapter_config.json` records as having
  written the bundle, read rather than chosen — and the setup smoke-test imports it.

**Nothing guessed.** The vocabulary size the trainer's server hardcodes as `10288` is the
tokenizer's own `vocab_info.size` (verified: `10288`, `derivable: True`), so it is read from the
bundle. The base checkpoint is the official card's own `checkpoint` field
(`https://dl.fbaipublicfiles.com/mms/omniASR-LLM-7B-v2.pt`), handed back to fairseq2 so its cache
answers — not a `~/.cache/...` path guessed about someone's disk.

**Kurdish invariant #5 is untouched.** Only the LLM decoder is adapted. CTC-3B, its tokenizer and
its device are byte-identical between the two backends, and every word timing still comes from
the Viterbi path over CTC emissions. An adapter changes *which words are read*, never *when they
are said*, and a test asserts exactly that.

## Mutation audit — 9/9 lint-clean

```
baseline: GREEN
baseline lint asr.py / asr_worker.py / pipeline.py / clip.py: clean

CAUGHT   the adapter is dropped from the reuse key, so a champion run reuses the stock words
CAUGHT   the artifact records no adapter, so an adapted transcript looks like a stock one
CAUGHT   the worker silently ignores an adapter it cannot apply
CAUGHT   the adapter never crosses into WSL, so the worker loads base weights
CAUGHT   only the weights are hashed, so re-attaching them at a new rank keeps one key
CAUGHT   only the config is hashed, so a retrain at the same rank keeps one key
CAUGHT   the delivered clip sidecar drops the adapter
CAUGHT   a path that is not an adapter bundle is accepted until deep inside WSL
CAUGHT   a supplied backend and an adapter may disagree about which weights run

all files restored byte-identical: True
9/9 caught lint-clean
suite after restore: GREEN
```

Each has its control: the stock path's artifact must still say `canonical=omniASR_LLM_7B_v2` with
`adapter=None`, a stock WSL request must gain **no key at all** (D-136 resumes a killed run by
comparing the request verbatim), and reuse must still fire for the *same* adapter or the 1,547 s
D-136 saved is spent on every invocation.

## Refusals verified on the real CLI

```
$ hawedit.pipeline … --omni-asr --omni-asr-adapter <path with no adapter_config.json>
✗ … is not a PEFT adapter bundle: adapter_config.json is missing
```

Raised **before** Stage 0, not 1,547 s later inside WSL.

## One operational finding, recorded because it cost a run

A real Stage 1 run died with `canonical OmniASR WSL2 runtime is not provisioned` while the
mutation audit was running. Not a defect: `WslOmniAsrProducer._runtime` resolves the runtime by
`package_fingerprint`, a digest over `src/hawedit/*.py`, and the audit was rewriting those files
in place. **A real run and any edit to `src/hawedit` cannot overlap.** The fingerprint returned to
`92ec251337f3aa1c` once the audit restored every file, and the provisioned snapshot matched again.

## The real run — the whole 38-minute file through HawEdit's own Stage 1

```
hawedit.pipeline "…\ZAR38MinTest.mp4" --work-dir …\champion --media-id zar38champion \
    --omni-asr --omni-asr-adapter '//wsl$/Ubuntu/home/ai/cortex_champion_model'
```

The Windows UNC path round-tripped through `wslpath` to `/home/ai/cortex_champion_model`, so the
flag needs no special-casing for a bundle that lives inside WSL. The request that actually crossed
the boundary:

```json
{"schema_version": 1, "media_id": "zar38champion", "segments": [ …547… ],
 "lora_adapter": "/home/ai/cortex_champion_model",
 "model_identity": "lora:22b2c9eed5a67425"}
```

**The provenance fix, proved on the two artifacts on disk:**

```
stock     canonical=omniASR_LLM_7B_v2  adapter=None
champion  canonical=omniASR_LLM_7B_v2  adapter='lora:22b2c9eed5a67425'
```

**Joined on the media clock**, not on line order — the first attempt aligned the two `text_ckb`
line lists positionally and was wrong, which its own output exposed: the champion transcribed 547
regions to the stock run's 545, so every line past the first extra one was compared against its
neighbour and the "largest differences" it printed were misalignment. The stock artifact predates
D-109 and carries no segment bounds, but its **words** carry media-clock timings, so each is
bucketed into the champion segment containing it — **6104/6104 placed, 0 homeless**.

| | |
|---|---|
| Regions comparable on the clock | 545 |
| Identical text | 50 |
| **Changed by the adapter** | **495 (90.8%)** |
| Median similarity on changed regions | 0.9059 |
| Rewritten heavily (<0.5 similarity) | 22 |
| Words | 6104 stock → **6227** champion |

**Both regions the stock run refused, the champion aligned** — and 0 of its own were refused:

```
[ 226.75s ..  227.07s]  stock: AlignmentInfeasible, 15 frames cannot emit 15 tokens
                        champion: بە هەر پێکە
[1985.35s .. 1985.69s]  stock: AlignmentInfeasible, 17 frames cannot emit 16 tokens
                        champion: وە ئەنێ

stock unaligned: 2    champion unaligned: 0
```

The base model's failure mode on short regions is visible in the heaviest rewrites — at 64.80s it
emits `موون ڕێکی لە بیت` and at 1669.63s a bare `موو`, where the champion emits different text
entirely.

**Invariant #5 holds on the artifact.** Both runs record `aligner=ctc_viterbi`; the champion's
6,227 word spans are monotone and none is degenerate. The adapter changed which words were read
and never how they were timed.

**Not claimed here:** that the champion is *better*. 90.8% changed and 2 recovered regions are
differences, not accuracy — that needs the labelled Sorani corpus of `BLOCKED.md` #1 and human
review. This measures that the adapter runs, that it reaches the weights, and that the artifact
says which weights read the words.
