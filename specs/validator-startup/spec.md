# EARS

| ID | Criterion | Named Regression |
|---|---|---|
| VS1 | WHEN Windows setup locking returns a non-contention error, THE setup SHALL refuse immediately without retry, unlocking an unowned region, or entering the transaction. | test_setup_noncontention_lock_error_refuses_without_sleep |
| VS2 | WHEN a genuine or legacy contention error occurs, THE setup SHALL preserve retry, deadline and owned unlock semantics. | test_setup_contention_retries_and_releases; existing test_windows_setup_lock_normalizes_acquire_timeout |
| VS3 | WHEN validator input is a complete bounded mono 16000 Hz PCM16 WAV, THE validator SHALL pass the exact decoded float32 samples and rate to Qwen's supported tuple input without changing model options. | test_validator_canonical_pcm_uses_exact_predecoded_samples; existing test_qwen_validator_uses_the_official_loader_and_model_card_contract |
| VS4 | WHEN input is outside that canonical bounded format or is truncated, THE validator SHALL retain its existing path-based decoder route. | test_validator_noncanonical_audio_keeps_original_route; test_validator_truncated_pcm_keeps_original_route |
| VS5 | WHEN model integrity or safe configuration verification refuses, THE validator SHALL refuse before audio adaptation or model construction. | test_qwen_validator_integrity_failure_precedes_config_parse_and_import; test_qwen_validator_refuses_a_code_loading_config_before_imports |

Real decoded sample parity is not ASR accuracy, first-reviewable-clip performance,
native-editor approval, runtime admission, CI or a release verdict.
