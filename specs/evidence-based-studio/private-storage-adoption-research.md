# Remaining Protected Storage Adoption

2026-10-02. Research only, while the frozen private-journal gate runs. Package
`637e9acc148c7b9000605df4c2a4006abd7b5268b6e9617641f509e7a6b6c302`, unchanged baseline
HEAD `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, uncommitted. Parent plan/D-276 still
require whole-studio private storage, per-user HTTP identity and protected worker adoption.
No paid execution, new production root, trusted keys or spending policy is configured here.

## Actual Dependency And Startup Boundaries

Serena research map now contains 210 records. The latest five class-level records cover
PrivateSqlitePath, StudioStorageError, SubmissionStore, UploadStore and ThreadingTCPServer;
their actual references complement constructor-method lookups that return no callers.
The LSP reported some import references as file symbols; retain those diagnostics rather
than claiming every import was resolved to a containing function. Embedded child programs
and the standalone POSIX probe remain manually inspected callers.

PrivateSqlitePath currently imports StudioStorageError from studio_submissions. Directly
adopting the binding in studio_submissions would introduce a cycle at module import.
Resolve that specific shared-error ownership before adoption, preserving the public old
import and all actual exception catchers. Map exception serialization/type assumptions,
not just text references. This is a concrete extraction need, not grounds for a broad
pipeline refactor. Current billing/private code imports successfully and its gate source
must not be changed during verification.

UploadStore.__init__ currently resolves its root and creates tickets/incoming/sources with
ordinary recursive mkdir. SubmissionStore initializes another SQLite pathname without the
new mandatory binding. DBOS owns a separate system database; protecting billing does not
protect either store or establish cross-database atomicity. Keep the existing outbox's
immutable token/snapshot semantics, actual DBOS identity/concurrency and original recovery
assertions when adding real private test storage. Never satisfy these tests by refusing
their valid path before the behavior under test occurs.

web.py constructs JOB_MANAGER and UPLOAD_STORE at import time under checkout work paths.
run_web_server only validates a loopback bind and starts ThreadingTCPServer. Handler routes
read the module globals. Native HTTP regressions inject actual isolated managers/stores,
and legacy programmatic JobManager tests still exercise direct runners. A private production
startup must not silently chmod, relocate or claim acceptance of existing owner files, nor
make module import itself start privileged work. Preserve original historical records/media
and explicit unverified context; replace the legacy writer/daemon only through the approved
authoritative worker integration, not a new parallel execution graph.

## Next Required Checks

The new journal mechanism is not persistent supervisor authority. Restart adoption must
bind the authorized reservation pool and original store identity outside an unverified
replacement database; loss of the authorized store requires reconciliation, not a new
empty pool. Include genuine restart/root-loss and retained uncertain-intent tests. The
current path fences deliberately diagnose observed substitution rather than certify all
privileged races or mapped/remote/DrvFS lock semantics.

All sensitive roots/members need actual owner/access/link checks before writes and reads:
uploads and reservations, job/event/checkpoint media, submission/DBOS/billing state, provider
responses, trust/signature snapshots and session bootstrap material. Choose supported local
storage and record actual OS/filesystem evidence. Preserve existing unsafe legacy bytes
and permissions; refuse or expose diagnostics instead of moving them automatically.

Current loopback, Origin and Sec-Fetch checks are not per-OS-user identity. Owner bootstrap,
session expiry/reconnect/revocation and authenticated API/media access need a complete native
browser/HTTP contract before paid work. Do not leak bootstrap/session authority through URL
queries, logs, persisted job/options or approval payloads; do not accept browser-supplied
trusted roots. Evaluate ambient cookie scope, media range/seek/download behavior, response
loss and refresh explicitly. No authentication scheme is selected or certified by this note.

Existing protection tests, original upload/outbox/queue/billing cases, real two-process
recovery, native storage drift and actual browser response-loss/history/preview tests must
remain genuine and be extended for adoption. Trusted provider/model/runtime prerequisites,
authenticated review/render revisions/reconciliation/export, current VEX/CI and all frozen
independent acceptance obligations remain separate. No study threshold is changed.

## Reproduced Defects And Scoped Repair

The pre-edit native test-first run failed six of seven cases (T3-storage-test-first.log).
It accepted an ordinary shared upload root, a hardlinked ticket and substituted source
container, and accepted a shared submission root. A real post-probe junction substitution
caused old cleanup to delete unrelated test-only original media; no owner media was used.
An actual deleted submission main file was recreated as empty SQLite state during a read.
Old module-qualified error deserialization already passed and must remain compatible.

The shared exception now lives in the leaf studio_private module and remains explicitly
exported from studio_submissions. Directory/root identity and private file checks are
mandatory in uploads and the request outbox. Private atomic metadata creation replaces
only this store's generic-writer usage; global atomic_fs and unrelated callers stay intact.
Failure cleanup removes only the transfer's tracked file identities from its still-bound
private staging directory. A substituted/moved namespace retains evidence, not cleanup
authority. Original response-loss/committed-ticket recovery contracts remain unchanged.

The second actual test-first finding is MPEG-TS bytes acknowledged under an `.mp4`
filename (T3-storage-container-test-first.log). The old all-supported-demuxer whitelist
refused the tested HLS external playlist already; do not report a newly reproduced HLS
leak. Narrow both probe and decoder demuxers by suffix and validate measured format aliases;
use actual decoded/remuxed positive cases for all seven suffixes, not mocked ffprobe JSON.
This is supported-container validation, not a complete FFmpeg sandbox/security certificate.
Primary reference: [FFmpeg format options](https://ffmpeg.org/ffmpeg-formats.html#Format-Options).

Native live-server tests execute run_web_server in exact test-owned child processes,
exercise real HTTP reservation/PUT/status and inspect finalized bytes/private ACLs or modes.
They cover configured and default roots, not authenticated user sessions or real producer
execution. Child termination targets only those exact test-owned processes, never console
control events. The first added positive/live tests had nine wrong response-shape assertions;
T3-storage-security-final.log retains them. Correct tests use the existing source descriptor
and status envelope, without changing or weakening the production API or prior assertions.
