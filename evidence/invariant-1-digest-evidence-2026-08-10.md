# Invariant #1 digest-evidence coverage — 2026-08-10

Protected main measured that `verify_raw_integrity`'s missing or unreadable sidecar refusal could be
neutralized while its suite remained green.  Existing tests changed the transcript and therefore
reached the digest-*mismatch* branch; none removed the sidecar that supplies the evidence.  With
the missing-evidence refusal removed, a caller could rewrite the canonical raw, delete the sidecar
and receive no integrity failure.

Readiness production code was already correct and unchanged.  Current-tree coverage now derives
its cases from one explicit set of five evidence-destruction states: deleted, empty, whitespace,
non-ASCII and a directory.  Every state is exercised through both public verification doors:
`verify_raw_integrity`, used directly by the runner, and `write_norm`, which independently
rechecks before derived transcript publication.  Every state is repeated after canonical raw-byte
tampering.  Deleted, non-ASCII and directory states must reach the exact unreadable-evidence
diagnostic; empty and whitespace sidecars are readable but cannot equal a SHA-256, so they must
reach exact digest mismatch.  An intact control must verify, publish and read the normalized
artifact, so an unconditional refusal cannot satisfy the matrix.

This proves that absent or unreadable unkeyed digest evidence cannot be interpreted as successful
verification.  It does not claim authenticity against an actor who can rewrite both the raw and
its unkeyed digest; that requires a signature or a secret-key MAC not presently owned by HawEdit.
