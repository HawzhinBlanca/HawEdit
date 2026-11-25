# Research — One command, many reels (a2-one-command-reels)

Date: 2026-11-18. Host: `HawaPC01` (`Windows-11-10.0.26300-SP0`, CPython `3.12.10`, dual RTX 3090 Ti 24564 MiB, driver `617.42`, `ffmpeg 8.1.1-full_build-www.gyan.dev`). Base commit: `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. GPU assignment: Lane 1 owns GPU `0` (`CUDA_VISIBLE_DEVICES=0`).
Serena MCP was unavailable; callers were mapped via `rg`.

Evidence files from this research:
- [4K VP9 vs 1440p H.264 baseline](../../evidence/4k-vp9-decode-and-stage0-2026-11-18.md)
- [A2 refusal and readiness audit](../../evidence/a2-pipeline-refusal-2026-11-18.md)

## 1. Exact Gate That Stops a Real Run Today (A2 Diagnosis)

Tested on the 5-minute 4K VP9 excerpt `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` (`300.014 s`, `264,329,839` B, SHA-256 `6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`):

1. **Default invocation (no stage flags):**
   - `python -m hawedit.pipeline EXCERPT.mp4 --work-dir ...` runs Stage 0 only, then stops at Stage 1 with `SKIPPED transcript [Stage 1 producer not enabled]` and `run is INCOMPLETE — 9 stage(s) did not run` (exit `1`), because Stage 1/3/4 defaults leave `--omni-asr`, `--gemini`, and `--auto-select` disabled (`src/hawedit/pipeline.py:4901-4946, 5517-5543`).
2. **With `--omni-asr --gemini --auto-select` (both LoRA default and `--omni-asr-checkpoint ...kurdish_omniasr_7b_v12_c750.pt`):**
   - Stage 0 completes, then Stage 1 fails immediately on:
     `RuntimeError: canonical OmniASR WSL2 runtime receipt is invalid: OmniASR WSL readiness receipt is missing or not a regular file: C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr\sources\a7b54139328bd7a9\.ready. Run hawedit-asr-setup`
   - Exact root cause: `WslOmniAsrProducer._runtime()` (`src/hawedit/asr.py:1842-1874`) falls back to `load_wsl_runtime_receipt()` (`src/hawedit/wsl_setup.py:1172`) whenever neither `self.interpreter` nor `HAWEDIT_WSL_PYTHON` is set. `load_wsl_runtime_receipt` insists on a hashed source-copy snapshot and `.ready` receipt inside `%LOCALAPPDATA%\HawEdit\wsl-asr\sources\<digest[:16]>\` (`C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr` does not exist on this machine), identical to the 2026-10-14 failure in `evidence/zar-real-retest-preflight-20261014.md`.

## 2. Downstream Blockers Discovered Beyond the Receipt Gate

Running the audit past Stage 0 revealed six additional blockers on a default real run:

| Blocker | Observed State on HawaPC01 (2026-11-18) | Code / Location |
|---|---|---|
| Host CUDA / `.venv` | `.venv` has `torch 2.13.0+cpu` (`cuda False`); passing `--visual` exits nonzero before Stage 0 (`this machine reports 0 CUDA device(s)`). | `pyproject.toml:32`, `src/hawedit/pipeline.py:5545-5551` |
| 4K VP9 Stage 0 decode | `ingest` took `341.341 s` (`0.88x` RT) on 300s 4K VP9 (`extract_proxy` `160.529 s`, `detect_shots` `~160.8 s`) vs `136.554 s` (`2.20x` RT) on derived 1440p H.264, with identical 33 `shot_cuts_ms` and 61 `speech` regions. Cause: `-threads 1` hardcoded in `extract_proxy` (`ingest.py:493`) and OpenCV 4K CPU decode in `detect_shots` (`ingest.py:534`). | `src/hawedit/ingest.py:10-11, 445, 493, 534` |
| WSL2 OmniASR assets & v12 | `/home/ai/.venv-wsl-whisper` exists (`torch 2.8.0+cu128`, `fairseq2 0.6`, `omnilingual-asr 0.2.0`, `peft 0.19.1`; `qwen-asr` absent). `/home/ai/.cache/fairseq2/assets/` lacks `omniASR-CTC-3B-v2.pt` and `omniASR-LLM-7B-v2.pt` (only `omniASR-CTC-1B-v2.pt` is cached). Fused v12 checkpoint (`kurdish_omniasr_7b_v12_c750.pt`, tokenizer, `SHA256SUMS`) sits at `F:\Kurdish Sorani Dataset\omni_7b_v3_continuation\runs\champion_v12_lora64_750_fused\`. Unconditional `VALIDATOR_MODEL_ID` check (`asr.py:1898-1909`) also fails unless `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` is downloaded or validator is optional (B6). | `src/hawedit/asr.py:1898-1909`, `models/sources.json` |
| GPU VRAM floor & device ownership | `DEFAULT_ASR_DEVICE = "cuda:1"` (`asr.py:127`) and `assert_gpu_headroom` (`asr_worker.py:60`) require `20.0 GiB` free. Resident WSL servers on `:8000/:8001` currently leave `6,256 MiB` free on GPU 0 and `7,849 MiB` free on GPU 1. Lane 1 is assigned GPU 0; `HAWEDIT_ASR_*_DEVICE` overrides exist. | `src/hawedit/asr.py:126-127`, `src/hawedit/asr_worker.py:60-84` |
| Judge deprecation & billing | `gemini-2.5-pro` auto-routes to `gemini-3.8-flash` on 2026-12-01 (`BLOCKED.md #3`, `A5` addresses upgrade to `gemini-4-argon` / `gemini-4-carbon`, requires confirmed paid key). | `src/hawedit/judge.py:92`, `BLOCKED.md #3` |
| Face tracker model | `models/face_detection_yunet.onnx` absent (`OpenCvFaceTracker` uses Haar fallback; measured `60/60` on 0–30 s of 1440p in `23.387 s`). | `src/hawedit/reframe.py:318` |

## 3. Existing Multi-Clip Support (`--max-clips` & Delivery)

- `src/hawedit/pipeline.py` already supports `--max-clips` (`4955+`, `5410-5416`, `5705`) and `_run_episode_delivery` (`2598-2650`), called at `3432`, `3626`, and `3727` to deliver up to `N` ranked non-overlapping clips with `.measured.json` sidecars and `episode_manifest.json`.
- Missing pieces for A2's one-command workflow:
  1. Running `python -m hawedit.pipeline EPISODE.mp4 --work-dir work` currently does nothing after Stage 0 unless `--omni-asr`, `--gemini`, `--auto-select`, `--max-clips` (5–10), and `--wsl-python` / runtime fixes are supplied.
  2. There is no `--output-dir` (or clean automatic export into `D:\HawEdit-media\reels\<run>\`) or `--strict-runtime` boundary (coordinated with `A3`).
  3. Per-stage wall times are not recorded in `PipelineRun` / `.measured.json` / CLI JSON summary.
  4. `load_wsl_runtime_receipt` / `resolve_champion_checkpoint` / `VALIDATOR_MODEL_ID` enforcement assumes the WSL sealed source-snapshot setup rather than plain WSL execution against `/home/ai/.venv-wsl-whisper/bin/python` + `/mnt/...` worktree paths.

Answers to: `BLUEPRINT.md` §3, §4, §6, §7; `DECISIONS.md` D-331, D-334, D-335 (proposes **D-336**); `BLOCKED.md` #3, #21, #24.
