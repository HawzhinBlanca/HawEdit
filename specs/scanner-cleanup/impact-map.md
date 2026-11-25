# Impact Map

Actual Serena at ae26afe: _run_hash_locked_audit <- run_live_gate. _run_bounded
callers include _find_uv, _verify_uv, _run_hash_locked_audit and
_execute_hash_locked_scanner. The latter two retain existing scanner lock,
package inventory, strict OSV options and audit report validation.

_install_success_mocks callers: successful pinned-contract, shared runtime-root,
wrong scanner version/inventory, policy ABA, operational failure, malformed report
and receipt-drift tests. Update only subprocess storage protocol; preserve all
existing assertions and command counts. Add named failure/cleanup regressions.
No _run_bounded signature or run_live_gate public API changes.

New storage script has no old callers. Test its actual subprocess execution:
Linux performs real filesystem operations; unsupported Windows refuses safely.
Actual Linux observations are separately required on this Windows host.

Full-gate follow-up at686b1e5: actual two-pair Serena map for STORAGE_SCRIPT and
scanner_directory_identity, unchanged, SHA256
d315c39b0e2c526bc67b54f1b39431a2d5a7b7ce03a8a72f88f1f9018c496b0f.
Raw root scanner-stream-map-686b1e5-20261008 under Local/HawEditEvidence.
Callers remain the audit launcher and storage/protocol tests. Capture the isolated
subprocess's original document stream and name it explicitly at output. Add the
new module to README and a WIP PROGRESS row; no existing ledger status is flipped.
