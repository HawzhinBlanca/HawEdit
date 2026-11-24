# Actual Caller Impact

Serena map: worker-continuation-map-20261007/serena-map.json under the native
HawEditEvidence root, cleanfffee676; all mapped source hashes unchanged.

- events.read_events: actual definition; module export.
- agent.run_timeline: direct reader; corruption must propagate as contextual
  ValueError, not an available-looking partial timeline. Missing-file semantics
  remain the existing explicit unavailable view.
- durable_workflow: import and public re-export; unchanged signature/valid
  roundtrip. The coarse step only writes through JsonlEventSink.
- tests/test_durable.py: import, replay and live second-reader assertions.
- tests/test_run_cost.py: billed-state real JSONL roundtrip.
- tests/test_agent.py: timeline integration/missing-file callers; supplement with
  a genuine damaged-ledger caller test.
- tests/test_events.py: existing event/pipeline contracts remain unchanged.
- studio_generation.project_events: inspected defense in depth, no edit; keep
  refusal of mixed attempts/duplicate sequences. Run its full caller module.
- JsonlEventSink: actual five refs, production coarse-step/test roundtrip.
  Documentation only, no sink behavior/signature change.

No RunEvent/from_dict schema, workflow registration, producer, HTTP, model,
artifact, trust policy or billing-journal behavior changes in this unit.
