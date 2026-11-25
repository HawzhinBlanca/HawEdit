# ASR worker diagnostic impact map

Actual map: `C:/Users/Wareen/HawEditQuality-7fa7-20261004/diagnostics-before-map.json`.
Baseline: clean `3ac37381a71a0c43c5692f75b369b5c876058e88`.

Only WslOmniAsrProducer.transcribe's unsuccessful-worker error message is edited.
Its public signature, request schema, subprocess arguments, timeouts, identity
checks, host checkpoint lease and refusal/return behavior are unchanged.

Actual method references: test_windows_wsl_producer_cuts_locally_then_invokes_one_worker,
test_wsl_worker_boundary_holds_a_real_host_lease_against_checkpoint_publication and
_capture_wsl_request in tests/test_asr.py. Class references additionally include
create_omni_asr_producer, tests/test_adapter_identity.py and tests/test_wsl_setup.py.
Imported-class references sometimes produce a file-symbol fallback; original
warnings are retained. The ASR protocol's dynamic dispatch is not fully described
by static method references: include the shared pipeline and producer-builder callers.

Mapped but not edited: _runtime (transcribe and two runtime/receipt tests) and
pipeline._operational_failure (ingest, ASR, discovery, judge, temporal and camera
refusals, plus two exact sanitization/limit tests in tests/test_pipeline.py).
Do not relax that shared report limit to solve one producer's oversized message.

Verification: complete new diagnostic module plus complete test_asr,
test_asr_stop, test_adapter_identity, test_wsl_setup, test_models, test_pipeline,
test_studio_generation and test_pro_video_repurpose modules, then the exact full
gate. Existing assertions and fixtures remain intact. The real-source CLI retest
uses the canonical producer, not the protocol stand-ins used in unit diagnostics.
