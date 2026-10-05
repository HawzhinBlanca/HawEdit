# ASR Context Grouping Impact Map

Baseline: 899ab32c0efcdf306245a2dcbe55d8124e436c0e. Actual worktree Serena
definition/reference pairs were captured before source edits in
`C:/Users/Wareen/AppData/Local/HawEditEvidence/asr-context-worktree-map-899ab32-20261006/serena-map.json`.
The source hashes remained unchanged. Constructor class references were captured
in `../asr-context-worktree-constructor-map-899ab32-20261006/serena-map.json`
(private evidence root): 18 native and 22 WSL references. __init__ searches alone
returned no callers, so class reference searches completed the map.

| Changed Symbol | Affected Callers / Regression Scope |
|---|---|
| OmniAsrProducer.__init__, transcribe | create_omni_asr_producer; tests/test_asr.py's canonical VAD/clock, validation routing, no-validator and identity-drift callers; tests/test_asr_stop.py's first ASR/validator failure callers |
| WslOmniAsrProducer.__init__, transcribe | create_omni_asr_producer; tests/test_asr.py's Windows cutting/one-worker, host lease and _capture_wsl_request callers; tests/test_asr_worker_diagnostics.py's _worker_error |
| Both admission_policy properties | tests/test_asr_completion.py's native/WSL parity; pipeline.run_pipeline's dynamic getattr binding and TranscriptStore.reusable_raw/bind_raw (verified by direct source inspection) |
| create_omni_asr_producer | pipeline._build_and_run (shared CLI/studio construction); tests/test_asr.py's explicit runtime selection and invalid adapter before Stage 0 |
| New grouping helper and policy constants | Both concrete producers, new tests/test_asr_context.py; no existing caller until implementation |

Run complete affected test files, not filtered/deselected cases. New tests must
cover real PCM cutting, input coverage/limits/refusals, constructor compatibility,
native/WSL factory parity, cache immutability and drift refusal.
Constructor mapping additionally identifies tests/test_adapter_identity.py and
tests/test_wsl_setup.py; both complete files are included in the focused regression run.

No edits to pipeline CLI signatures, studio requests, Stage 0, asr_worker request
schema, model/adapter loading, completion observer, CTC alignment, validator,
transcript schema, golden fixtures or gate harness are planned. Polymorphic
pipeline invocation is not enumerated by Serena's concrete-method search, so its
transcribe/getattr call sites were inspected directly rather than omitted.

Studio source binding is already present: studio_generation.prepare_generation records
pipeline_source_sha256 from package_digest(), studio_runtime constructs JournalPolicy
with that source digest, and studio_authorization refuses changed producer source.
No additional studio or pipeline edits are required for this source-bound policy.

## Narrower Budget Revision

At rejected prototype a94a075e58c0e562a87dbe0a5edddc7e78cb3a5b, fresh actual
Serena definition/reference pairs for _CONTEXT_MAX_SPAN_MS,
CONTEXT_GROUPING_POLICY_ID and _contextual_speech_regions close unchanged in
asr-context-budget-map-a94a075-20261006/serena-map.json (private evidence root).
The budget is referenced by the policy constant and grouping helper. The policy
is referenced by both admission_policy properties and two tests in
tests/test_asr_context.py. The helper is called by both concrete transcribe
methods and the three input-contract tests. Existing native/WSL, pipeline/cache,
worker and constructor caller scope above remains applicable; run complete files.
No new signature or caller is introduced by the proposed scalar-budget revision.
