# Plan: Validator Off Default & WER Ablation (`specs/b6-validator-ablation`)

Research: `research.md`. Spec: `spec.md`. Callers & tests: `impact-map.md`.

**Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"**

## 1. Decision to Record as D-341

Take the Qwen validator (`rzgar/qwen3-asr-sorani-kurdish-ckb-v1`) **off the default `hawedit.pipeline` / `create_omni_asr_producer` Stage 1 path** (`--validate-asr` opt-in; default `validate_hard_segments=False`) until paired WER on real conversation clips (`validator ON vs OFF`) justifies re-enabling or permanently retiring it (`gemini-task-sheet-2026-11-18.md` §B6).

Why:
1. Current canonical Stage 1 (`asr.py:1322,1907`, `asr_worker.py:167`, `asr_resume.py:331,351`) blocks every Windows/WSL run unless `rzgar` (~10 GB) and `qwen-asr==0.0.6` are installed and loaded, adding ~48% extra Qwen passes + CTC realignments on long episodes (`HawEdit-ZAR-ASR-final-verdict-20261008.md`: 76 validator ops + 76 realignments alongside 158 draft ops).
2. `v12` fused weights (`kurdish_omniasr_7b_v12_c750.pt`) already exist on `HawaPC01`, whereas `rzgar` weights and `qwen-asr` are not provisioned, and Cortex canon forbids Qwen-ASR for `ckb`.
3. Taking validator off the default path does **not** weaken `--validate-asr`: when enabled, every `rzgar` verification, D-324 natural-EOS completion check, and `SegmentOrigin` validation invariant remains unchanged and byte-identical. When disabled (`validate_hard_segments=False`), `SegmentOrigin` truthfully records `outcome="validator-disabled"` (`escalated=False`), `admission_policy` includes `+validator-off` to isolate caches (`D-136`), and no validator checkpoint or `qwen-asr` metadata is queried.

## 2. Considered and Not Chosen

- **Delete `QwenSoraniValidator` and `_validate_hard_segments` right now:** Rejected because Phase B6 explicitly requires measuring paired WER with and without the validator on the same clips before deciding whether to permanently retire or keep it.
- **Fake `"not-routed"` or relax `RawTranscript._validate_origins()`:** Rejected because muting `_validate_origins()` would make `"not-routed"` ambiguous between *"active validator passed this segment"* and *"validator never loaded"*, violating HawEdit provenance honesty. Uniform `"validator-disabled"` is explicit and forbids mixed batches.
- **Keep validator ON by default and only add `--no-validate-asr`:** Contradicts B6 verbatim (*"Validator off the default path until it is measured"*), and leaves default single-command runs (`A2`) blocked when `rzgar` / `qwen-asr` are absent.

## 3. Implementation Tasks (Test-First, One Task at a Time)

1. **T1 — Honest `"validator-disabled"` `SegmentOrigin` & `RawTranscript._validate_origins()` (`src/hawedit/transcripts.py`, `src/hawedit/pipeline.py`):**
   - Allow uniform `outcome="validator-disabled"` batches in `SegmentOrigin` and `RawTranscript._validate_origins()` (`escalated=False`, `validator=None`, `route_reason` still preserving deterministic `select_for_validation` counterfactual signal). Refuse any mixed batch.
   - Update `PipelineRun.to_dict()` (`pipeline.py:554–606`) to report `routing_status="validator-disabled"` and `escalated=0` rather than claiming escalated segments reached Qwen.
   - Write AC4 tests first (`tests/test_validator_ablation.py`).
2. **T2 — `validate_hard_segments: bool` across producers, worker request, and journal (`src/hawedit/asr.py`, `src/hawedit/asr_worker.py`, `src/hawedit/asr_resume.py`, `src/hawedit/pipeline.py`):**
   - Add `validate_hard_segments: bool = True` on `OmniAsrProducer` / `WslOmniAsrProducer` (default `False` in CLI / `create_omni_asr_producer` once D-341 approved; existing direct unit callers passing explicit backends/validators keep backward-compatible defaults or explicit args checked against impact map).
   - When `validate_hard_segments=False`: append `+validator-off` to `admission_policy`; skip `ModelStore` validator resolution and `verified_checkpoint_access`; send `"validate_hard_segments": False` (omit `"validator_model_dir"`) in `omni-asr-request.json`; make `validator_path: Path | None` in `asr_resume.worker_journal` so `"qwen-asr"` distribution version and `ModelStore().verify_checkpoint(VALIDATOR_MODEL_ID, ...)` run ONLY when `validate_hard_segments=True`; skip `_validate_hard_segments` and emit uniform `"validator-disabled"` `SegmentOrigin`s.
   - Add `--validate-asr` / `--no-validate-asr` flags in `pipeline.build_parser` & `_build_and_run` (default OFF).
   - Write AC1, AC2, AC3, AC5 tests first (`tests/test_validator_ablation.py`, `tests/test_pipeline.py`).
3. **T3 — Paired WER ablation helper + ADR `D-341` + `PROGRESS.md`:**
   - Add a small pure ablation comparison script/helper (`metrics.normalized_cer` + word error rate on reference clips) and append `D-341` recording validator off default pending real WER measurement.
4. **T4 — Live paired WER measurement (`validate OFF vs ON`) & final keep-or-retire ADR addendum (gated by prerequisites):**
   - Requires `wsl-asr` + `CTC-3B`, `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` (`d71490a6...`) + `qwen-asr==0.0.6` for the ON arm, and `>= 20` hand-corrected Sorani clip references (`#1` / `B5`).
   - Run paired passes on identical clips, record WER / CER / RTF / realignment failure counts into `evidence/b6-validator-ablation-YYYY-MM-DD.md`, and amend `D-341` to permanently keep or remove Qwen validation.

## 4. Explicit Owner Decisions / Prerequisites Required Before Implementation

1. **Default inversion & existing test impact:** Confirm `validate_hard_segments=False` as the new default for `create_omni_asr_producer` / `hawedit.pipeline --omni-asr` (`--validate-asr` opts back in), noting which existing `tests/test_asr*.py` / `tests/test_pipeline.py` tests construct `create_omni_asr_producer` expecting validation ON and must pass `validate_hard_segments=True` or update to `--validate-asr`.
2. **VEX digest pin update (`tests/test_vex.py` / `security/wsl-asr-vex.json`):** Editing `asr.py`, `asr_worker.py`, `asr_resume.py`, `transcripts.py`, `pipeline.py` moves `package_digest(src/hawedit)`, requiring owner-approved VEX re-pinning (or Lane 1's A3 parking). Note also: omitting `qwen-asr` & `validator_model_dir` on `"validate_hard_segments": false` shrinks the attack surface covered by D-333's `accelerate`/`transformers` Qwen dispositions.
3. **Final T4 ablation prerequisites:** Owner confirmation to stage `rzgar` + `qwen-asr==0.0.6` for the ON control arm and `[HAWA]` hand-corrected reference text (`B5` / `#1`) for `>= 20` clips.
