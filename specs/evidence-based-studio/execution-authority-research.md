# Protected Execution Authority Research

2026-10-03. Baseline clean 2598e8ee7284dba572f790e22226ff5301f4c01c;
package 27c7edfab83d569a8622b339cf2b8a546382517fa247d84fa5270568f1831c70.
Previous goal turn made progress: SD-B code committed and exact terminal gate captured,
4382 passes/one VEX binding failure, no skips; no task acceptance or paid execution.

Read current source and Obsidian canon before design. Parent plan already approves
protected producer adoption, authenticated governance/billing authority and raw-proof
consumption (D-276, BLUEPRINT §§3/7); implementation approval is not spending authority.
This unit resolves a necessary worker prerequisite, not a substitute for connecting it.

## Actual Mapping

execution-authority-before-map.json contains eleven actual Serena LSP definition and
reference queries. Each resolves one definition. BillingPolicy has seven references;
GuardedGeminiTransport eleven; candidate_review's bounded JSON/read/write helpers and
signature verifier are real inspected contracts, not invented interfaces. Existing private
storage, producer package digest and Vertex signature conventions are also mapped.
The headless Serena runtime is the cached 1.7.1.dev0 environment; its log is preserved at
LocalAppData/HawEditEvidence/execution-authority-serena-20261003.log.

## Current Gap

GuardedGeminiTransport validates policy values, persists integer reservations and protects
uncertain billing. It intentionally does not authenticate who granted those policy values.
Its confirmed-response replay path makes no upstream call, so guarding only network egress
would allow cached results after authorization revocation. Both replay and every count/
generation request/response must reopen raw configured authority.

Existing candidate/Vertex approval namespaces cannot authorize recurring studio spending.
Review roots and test keys must never silently become execution owners. Private host-selected
authority and signed document locations are mandatory; no web request may select those paths.
No provider availability, price semantics, model licences, retention contract, runtime/GPU
readiness or invoice is inferred from signed statements or a caller-provided binding digest.

## Narrow Implementation

Use a dedicated hawedit-studio-execution-v1 OpenSSH purpose, strict canonical bounded raw
document, configured owner principals/allowed signers and freshness policy. Bind current
producer package, supervisor-computed execution context, explicit count/generate actions,
governance references, canonical model route, caps/prices and shared reservation pool.
Return descriptive proof evidence, never a verified=True capability.

Compose the existing journal with a signed-authority transport. Verify before construction,
before every call including replay, immediately before/after each upstream operation and
before returning. Any document/proof/trust change refuses; generation response loss or
revocation after intent retains uncertain reservations. Reuse private storage/bounded JSON
helpers without changing their existing candidate semantics. No new runtime dependency.

## Remaining Integration

An actual ID-only worker must compute/revalidate the execution-context binding from current
runtime/model/governance observations, select these authority paths itself, bind the signed
document digest into the immutable outbox and refuse unguarded screener routes. OS-owner
HTTP sessions, live approved cloud/model preflight, attempt/recovery state and SD-C review/
revision/export remain mandatory. HTTP remains unavailable in this prerequisite unit.
Blockers #1/#3/#4/#21/#24/#25 remain; ephemeral test owners authorize only protocol probes.

## Focused Engineering Evidence

Real test-first collection failed because studio_authorization did not exist (red log).
The first implemented run is preserved as invalidated: formatting overlapped live signed
tests, yielding 78 passes/one producer-identity refusal in 88.965 seconds. It is not clean
verification. Never change producer source while signed-boundary tests or a full gate run.

Corrected frozen run: 89 passed, zero failures/errors/skips, 103.484 seconds. Both initial
and terminal producer digests were
8dc4fe8550ec6e54a1abf02b51faee8284fdc11d4992f6f6ed4110fa97b66a1b.
Host HawaPC01, Windows 11 build 26200, CPython 3.12.10, pytest 9.1.1, DBOS 2.29.0.
Current exact lint/types passed on 305 files; format check also reported 305 formatted files.
execution-authority-native-mechanics.json binds actual XML/log/map hashes and limitations.
This is uncommitted diagnostic evidence, not canonical gate/CI acceptance or live execution.

Preserve exact native generated log/XML/map/diagnostic bytes with scoped -text Git attributes;
text diffs remain visible. Full diff whitespace inspection reports pytest's literal trailing
whitespace in the preserved first failure log/XML. Source/doc whitespace checks pass; these
raw records are not reformatted or hidden to manufacture a whitespace pass.
