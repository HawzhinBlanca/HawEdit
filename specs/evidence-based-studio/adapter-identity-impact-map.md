# Adapter Identity Caller Impact

Baseline 2cedcca; twelve initial queries in adapter-identity-before-map.json plus two class/
constructor queries in adapter-identity-constructor-map.json before the constructor edit.
Definition locations are zero-based tool positions. Protocol/dynamic dispatch needs tests too.

| Changed symbol | Actual affected callers / tests |
|---|---|
| adapter_fingerprint | OmniAsrBackend.adapter_name, WslOmniAsrProducer.model_identity, create_omni_asr_producer; adapted provenance, rank/weight/stability identity tests |
| OmniAsrBackend.adapter_name | native producer model_identity/output, worker output via getattr; adapted transcript/delivered-sidecar and stock controls |
| OmniAsrBackend._load | transcribe_segment, align_segment; stock held-descriptor/load-before-import/parallel-forward tests |
| OmniAsrBackend.__init__ | nineteen class references including OmniAsrAdapter, native producer, worker and backend subclasses; no direct constructor references surfaced by LSP |
| OmniAsrBackend.transcribe_segment / align_segment | ASR benchmark, transcribe_prepared_segments and validator realignment protocol calls; existing ASR/validator tests |
| OmniAsrProducer.transcribe | six direct producer tests, pipeline CanonicalTranscriptProducer protocol; native segment/validator/empty-VAD tests |
| WslOmniAsrProducer.transcribe | _capture_wsl_request, Windows cut/worker test, real host lease test; resume/schema and host output-provenance tests |
| create_omni_asr_producer | shared pipeline._build_and_run and runtime-selection/early-refusal tests |
| asr_worker.run_request | main, Windows worker/host-lease, worker segment/validator/stock/ignored-adapter tests |
| _capture_wsl_request | two bridge field/schema tests; deterministic worker boundary must return the actually requested adapter, not falsely labelled stock |

No signature changes to existing public producers. Full v2 adapter digest changes adapted
reuse identity intentionally; old records remain unmodified. Stock model identity and request
schema fields remain unchanged. No fixture/golden or enforcement-surface edit is planned.
The injected protocol backends in existing tests do not establish actual ASR/model quality.
