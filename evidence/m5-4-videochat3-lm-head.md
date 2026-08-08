# VideoChat3-4B loads in 4.8 s with a randomly-initialised output head

M5.4's premise check, before writing a line of adapter. The model is on disk, Apache-2.0, and
§7 names the repository outright — so the expectation was ordinary work. It is not.

## What the load actually reports

```
VideoChat3ForConditionalGeneration LOAD REPORT from: models/MCG-NJU__VideoChat3-4B
Key            | Status  |
---------------+---------+-
lm_head.weight | MISSING |

Notes:
- MISSING: those params were newly initialized because missing from the checkpoint.

model OK: VideoChat3ForConditionalGeneration, 4.86B params, 4.8s
```

`lm_head` is the projection from hidden states to token logits. Randomly initialised, the model
generates noise — and it loads in under five seconds, reports the right architecture and the
right parameter count, and raises nothing. §3 Stage 3 Path B would have produced SV6D labels
that looked like labels.

Programmatically, which is what a guard can use:

```
missing_keys reported programmatically: {'lm_head.weight'}
unexpected_keys: []
lm_head shape: (151936, 2560) | embed shape: (151936, 2560)
tied by identity (same storage): False
equal by value: False
lm_head std: 0.02000090852379799
embed   std: 0.02014116570353508
```

**The two standard deviations are 0.0200 and 0.0201.** No statistic separates a random head
from a trained one here — `missing_keys` is the only signal, and it is a list nothing was
reading.

## Why it is missing, established rather than assumed

All three shards are present (4.25 + 4.29 + 0.40 GB) and the index holds 734 tensors, none of
them `lm_head`. The checkpoint is complete; the head was never meant to be stored separately:

| Setting | Value |
|---|---|
| top-level `config.json` → `tie_word_embeddings` | **False** |
| `config.json` → `text_config.tie_word_embeddings` | **True** |
| `lm_head` shape vs `embed_tokens` shape | identical, (151936, 2560) |

The config contradicts itself, and transformers 5.14.1 resolves it from the top level. The
checkpoint declares `transformers_version: 4.57.0.dev0`, and the demo scripts shipped inside it
(`demo_vc3.py`, `inference_fast_vc3.py`) do a plain `from_pretrained` with no tying and no
special handling — so on the version its authors tested, the plain load must have tied the head
from `text_config`. This is a transformers behaviour change, not an intentionally untied head.

That matters for what the fix *is*: tying restores the authors' intent rather than overriding
it. It is still a judgment call about someone else's checkpoint, so it belongs to M5.4 with a
decision recorded, not to a flag set quietly here.

## The retroactive check that mattered more

The reranker's score reads `lm_head.weight` directly (D-051). If M5.2's checkpoints had the
same problem, the "the reranker reorders" evidence would have been measuring a random head.
Checked:

```
Qwen3-VL-Reranker-2B    config tie_word_embeddings: True   missing_keys: NONE   tied: True
Qwen3-VL-Embedding-2B   config tie_word_embeddings: True   missing_keys: NONE   tied: True
```

**M5.2's evidence stands.** Recorded as a verified fact rather than left as an assumption,
because it was one until this iteration.

## The guard

`models.assert_fully_loaded` refuses any load with a non-empty `missing_keys`, and
`qwen_visual.load_processor_and_model` passes `output_loading_info=True` to get it. Three tests,
no weights required: the real VideoChat3 case refused, a complete checkpoint accepted (the
positive control — a guard that refused every load would pass the first test and break Stage 2),
and every invented weight named rather than the first.

This is `encoder_available`'s lesson applied to weights. That function exists because
`ffmpeg -encoders` lists what was compiled in rather than what works; this exists because
`from_pretrained` returning a model says what was constructed rather than what was loaded. Both
answers look identical from the outside, and in both cases the honest answer had to be asked
for directly.

## Two more incompatibilities, and then the model works

Chasing the tie found that 5.14.1 breaks this checkpoint in two further ways:

- `prepare_inputs_for_generation` raises `KeyError: 'inputs_embeds'` — the checkpoint reads a
  key 5.x no longer provides. 5.x also warns that `cache_position`, which the code uses, "has
  been removed from the Transformers library".
- the vision tower calls `flash_attn_varlen_func`, which is `None` without flash-attn — and
  flash-attn publishes no Windows wheels. Not fatal: `VL_VISION_ATTENTION_FUNCTIONS` also holds
  `sdpa` and `eager`, selected by `vision_config.attn_impl`, which defaults to
  `flash_attention_2`.

On **`transformers` 4.57.6** with `attn_impl="sdpa"`, all three go away and the tie resolves by
itself — 4.57 reads `text_config.tie_word_embeddings` correctly:

```
transformers 4.57.6, vision attn=sdpa | missing_keys: NONE | lm_head tied: True
GENERATED: 'A red number "0" is centered on a black background.'
```

Coherent and specific about a real frame of the fixture. A working model.

So the fix is not to override a third-party config after all — it is to run the version the
checkpoint was released against. `transformers` is pinned to `==4.57.6` (D-055), which is what
every §7 visual checkpoint declares.

## M5.4 status

Startable, with the obstacle gone rather than merely characterised. Still to write: the
`VideoUnderstanding` implementation, the SV6D prompt, §3's 256-frame budget, and D-049's
`video_metadata` handling — which was re-measured under the pin and holds identically.
