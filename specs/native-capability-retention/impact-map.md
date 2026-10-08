# Caller Impact

Actual current Serena map and hash in research.md, not provisional text search.
NativeJob.close: run_native finalization; both create failure handlers; __exit__;
native-process invalid-input, pre-resume close and actual context-drain tests.
NativeJob.stop: run_native refusal, wait deadline, close and descendant tests.
NativeJob.create: run_native and complete native-process/IO tests. _discard remains
unchanged; its snapshot must detach before partial release or uncertainty.
_quiescent/_retain_members retain original observations and are not rewritten.

New helper retains original uncertain objects and gates create/stop/close; no
public reset, exported signature, dependency or host execution route added.
Individual release clears only its successful handle; image access remains until
all native releases succeed. Normal constructor/abandonment paths stay covered.
Actual native tests isolate faults in child owners so the pytest owner stays healthy.

Whole affected modules: native_capability_retention, native_process, native_io,
native_io_memory, studio_private, studio_storage, studio_billing,
studio_activation_fence, studio_runtime, studio_host, model_fetch,
vertex_acceptance. These last consumer modules include actual Windows security
helper imports; they do not imply an added protected producer caller.
Run the complete gate as well; no exclusions, skip, fixture/golden or harness edits.
No WSL ASR/producer, DBOS/effects/attempt-store, pipeline, HTTP or review adoption.
