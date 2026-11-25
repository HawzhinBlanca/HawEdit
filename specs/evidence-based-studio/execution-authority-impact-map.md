# Execution Authority Caller Impact

Baseline 2598e8e. Actual queries: execution-authority-before-map.json.

| Symbol | Actual callers / adoption | Coverage |
|---|---|---|
| BillingPolicy | studio_billing and test_studio_billing, seven references | Existing billing suite plus signed-policy validation; signature-bound exact integer fields |
| GuardedGeminiTransport | existing billing tests; eleven references | Existing schema/reservation/replay/loss tests unchanged; new composition probes actual private SQLite |
| GuardedGeminiTransport/__call__ | dynamic callable, no LSP method references | New signed wrapper explicitly invokes real journal, fences replay and internal count/generate |
| candidate_review._json/_canonical/_read/_write | candidate review/publication/tests; counts 11/12/20/3 | Reused bounded parsing/private snapshots; no existing helper edits or candidate purpose change |
| candidate_review._signature | verify_candidate_review, one reference | Inspected convention only, not used to reinterpret review authority; no source edit |
| PrivateDirectory | private stores/review/publication/tests, 48 references | Actual private roots/files/scratch; unsafe/lost/mutated storage refused, never repaired |
| package_digest | runtime/release/pipeline/tests, 47 references | Actual current producer hash before/after raw proof verification; stale signed package refused |
| vertex_acceptance._verify_signature | run_vertex_acceptance, one reference | Inspected purpose separation/private snapshot convention, unchanged |

No existing runtime symbol is changed by this prerequisite; no existing caller is removed.
New studio_authorization symbols are mapped with Serena before subsequent integration edits.
Full exact gate covers the old caller families. A new signed wrapper is not a registered
worker, spending enrollment, runtime certificate, HTTP authentication or creator acceptance.
