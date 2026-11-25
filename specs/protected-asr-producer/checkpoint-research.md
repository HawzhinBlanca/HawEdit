# PA3 Host Checkpoint And Shared Inference Unit

Approved scope: protected-asr-producer/plan.md steps3-4, D-329; BLUEPRINT
sections2-5 and8.1. No model release or publication is authorized by this unit.

Actual Serena FindSymbolTool/FindReferencingSymbolsTool map:
C:/Users/Wareen/HawEditCheckpointTransportMap-1591502-20261014/serena-map.json.
On2026-10-14 at9e6b17a0ae8ed0af1cc0d94a288afd3bdf291b07, both mapped sources
remain byte-identical to that map: asr_resume.py SHA3ca99954d48decf87e655d2924e518af0bffaa2e3efa46f01917e8d0443b9693;
asr_worker.py SHA44d05bf9f966e0312f5d4244ed66dc3dc9c594934842212bff28fe3f667dac9d.
OperationJournal callers: ResumableBackend/Validator and worker_journal, with
test_asr_resume. Resumable wrappers and worker_journal: run_request and resume
tests. run_request: CLI main and test_asr, test_adapter_identity,
test_asr_completion, test_asr_model_lifecycle, test_asr_origin, test_asr_resume,
test_asr_stop, test_worker_publication and test_worker_publication_collisions.
These complete modules are the caller regression set. No existing caller is
permitted to lose exclusive result creation, fail-stop semantics or provenance.

The existing journal needs writable owner-private storage; the original worker
does not have it. Extract shared inference without changing model selection or
validation. The CLI keeps its existing file publication and local journal.
A structural operation-cache protocol permits the same canonical inference to
use a host checkpoint session. A protected entry point requires the remote
checkpoint client and never supplies a writable worker checkpoint/output path.

The host maps opaque audio identifiers to its own admitted audio files. Remote
operations cannot choose host paths. Bind source/config/runtime digests through
the existing journal binding; validate audio hash and duration against the
host's current files on every operation. Frames are canonical UTF-8 JSON with
strict fields, sequence, binding and SHA-bound responses, capped64KiB. Duplicate
JSON keys and nonfinite numbers refuse. Storage errors do not produce an ACK.
Failure poisons that session; restart requires a new session and journal lease.
The final transcript is canonically serialized and bounded16MiB.32KiB binary
chunks each fit a64KiB JSON frame and are durably saved in the same journal;
final size/hash/media validation precedes its durable completion record.
All audio bindings are rechecked at finalization. Pending private result only,
not pipeline completion or evidence that inference ran in an admitted worker.
Use existing durable atomic journal writes, not an independent cache policy.

This unit implements protocol/inference integration, not native endpoint
authentication, owned deadlines/drain, complete SDK/resource admission or a
fresh runtime receipt. Those are still required before a protected producer
can release models. Never interpret protocol hashes as sender authentication.
Do not loosen the existing RootedLaunch EOF handoff or nonce control exchange.

EARS: WHEN a protected request executes, THE worker SHALL use the same canonical
inference and remote operation cache without creating output/checkpoint files.
Tests: test_protected_inference_uses_host_checkpoint_without_worker_writes;
test_protected_inference_requires_remote_journal.
WHEN a host checkpoint save succeeds, THE host SHALL ACK only after atomic
persistence; a restarted journal SHALL recover the same result.
Test: test_checkpoint_exchange_persists_before_ack_and_survives_restart.
WHEN sequence, binding, source bytes, clocks or frame evidence changes, THE
session SHALL refuse and remain unusable.
Tests: test_checkpoint_exchange_refuses_changed_evidence;
test_checkpoint_exchange_failed_session_cannot_continue.
WHEN storage fails, THE host SHALL emit no success response.
Test: test_checkpoint_exchange_storage_failure_has_no_ack.
WHEN a result exceeds one frame, THE exchange SHALL preserve exact UTF-8 bytes
through bounded durable chunks without reporting an incomplete result.
Tests: test_checkpoint_result_large_utf8_uses_durable_bounded_chunks;
test_checkpoint_result_refuses_damage_without_completion.
WHEN an existing CLI output exists, THE worker SHALL refuse before inference.
Existing test_worker_existing_output_refuses_before_backend remains unchanged.

Test-first, complete affected caller modules, exact bash scripts/verify.sh.
Controlled backend responses prove contracts only, not Kurdish accuracy.
