# Plan — One command, many reels (a2-one-command-reels)

Read [`research.md`](./research.md) and [`spec.md`](./spec.md) first. Baseline measurements in [`evidence/4k-vp9-decode-and-stage0-2026-11-18.md`](../../evidence/4k-vp9-decode-and-stage0-2026-11-18.md) and [`evidence/a2-pipeline-refusal-2026-11-18.md`](../../evidence/a2-pipeline-refusal-2026-11-18.md).

## Approach

Fix the real causes blocking end-to-end reel generation on HawaPC01 without deleting any existing security or fail-stop invariant:

1. **Unblock plain WSL OmniASR execution (without deleting the receipt gate):**
   - Keep `load_wsl_runtime_receipt` intact and required whenever `--strict-runtime` / `HAWEDIT_STRICT_RUNTIME=1` is passed (per `A3`).
   - On default single-user desktop runs, allow `WslOmniAsrProducer` to resolve WSL Python directly from `HAWEDIT_WSL_PYTHON` or the discovered distro venv (`/home/ai/.venv-wsl-whisper/bin/python`) and mount the local worktree `src/` path into WSL (`PYTHONPATH`), failing stopped cleanly if WSL, `.venv-wsl-whisper`, or weights (`kurdish_omniasr_7b_v12_c750.pt`, `omniASR_CTC_3B_v2.pt`) are absent.
   - Make champion checkpoint auto-discovery check configured paths (`HAWEDIT_CHAMPION_CHECKPOINT` or known local fused directory `F:\Kurdish Sorani Dataset\...\kurdish_omniasr_7b_v12_c750.pt`) cleanly before failing over to LoRA adapter lookup, and decouple validator checkpoint check when `--no-validator` / validator-off mode (aligned with Phase B6) is used or until `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` is staged.
   - Honor GPU selection cleanly (`CUDA_VISIBLE_DEVICES=0` / `HAWEDIT_ASR_DEVICE=cuda:0` for Lane 1 when `cuda:1` headroom is below budget or operator pins GPU 0) without violating explicit device fail-stop rules.
