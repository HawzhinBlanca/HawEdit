---
commit: f46f62731d0d7865c6248c9399fbe30f60204a73
media_sha256: 6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0
host: HawaPC01 Threadripper-3990X Windows-11-10.0.26300-SP0 / WSL2-Linux-6.18.58.1 2x-RTX-3090-Ti
command: CUDA_VISIBLE_DEVICES=1 /home/ai/.cache/hawedit-plain-wsl-venv/bin/python run_wsl_asr.py --stage0-root /mnt/c/Users/Wareen/AppData/Local/Temp/he2-asr-run --mode 5m
libraries: win-py3.12.10 torch2.13.0+cpu silero-vad5.1.2 ffmpeg8.1.1-full | wsl-py3.12.13 torch2.8.0+cu128 cuda12.8 fairseq2-0.6 omnilingual-asr0.2.0 klpt0.1.7
status: measured-gpu1-parity-verified
---

# B2 Clip-Scoped Final ASR Parity & Speedup Evidence (2026-11-19)

Measurements recorded on `HawaPC01` against code commit `f46f62731d0d7865c6248c9399fbe30f60204a73` (`specs/b2-clip-scoped-final-asr`, ADR `D-340`), executing real `hawedit.asr.OmniAsrProducer` (`context_grouping=True`, `validate_hard_segments=False` per `D-341`) with fused checkpoint `kurdish_omniasr_7b_v12_c750.pt` (`15,610,646,560 B`, SHA-256 `f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2`) and `omniASR-CTC-3B-v2.pt` (`12,325,920,624 B`, SHA-256 `fa7f662c326842bb80561db97631ae3c48d911aec579654a1e8414c26caf9089`) on GPU 1 (`NVIDIA GeForce RTX 3090 Ti`, `CUDA_VISIBLE_DEVICES=1`). GPU 0 (`asr-replica-b.service`) remained untouched.

## 1. Provenance

- **Host / OS:** `HawaPC01`, Windows 11 (`Windows-11-10.0.26300-SP0`), WSL2 `Linux-6.18.58.1-microsoft-standard-WSL2-x86_64-with-glibc2.43`
- **WSL Runtime:** `/home/ai/.cache/hawedit-plain-wsl-venv/bin/python` (CPython `3.12.13`, PyPI hash-locked `omnilingual-asr==0.2.0`, `klpt==0.1.7`, `chunspell==2.0.4`, `tbb==2023.1.0` chaining `.venv-wsl-whisper` `torch==2.8.0+cu128`, CUDA `12.8`, `fairseq2==0.6`; genuine stock `beamsearch.py` SHA-256 `91233570...` and `model.py` SHA-256 `23961934...` verified)
- **Windows Stage 0:** CPython `3.12.10`, `torch 2.13.0+cpu`, `silero-vad 5.1.2`, `ffmpeg version 8.1.1-full_build-www.gyan.dev`
- **Input Media:** `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` (`300.014 s`, SHA-256 `6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`; extracted WAV SHA-256 `0f069cb30e60012fa5c8192855737490ea0d4cf7674fcc72c56fa2f5789a64a5`)

## 2. Whole-Excerpt vs. B2 Clip-Scoped Final ASR (`pad_ms=4000`)

Target clip spans selected for B2 batching: `[(25_000, 65_000), (185_000, 225_000)]` (two 40 s spans). `select_contextual_regions_for_spans(..., duration_ms=300_014, pad_ms=4_000)` snapped padded windows to exact episode `_contextual_speech_regions` bounds.

| Metric | Whole-Excerpt Stage 1 | B2 Clip-Scoped Stage 1 | Ratio / Delta |
|---|---|---|---|
| Context regions transcribed | `21` | `8` | `38.1%` of regions |
| Grouped speech audio (ms) | `290,366` | `121,984` | `42.01%` (`2.38x` less audio) |
| Model load wall time (s) | `256.041` (cold 7B + CTC-3B) | `117.366` (warm 7B reload after `release_draft_model`) | Separate load phase |
| Audio slice ffmpeg I/O (s) | `2.491` | `0.890` | `2.80x` faster |
| v12 greedy branch sum (s) | `176.690` | `49.934` | `3.54x` less greedy decode time |
| v12 beam-5 retries | `1` (`11.048 s`) | `0` (`0.000 s`) | Subset skipped seg 1 |
| CTC-3B emissions branch sum (s) | `17.713` | `3.687` | Concurrent w/ greedy |
| CTC Viterbi alignment sum (s) | `1.166` | `0.549` | `2.12x` less align time |
| Inference wall time excl. load (s) | `194.378` | `52.154` | **`3.73x` faster inference** |
| Inference RTF (`infer_wall / audio_300s`) | `0.6479` | `0.1738` (vs full 300 s excerpt) | `0.4275` vs `121.984 s` processed |
| Peak GPU 1 VRAM allocated / reserved (MiB) | `21,831.3` / `23,364.0` | `21,701.6` / `23,246.0` | — |

## 3. Exact Text, Word Timing, and Confidence Parity Verification

Comparing all `RawTranscript.words` falling inside the 8 chosen `subset_regions` between the whole-excerpt run and the B2 clip-scoped run:

- Expected words inside chosen regions (from whole-excerpt `RawTranscript`): **`335`**
- Words emitted by B2 clip-scoped `RawTranscript`: **`335`**
- Exact tuple equality `(w, start_ms, end_ms, round(conf, 6))`: **`exact_match = true`**, **`mismatch_count = 0`**, **`first_diff = null`**

Because `select_contextual_regions_for_spans` returns exact member intervals of `_contextual_speech_regions`, `ffmpeg` emits identical bounded PCM WAVs for each selected region and greedy v12 + CTC-3B Viterbi alignment produces identical words and millisecond timestamps.

## 4. Operational Observation on Long Episodes (`RO1PmSoqmCM`, 40 min)

On the full 40-min parent episode (`zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM.mp4`, SHA-256 `17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72`), whole-episode strict Stage 1 transcribed regions `0..76` (`2,608` words, median `5.08 s/region`, mean `5.35 s/region` for regions `2..77`, `3` beam-5 retries) and halted strictly per D-332 at region `78/175` (`1,048,834..1,062,334 ms`, `speech-0077.wav`, greedy+beam-5 repetition loop). Clip-scoped final ASR isolates Stage 1 strict execution to chosen clip regions (`D-340`) so unrelated segments elsewhere in long episodes cannot abort clips whose audio decodes cleanly.
