# hawapc01 — what this machine actually is, measured

Date: 2026-08-08. Every prior entry in `BLOCKED.md` was assessed in a cloud container with no
GPU and a deny-all proxy. This checkout is not there. Nothing below is inferred from a
hostname or a config file; each row is the output of a command run on this box.

## The machine

| Fact | Command | Result |
|---|---|---|
| Hostname | `icacls` on a temp file, owner principal | `HAWAPC01\Wareen` |
| GPU | `nvidia-smi --query-gpu=name,memory.total,driver_version` | 2 × `NVIDIA GeForce RTX 3090 Ti`, `24564 MiB` each, driver `596.36` |
| ffmpeg | `ffmpeg -version` | `8.1.1-full_build`, on `PATH` |
| RTL stack | `ffmpeg -buildconf` | `--enable-libass --enable-libharfbuzz --enable-libfribidi` |
| NVENC | `ffmpeg -buildconf` | `--enable-nvenc` (also `--enable-cuda-llvm`, `--enable-nvdec`) |
| OS | — | Windows 11 Pro 10.0.26200 |
| Python | `py --version` | 3.12.10 base; the project venv is 3.11.15 |

Two 24 GiB cards is exactly §6's "2×24 GiB" and exactly the split §3 Stage 1 assumes:
`omniASR_LLM_7B_v2` on GPU 0 at ~17 GiB, `omniASR_CTC_3B_v2` on GPU 1 at ~8 GiB. **This is the
box §8.1 means when it says "real-time factor measured on hawapc01".**

## Network — every host `BLOCKED.md` #6 recorded as denied

`Invoke-WebRequest -Method Head`, from this machine:

| Host | Container (2026-08-06) | hawapc01 (2026-08-08) |
|---|---|---|
| `huggingface.co` | connection refused by proxy | **200** |
| `commonvoice.mozilla.org` | connection refused by proxy | **200** |
| `www.openslr.org` | connection refused by proxy | **200** |
| `zenodo.org` | connection refused by proxy | **200** |
| `datasets-server.huggingface.co` | `403` to CONNECT | reachable (404 to a HEAD on `/`, which is the app answering) |

## Weights — a homepage 200 is not a download

Reachability of a host says nothing about whether a *file* can be fetched, so each §7 repo was
asked for a real file over `https://huggingface.co/<repo>/resolve/main/<file>`:

| Repo | File | Result |
|---|---|---|
| `Qwen/Qwen3-VL-Embedding-2B` | `config.json` | **200** — `{"architectures": ["Qwen3VLForCo…` |
| `Qwen/Qwen3-VL-Reranker-2B` | `config.json` | **200** — `{"architectures": ["Qwen3VLForCo…` |
| `MCG-NJU/VideoChat3-4B` | `config.json` | **200** — `{"architectures": ["VideoChat3Fo…` |
| `MCG-NJU/TimeLens2-4B` | `config.json` | **200** — `{"architectures": ["Qwen3VLForCo…` |
| `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` | `config.json` | **200** — `{"architectures": ["Qwen3ASRForC…` |
| `pyannote/speaker-diarization-community-1` | `config.yaml` | **401 Unauthorized** |
| `facebook/omniASR-LLM-7B` | `README.md` | **200** — `license: apache-2.0` |

The 401 is the point of the table: `BLOCKED.md` #4 is not resolved by the network opening, and
now there is a measurement saying so rather than an assumption. The Hub also reports the repo
as `🔒 Gated`, `license:cc-by-4.0` — the licence whose attribution notice §7 and §10 require.

## The four §7 names that are checkpoints, not repositories

`models.py` refuses to guess these (D-022). Two resolved unambiguously and are now configured
in `models/sources.json`; two did not.

| §7 name | Resolution |
|---|---|
| `Qwen3-VL-Embedding-2B` | `Qwen/Qwen3-VL-Embedding-2B` — exact name, official namespace, `apache-2.0` (the licence §7 records), 8.9M downloads, 2127.5M params |
| `Qwen3-VL-Reranker-2B` | `Qwen/Qwen3-VL-Reranker-2B` — exact name, same namespace and licence, 580K downloads |
| `omniASR_LLM_7B_v2` | **unresolved** — `BLOCKED.md` #10 |
| `omniASR_CTC_3B_v2` | **unresolved** — `BLOCKED.md` #10 |

Meta publishes thirteen omniASR checkpoints under `facebook/`, all Apache-2.0:
`omniASR-LLM-{300M,1B,3B,7B}`, `omniASR-LLM-7B-ZS`, `omniASR-CTC-{300M,1B,3B,7B}`,
`omniASR-W2V-{300M,1B,3B,7B}`. **None carries a `_v2` suffix.** The sizes §7 wants exist; the
version marker in their §7 names does not. Picking the un-suffixed checkpoint would produce a
model that loads, runs, and returns plausible Sorani — and might not be the model §8.1's
numbers are supposed to be about. That failure is silent, so it is a decision, not a lookup.

## What this changes

Resolved: `BLOCKED.md` #2 (GPU) and #6 (network reachability).
Still live: #1 (labelled audio), #3 (Gemini credentials + the ZDR governance answer),
#4 (gated repo — measured 401 above), #7 (required CI check), #9 (M8's two models), and the
newly separated **#10**, which #6 had been masking: while nothing could be downloaded, "we
cannot reach it" and "we do not know which repository it is" looked identical.
