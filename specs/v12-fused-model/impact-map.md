# Impact map: fused-checkpoint drafting (v12)

Positions are line numbers on `6fe060d` (`codex/evidence-based-studio`). Every changed symbol is listed with its callers and the tests that must cover it.

## asr.py
| Symbol | Change | Callers | Tests |
|---|---|---|---|
| `resolve_champion_adapter` (222-269) | unchanged; a sibling `resolve_champion_checkpoint` is added | `pipeline.py:5439-5453`; `studio_host.py:143-144, 203-204, 228` | `test_asr.py` champion tests; `test_studio_host.py` |
| `OmniAsrBackend.__init__` (517-545) | new `fused_checkpoint`; LLM default `cuda:1` | `asr.py` adapter and producer; `asr_worker.py:100`; tests | `test_asr.py` device tests; `test_champion_held_assets.py:225` |
| `OmniAsrBackend.adapter_name` (552-570) | returns `fused:<sha>` for fused | `asr.py:896, 913, 921, 925`; `asr_resume.py:232-233` | `test_adapter_identity.py` |
| `OmniAsrBackend._load` / `_load_adapted_llm` (572-646, 719-811) | fused branch without PEFT; assets subset | `_load` call sites | `test_asr.py:94-137` loader tests (fakes) |
| `WslOmniAsrProducer.model_identity` / request (1435-1444, 1545-1631) | `fused_checkpoint` field and identity re-check | `create_omni_asr_producer` (1635-1650) | `test_asr.py` worker/producer tests; `test_trusted_producer_parity.py` |
| `create_omni_asr_producer` (1635-1650) | accepts a checkpoint | `pipeline.py` around 5450 | `test_pipeline.py` |

## Other files
| Symbol | Change | Callers | Tests |
|---|---|---|---|
| `asr_worker.run_request` (53-168; regex at 110) | accepts `fused:[a-f0-9]{64}`; free-VRAM check | WSL subprocess from `WslOmniAsrProducer` | `test_adapter_identity.py:127`; `test_asr_worker_diagnostics.py` |
| `asr_resume` binding (273-337; device at 318) | identity passes through; LLM default `cuda:1` | `ResumableBackend` | `test_asr_resume.py` |
| `studio_host` champion stage (114-250) | fused descriptor and drift check | studio host process | `test_studio_host.py:154-300` |
| `pipeline.py` CLI (4854, 4862, 5263-5303, 5439-5453) | `--omni-asr-checkpoint` / env; mutual exclusion | CLI | `test_pipeline.py` refusal tables (around 3435, 3510, 5280) |
| `wsl_setup.py:1061` | message only | `wsl_setup` checks | `test_wsl_setup.py` |
| `asr_completion.py` | **no change** (same model class and generator); verified on hardware in T0 | `asr.py:892-893`; `asr_resume.py:293` | `test_asr_completion.py` (unchanged) |
| `omni_assets.py` | **no change** (the `assets=` subset already exists) | | `test_champion_held_assets.py` |
| `transcripts.py:544` | comment only (validation already accepts any string) | | `test_transcripts.py` |
| `asr_completion.py` (T8) | new pure `loop_suspect(text, seconds)`; beam variant of `require_natural_completion` (selected hypothesis must end on EOS); new `COMPLETION_POLICY_ID` | `asr.py:893` `transcribe_completed`; `asr_resume.py:24` policy ID | `test_asr_completion.py` (new cases); cache-reuse refusal tests |
| `asr.py:893` caller (T8) | suspect → one beam-5 retry of that segment → else `DecodeIncomplete`; per-segment `decode_mode` | `OmniAsrBackend` transcribe path | `test_asr.py` fake loop/complete generators |
| run report / transcript provenance (T8) | `decode_mode` and the retry count | `transcripts.py`, run report | `test_transcripts.py` |
| `DECISIONS.md` | new ADR D-xxx; T8 needs a separate ADR amending D-281 | | |
| `scripts/run-with-omniasr-paused.sh` | new operator wrapper | operator | new shell test |
