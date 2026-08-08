# The GPU stack on hawapc01, verified — and two things it cannot say

Prerequisite for M5.2, M5.4 and M6.3. `scripts/setup.sh` installs **CPU** torch on purpose (§6
puts Stage 0 on CPU, and the CUDA build is gigabytes of kernels Stage 0 never calls), and its own
comment anticipates this: *"A GPU box that wants the CUDA build can install it after."* This is
that "after", measured.

## What is installed, and one trap on the way

| Package | Version | Licence |
|---|---|---|
| `torch` | **2.13.0+cu130** | BSD-3-Clause |
| `torchvision` | 0.28.0+cu130 | BSD-3-Clause |
| `transformers` | 5.14.1 | Apache-2.0 |
| `sentence-transformers` | 5.7.0 | Apache-2.0 |
| `accelerate` | 1.14.0 | Apache-2.0 |
| `pillow` | 12.3.0 | MIT-CMU (HPND) |

No NonCommercial licence anywhere, which `registry.assert_commercially_usable` treats as a hard
reject and D-002 requires checking before use.

**The trap.** `pip install torch==2.13.0 --index-url .../cu130` reported success and changed
nothing: the CPU wheel already installed *is* version `2.13.0`, so the requirement was already
satisfied and pip no-op'd. `torch.cuda.is_available()` stayed `False` and
`torch.__version__` stayed `2.13.0+cpu` — a green install and no CUDA. The local version has to
be named explicitly, `torch==2.13.0+cu130`. PEP 440 makes `==2.13.0` match any local version, so
`pyproject.toml`'s pin still holds and nothing had to be loosened.

`cu130` is also the only channel carrying torch 2.13.0 for cp311/Windows — `cu128` stops at
2.9.1 and `cu129` at 2.9.0 — so keeping the pinned version and getting CUDA are the same choice.

## Both cards do real work

```
cuda:0 NVIDIA GeForce RTX 3090 Ti  24.0 GiB  sm_86
cuda:1 NVIDIA GeForce RTX 3090 Ti  24.0 GiB  sm_86
cuda:0 bf16 4096x4096 matmul -> 8.567e+08  ok=True
cuda:1 bf16 4096x4096 matmul -> 8.565e+08  ok=True
cuDNN: 92000 | CUDA built: 13.0
```

sm_86 is Ampere, so bfloat16 is native — which matters because every §7 checkpoint here declares
`dtype: bfloat16`.

## §7 weights on disk — 33.7 GB, all Apache-2.0

| Component | Size | Notes |
|---|---|---|
| `Qwen3-VL-Embedding-2B` | 4.0 GB | `Qwen/Qwen3-VL-Embedding-2B` |
| `Qwen3-VL-Reranker-2B` | 4.0 GB | `Qwen/Qwen3-VL-Reranker-2B` |
| `MCG-NJU/TimeLens2-4B` | 9.1 GB | M6.3 |
| `MCG-NJU/VideoChat3-4B` | 8.4 GB | M5.4 |
| `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` | 8.2 GB | §3 Stage 1's *validator* |

Not downloaded: `pyannote/speaker-diarization-community-1` (gated, `BLOCKED.md` #4) and the two
omniASR checkpoints (43.5 GB, no loader on this OS — `BLOCKED.md` #11).

## The embedder runs

`Qwen3-VL-Embedding-2B` on `cuda:0` in bfloat16:

```
loaded in 4.9s
dim: 2048
text embeddings: (2, 2048) | norms: [1.0022, 1.0018]
peak VRAM: 3.98 GiB
```

Real Kurdish text in, 2048-d L2-normalised vectors out. 3.98 GiB leaves the whole second card
free, which is the layout §3 Stage 1 assumes. The model's own recipe — read from the files it
shipped with, not guessed — is `lasttoken` pooling, dimension 2048, then Normalize, with the
prompt `"Represent the user's input."` and cosine similarity. `visual_index._cosine` already
matches that.

## Finding 1 — a window must go in as a video, and that is not the obvious call

§7 **excludes CLIP** with a stated reason: *"Frame-averaging loses temporal structure — 0.325 vs
0.75+ NDCG@10."* So how a `SceneWindow`'s frames reach the model decides whether Stage 2 is the
thing §3 designed or the thing §7 rejected. Measured, four frames of the fixture:

| Input | Result |
|---|---|
| one PIL image | `(2048,)` |
| **list** of 4 PIL images | `(4, 2048)` — four separate embeddings |
| `{"video": frames}` | **`(2048,)`** — one embedding for the window |
| `[{"video": frames}]` | `(1, 2048)` |

The list form is the one that invites a mean afterwards, and it is available, silent, and
type-correct. `{"video": ...}` is the form Stage 2 needs.

## Finding 2 — through sentence-transformers, the model is told the wrong frame rate

Every video encode emits:

```
[transformers] Asked to sample `fps` frames per second but no video metadata was provided
which is required when sampling with `fps`. Defaulting to `fps=24`.
```

§3 Stage 2's reference setting is **~1 fps**. The frames handed over are one second apart and
the model is being told they are 1/24 s apart. `visual_index.SceneWindow` already refuses a
window that quietly lowers the rate, for exactly this reason — *"the resulting embedding is
indistinguishable from an honest one"* — and this is the same mistake one layer down.

It cannot be fixed through this loader. `video_metadata` is rejected:

```
ValueError: Multimodal dict input contains unrecognized modality keys: ['video_metadata'].
Expected keys from: ['audio', 'image', 'text', 'video', ...]
```

So `sentence-transformers` — which is the loader the repo itself declares, in `modules.json` and
`config_sentence_transformers.json` — has no channel for the one setting §3 Stage 2 is specific
about. The route that does is the `transformers` processor directly, which is also what the
`scripts/qwen3_vl_embedding.py` shipped inside the checkpoint uses: it builds the chat template
itself and can pass `video_metadata` alongside `pixel_values_videos` / `video_grid_thw`.

**M5.2 is therefore not "call SentenceTransformer.encode".** It is the processor route, with the
window's real fps passed in, and a test that the fps actually reaches the model — because if it
does not, every embedding in the index is honest-looking and about footage sampled at a rate the
model was misinformed about. D-048.

## Finding 3 — planned frames and extracted frames are not the same number

`SceneWindow.frame_count` for the 4162 ms fixture at 1 fps is `ceil(4.162) = 5`. ffmpeg's
`fps=1` filter over the same span emits **4**. The window's count is a plan; ffmpeg's output is
the fact. This is M3.4's lesson in a new place — there, `RenderResult.duration_ms` was the
request echoed back and the file was never opened. Whatever embeds a window has to carry the
count it actually saw, not the count that was planned.
