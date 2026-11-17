# Protected Billing Journal Adoption

Date: 2026-10-02. Approved parent program: plan.md, Wareen's explicit implementation
request. BLUEPRINT sections 2-5; D-276 protected supervisor/private evidence obligations.
No new runtime dependency, paid egress, model change or production authorization.

## Current Native Evidence

At source package `66a377dabc4c08b265994e85ab18d66d8a89f90553e7a90cdec0f19ff8ebbd39`,
T3-private-journal-baseline.json records actual GuardedGeminiTransport construction in a
new isolated temporary directory. Existing Windows private-path policy rejects its root
for an access-allowed foreign principal, but construction creates billing.sqlite3 anyway.
No upstream function is called. This contradicts the module's private-journal label; it
does not demonstrate another account's actual access or authorize a permissions change
to owner data. Native runtime is CPython 3.12.10/SQLite 3.49.1 on HAWAPC01; the T5 browser
host inventory records hardware/OS. No throughput/quality measurement.

## Symbols And Callers

Serena find_symbol/find_referencing_symbols evidence is in serena-map.json and
serena-T3-private-journal.log. Actual changed symbols are
GuardedGeminiTransport.__init__, _connection and _call. __init__ currently resolves the
path (thereby hiding aliases), makes its parent with ordinary mkdir and connects SQLite.
_connection repeatedly opens the pathname without owner, link or identity checks.
_call has three upstream paths: direct count, generation's pre-reservation count and
generation after committed intent. The count shortcut bypasses persistence entirely.

Actual callers: tests/test_studio_billing.py guard helper, slow-count expiry test and
embedded abrupt-child program. The embedded program is read as real source; Python LSP
cannot resolve function calls inside a string literal. There are no production adopters
yet. All 44 existing billing cases must continue to exercise their actual intended
arithmetic/replay/schema behaviors using genuinely private test-only storage, not pass
early because privacy refused an invalid fixture. Keep policy and response assertions.

Reuse unchanged windows_security.create_private_directory and
assert_private_windows_path. Their other callers (model_fetch and vertex_acceptance)
are not edited. Windows root policy is protected current-user/SYSTEM/Administrators;
files inherit this private policy. POSIX root/file ownership and private mode are checked.
Existing owner directories/files are never chmodded, moved, erased or silently repaired.

## Bounded Repair

Introduce a journal-specific private pathname binding. Create only a missing leaf root
under existing real directory components, using the existing atomic Windows creation or
POSIX mode 0700. Refuse existing nonprivate roots, symlinks/reparse components, nonregular
or multiply linked files, changed root/database identities and unsafe SQLite sidecars.
Precreate a new DB exclusively with POSIX mode 0600; do not overwrite existing bytes.
Orphan WAL/SHM/rollback sidecars are refused, not deleted. Fence every SQLite connection
and each upstream request/result; retain actual WAL/crash evidence and existing uncertainty.

SQLite explicitly warns about aliasing/renaming a database in use and about separated
journal state. Its sidecars are part of database recovery, not disposable caches:
[SQLite corruption guidance](https://www.sqlite.org/howtocorrupt.html),
[SQLite file format](https://www.sqlite.org/fileformat.html).
Windows creation accepts a security descriptor and filesystem ACL inheritance matters:
[Microsoft file security](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights).

This protects storage from unauthorized filesystem principals under the existing policy;
it is not per-user HTTP authentication, signed spending authority, provider cap/invoice
confirmation, protection from the current owner/SYSTEM/Administrators, filesystem/mount
certification or a cross-OS SQLite lock guarantee. Root/identity fences detect observed
substitution; they do not claim elimination of all races from a privileged actor. HTTP
generation stays unavailable. Protected uploads/jobs/DBOS/trust roots, session bootstrap,
actual producer/runtime/governance and blockers 1/3/4/21/24/25 remain required.

## Frozen Implementation And Native Checks

Frozen package identity for the full-gate run is
`637e9acc148c7b9000605df4c2a4006abd7b5268b6e9617641f509e7a6b6c302`;
baseline HEAD remains unchanged and source is uncommitted. Actual current definitions and
references are in serena-T3-private-final-map.json (21 fresh records), in addition to the
205-record historical Serena research map. No cached definition is relabelled as fresh.

The test-first log records four reproduced old transport defects, with all original
44 billing cases passing. Initial repair passed 48 cases. Expanded native tests then
reported 70 passed/two failed: trailing-dot abspath normalization and legitimate SQLite
sidecar disappearance during concurrent pool allocation. Both failures remain preserved
in T3-private-journal-focused.log. The subsequent focused run passed all 76 cases
(50 billing, 26 private-path cases), before the final nonbehavioral import/type-guard
adjustments. The full exact gate is the current-source verifier, not that earlier log.

Raw filename/component validation now occurs before abspath; parent traversal/trailing
dots/spaces are refused. Existing real directory components are checked rather than
resolved through aliases. Optional SQLite sidecars may disappear naturally; a failed
inspection is ignored only when that sidecar is confirmed absent. Present unsafe files,
root/main disappearance, changed binding and unsafe permissions still refuse. Bound
root/main are rechecked after sidecar inspection. Original concurrency assertions remain.

T3-private-journal-posix-final.json records 12 bounded native POSIX observations using
the existing Ubuntu runtime (CPython 3.12.0, SQLite 3.43.1), actual /tmp filesystem
reported by stat as ext2/ext3, and the same canonical package_digest as Windows.
It verifies owner-private creation, shared root/file and symlink/hardlink refusal,
all three unsafe/orphan sidecars, original byte/mode preservation and a real committed
WAL after abrupt child exit. No pytest is installed in that environment; this is a
reproducible standalone assertion probe, not the Linux canonical gate. Earlier probe
T3-private-journal-posix.json used a raw Python-tree digest; that value is NOT the
canonical package_digest and its earlier source is not rebound to the final source.
Probe code is private_journal_posix_probe.py. No installation or model load occurred.

New Windows files inherit the existing verified private root ACL; POSIX main files
are exclusive mode 0600, roots 0700. No unsafe legacy root is automatically migrated.
Within a transport lifetime the main/root identities are pinned. A new supervisor
process still needs its persistent authoritative pool/root binding and startup recovery
reconciliation before creating/adopting a journal; this unit does not claim that a
lost disk/root can be safely recreated for a previously authorized pool. Likewise no
remote/DrvFS/mapped-drive lock/privacy certification or privilege isolation is inferred.
