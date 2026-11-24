```yaml
commit: 1714a8b1312299fc62835bdc4bdaae7fdd30e7bf
media_sha256: 6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir C:\Temp\he-a2-4k --omni-asr --gemini --auto-select
```

# A2 Pipeline Refusal & Downstream Readiness Audit (2026-11-18)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`
- **Git commit:** `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`
- **Env:** `PYTHONIOENCODING=utf-8`, `HAWEDIT_MEDIA_ROOT=D:\HawEdit-media`, `CUDA_VISIBLE_DEVICES=0`
- **Input excerpt:** `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` (SHA-256 `6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`, `300.014 s`)

## Exact Refusal Logs Measured Today

### 1. Default invocation (no stage flags)

Command: `.venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir C:\Temp\he-a2-4k` (captured in `C:\Temp\he-a2-4k\cli_default_text.stdout.txt`, exit `1`):

```text
media   zar-ai-lamo__RO1PmSoqmCM__05m00-10m00
stage 0 300014 ms · 33 shot cut(s) · 61 speech region(s) · diarization unavailable
stage 2 34 scene window(s) · 315 frame(s) at 1.0 fps · local visual retrieval not enabled
stage 1 original ASR routing unavailable
SKIPPED diarization [Stage 0 diarization producer not enabled]: no Stage 0 diarization producer was enabled. Community-1 remains gated; enable only an authenticated, integrity-verified producer rather than treating no result as zero speakers.
SKIPPED transcript [Stage 1 producer not enabled]: no Stage 1 producer was enabled. Supply --transcript or run the canonical omniASR_LLM_7B_v2 + omniASR_CTC_3B_v2 path with --omni-asr.
SKIPPED index [a transcript]: index did not run because a transcript was not available.
SKIPPED visual_index [visual discovery not enabled]: local visual retrieval was not enabled. Use --visual to compose frame extraction, Qwen indexing, top-50 retrieval, reranking, a 5–10 survivor set and VideoChat3.
SKIPPED discovery [discovery producer not enabled]: no Stage 3 producer was enabled. Select --gemini or --vertex-project for Path A, --visual with --visual-query for composed Path B — Stage 2 must retrieve against a query, and the whole transcript is the corpus rather than a fallback query — or both for the two-sided union.
SKIPPED editorial [Stage 4 judgment not enabled]: no Stage 4 judge or persisted verdict was supplied. Use --gemini for non-confidential work, --vertex-project with governance confirmation for confidential work, or --verdict for an already-reviewed exact span. Note that §4 pins gemini-2.5-pro and it has a free-tier limit of exactly zero, so --gemini needs billing on the key's project — BLOCKED.md #3.
SKIPPED boundary [complete selected sentences]: boundary did not run because complete selected sentences was not available.
SKIPPED render [a judged boundary and QC pass]: render did not run because a judged boundary and QC pass was not available.
SKIPPED delivery [a successful render]: delivery did not run because a successful render was not available.

run is INCOMPLETE — 9 stage(s) did not run
```

### 2. Canonical OmniASR + Gemini (`--omni-asr --gemini --auto-select`, LoRA or fused v12)

Both commands stopped identically at Stage 1 (`C:\Temp\he-a2-4k\cli_omni_gemini_autoselect_text.stdout.txt` and `cli_omni_v12_gemini_autoselect_json.stdout.txt`, exit `1`), matching the 2026-10-14 preflight refusal in `evidence/zar-real-retest-preflight-20261014.md`:

```text
SKIPPED transcript [canonical ASR runtime]: canonical ASR runtime failed with RuntimeError: canonical OmniASR WSL2 runtime receipt is invalid: OmniASR WSL readiness receipt is missing or not a regular file: C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr\sources\a7b54139328bd7a9\.ready. Run hawedit-asr-setup
```

Why this happened:
- `src/hawedit/pipeline.py:5538-5543` calls `create_omni_asr_producer("auto", ...)` -> `WslOmniAsrProducer._runtime()` (`src/hawedit/asr.py:1842-1874`).
- Unless `interpreter` or `HAWEDIT_WSL_PYTHON` is set, `_runtime()` calls `load_wsl_runtime_receipt()` (`src/hawedit/wsl_setup.py:1172`), which demands `C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr\sources\<package_digest(src/hawedit)[:16]>\.ready` (plus an exact immutable source snapshot and WSL lock match).
- On disk today, `C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr` does not exist (`exists: False`), even when `--omni-asr-checkpoint` points directly to the fused v12 file.

### 3. Visual discovery flag (`--omni-asr --gemini --visual --auto-select`)

Captured in `C:\Temp\he-a2-4k\cli_omni_gemini_visual_autoselect_text.stderr.txt` (exit nonzero before Stage 0):

```text
✗ this machine reports 0 CUDA device(s), and the run asks for Stage 2 indexing on cuda:1; the Path B reader on cuda:0. §6 assigns the video phase across two GPUs (GPU 0 → VideoChat3-4B, GPU 1 → Embedding / Reranker / TimeLens2), so the defaults assume hawapc01's pair. On fewer, pass the devices you have — e.g. --index-device cuda:0 --timelens-device cuda:0 — and expect the video phase to serialise.
```

