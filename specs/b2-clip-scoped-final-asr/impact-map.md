# Impact Map: Clip-Scoped Final ASR (`specs/b2-clip-scoped-final-asr`)

Base commit: `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf` (`gemini/lane-2`).
Mapping method: Serena MCP is unavailable in this environment; every symbol, caller, and line number below was mapped using `rg -n` and direct file inspection.

## 1. Source Symbols & Callers (`src/hawedit/`)

| Symbol & Location | Proposed Change | Existing Callers (`src/`, `tests/`, `scripts/`) | Test Impact |
|---|---|---|---|
| `src/hawedit/asr.py`: `_contextual_speech_regions` (`1357–1383`), new `select_contextual_regions_for_spans` | Keep `_contextual_speech_regions` intact; add pure span-selection helper using it and returning deduplicated episode `SpeechSegment` intervals overlapping padded clip spans (`3000–5000 ms`) | Currently called by `OmniAsrProducer.transcribe` (`asr.py:1315`), `WslOmniAsrProducer.transcribe` (`asr.py:1887`), `tests/test_asr_context.py` | Existing `test_asr_context.py` unchanged; new `tests/test_clip_scoped_asr.py` tests AC1/AC4 |
| `src/hawedit/pipeline.py`: `PipelineRun` / `to_dict` (`370–640`), `_render_episode_single_clip` (`2081–2595`), `_run_episode_delivery` (`2598–2790`), `run_pipeline` (`2812–4718`) | Accept optional `clip_asr_producer` / `clip_scoped_asr: bool` + `clip_asr_pad_ms: int = 4000`; batch chosen spans in `_run_episode_delivery` (`2646–2691`) and single-clip Stage 5/6 (`3768–3966`) through one `canonical_asr.transcribe(...)` pass into isolated `work_dir/clip_asr/transcripts`; re-segment & re-bind words for ASS/SRT; report `clip_scoped_asr_*` metrics in `to_dict()` | `pipeline.main`, `durable_workflow.py` (`run_pipeline`), `episode.py` (via `pipeline`), `tests/test_pipeline.py`, `tests/test_episode.py` | Existing `test_pipeline.py` & `test_episode.py` keep identical behavior when flag omitted; new tests verify batching, fail-stop, and parity |
| `src/hawedit/pipeline.py`: `build_parser` (`4895–5263`), `_build_and_run` (`5332–5545`) | Add `--clip-scoped-asr` and `--clip-asr-pad-ms`; allow `--transcript` + `--omni-asr` ONLY when `--clip-scoped-asr` is set (currently mutually exclusive at `5375`); construct `canonical_asr` even when `--transcript` is also supplied for draft | `pipeline.main`, `studio_generation.py` (uses parser), `tests/test_pipeline.py` CLI refusal tables (`_REFUSAL_CASES`, `_CLI_PREFLIGHT_CASES`) | Bidirectional CLI source scans in `test_pipeline.py` must pass; update refusal test for invalid `--clip-scoped-asr` combos |
| `src/hawedit/transcripts.py`: `TranscriptStore` (`1121–1275`), `RawTranscript` (`712–870`) | **Unchanged** (reused as-is with isolated `work_dir / "clip_asr" / "transcripts"` and deterministic subset key in `audio_sha256` or `admission_policy`) | `pipeline.py:3108,3206`, `asr_worker.py`, `tests/test_transcripts.py`, `tests/test_asr_admission_cache.py` | Zero breaking changes to `TranscriptStore` invariants |
| `src/hawedit/asr_worker.py`: `_infer_request` (`148–283`), `asr_resume.py`: `worker_journal` (`290–355`) | **Unchanged** for B2 (worker receives only the subset of WAV segments matching overlapping `_ContextSpeechRegion`s, and caches per segment in `OperationJournal`) | `WslOmniAsrProducer.transcribe` (`asr.py:1977`), `tests/test_asr_resume.py`, `tests/test_asr_worker_diagnostics.py` | Unchanged |
| `src/hawedit/studio_host.py`: (`17, 114–270`), `security/wsl-asr-vex.json`, `tests/test_vex.py` (`27–30`) | Modifying `src/hawedit/*.py` changes `package_digest(src/hawedit)` (`a7b54139...`) -> `REVIEWED_VEX_SOURCE` & `security/wsl-asr-vex.json` pin check fails unless owner updates VEX pin / Phase A3 parks it | `tests/test_vex.py`, `wsl_setup.py`, `wsl_vex_gate.py` | Tracked in plan §4 for owner approval before editing `src/` |

## 2. Affected Documentation & Living Docs

- `BLUEPRINT.md`: §3 Stage 1 (lines 110–129), §4.2, §5, §8.1. (No edit needed; B2 refines *which* regions receive final ASR, preserving Stage 1 model/alignment canon).
- `DECISIONS.md`: `D-136` (6319), `D-144` (6935), `D-260` (13617), `D-278` (14544), `D-281` (14629), `D-331` (16354), `D-332` (16429), `D-333` (16485). Append new **`D-340`**.
- `BLOCKED.md`: `#1` (26, labelled accuracy corpus), `#21` (1009, adapter/fused weights licence), `#24` (1178, VEX digest re-pin).
- `PROGRESS.md`: Stage 1 (`M1.4`, line 773) and any Phase B tracking note; update only after gate pass via `scripts/update-ledger.sh`.
