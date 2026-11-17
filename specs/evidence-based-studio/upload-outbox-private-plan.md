# Mandatory Private Upload And Submission Storage

2026-10-02. Approved-by: Wareen, explicit parent implementation request and D-276's
private supervisor/storage obligations. No new dependency, spending/model/licence/trust
approval. Baseline source package 637e9acc148c7b9000605df4c2a4006abd7b5268b6e9617641f509e7a6b6c302;
HEAD remains 372a16645d7a8558bc6cedcff34a9fbfa13f712f, uncommitted.

## Research And Impact

private-storage-adoption-research.md records current topology. Fresh actual symbol/caller
mapping is private_storage_serena.py / serena-T3-storage-before-map.json. UploadStore's
constructor resolves away aliases and ordinary mkdir/writes do not enforce private roots,
members or metadata. Failure cleanup unlinks staged paths without a transfer-identity fence.
SubmissionStore's constructor/connections can recreate unsafe/lost storage. Existing tests
use ordinary isolated temporary storage; their original domain assertions must still run
against genuine private fixtures rather than pass on an early unrelated policy refusal.

Move the existing shared StudioStorageError definition to the leaf studio_private module,
explicitly re-export it from studio_submissions. This avoids the actual private/submission/
generation/upload import cycle. Preserve exception catchers and check deserialization of
the old module-qualified test-only pickle captured before edits. New private directory and
atomic-text helpers belong in that same storage module, not another producer graph. Reuse
existing native Windows helpers; do not change global atomic_fs behavior or its callers.

Affected production symbols: PrivateSqlitePath constructor; SubmissionStore constructor,
connections and work_dir namespace validation; all UploadStore I/O; handler upload/source
preparation routes and server upload initialization. Actual test caller families are complete
upload, generation, submission, queue and prior billing/private suites. Embedded second-process
queue programs remain genuine and are inspected separately from LSP string limitations.
Source/test module map and WIP ledger are frozen before full canonical collection.

## Sequential Implementation Unit

Add failing native shared-root, hardlink/alias, metadata/transfer cleanup and outbox-loss
regressions first. Add genuine private inline fixtures without changing existing assertions.
Create/check only private missing leaf directories, private single-link files and stable
namespaces. Metadata writes use exclusive mode-0600 staging and fsync/atomic replace, refuse
unsafe existing targets, and clean only the newly owned temporary identity. Upload staging
is private; reads and atomic publication validate scoped roots/members. Failure cleanup
must never unlink through a substituted namespace or remove another identity. Retain actual
committed media after response/ticket failure so the original guarded recovery still works.

SubmissionStore uses mandatory PrivateSqlitePath around opening/commit/close; missing main
or changed root/main refuses without an empty replacement, token loss or false dispatch.
Keep actual schema, identity/conflict, rollback and DBOS two-database/concurrency behavior.
Protect/validate its artifact namespace without inventing worker/publication authority.

Web import no longer creates upload state in shared checkout work/uploads. Initialize new
private upload storage explicitly at server startup, with local root override and unchanged
upload ceiling. Default Windows root is LocalAppData/HawEditStudio; POSIX is home/.hawedit-studio.
Preserve original historical jobs/media and old uploads; do not chmod/move/adopt them. Bare
unconfigured handlers refuse instead of silently choosing public storage. Storage faults
produce actionable contextual refusals. HTTP identity, jobs/checkpoint/DBOS/trust/session
storage and real protected worker adoption remain required; this unit cannot enable paid work.

Run complete affected groups, native probes where available, fast checks and exact full gate.
Preserve intermediate failures, source/runtime/hardware/file hashes and actual decoded-media
evidence. Do not flip T3 or any milestone without green gate plus current required CI.

## EARS And Named Regressions

- PS7: WHEN an upload root/member is unsafe or replaced, THE studio SHALL refuse before
  reading/writing/publishing outside its bound private namespace.
  Tests: test_studio_upload_shared_root_is_preserved_and_refused,
  test_studio_upload_linked_ticket_is_preserved,
  test_studio_upload_container_replacement_refuses.
- PS8: WHEN transfer failure follows namespace substitution, THE studio SHALL preserve
  unrelated original bytes and SHALL NOT acknowledge a runnable source.
  Test: test_studio_upload_failure_cleanup_cannot_follow_replaced_staging.
- PS9: WHEN private metadata is atomically written, THE storage SHALL retain actual
  owner/access policy and refuse unsafe prior targets without altering their bytes.
  Tests: test_studio_private_atomic_metadata_is_private,
  test_studio_private_atomic_metadata_refuses_linked_target.
- PS10: WHEN submission storage is lost/replaced, THE outbox SHALL refuse without
  recreating the main file, losing the token or fabricating dispatch confirmation.
  Tests: test_studio_submission_missing_database_is_not_recreated,
  test_studio_submission_shared_root_is_preserved_and_refused.
- PS11: WHEN old module-qualified storage errors are restored, THE system SHALL retain
  public catcher compatibility without a circular import.
  Test: test_studio_storage_error_preserves_legacy_pickle_and_catchers.

These are implementation contracts, not whole-studio security, authenticated authority,
Linux canonical-gate, model/provider readiness or frozen independent acceptance claims.

## Actual Container Finding And PS12

The pre-repair native test `test_studio_upload_refuses_mismatched_container` failed
with real MPEG-TS bytes submitted as `.mp4` (T3-storage-container-test-first.log).
The existing demuxer whitelist already refused the tested external HLS playlist;
that negative test is not evidence of a newly reproduced external-file leak.
Narrow both actual probe and first-frame decoder demuxer whitelists to the declared
supported suffix and check the returned format aliases. Preserve genuine decoded
uploads for all seven supported suffixes. This implements the approved supported-
container upload contract, not a complete media sandbox or codec security certificate.
Primary technical reference: [FFmpeg format options](https://ffmpeg.org/ffmpeg-formats.html#Format-Options).

- PS12: WHEN media bytes use a container incompatible with their supported filename,
  THE studio SHALL refuse a runnable source while preserving original external bytes;
  WHEN a supported container decodes, THE studio SHALL retain the exact uploaded bytes.
  Tests: test_studio_upload_refuses_mismatched_container,
  test_studio_upload_refuses_external_playlist_container,
  test_studio_upload_accepts_actual_supported_containers.

- PS13: WHEN upload storage is unconfigured or lost, THE HTTP API SHALL report storage
  unavailability without recreating public state or returning a runnable source.
  Tests: test_studio_http_unconfigured_upload_storage_refuses,
  test_studio_http_lost_upload_root_refuses_without_recreation.
- PS14: WHEN the native server starts, THE studio SHALL initialize privately at the
  local configured/default root and finalize actual uploaded bytes there.
  Test: test_studio_native_server_uploads_use_private_startup_storage.
