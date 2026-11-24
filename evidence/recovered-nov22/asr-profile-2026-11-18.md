---
commit: 56501a7fcfc8fff2cb3abe4fdc8603393054cfbf
media_sha256: 6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0
host: HawaPC01 Threadripper-3990X Windows-11-10.0.26300-SP0 / WSL2-Ubuntu 2x-RTX-3090-Ti
command: .venv/Scripts/python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir %TEMP%\he-b1-probe --omni-asr --omni-asr-checkpoint kurdish_omniasr_7b_v12_c750.pt --json && CUDA_VISIBLE_DEVICES=1 /home/ai/.cache/hawedit-plain-wsl-venv/bin/python run_wsl_asr.py --stage0-root %TEMP%\he2-asr-run --mode {5m,40m}
libraries: win-py3.12.10 torch2.13.0+cpu torchaudio2.11.0+cpu silero-vad5.1.2 scenedetect0.6.5 klpt0.1.7 numpy2.2.2 ffmpeg8.1.1-full_build-www.gyan.dev | wsl-py3.12.13 torch2.8.0+cu128 cuda12.8 fairseq2-0.6 omnilingual-asr0.2.0 klpt0.1.7 driver617.42
status: round2-gpu1-5m-complete; d342-d343-40m-complete-175-of-175
---

# B1 ASR Baseline Profile & Stage 1 Refusal Log (2026-11-18)

