# Research: Validator Off Default & WER Ablation (`specs/b6-validator-ablation`)

- **Status:** Research only (Round 1 stop-for-approval gate). No production or test code edited.
- **Worktree / Commit:** `C:\Users\Wareen\.gemini\antigravity\scratch\HawEdit-lane-2` (`gemini/lane-2` @ `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`).
- **Date:** 2026-11-18.
- **Methodology:** Serena MCP is unavailable in this environment; all callers and symbol locations were mapped using `rg -n` and direct source inspection.
- **Spec / Task reference:** `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` §3 Phase B6; `BLUEPRINT.md` §3 Stage 1 (lines 118, 128), §7 (line 378), §8.1.

## 1. Problem Statement & Empirical Baseline

1. `BLUEPRINT.md` §3 Stage 1 (lines 118, 128) routes the bottom CTC log-probability quartile plus materially disagreeing segments (`normalized_cer >= 0.15`, `D-015`) to `rzgar/qwen3-asr-sorani-kurdish-ckb-v1`, then re-aligns any validator-modified text via CTC-3B (`backend.align_segment`).
2. `C:\Users\Wareen\HawEdit-ZAR-ASR-final-verdict-20261008.md` (`ZAR38MinTest.mp4`, commit `c1635118...`) observed **158 draft operations -> 76 validator operations -> 76 correction-alignment operations** (~48% of draft windows escalated across quartile + disagreement). `evidence/full-sorani-stage1-acceptance-2026-08-10.md` recorded 2 rejected corrections where Qwen output failed CTC alignment (`AlignmentInfeasible`) or returned empty text.
3. Since v12 fused checkpoint training (`D-331`: `kurdish_omniasr_7b_v12_c750.pt`, 23.29 WER / 5.50 CER on FLEURS `ckb`, `specs/v12-fused-model/research.md`), two facts make unconditional validator execution harmful today:
   - **Operational blocker verified in `evidence/asr-profile-2026-11-18.md`:** On `HawaPC01`, `models/rzgar__qwen3-asr-sorani-kurdish-ckb-v1` is not present (`hawedit.models` reports `MISS not downloaded`), `F:\huggingface\hub\models--rzgar--qwen3-asr-sorani-kurdish-ckb-v1` contains zero blobs, and `/home/ai/.venv-wsl-whisper` lacks `qwen-asr==0.0.6`.
   - **Quality question:** Cortex canon (`specs/v12-fused-model/research.md:105`) avoids Qwen-family ASR for `ckb`, and v12 likely performs better without a weaker validator second-guessing bottom-quartile segments and adding extra decode + CTC realignment passes.
   - **Phase B6 goal:** Take Qwen validator off the default path until measured, and measure WER on the same >=20 real clips with validator ON vs OFF to write the final keep-or-retire ADR.

## 2. Hard-Coupled Code Locations Found Across the Stack

Today there is **zero** way to run canonical OmniASR without both requiring `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` weights on disk AND installing `qwen-asr==0.0.6`:

1. **CLI & Factory (`src/hawedit/pipeline.py`, `src/hawedit/asr.py`):**
   - `pipeline.build_parser` (`4901–4938`) and `_build_and_run` (`5518–5543`) expose no `--validate-asr` / `--no-validate-asr` switch.
   - `create_omni_asr_producer` (`asr.py:2015–2049`) always constructs `OmniAsrProducer` / `WslOmniAsrProducer` with validation enabled.
2. **Host & Native Producers (`src/hawedit/asr.py`):**
   - `OmniAsrProducer.transcribe` (`1304–1337`) calls `_validate_hard_segments(initial, self.backend, self._validator, stop_on_failure=True)` unconditionally at line `1322`. Whenever `len(results) >= 4`, `select_for_validation` (`escalation.py:125`) escalates `>= 1` segment (`len // 4`), triggering `self._validator()` -> `ModelStore().assert_available(VALIDATOR_MODEL_ID)` + `QwenSoraniValidator`.
   - `WslOmniAsrProducer.transcribe` (`1875–2013`) resolves `VALIDATOR_MODEL_ID` (`1898–1903`), acquires `verified_checkpoint_access(VALIDATOR_MODEL_ID, validator_model_dir)` (`1907–1909` — refusing immediately if `rzgar` checkpoint files are missing!), and always writes `"validator_model_dir"` into `omni-asr-request.json` (`1915`).
   - Both producers expose `admission_policy` (`1284–1293`, `1822–1829`), which must differentiate validator-on vs validator-off so `TranscriptStore.reusable_raw` never cross-reuses validated vs unvalidated runs.
