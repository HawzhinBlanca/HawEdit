# Caller Impact Map

Actual Serena map is referenced in research.md. Supplemental repository reads
cover Protocol dispatch not resolved by LSP.

| Symbol | Callers / impact | Regression scope |
| --- | --- | --- |
| OmniAsrBackend, adapter_name | OmniAsrAdapter, OmniAsrProducer, worker run_request, fingerprints and provenance tests | identity after CTC-only load/release, unchanged canonical policies |
| OmniAsrBackend._load | transcribe_segment, align_segment and held-assets/adapter tests | both-model draft construction/order, cached CTC reuse |
| OmniAsrBackend.align_segment | _validate_hard_segments via OmniSegmentBackend; ResumableBackend operation callbacks | no LLM construction for correction, same emission/alignment semantics |
| OmniAsrProducer.transcribe | pipeline producer Protocol; native/context/stop/completion/admission tests | release only after every admitted draft, before validation; no custom backend policy change |
| asr_worker.run_request | worker main; host WSL subprocess bridge; worker/resume/stop/completion tests | same handoff on actual underlying backend, checkpoint wrapper unchanged |
| _validate_hard_segments | native producer, worker, strict helper tests | read only; routing, role and failure handling unchanged |

New private CTC constructor is shared only by the two loaders. New release
method is called only for exact OmniAsrBackend instances by both production
entry points. Custom Protocol implementations/subclasses are left untouched.
No journal schema/cache compatibility changes, pipeline-wide rewrite or harness edit.
