# Research — visual-short-window-provenance

Parent acceptance package: `specs/true-10-10-acceptance/` (AC-4 and Phase 3).

## Method

Serena is not available in this Codex environment. The required symbol and caller mapping was
performed with `rg` over `src/hawedit`, `tests`, `BLUEPRINT.md`, `BLOCKED.md`, `DECISIONS.md`, and
the existing evidence. No source or test file was changed during research.

This unit is grounded in BLUEPRINT §3 Stage 2/3, `BLOCKED.md` #22, and D-060, D-063, D-186,
D-187, D-190, and D-193. The frozen blueprint requires one visual embedding per scene, ~1 fps,
top-50 retrieval, reranking, 5–10 survivors, and VideoChat3 only over those survivors. It also
requires scene segmentation; a remedy must not silently cross the cut that created the scene.

## Current failure

`SceneWindow.frame_count` is the plan (`ceil(duration * fps)`). ffmpeg samples at interval
centres, so a 1,000–1,499 ms scene at 1 fps can contain only one emitted frame. The current
`extract_window_frames` correctly refuses that one-frame video as having no temporal structure.
`VisualComposer`, however, must embed every window before retrieval and normalises that refusal
into one `VisualPipelineError`; therefore one short scene aborts the complete visual path.

Measured on `ZAR38MinTest.mp4` in D-187:

| requested rate | planned windows | windows below checkpoint `min_frames=4` | smallest |
|---|---:|---:|---:|
| 2 fps | 641 | 1 | 2 planned frames over 1,000 ms |
| 1 fps | 364 | 31 | 1 planned frame over 1,000 ms |

The 1-fps mode is the only measured configuration on hawapc01 whose 8-frame VideoChat3 ceiling
can hold the 6.72-second median complete sentence (D-186). Dropping the short windows would create
an unreported coverage hole; rejecting the whole plan leaves that operating point unusable.

## Checkpoint-derived constraints

The checked-in, byte-verified checkpoint configurations declare:

| checkpoint | fps | min frames | temporal patch |
|---|---:|---:|---:|
| Qwen3-VL-Embedding-2B | 2 | 4 | 2 |
| Qwen3-VL-Reranker-2B | 2 | 4 | 2 |
| MCG-NJU/VideoChat3-4B | 2 | 4 | 1 |
| MCG-NJU/TimeLens2-4B | 2 | 4 | 2 |

On exact main `4dbffa2585e50e60d4dcebf6c508699aac0a35ad`, a processor-only experiment used
CPython 3.11.15, Transformers 4.57.6, Torch 2.13.0+cu130, and Pillow 12.3.0. No model weights
were loaded and no GPU inference was performed.

* Qwen embedding and reranking reject one video frame with
  `ValueError: t:1 must be larger than temporal_factor:2`.
* VideoChat3 accepts one frame because its temporal patch is one, but that does not help: the
  window must first survive Qwen embedding and reranking.
* Two references at an explicitly supplied effective rate are accepted by Qwen embedding,
  reranking, VideoChat3, and TimeLens preprocessing. For two frames over 1.0 s the Qwen prompt
  stamps `0.2 s`; over 1.4 s it stamps `0.3 s`. `video_grid_thw` proves two frames reach every
  temporal-patch-two model.

That experiment proves shape compatibility only. It does **not** justify duplicating a frame or
changing a production sampling policy: the pixel and ranking effects still need measurement.

## Exact real-media specimen

A fresh Stage-0 shot detection on the same 82,446,418-byte source returned 138 cuts. Scene 22 is
exactly `385,720–386,720 ms`: a one-second shot with a cut at each end, rather than an arbitrary
one-second slice. The existing 1-fps extractor produced one midpoint frame. Separate, bounded
experiments produced two distinct real frames at 2 fps, both strictly inside the scene. Their
SHA-256 identities are:

| representation input | SHA-256 |
|---|---|
| ordinary 1-fps frame | `cc0b4e20601daff27acb23744ddf0c18fc993610e0abe6581dd74eb3465db09c` |
| adaptive frame 1 | `c61eb2d822074a5f5c24a10b9317408eba6ec50db967091f44a6ab2cf9befd96` |
| adaptive frame 2 | `e396d66154098df29c6ff21f43656c1ee2bb07e6c6cd7a38784ce04dc6d136ad` |

