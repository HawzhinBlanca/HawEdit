# Caller Impact

- PyannoteDiarizer.__post_init__: dataclass construction via create_diarizer and
  direct adapter tests; enforce the already-named canonical model identity.
- PyannoteDiarizer.diarize: direct adapter/wire tests and dynamic Diarizer calls
  through ingest.attach_diarization -> pipeline.run_pipeline. Preserve named
  unavailable/invalid-output exceptions and exact exclusive conversion rules.
- create_diarizer: pipeline._build_and_run (CLI/durable/studio shared builder),
  test_pyannote_wire._wire. Signature/defaults unchanged.
- verified_checkpoint_access: existing models/ASR/visual consumers unchanged;
  adapter becomes an additional consumer, not a new verifier implementation.
- Test wiring: _wire and missing-extra test must supply actual temporary manifest
  and files rather than an empty directory. All original assertions retained.

Actual seven-pair Serena map and reference excerpts retained externally. Full
test_pyannote_checkpoint, test_pyannote_adapter, test_pyannote_wire, test_ingest,
test_pipeline and test_models modules plus exact canonical gate cover callers.

## Reload Refusal Repair

Actual fresh seven-pair Serena map at f083a896 additionally covers model exception
classes, verified_checkpoint_access, attach_diarization and the pipeline's named
unavailable-diarizer regression. Module-bound references replace stale imported
class/function identities only inside PyannoteDiarizer.diarize. Model contracts,
constructors, shared builder, ingest and test_models reload behavior are unchanged.
Existing failure cases in checkpoint/adapter/pipeline callers remain assertions
of the same named refusal. Add test_diarizer_refusal_survives_model_module_reload
using a real isolated child/missing checkpoint. Whole models + adapter modules
must reproduce the original7failures before repair and pass afterward; whole
ingest/pipeline callers and exact full gate remain required. No dynamic callers
are excluded merely because the static protocol map cannot resolve them.
