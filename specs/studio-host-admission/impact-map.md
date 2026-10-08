# Impact Map

One writer. This unit introduces `studio_host.py`; existing symbols are consumed,
not edited. Core actual map plus the additional actual map named in research.md
are the definition/reference baseline. LSP alias limitations remain explicit.

| Symbol | Existing callers and integration obligation |
|---|---|
| audit_installed_profile | model provisioning, environment tests; keep strict installed studio profile, no injected ready flags |
| ModelStore.verify_checkpoint | loaders, model fetch/readiness/integrity tests; six selected checkpoints, retain loader fences |
| resolve_champion_adapter / adapter_fingerprint | ASR producer, worker/cache/revision paths and champion tests; default champion remains mandatory |
| probe_wsl_runtime / run_live_gate | canonical ASR/model readiness, setup/security CLI and tests; retain real receipt, scanner and VEX refusal |
| ProducerSelection.argv | generation, reconstruction, outbox tests; new admission requires explicit named WSL selection, does not change CLI defaults |
| assert_devices_available | shared builder and pipeline tests; use actual shared parser device defaults |
| VertexGeminiJudge.__init__ / _url | Vertex judging and discovery; no ADC call during parity checks; preserve canonical model/global and regional URLs |
| load_studio_authorization | SignedStudioTransport and raw-proof tests; new consumer reopens real proof, never treats a receipt as authority |
| SignedStudioTransport | billing and owner-authority tests; new factory checks deployment/proof and uses shared global billing pool |
| package_digest / _read_bound | WSL receipt/security identity; recheck package and raw VEX around the full admission |

Manual callers not inferred solely from LSP: `durable_workflow` imports the
`build_and_run` alias; web generation remains refused and will not consume this
unit until a protected worker is actually composed. No pipeline, attempt journal,
DBOS registration, HTTP, publication or recovery schema is changed here.

Tests: new host composition tests, complete studio authorization/billing/generation/
execution-input suites and claims, then the exact full gate at a frozen local commit.
Protocol fixtures exercise boundary composition, not real runtime/model readiness.

New-symbol follow-up: four actual definition/reference pairs before type/fixture
repairs, unchanged=true, external studio-host-new-symbols-20261008/serena-map.json
SHA256 ad70d2cfa710d3a5a904f7104cdbacc30f10660e3459b2454d633d64075a3510.
`capture_studio_deployment` callers are new host authorization and its tests;
observation/refusal/drift helpers are test-only. No existing caller signature changes.

Before authority post-check edits: two actual definition/reference pairs,
studio-host-authority-map-20261008/serena-map.json, unchanged=true, SHA256
2541494e25cbcad231b6e93cff69e459c0c3a47b0bbd69d926b538d7b0716b19.
Both consumers are called by the new factory and protocol tests, not HTTP or the
legacy pipeline worker. Two actual counterexamples then failed with DID NOT RAISE:
VEX mutation during genuine owner verification, and configured policy mutation
after genuine SignedStudioTransport construction. No production proof was forged.