All three show the same speaker and set; the two adaptive frames retain real within-shot motion.
Their 640x360 absolute pixel difference is nonzero over the full frame, with mean RGB differences
of `(3.672674, 3.535543, 3.898785)`, so “adaptive” is not a disguised duplicate.
No source pixel has been copied into the repository.

The four real checkpoint processors also accept that ordinary one-frame sample as an **image**
rather than a video. Qwen embedding/reranking and VideoChat3 produced an `image_grid_thw`; TimeLens
did too after the same checkpoint-derived 640x352 patch-grid resize its existing video path uses.
The image prompt carries no automatic timestamp, so a still policy would have to bind and inject
the measured sample time itself. This establishes processor compatibility, not retrieval or
grounding quality; real model output remains Task 1's decision evidence.

The processor tensors narrow the comparison further. On Qwen3-VL-Embedding-2B, the one-frame
image and a two-reference repeated-frame video produced the same `(880, 1536)` vision tensor,
the same `[[1, 22, 40]]` grid, and the exact same tensor SHA-256
`bc837311f8aad651eab432891cd4e0a563786730fe981eaaf35b9f7d28f3d888`; the adaptive pair
produced a different tensor, SHA-256
`71d3229e6f8d8b33bbb06e3fb95dcbb1bc580c29647f8ee7f662603c83ff6ab1`.
The image/video placeholder tokens and prompt clock still differ, so only real model embeddings can
show the final effect. VideoChat3, whose temporal patch is one, retained two full frame tensors for
both repeated and adaptive video. This is why processor shape alone cannot select the policy.

A second processor-only experiment tested whether the adaptive option is a one-second special
case. The first 500 ms of scene 22 was sampled as exactly two interval-centred real frames
(effective 4 fps), still wholly inside the shot. Their SHA-256 values are
`b9cfe5503ca4c890637f16935c903ce360e4888107f977930644fbd124d00c62` and
`c53957c8b1bd0321f826c489de2e2aeb7c843a0995fb8d9fee10c54591430b25`; mean absolute RGB
difference is `(2.821359, 2.685760, 3.061042)`. All four processors consumed exactly two frames:

| checkpoint | model-visible grid | temporal patch | frames seen | prompt stamps |
|---|---|---:|---:|---|
| Qwen embedding | `[[1, 22, 40]]` | 2 | 2 | `(0.1,)` |
| Qwen reranker | `[[1, 22, 40]]` | 2 | 2 | `(0.1,)` |
| VideoChat3 | `[[2, 26, 46]]` | 1 | 2 | `(0.1,)` |
| TimeLens2 | `[[1, 22, 40]]` | 2 | 2 | `(0.1,)` |

TimeLens used its checkpoint-derived 640x352 patch-grid resize; the other inputs stayed 640x360.
This proves processor compatibility and bounded clock semantics even when the effective adaptive
rate exceeds the checkpoints' ordinary 2 fps sampling declaration: because the delivered count
is two, no processor drops or pads a frame. It does not yet prove real-model retrieval or reading
quality, which remains the GPU decision gate below.

The same preflight exposed one warning that could otherwise contaminate the model comparison.
Transformers 4.57.6 warns that TimeLens2's `Qwen2Tokenizer` carries the Mistral-regex pattern and
recommends `fix_mistral_regex=True`. Loading the exact pinned processor both ways produced
byte-identical token-id sequences for the complete grounding prompt with the positive Sorani query,
the contrast Sorani query, doubled spaces, a newline, a decimal, and a curly apostrophe. The two
Sorani prompts were 55 and 49 tokens respectively in both modes. Therefore the warning is recorded,
but changing the production tokenizer is not part of this unit: it did not change any tested input
and a loader change without model-output evidence would be a new unmeasured recipe.

