# EARS Specification

DR1: WHEN the local vendor is imported or loaded, THE adapter SHALL set process
metrics disabled before that operation. test_metrics_disabled_before_vendor_load.

DR2: WHEN local load/inference/conversion attempts an SDK import, THE adapter SHALL
refuse before module execution, including swallowed failures, and restore unrelated
import machinery. test_local_diarizer_refuses_sdk_import;
test_swallowed_sdk_import_still_refuses; test_import_guard_is_removed_after_failure.

DR3: WHEN an SDK is preloaded, THE adapter SHALL refuse before model load without
removing unrelated modules. test_local_diarizer_refuses_preloaded_sdk.

DR4: WHEN canonical PCM is supplied, THE adapter SHALL pass exact normalized
float32 mono16kHz samples and preserve input bytes/clocks.
test_diarizer_passes_exact_pcm_waveform.

DR5: WHEN WAV input is malformed, empty, truncated or not canonical PCM, THE
adapter SHALL refuse actionably before model load without modifying source or
checkpoint bytes. test_invalid_pcm_refuses_before_model_load.
This includes a partial final PCM sample, not silently truncated valid frames.

Existing checkpoint-before-vendor, held-lock, exclusive-output/rounding/overlap and
device rules remain unchanged; existing named regressions remain mandatory.
