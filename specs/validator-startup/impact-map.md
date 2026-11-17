# Impact Map

Actual Serena map in research.md, seven definitions/reference calls; supplemented
by direct reads for Protocol dispatch (LSP cannot enumerate every dynamic call).

| Symbol | Callers / Required Coverage |
|---|---|
| QwenSoraniValidator.transcribe_segment | test_asr official-loader contract; _validate_hard_segments via validator Protocol; ResumableValidator delegation |
| QwenSoraniValidator._load | transcribe_segment; test_asr integrity-before-import, code-loading refusal, ASR model allowlist |
| _validate_hard_segments | OmniAsrProducer.transcribe; asr_worker.run_request; test_asr_stop strict-helper failure evidence |
| ResumableValidator.transcribe_segment | worker checkpoint wrapper; test_asr_resume draft/validator/alignment separation |
| _windows_file_lock | _runtime_transaction_lock |
| _runtime_transaction_lock | provision_wsl_runtime; test_wsl_setup contention/timeout/unlock/posix/hardlink/symlink/multiprocess cases |
| provision_wsl_runtime | CLI main; test_wsl_setup direct root, wheel source, revalidation, substitution, concurrent receipts, linked root and every receipt integrity case |

Only transcribe_segment and _windows_file_lock change; new internal PCM input
helper has no existing callers. Whole test_asr, test_asr_stop, test_asr_resume,
test_wsl_setup and new startup module run, followed by exact full verify.sh.
No change to worker checkpoint binding, escalation, canonical text/alignment,
model verification, source staging, lock ownership or publication authority.