The non-repository measurement harness now covers all four real checkpoints sequentially. Its
SHA-256 is `7668657ef1f9ce23c227c141b2d6e1369a1241d49400954d0c54b85b7aa8d8bf` and it refuses an
existing result path or any pixel-identity drift. A first launch was stopped before publication
after a processor-only review found that a TimeLens still image needs the checkpoint's spatial
image-grid resize rather than its temporal video resize; no result artifact was created. The
corrected processor preflight now records an `image_grid_thw` for the still and consumes exactly
two frames for every video representation. The real inference run remains pending a GPU lease and
will use a fresh non-overwriting output.

## Alternatives and invariants

1. Drop/refuse a short scene: rejected because the planned windows no longer give Path B visual
   coverage of the media.
2. Merge with a neighbour: rejected because it crosses the scene cut Stage 2 is required to
   preserve.
3. Extend beyond the scene: rejected because the embedding would describe footage outside its
   claimed interval.
4. Allow processor padding: rejected because the model sees invented temporal duplication that
   HawEdit neither chose nor records; D-060 exists to prevent exactly this.
5. Treat one real frame as an image/still: semantically explicit, but every downstream adapter
   and the SV6D/TimeLens timestamp contract must be measured before it is eligible.
6. Extract two distinct real frames inside the same short scene at the interval-centred adaptive
   rate that makes exactly two frames: preserves cut and interval, and the processor experiment
   proves no checkpoint pads or drops them, but it creates mixed effective sampling density whose
   retrieval effect must be measured and recorded.
7. Deliberately repeat the one real frame as a declared still representation: preserves cut and
   interval and is accepted by all processors, but represents the scene as static. It is eligible
   only if the duplication, effective clock, cache identity, and downstream evidence all remain
   explicit and a real-model comparison supports it.

The implementation choice will be made from a real-pixel/model experiment after the active
long-form ASR run releases both GPUs. Until then, alternatives 5–7 remain candidates rather than
decisions.

## Required proof

The selected representation must:

* preserve every planned scene interval without crossing a cut or claiming outside footage;
* make synthetic/repeated/adaptive sampling explicit and serializable if it is used;
* bind the representation into the embedding cache identity;
* prove the exact delivered count at the embedder, reranker, reader, and TimeLens boundaries;
* preserve timestamp bounds on the original scene clock;
* make a single bad scene a named per-scene refusal only when representation is genuinely
  impossible, never a raw backend crash;
* complete Path B at 1 fps on the representative long-form media; and
* rerun the canonical gate plus an exact real-GPU comparison before closing #22.

## Exact real-model decision protocol

The decision experiment is fixed before either visual checkpoint is loaded. It uses scene 22's
three immutable pixel identities above and compares these representations of the same
`385,720–386,720 ms` interval:

1. one real midpoint frame, explicitly presented as an image/still;
2. two references to that same frame, explicitly declared as a repeated-still video; and
3. the two distinct real in-scene frames, explicitly declared as an adaptive two-frame video.

No experiment may seek before `385,720 ms`, seek at or after `386,720 ms`, merge a neighbour, or
let a processor silently add or discard a frame. The positive retrieval query is
`پیاوێک لە ستۆدیۆدا قسە دەکات`; the contrast query is `دیمەنی سروشت و چیا`. Both pass through the
production Sorani normaliser. The run records, per representation:

* decoded prompt and model-visible temporal/image grid;
* Qwen embedding norm, SHA-256 of canonical float32 vector bytes, and pairwise cosine similarity;
* Qwen reranker score for both fixed queries;
* VideoChat3 raw answer, parsed SV6D or named refusal, and every cited timestamp;
* wall time, CUDA device, peak allocated/reserved memory, and post-`close()` allocated memory; and
* exact source revision, checkpoint revisions, Python/Torch/Transformers versions, and input pixel
  SHA-256 values.

Models run sequentially and are closed before the next checkpoint is constructed. A policy is
eligible only when every checkpoint boundary either consumes exactly the declared representation
or issues a named refusal, the positive/contrast scores are finite, all generated evidence is
inside the original interval, and a second identical run reproduces the deterministic outputs.
The ADR will choose among eligible policies from these measurements and §3 semantics; no numeric
threshold will be invented after seeing the scores.
