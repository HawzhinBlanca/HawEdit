# Impact Map

Actual fresh Serena map: research.md. Before existing source edits:

| Symbol | Actual references and additional dispatch | Coverage |
| --- | --- | --- |
| QwenSoraniValidator.transcribe_segment | test_asr official loader, four test_validator_startup PCM families; Protocol dispatch from _validate_hard_segments and asr_worker lazy factory | test_qwen_completion, test_validator_startup, test_asr, test_asr_origin, test_asr_stop, test_asr_worker_diagnostics, test_worker_publication |
| OmniAsrProducer.admission_policy | transcribe identity freeze, completion/context tests, pipeline via getattr | test_asr_completion, test_asr_context, test_asr_admission_cache, test_pipeline |
| WslOmniAsrProducer.admission_policy | before/after worker identity freeze; completion/context tests | same and test_asr_worker_diagnostics, test_worker_publication_collisions |
| worker_journal | import/call in asr_worker.run_request before resumable draft/validator/alignment | test_asr_resume; current full gate |
| ResumableValidator.transcribe_segment (unchanged) | one static test; dynamic lazy wrapper in asr_worker | test_asr_resume actual immutable storage binding controls |
| TranscriptStore.reusable_raw (unchanged) | pipeline and twenty cache/context/transcript references | test_asr_admission_cache, test_transcripts, test_pipeline |
| _qwen_audio_input (unchanged) | validator call; extracted direct PCM assertions retain all cases | test_validator_startup, test_asr official loader |

Fresh map also covers helper/test definitions before changing the CPU tests and
three admission-policy expectations. _load and Omni EOS observer stay unchanged.
New qwen_completion module has no pre-existing callers; add README module map,
initial WIP PROGRESS accounting and proper evidence header. Whole test_claims
must pass before the exact committed gate. No fixture/golden/harness edits.

Mode repair: fresh three-pair map in research.md. _configuration -> observer
initial freeze/check; QWEN_COMPLETION_POLICY_ID -> asr aggregate/native/WSL and
asr_resume worker_journal, completion/resume tests. Configuration test definition
mapped before adding three non-greedy mode cases. Policy v2 invalidates v1 cache;
all previously mapped caller cohorts remain required. Superseded interrupted
6c3b5d6 gate is not completed verification. New exact committed gate required.

Two new named v1-to-v2 migration tests use the existing actual storage APIs;
their assertions include original canonical/normalised/provenance and operation
byte preservation, before cached correction consumption. Existing cache/journal
implementations and test symbols are not changed by this follow-up.