3. **WSL Worker & Resume Journal (`src/hawedit/asr_worker.py`, `src/hawedit/asr_resume.py`):**
   - `asr_worker._infer_request` (`167–170`) refuses if `"validator_model_dir"` is omitted or blank; lines `255–270` unconditionally wire `QwenSoraniValidator` and `_validate_hard_segments`.
   - **`asr_resume.worker_journal` (`290–355`):** Even if `_validate_hard_segments` were skipped, `worker_journal` unconditionally takes `validator_path: Path`, puts `"validator_completion_policy": QWEN_COMPLETION_POLICY_ID` in `binding` (`311`), calls **`importlib.metadata.version("qwen-asr")` (`331`)** (which crashes in `/home/ai/.venv-wsl-whisper` where `qwen-asr` is absent!), and calls `ModelStore().verify_checkpoint(VALIDATOR_MODEL_ID, validator_path)` (`351`)!
4. **Canonical Transcript Provenance & Origin Audit (`src/hawedit/transcripts.py`, `src/hawedit/pipeline.py`):**
   - `SegmentOrigin.__post_init__` (`transcripts.py:555–617`) allows `outcome == "not-routed"` ONLY if `not self.escalated`, and routed outcomes (`"validator-selected"`, `"validator-transcription-refused"`, `"validator-alignment-refused"`) ONLY if `self.escalated` and `self.validator` resolves to `asr_validator`.
   - `RawTranscript._validate_origins` (`transcripts.py:815–869`) requires every origin's `escalated == decision.escalate and route_reason == decision.reason` for `select_for_validation(scores)`. Therefore, disabling the validator breaks `_validate_origins()` unless `SegmentOrigin` defines an honest explicit state (e.g., `outcome = "validator-disabled"`), strictly verified uniformly across all segments in a disabled run and forbidden in mixed batches.
   - `PipelineRun.to_dict()` (`pipeline.py:546–606`) replays `select_for_validation(scores)` directly into `routing_summary["escalated"]` and `routing_status`. When `segment_origins` carries `"validator-disabled"`, `to_dict()` must report `"validator-disabled"` and `escalated: 0` (retaining counterfactual diagnostics separately if desired) rather than claiming segments reached Qwen.
5. **Ready-state & VEX coupling (`src/hawedit/models.py`, `security/wsl-asr-vex.json`, `tests/test_vex.py`):**
   - `tests/test_vex.py:27–30` (`REVIEWED_VEX_SOURCE`) pins `package_digest(src/hawedit)` (`a7b54139...`), which moves on any `src/hawedit/**` edit.
   - `models.py:109–110,981` probes `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` independently; when validator is off by default, missing `rzgar` stays reported cleanly by `hawedit.models` as `MISS`, while `--omni-asr` without `--validate-asr` succeeds without needing `rzgar` weights or `qwen-asr`.

## 3. Prerequisites for Final WER Ablation Measurement

Taking the validator off the default path (code change) is testable immediately with unit/worker/pipeline tests once approved. Running the **live WER ablation (`validator ON vs OFF` on the same >=20 clips)** additionally depends on:
1. Provisioned WSL OmniASR runtime (`wsl-asr` + `omniASR-CTC-3B-v2.pt` + GPU 1 headroom with `:8000` paused).
2. Downloading/staging verified `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` weights (`d71490a623113b4b069ac07cfc85b409389dde4c`) and `qwen-asr==0.0.6` in WSL for the **ON** arm.
3. Hand-corrected Sorani reference text for `>= 20` real clips (`BLOCKED #1` / Phase `B5` `[HAWA]` request).
