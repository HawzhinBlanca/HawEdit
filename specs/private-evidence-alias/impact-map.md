# Impact Map

Actual Serena maps at 1400a20, source/observers/HEAD/status unchanged:
C:/Users/Wareen/HawEditEvidenceAliasCallerMap-20261008/serena-map.json;
C:/Users/Wareen/HawEditEvidenceAliasHostMap-20261008/serena-map.json;
C:/Users/Wareen/HawEditEvidenceAliasBindingMap-20261008/serena-map.json.

- capture_studio_deployment: load_studio_host_authorization; existing composition,
  stage-refusal, identity, drift and signed-host tests. Signature unchanged.
- _check_deployment_bindings: load_studio_host_authorization and
  prepare_studio_host_transport; existing raw authority/transport drift tests.
- _evidence_target: preflight/publication, both called by run_live_gate. Consult,
  do not edit. Link and existing-evidence refusal remain required.
- PrivateDirectory constructor/verify/identity: consult, do not edit; global
  upload/review/runtime/journal callers retain original semantics.
- New _canonical_evidence_directory: only internal host calls and direct actual
  filesystem regressions. It does not canonicalize arbitrary artifact parents.

Whole test_studio_host, test_studio_private, test_wsl_vex_gate,
test_wsl_scanner_storage and test_claims plus new direct regressions required.