2. **Stage 0 & 1440p ingest throughput:**
   - Derive a 1440p H.264 copy of the 40-minute AI episode (`zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM.mp4`) into `D:\HawEdit-media\excerpts\` using GPU 0 NVENC (never touching `D:\HawEdit-media\sources\`).
   - Add configurable `--ingest-threads` (default auto/bounded rather than hardcoded `-threads 1`) in `extract_proxy` (`ingest.py:493`) and reuse `proxy.mp4` (or fast OpenCV thread config) for `detect_shots` while verifying cut/speech parity against the 4K excerpt (`33` cuts, `61` speech regions).
3. **One-command production defaults + reel output folder + stage timings:**
   - Wire `pipeline.py` so `python -m hawedit.pipeline EPISODE.mp4 --work-dir work [--output-dir D:\HawEdit-media\reels\<run>]` uses clean one-command defaults (`--omni-asr`, active judge from `A5`, `--auto-select`, `--max-clips 10`, plain WSL runtime unless `--strict-runtime`) while preserving explicit offline/test overrides (`--transcript`, `--verdict`, `--stock-decoder`, unit tests calling `run_pipeline(...)` directly).
   - Record monotonic wall-clock seconds per stage (`stage_timings_s`) on `PipelineRun`, CLI text/JSON report, and copy/export delivered episode clips + `.measured.json` sidecars into `--output-dir` (`D:\HawEdit-media\reels\<run>\`).
4. **Deliver 10 real reels & measure stage wall times:**
   - Prerequisite checks: confirm `omniASR-CTC-3B-v2.pt` presence/provisioning in WSL fairseq2 cache (only approved model download, no unapproved model edits), confirm `A3` (receipt/VEX park) + `A5` (judge upgrade & paid key #3), then run full 40-minute 1440p AI episode to produce 10 reels in `D:\HawEdit-media\reels\<run>\` and log wall time per stage in `evidence/`.

## Files and symbols

| File | Symbol | Planned Change |
|---|---|---|
| `src/hawedit/asr.py` | `WslOmniAsrProducer._runtime` (`:1842`), `resolve_champion_checkpoint` (`:380`), `create_omni_asr_producer` (`:2015`) | Plain WSL discovery + strict toggle (`require_receipt`); optional/lazy validator resolution when disabled; honor `HAWEDIT_ASR_DEVICE` cleanly |
| `src/hawedit/ingest.py` | `extract_proxy` (`:478`), `detect_shots` (`:534`), `ingest` (`:787`) | Parameterize decode/proxy threads (`-threads 0` / configurable) & support proxy-assisted shot detection |
| `src/hawedit/pipeline.py` | `PipelineRun` (`:330+`), `_run_episode_delivery` (`:2598`), `run_pipeline` (`:2812`), `build_parser` (`:4884`), `_build_and_run` (`:5325+`) | Add `--strict-runtime`, `--output-dir`, `--ingest-threads`, one-command defaults (CLI entrypoint only, preserving unit `run_pipeline` defaults), export reels + `.measured.json`, record `stage_timings_s` |
| `tests/test_a2_one_command_reels.py`, `tests/test_pipeline.py` | New AC tests + existing CLI/ingest tests | Test-first coverage of AC1–AC5 |
| `DECISIONS.md`, `PROGRESS.md` | New `D-336`, progress row | Record architectural decision + verified measurements |

## Divergence, Cross-Lane Dependencies, and Risks

- **Proposed ADR (`D-336`):** Plain WSL runtime default for single-user desktop runs alongside `--strict-runtime` gate preservation, configurable ingest threading, and `--output-dir` reel delivery with per-stage timing.
- **Blocking dependencies before implementation:**
  1. **`A3` (`D-337`) or VEX re-pin:** Modifying `src/hawedit/*.py` changes `package_digest(src/hawedit)`, which causes `tests/test_vex.py` to fail unless `A3` is approved in the same batch or the owner re-pins `REVIEWED_VEX_SOURCE`.
  2. **`A5` (`D-339`) + `BLOCKED.md #3`:** End-to-end real Path A + Stage 4 judging needs the upgraded Gemini Pro model and confirmed billing on `GEMINI_API_KEY`.
  3. **Model assets in WSL:** Plain WSL execution of the 40-min episode requires `omniASR-CTC-3B-v2.pt` (12.3 GB) in `/home/ai/.cache/fairseq2/assets/` alongside `kurdish_omniasr_7b_v12_c750.pt` (F:) and freeing/sharing GPU 0 VRAM cleanly with any resident servers.
- **No silent fallbacks:** If `v12_c750.pt`, `CTC-3B`, WSL venv, GPU headroom, or Gemini billing is unavailable, `pipeline.py` still fails stopped with the explicit blocker rather than dropping down to synthetic/stock paths.
- **Existing CLI unit tests:** Existing tests in `tests/test_pipeline.py` invoking `build_parser().parse_args(...)` without `--transcript`/`--omni-asr` and expecting Stage 1–6 to report skipped defaults must be audited; keeping `run_pipeline()` signature defaults untouched and isolating desktop auto-enablement cleanly (or opting CLI desktop preset only when requested/documented in tests) avoids breaking existing contract tests — exact CLI test updates will be verified via `verify.sh --fast` and targeted pytest before lead gate.

## Owner Actions Folded Into This Approval

1. Approve this plan (`D-336`), coordinated with `A3` (`D-337`) so editing `src/hawedit/` does not wedge `tests/test_vex.py`.
2. Confirm `CUDA_VISIBLE_DEVICES=0` / stopping idle resident WSL `:8000/:8001` servers during full-episode GPU runs if needed to free ~18+ GB VRAM on GPU 0 (or confirming ASR GPU headroom allocation for Lane 1 GPU 0 / Lane 2 GPU 1).
3. Approve staging `omniASR-CTC-3B-v2.pt` into WSL fairseq2 asset cache if missing for full CTC alignment.

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"
