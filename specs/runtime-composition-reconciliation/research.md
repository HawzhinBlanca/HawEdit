# Research — runtime composition reconciliation

## Method

The five previously reported composition defects were re-audited against protected `main`
`ad807478f8dab181f505ffb68ffebd16d29ba977`. Serena is not available in this workspace, so
symbols and callers were mapped with `rg`, direct source inspection, and their named regression
tests. The exact tree passed the hosted Python 3.12 and canonical gate jobs with 2,489/2,489
tests and zero skips.

## Current state

### Closed on current main

1. **Per-segment ASR preservation** — `transcribe_prepared_segments()` records one
   `AlignmentInfeasible` region as `UnalignedSpeech`, continues the remaining regions, refuses an
   all-unaligned run, and carries the gaps into canonical JSON. Both host and WSL worker use the
   helper before validator escalation.
2. **Frame-count/parity order** — `extract_window_frames()` checks the raw ffmpeg delivery
   against the planned count before trimming to complete temporal patches. The measured
   36-planned/35-delivered/34-consumed case is accepted; two frames short is refused.
3. **Dual-GPU device composition** — CLI defaults and `build_visual_composer()` put
   embedding/reranking and TimeLens2 on `cuda:1`, VideoChat3 on `cuda:0`, and preflight names
   unavailable devices before loading.
4. **Sequential GPU lifecycle** — `VisualComposer` closes embedding before reranker
   construction, reranker before VideoChat3 construction, and reader after materialization.
   `run_pipeline()` closes TimeLens2 on success and failure. Cleanup errors refuse safe success
   and never replace the primary failure.
5. **WSL command semantics** — setup and Stage 1 use `--exec`, not bare `--`, and the Stage 1
   producer delegates to the setup prefix builder.

### Residual seam

`wsl_setup._prefix()` says every project `wsl.exe` invocation is built once, but
`wsl_vex_gate._wsl_prefix()` duplicates the builder. Both currently emit `--exec`, so this is not
a current runtime failure; it is the exact drift seam that previously made setup, Stage 1, and the
live security gate independently non-executable. `asr.py` also imports the shared function by its
private name.

## Callers

- `wsl_setup`: path translation, incomplete-generation cleanup, provisioning, probing, CLI setup.
- `asr.WslOmniAsrProducer`: path translation and worker execution.
- `wsl_vex_gate`: uv discovery/versioning, private scanner creation, audit, and cleanup.
- Tests: `test_wsl_setup.py` and `test_wsl_vex_gate.py` inspect exact argv at the command seams.

## Conclusion

Promote the builder to public `wsl_prefix`, use it in all three modules, delete the duplicate VEX
builder, and add an injected-sentinel regression proving the live gate calls the shared symbol.
No ASR, frame, GPU placement, or model lifecycle behavior needs another implementation.