Baseline profiling for Phase B1 (`specs/pro-grade-program/gemini-task-sheet-2026-11-18.md`) on `HawaPC01`, commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`, `hawedit` source package digest `a7b54139328bd7a9a79c0d62237683ebc517d9e247367fe81928425ac1ea62f2`. GPU workload targeting used GPU 1 only (`CUDA_VISIBLE_DEVICES=1`); no `src/hawedit/**` or `tests/**` files were modified, and no WSL `.ready` receipt or admission guard was bypassed or forged.

## 1. Machine, Software, and Input Media Provenance

| Field | Measured Value |
|---|---|
| Host / CPU | `HawaPC01` — AMD Ryzen Threadripper 3990X (64 cores / 128 logical processors) |
| GPUs | `0`: NVIDIA GeForce RTX 3090 Ti (24,564 MiB; reserved for Lane 1), `1`: NVIDIA GeForce RTX 3090 Ti (24,564 MiB; driver `617.42`) |
| Windows host runtime | `Windows-11-10.0.26300-SP0`, CPython `3.12.10` (`.venv`), `torch 2.13.0+cpu`, `torchaudio 2.11.0+cpu`, `silero-vad 5.1.2`, `scenedetect 0.6.5`, `klpt 0.1.7`, `numpy 2.2.2` |
| FFmpeg binary | `ffmpeg version 8.1.1-full_build-www.gyan.dev` (`C:\Users\Wareen\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.EXE`) |
| WSL2 GPU runtime | CPython `3.12.13` (`/home/ai/.venv-wsl-whisper`), `torch 2.8.0+cu128`, CUDA `12.8`, `fairseq2 0.6`, `omnilingual-asr 0.2.0` (`qwen_asr` not installed) |
| 5-min excerpt input | `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` (`264,329,839 B`, SHA-256 `6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`, `300,014 ms` / `300.014 s`, VP9 `3840x2160 @ 25 fps`, Opus `48,000 Hz` 2 ch) |
| Full AI episode (40-min target) | `D:\HawEdit-media\sources\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM.mp4` (`2,030,532,996 B`, SHA-256 `17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72`, `2,391.694 s` = `39m 51.694s`, VP9 `3840x2160 @ 25 fps`, Opus `48,000 Hz` 2 ch) |
| Fused v12 checkpoint tested | `F:\Kurdish Sorani Dataset\omni_7b_v3_continuation\runs\champion_v12_lora64_750_fused\kurdish_omniasr_7b_v12_c750.pt` (`15,610,646,560 B`) |

## 2. Measured Per-Stage Profile on the 5-Minute Excerpt (`300.014 s`)

| Stage / Sub-operation | Scope & Measurement Basis | Wall Time (s) | RTF (`wall / 300.014 s`) | Output / Result |
|---|---|---|---|---|
| End-to-end cold CLI run (`--omni-asr --omni-asr-checkpoint ... --json`) | Full subprocess stopwatch on clean `%TEMP%\he-b1-probe` | `326.054` | `1.087` | `exit=1`, `complete=false`, Stage 0 complete, Stage 1 refused at WSL `.ready` receipt |
| End-to-end warm CLI rerun (same `%TEMP%\he-b1-probe`, Stage 0 cached) | Full subprocess stopwatch (`audio.wav`, `proxy.mp4`, `ingest.json` reused) | `2.614` | `0.0087` | `exit=1`, identical Stage 1 WSL `.ready` refusal (`--omni-asr-checkpoint` and default `--omni-asr` LoRA route both reach same gate) |
| Stage 0 source SHA-256 (`_source_digest`) | Isolated measurement on `zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` | `0.304` | `0.0010` | `264,329,839 B` (~`0.87 GB/s`) |
| Stage 0 `extract_audio` (`ffmpeg -threads 1 -af loudnorm=I=-23:TP=-2:LRA=7`) | Isolated `extract_audio()` (`~12 s` inside pipeline by lock/provenance mtime `20:59:19`->`20:59:31`) | `14.838` | `0.0495` | `9,600,526 B` WAV (`16 kHz` mono PCM16, SHA-256 `0f069cb30e60012fa5c8192855737490ea0d4cf7674fcc72c56fa2f5789a64a5`) |
| Stage 0 `extract_proxy` (`ffmpeg -threads 1 -vf fps=1,scale=-2:720 libx264 -crf 28`) | Observed in-pipeline artifact timestamps (`20:59:31` -> `21:02:08`) | `~157` | `~0.523` | `7,962,705 B` MP4 (`c0a54c8294a93f3737cf7fd4ef655f74a886203e59ca3ec9aa46cc7a78985c23`) |
| Stage 0 `detect_speech` (`ingest.detect_speech`, Silero VAD) | Isolated `detect_speech(stage0/audio.wav)` | `4.917` | `0.0164` | `61` speech segments, `273,534 ms` total speech (`91.17%` of excerpt) |
| Stage 0 `detect_shots` (PySceneDetect OpenCV on 4K VP9 source) + final source digest | Remainder of `~153 s` (`21:02:09` -> `21:04:42`) minus `4.917 s` VAD and `0.304 s` hash | `~148` | `~0.493` | `33` shot cuts (`shot_cuts_ms`) |
| Stage 1 `_contextual_speech_regions` (`max_gap=1000 ms`, `max_span=18000 ms`) | Run on the 61 Stage 0 speech segments | `< 0.01` | `~0.000` | `21` context regions (`290,366 ms` span; mean `13.83 s/region`) |
| Stage 1 `_cut_speech_regions` (sequential `ffmpeg` per region into temp dir) | Isolated `_cut_speech_regions(stage0/audio.wav, grouped_regions, ...)` | `1.526` | `0.0051` | `21` PCM WAVs (`speech-0000.wav`..`speech-0020.wav`, `9,293,350 B` total, `72.7 ms/call`) |
| Stage 1 WSL admission (`load_wsl_runtime_receipt`) | Isolated `load_wsl_runtime_receipt()` | `0.056` | `0.0002` | `WslRuntimeError` (missing `.ready` receipt) |
| Stage 1 model load (v12 + CTC-3B) | Blocked before WSL worker launch (see §4) | `not run` | `—` | Refused at WSL receipt + missing CTC-3B / rzgar / GPU 1 VRAM headroom |
| Stage 1 fused v12 draft pass | Blocked before WSL worker launch (see §4) | `not run` | `—` | Refused at WSL receipt |
| Stage 1 Qwen validator passes | Blocked before WSL worker launch (see §4) | `not run` | `—` | `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` weights + `qwen_asr==0.0.6` absent |
| Stage 1 CTC-3B Viterbi forced alignment | Blocked before WSL worker launch (see §4) | `not run` | `—` | `omniASR-CTC-3B-v2.pt` absent from WSL fairseq2 asset cache |

Note on full 40-min episode (`RO1PmSoqmCM`, `2,391.694 s`, `7.972x` excerpt length): Stage 0 alone scales linearly with 4K VP9 software decode (`extract_proxy` at `RTF ~0.523` + `detect_shots` at `RTF ~0.493` -> `~43 minutes` just for Stage 0 before Stage 1 begins), and Stage 1 itself cannot pass the readiness gate without provisioning (see §4). Per Lane 2 instructions, the full episode was therefore NOT queued.

## 3. Exact Refusal Log & Readiness Output

Pipeline JSON (`transcript` stage result on `--omni-asr --omni-asr-checkpoint ...kurdish_omniasr_7b_v12_c750.pt --json`, exit code `1`):

```json
"transcript": {
  "skipped": true,
  "stage": "transcript",
  "reason": "canonical ASR runtime failed with RuntimeError: canonical OmniASR WSL2 runtime receipt is invalid: OmniASR WSL readiness receipt is missing or not a regular file: C:\\Users\\Wareen\\AppData\\Local\\HawEdit\\wsl-asr\\sources\\a7b54139328bd7a9\\.ready. Run hawedit-asr-setup",
  "blocked_by": [
    "canonical ASR runtime"
  ]
}
```

`.venv\Scripts\python.exe -m hawedit.models` readiness summary (`5/15 available`):

```text
MISS pyannote/speaker-diarization-community-1     weights  not downloaded (pyannote/speaker-diarization-community-1)
MISS omniASR_LLM_7B_v2                            pip      canonical OmniASR runtime verification failed: OmniASR WSL readiness receipt is missing or not a regular file: C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr\sources\a7b54139328bd7a9\.ready
MISS omniASR_CTC_3B_v2                            pip      canonical OmniASR runtime verification failed: OmniASR WSL readiness receipt is missing or not a regular file: C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr\sources\a7b54139328bd7a9\.ready
MISS rzgar/qwen3-asr-sorani-kurdish-ckb-v1        weights  not downloaded (rzgar/qwen3-asr-sorani-kurdish-ckb-v1)
```

## 4. Exact Missing Artifacts & GPU 1 Occupation Preventing Live Neural Stage 1 Today

Even without bypassing `load_wsl_runtime_receipt()`, inspection of `HawaPC01` shows five concrete blockers between today's state and a live GPU-1 Stage 1 neural profile:

1. **WSL receipt & snapshot unprovisioned:** `C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr` does not exist for package digest `a7b54139328bd7a9...`.
2. **Canonical CTC-3B asset absent:** `OMNI_ASSETS` requires `omniASR-CTC-3B-v2.pt` (`12,325,920,624 B`, SHA-256 `fa7f662c326842bb80561db97631ae3c48d911aec579654a1e8414c26caf9089`). `/home/ai/.cache/fairseq2/assets/` currently contains only `fca49af82b51089226da7de9/omniASR-CTC-1B-v2.pt` (`3.7 GiB`, plus `tmpy6d4q2mt`), and `omniASR-LLM-7B-v2.pt` sits in `/mnt/f/Kurdish Sorani Dataset/omniasr_champion_package/` rather than fairseq2's `OMNI_ASSETS` cache. (Default LoRA adapter `\\wsl.localhost\Ubuntu\home\ai\cortex_champion_model`, fingerprint `dfa6237a...`, and fused v12 `kurdish_omniasr_7b_v12_c750.pt`, `15,610,646,560 B`, DO exist on disk.)
3. **Validator weights & loader package absent:** `models/rzgar__qwen3-asr-sorani-kurdish-ckb-v1` is not present (`F:\huggingface\hub\models--rzgar--qwen3-asr-sorani-kurdish-ckb-v1` has zero blobs), and `/home/ai/.venv-wsl-whisper` lacks `qwen-asr==0.0.6`. Both `WslOmniAsrProducer.transcribe` (`src/hawedit/asr.py:1907`) and `asr_resume.worker_journal` (`src/hawedit/asr_resume.py:331,351`) require `rzgar` and `qwen-asr` unconditionally, even when validation is not wanted.
4. **GPU 1 actively held below `20.0 GiB` headroom floor:** `nvidia-smi` reports GPU 1 (`NVIDIA GeForce RTX 3090 Ti`, `24,564 MiB`) at **`16,452 MiB used / 7,858 MiB free`** because `asr-replica-a.service` (`:8000`, peak `15.4G`) and `ctc-aligner-gpu1.service` (`:8003`) are running. `asr_worker.assert_gpu_headroom` (`DEFAULT_MIN_FREE_GPU_GIB = 20.0`) refuses below `20.0 GiB` free unless `:8000` is paused with `scripts/run-with-omniasr-paused.sh` (note `stop_server.sh` stops `asr-replica-a`, not `ctc-aligner-gpu1`).
5. **Expired VEX policy date:** `security/wsl-asr-vex.json` has `reviewed: 2026-10-15`, `expires: 2026-11-14` (`4 days` expired as of `2026-11-18`), and any `src/hawedit/**` edit moves `package_digest` away from `a7b54139328bd7a9...`.

## 5. Prior Historical HawaPC01 Stage 1 Measurements (Context Only, Different Source/Tree/Stack)

The following measurements are pre-existing records on `HawaPC01` from earlier commits/media and are NOT substituted for fresh B1 runs on `RO1PmSoqmCM`:

- **`evidence/full-sorani-stage1-acceptance-2026-08-10.md`** (`commit` tree `738d6eda...`, source `ZAR38MinTest.mp4`, `2,313.8 s` `640x360` H264/AAC, dual RTX 3090 Ti LoRA route + rzgar validator): Stage 1 WSL worker boundary **`2,524.3 s`** (`RTF = 1.091`) across `547` regions (`545` aligned, `5,897` words, `2` unaligned `664 ms`, `2` rejected validator corrections); Stage 0+1+2 CLI total **`2,742.2 s`**.
- **`C:\Users\Wareen\HawEdit-ZAR-ASR-final-verdict-20261008.md`** (`commit c1635118...`, `ZAR38MinTest.mp4`, concurrent test gate): controller elapsed **`13,288.42 s`** (`3h 41m 28s`) across **`158` draft ops**, **`76` validator ops**, and **`76` correction-alignment ops** (`5,769` words).
- **`C:\Users\Wareen\Desktop\omniasr-v11-audit\results\hawedit_t0_measure.json`** (GPU 1 `:8000` stopped, `torch 2.8.0+cu128`, `fairseq2 0.6`, `omnilingual-asr 0.2.0`, fused v12 + CTC-3B): **`221.1 s` model load**, greedy LLM + CTC forward `4.8 s` (`9.1 s` clip, RTF `0.527`), `7.9 s` (`19.2 s` clip, RTF `0.411`), `13.0 s` (`33.9 s` clip, RTF `0.383`, **`21.90 GiB` allocated / `23.41 GiB` reserved** peak), `5.4 s` (`10.0 s` clip, RTF `0.540`).
- **`C:\Users\Wareen\Desktop\omniasr-v11-audit\results\hawedit_t0_measure_nbest5.json`** (same setup, `nbest=5` without CTC CPU parking): `126.9 s` on `19.2 s` clip (`24.38 GiB` reserved) and `586.2 s` on `33.9 s` clip (`31.04 GiB` reserved WDDM spill), illustrating why beam-5 retries require CTC CPU offloading (D-332) and why greedy/no-validator runtime differs sharply from beam/validator passes.

## 6. Round 2 Live GPU-1 WSL Stage 1 Measurements (2026-11-19, Commit `f46f6273`, Validator Off per D-341)

Following owner approval of `B6` (`D-341`) and provisioning of `omniASR-CTC-3B-v2.pt` (`12,325,920,624 B`, SHA-256 `fa7f662c326842bb80561db97631ae3c48d911aec579654a1e8414c26caf9089`) and `omniASR_tokenizer_written_v2.model` (`91,481 B`, SHA-256 `8aa11a1092142ef472537476ef6e76541123e2f0d789b79f3ebd119008240b1e`) into `/home/ai/.cache/fairseq2/assets/`:

### 6.1 Completion-Contract Refusal Observed on `/home/ai/.venv-wsl-whisper` (Unbypassed)
Running unmodified `hawedit.asr.OmniAsrProducer` inside `/home/ai/.venv-wsl-whisper/bin/python` halted fail-stop at `hawedit.asr_completion.transcribe_completed` (`src/hawedit/asr_completion.py:89`):

```text
hawedit.asr.AsrProductionFailure: production ASR halted during draft/alignment at 0..14686 ms: DecodeIncomplete: Installed decoder differs from the validated completion contract
```

Inspection showed `/home/ai/.venv-wsl-whisper` lacked `klpt` and contained a Sep-20 KenLM rescoring patch in `omnilingual_asr/models/wav2vec2_llama/beamsearch.py` (`sha256 ffa0da2caa75bf173271e5e6f4ff398ea7314e9ac493702928e4cea0a21d46da`), while `beamsearch.py.bak` retained the stock SHA-256 `91233570765a2fbd3199f3b65508e53b1be0199cf9e33bcddf9c9b9c2f575481`. Per coordinator ruling (`#28`), `/home/ai/.venv-wsl-whisper` was left untouched and an isolated plain-WSL venv `/home/ai/.cache/hawedit-plain-wsl-venv` was created via `uv` with hash-verified PyPI `omnilingual-asr==0.2.0`, `klpt==0.1.7`, `chunspell==2.0.4`, and `tbb==2023.1.0` chaining `.venv-wsl-whisper`'s `torch 2.8.0+cu128` / `fairseq2 0.6` via `.pth` (`beamsearch.py` and `model.py` SHA-256s verified against `asr_completion.py`). GPU 1 (`asr-replica-a`, `ctc-aligner-gpu1`) was paused under `MAINTENANCE` lock during measurements and restored (`active`) afterward; GPU 0 (`asr-replica-b`) stayed untouched (`active`).

### 6.2 Measured Stage Breakdown — 5-Minute Excerpt (`300.014 s`)

| Stage / Sub-operation | Measured Value | Notes / Basis |
|---|---|---|
| Stage 0 `extract_audio` (`16 kHz` mono PCM16 loudnorm) | `11.422 s` (`RTF 0.0381`) | `audio.wav` SHA-256 `0f069cb30e60012fa5c8192855737490ea0d4cf7674fcc72c56fa2f5789a64a5` |
| Stage 0 `detect_speech` (Silero VAD `5.1.2`) | `5.953 s` (`RTF 0.0198`) | `61` raw segments (`273,534 ms`) -> `21` context regions (`290,366 ms`) |
| Stage 1 cold model load (`_load`, SHA-256 + 7B + CTC-3B to GPU 1) | `256.041 s` (`RTF 0.8534`) | Reads/hashes `15.6 GB` `v12_c750.pt` + `12.3 GB` `CTC-3B` |
| Stage 1 `_cut_speech_regions` (`ffmpeg` 21 WAV slices) | `2.491 s` (`RTF 0.0083`) | WSL `ffmpeg 8.0.1-3ubuntu2` |
| Stage 1 fused `v12` greedy branch (`21` segments, overlapped) | `176.690 s` (branch sum) | Segment 14 (`23.08 s`) and 15 (`49.91 s`) accounted for `~73 s`; median `5.71 s` |
| Stage 1 fused `v12` `beam5_retry` (`1` segment: seg 1) | `11.048 s` (branch sum) | Includes parking CTC-3B to CPU & restoring (`D-332`) |
| Stage 1 `CTC-3B` emissions branch (`21` segments, overlapped) | `17.713 s` (branch sum) | Concurrent with greedy in `ThreadPoolExecutor(max_workers=2)` |
| Stage 1 CTC Viterbi word alignment (`21` segments) | `1.166 s` (`0.056 s/seg`) | Pure CPU Viterbi projection (`0.6%` of inference wall) |
| Stage 1 inference wall excluding model load | `194.378 s` (**`RTF 0.6479`**) | `749` aligned words, `0` unaligned, `9` sentences (`7` complete) |
| Stage 1 total wall including cold model load | `450.419 s` (`RTF 1.5013`) | Peak GPU 1 VRAM: `21,831.3 MiB` alloc / `23,364.0 MiB` reserved |

Saved verified excerpt raw transcript JSON: `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.transcript.raw.json` (verified `media_sha256` match, `klpt` normalizable, `mean_logprob = -6.4625`, `adapter = fused:f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2`).

### 6.3 Measured Stage 0 & Partial Stage 1 Refusal — Full 40-Minute AI Episode (`RO1PmSoqmCM`, `2,391.694 s`)

- **Stage 0 (`extract_audio` + Silero VAD):** `100.563 s` audio extraction (`audio.wav` SHA-256 `81cdd22d82b88f7dd282cdd17239a47a55092b9834bcb9fb342ddaa79118459c`) + `24.984 s` Silero VAD -> `540` raw speech regions (`2,113,616 ms`) -> **`175` context-grouped regions (`2,247,876 ms`)**.
- **Stage 1 GPU-1 Execution:** Completed regions `0..76` (`77 / 175` regions = `~17.5 min` audio, `2,608` words, `3` successful `beam5_retry` rescues at segs 27, 52, 67; segs 2..77 wall time min `0.29 s`, **median `5.08 s/region`**, **mean `5.35 s/region`**, max `17.53 s`). Halted fail-stop per `D-332` at region `78/175` (`speech-0077.wav`, `1,048,834..1,062,334 ms`, `13.500 s`, RMS `0.0589`, peak `0.3238`):

```text
hawedit.asr.AsrProductionFailure: production ASR halted during draft/alignment at 1048834..1062334 ms: DecodeIncomplete: segment speech-0077.wav: greedy attempt: a 1-4 word unit repeats at least 4 times in a row; beam-5 retry: a 1-4 word unit repeats at least 4 times in a row
```

Per strict fail-stop rules, no partial or bypassed whole-episode raw transcript was written to `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM.transcript.raw.json`. See `evidence/b2-clip-scoped-asr-2026-11-19.md` for B2 clip-scoped measurements.

### 6.4 D-342 Constituent Split Probe & Updated `RO1PmSoqmCM` Run

Follow-up verification of `D-342` (commit `613c05bd337f972adc3dc80e7a9d3abd081fdbe6`) on `HawaPC01` GPU 1 (`CUDA_VISIBLE_DEVICES=1`, isolated `/home/ai/.cache/hawedit-plain-wsl-venv`, `asr-replica-a` paused under `MAINTENANCE` lock and restored `active` afterward; GPU 0 `asr-replica-b` untouched `active`):

1. **Standalone GPU 1 probe of grouped region `77` (`speech-0077.wav`, `1,048,834..1,062,334 ms`) raw Silero VAD constituents** (`223.229 s` cold model load):
   - `speech[223]` (`1,048,834..1,052,510 ms`, `3,676 ms`, RMS `0.0589`, peak `0.3238`): decoded `greedy` in `2.314 s`, `7` words, `mean_logprob = -9.4666`.
   - `speech[224]` (`1,052,642..1,055,006 ms`, `2,364 ms`, RMS `0.0717`, peak `0.2818`): decoded `greedy` in `1.064 s`, `7` words, `mean_logprob = -6.807`.
   - `speech[225]` (`1,055,138..1,062,334 ms`, `7,196 ms`, RMS `0.0552`, peak `0.2911`): decoded `greedy` in `3.39 s`, `21` words, `mean_logprob = -5.2487`.
   - `3/3` constituents decoded cleanly with `0` beam-5 retries (`6.768 s` sum vs repetition loop on the grouped span).

2. **Full 40-min `RO1PmSoqmCM` Stage 1 rerun with `D-342` enabled** (`OmniAsrProducer(..., context_grouping=True, validate_hard_segments=False)` on `540` Silero VAD segments / `175` grouped regions):
   - Regions `0..76` completed (`seg 1` `230.98 s` incl. cold load, `beam5_retry` rescues at segs `27`, `52`, `67`).
   - At grouped region `77` (`speech-0077.wav`, `1,048,834..1,062,334 ms`), `D-342` triggered automatically (`[D-342 split #1]`), sliced `speech-0077-sub-00.wav` (`117,676` B), `speech-0077-sub-01.wav` (`75,692` B), and `speech-0077-sub-02.wav` (`230,316` B), decoded all `3` cleanly on `greedy` (`1.25 s` / `7` words, `0.91 s` / `7` words, `3.22 s` / `21` words; `cum_infer = 802.8 s`), and continued through grouped region `89` (`cum_infer = 859.6 s`).
   - At grouped region `90` (`speech-0090.wav`, `1,229,858..1,243,998 ms`, `14,140 ms`, `452,558` B WAV), `stage0_meta` shows a single unbroken raw Silero VAD segment (`[1229858, 1243998]`, `< 2` constituents). `OmniAsrBackend` failed both `greedy` (no natural EOS) and `beam-5` (repetition loop), and `D-342` strictly failed-stop with `AsrProductionFailure` without emitting `-sub-*.wav` or writing a partial `RO1PmSoqmCM.transcript.raw.json` to `D:\HawEdit-media\excerpts\`.
   - Operational conclusion: `D-342` resolves false decode loops caused by `_contextual_speech_regions` merging across brief pauses, while unbroken long single-turn Silero VAD segments (`14.14 s` on `RO1PmSoqmCM`) still exceed OmniASR-7B single-turn EOS stability without separate Stage 0 VAD chunking (`detect_speech` left unchanged). Final strict ASR for Phase 3 on 40+ min episodes therefore relies on `D-340` (`--clip-scoped-asr`) against chosen clip windows once a draft transcript exists.

### 6.5 D-343 Singleton RMS-Dip Probe, Full 40-min `RO1PmSoqmCM` Completion (`175/175`), & Cache Catch

1. **Diagnostic GPU 1 tail scan (`91..174`, `stop_on_failure=False`) + `speech-0090.wav` RMS-dip probe** (`CUDA_VISIBLE_DEVICES=1`, `211.481 s` load, zero `.transcript.raw.json` written):
   - Remaining `84` grouped regions (`91..174`, `448.786 s` scan) aligned **`84/84` (`0` unaligned**, `92` decoded items, `2,850` words), firing `2` automatic `D-342` splits (`speech-0149.wav` `5/5`, `speech-0169.wav` `5/5`) and `2` `beam5_retry` rescues (`speech-0106.wav` `16.094 s`/`44` words, `speech-0170.wav` `13.335 s`/`31` words).
   - Singleton `speech-0090.wav` (`1,229,858..1,243,998 ms` = `14,140 ms`, `overall_rms = 0.055895`) scanned inside `[3_000, 11_140] ms` (`10 ms` hop) found sliding min RMS of `0.001138` (`150 ms`, center `9,365 ms`), `0.001335` (`200 ms`, `9,240..9,440 ms`, center `9,340 ms`, media `1,239,198 ms`), and `0.002344` (`250 ms`, center `9,315 ms`). Decoding the `200 ms` split halves succeeded `2/2` on `greedy` with natural EOS: `half0` (`9,340 ms`, `6.218 s`, `32` words, `mean_logprob = -4.4269`) and `half1` (`4,800 ms`, `2.341 s`, `16` words, `mean_logprob = -4.9452`).

2. **Fused checkpoint integrity catch (`_held_fused_checkpoint`):**
   - Initial launch (`task-1438`) legitimately refused to load `kurdish_omniasr_7b_v12_c750.pt` after cached Windows/WSL page-cache reads hashed `e9ffd45ac7d052fd6b1c4ce1a5a86ed4ba6337aaee6c75411d3716b96ec28f4a` despite untouched `2026-10-02 01:33:56` mtime (`15,610,646,560` B). Direct unbuffered Windows `FILE_FLAG_NO_BUFFERING` reading (`task-1455`) confirmed on-disk bytes on `F:` match `f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2` and purged the poisoned standby cache page (`Get-FileHash` + WSL `sha256sum` returned `f7b3a5e2...`, `task-1459`).

3. **Complete 40-min `RO1PmSoqmCM` Stage 1 completion (`2,391.693 s`, commit `56501a7f`, `D-342` + `D-343`):**
   - Cold model load: `202.405 s` (`RTF 0.0846`); `_cut_speech_regions` (`175` WAV slices): `18.555 s`.
   - `v12` greedy branch sum (`186` items, overlapped): `896.471 s`; `v12` `beam5_retry` sum (`5` retries): `50.927 s`; `CTC-3B` emissions sum (overlapped): `61.789 s`; CPU CTC Viterbi alignment: `8.537 s`.
   - Automatic recovery events: `3` `D-342` constituent splits (`speech-0077` `3/3`, `speech-0149` `5/5`, `speech-0169` `5/5`) + `1` `D-343` singleton dip split (`speech-0090` -> `1,229,858..1,239,198` and `1,239,198..1,243,998 ms`).
   - **Total inference excl. model load:** `1,024.241 s` (**`RTF 0.4282`**); **total incl. load:** `1,226.646 s` (`20m 26.6s`, **`RTF 0.5129`**); peak GPU 1 VRAM: `21,894.0 MiB` alloc / `23,402.0 MiB` reserved.
   - **Output:** **`175 / 175` grouped regions (`186` decoded items), `5,951` aligned words, `0` unaligned (`mean_logprob = -6.3986`)**, `5,951` KLPT-normalized words. Saved verified canonical raw transcript JSON to `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM.transcript.raw.json` (`2,152,666` B, SHA-256 `9286cab3d58eeb5bae8f72621c26bf9c4e64678f19e317ea2e39eda9110c1d9e`, `media_sha256` `17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72`).
   - **B2 clip-scoped check on 3 representative `45 s` clip spans** (`310..355 s`, `950..995 s`, `1,720..1,765 s`): selected `14` grouped regions (`197,032 ms` = `8.77%` of episode speech audio) in `84.867 s` inference (`12.07x` speedup vs `1,024.241 s` full inference, excl. `102.75 s` draft-model reload after `release_draft_model()`). All `14/14` region spans matched identically; `12/14` matched token-for-token and logprob identically, while `2/14` shifted 1 token each across separate draft-model loads (`957026..974526` `یەعنی` vs `یانی`, `1762658..1777566` `+ئەی`; `527` vs `528` words).