Why this happened: `.venv\Scripts\python.exe` has `torch 2.13.0+cpu` (`torch.cuda.is_available() == False`, matching `pyproject.toml:32` `[media]` extra instead of `+cu130`).

## Downstream Stage & Readiness Audit (2026-11-18)

| Subsystem | Inspected Result | Code / Location |
|---|---|---|
| Component readiness (`python -m hawedit.models`) | `5/15 available` (`PySceneDetect`, `Silero VAD`, `Custom Viterbi`, `KLPT`, `ASS/ffmpeg` OK). `omniASR_LLM_7B_v2` and `omniASR_CTC_3B_v2` FAIL on missing `...\a7b54139328bd7a9\.ready`. All HF weights report `not downloaded` in repo `models/`. | `src/hawedit/models.py`, `models/sources.json` |
| Host HF model cache | `F:\huggingface\hub` holds `models--Qwen--Qwen3-VL-Embedding-2B`, `models--Qwen--Qwen3-VL-Reranker-2B`, `models--MCG-NJU--VideoChat3-4B`, `models--MCG-NJU--TimeLens2-4B` (outside repo `models/`). | `F:\huggingface\hub` |
| WSL2 Ubuntu ASR runtime & weights | `/home/ai/.venv-wsl-whisper` exists (`torch 2.8.0+cu128`, `fairseq2 0.6`, `omnilingual-asr 0.2.0`, `peft 0.19.1`, `transformers 4.46.0`; `qwen-asr` absent). `/home/ai/.cache/fairseq2/assets/` contains `omniASR-CTC-1B-v2.pt` (3.7G) + `tmpy6d4q2mt`; missing `omniASR-CTC-3B-v2.pt` and `omniASR-LLM-7B-v2.pt`. Fused v12 champion (`kurdish_omniasr_7b_v12_c750.pt`, `omniASR_tokenizer_written_v2.model`, `SHA256SUMS`) is present at `F:\Kurdish Sorani Dataset\omni_7b_v3_continuation\runs\champion_v12_lora64_750_fused\`. | `src/hawedit/asr.py:1898-1909` (also validates `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` unconditionally via `ModelStore`) |
| GPU VRAM headroom (`nvidia-smi`) | GPU 0: `6,256 MiB` free / `24,564 MiB`; GPU 1: `7,849 MiB` free / `24,564 MiB`. WSL processes PID `520`/`521` (`server.py --port 8000/8001`) and `525` (`dengnoos_gateway.py`) are resident. `asr_worker.assert_gpu_headroom` defaults to `20.0 GiB` on `DEFAULT_ASR_DEVICE = "cuda:1"`. | `src/hawedit/asr.py:127`, `src/hawedit/asr_worker.py:60` |
| VEX / Source digest pin | Live `package_digest(src/hawedit)` is `a7b54139328bd7a9a79c0d62237683ebc517d9e247367fe81928425ac1ea62f2`, matching `security/wsl-asr-vex.json` and `REVIEWED_VEX_SOURCE` (`2026-10-15`), while `expires` is `2026-11-14` (past). Any change under `src/hawedit/` breaks `tests/test_vex.py` unless A3 parks the binding or the owner re-pins. | `security/wsl-asr-vex.json`, `tests/test_vex.py:27-30,140-163` |
| Credentials (`hawedit.credentials --check`) | `C:\Users\Wareen\AppData\Roaming\hawedit\credentials.env` present (ACL owner-only): `GEMINI_API_KEY: …IEu4` accepted with 50 models visible (`HF_TOKEN` also configured; raw values never read or printed). Paid `generateContent` billing was NOT exercised in Round 1 (`BLOCKED.md #3` notes free-tier limit 0 on Pro tier). | `src/hawedit/credentials.py:577` |
| Gemini Pro-tier model deprecation (official Google docs, verified 2026-11-18) | `ai.google.dev/gemini-api/docs/deprecations` & `/docs/models`: `gemini-2.5-pro` is deprecated and **auto-routes to `gemini-3.8-flash` on `2026-12-01`** (`cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions`: Vertex AI retired `2026-10-20`). Live API probe (`:countTokens`): current `JUDGE_SHADOW = "gemini-3.1-pro"` returns **HTTP 404**; `gemini-4-carbon`, `gemini-4-argon`, and `gemini-3.1-pro-preview` are visible in `/v1beta/models` and pass `:countTokens`. | `src/hawedit/judge.py:92-93`, `src/hawedit/path_a.py:141`, `src/hawedit/pipeline.py:3587`, `src/hawedit/registry.py:298-322` |
| Face tracker (`OpenCvFaceTracker`) | `models/face_detection_yunet.onnx` does not exist (`yunet_model_exists=False`). Haar fallback tracked 0–30 s of the 1440p excerpt at `2.0 fps`: `60/60` frames (`100.0%`) in `23.387 s`. | `src/hawedit/reframe.py:260-333, 524` |
| Studio API (`POST /api/repurpose`, `GET /api/status`) | Upload validation succeeds, then `web.py:591` unconditionally returns HTTP `503` `studio_runner_unavailable`; `web.py:814` hardcodes `"status": "unavailable", "runner_ready": False`. | `src/hawedit/web.py:580-601, 807-829` |
