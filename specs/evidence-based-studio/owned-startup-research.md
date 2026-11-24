# Owned Startup Research

2026-10-03. Clean baseline80d6091329071ae281be1532c661002d793279c1;
producer49c71aa17cab05876d03299a9ff984f3ce2874bb7c4996e97a9c3aad9841d356.
Previous goal turn: implementation progress and a complete exact gate,4698passes/one
VEX source-binding failure/zero errors/skips,2069.16s. Preserve that result and BLOCKED24;
it does not prevent this approved T3 integration. No source edits before this map/plan.

Vault: HawEdit raw admission and NUL projection checkpoint2026-10-03, project canon
and parent approved plan. Extend BLUEPRINT sections2-5, D-263/D-274/D-276/D-277;
do not replace AC-1-AC-12 or independent/sustained acceptance.

## Actual Pinned DBOS Source

Installed DBOS2.29.0 _dbos.py _sys_db.py _sys_db_sqlite.py _queue.py _event_loop.py
_core.py _dbos_config.py _utils.py inspected read-only. Native CPython3.12.10/SQLite3.49.1.
No model, provider, deserialization probe, licence acceptance or publication here.

DBOS is process-global and silently preserves first configuration. Launch starts executor
and event loop, creates SystemDatabase, runs migrations, registers application version,
then submits pending recovery before queue/poller/scheduler threads. A listen_queues filter
is not a global pause; the internal queue is special. Portable config cannot override a
persisted py_pickle tag; the existing separate inspector is not later-read fencing.

SystemDatabase.create accepts an actual custom engine and marks created_engine=False;
destroy does not dispose it. The default SQLite factory supplies IMMEDIATE transactions,
busy_timeout30000 and foreign_keys ON; a custom engine must restore reviewed behavior.
SQLAlchemy autobegin alone does not prove native SQLite DDL/read transaction ownership.
Use explicit BEGIN IMMEDIATE so bootstrap DDL and later admission share actual transactions.

DBOS.register_queue requires a DBOS instance; offline SystemDatabase.upsert_queue takes
explicit reviewed scalar policy and update_existing=False. Queue constructor installs the
in-memory serial queue before launch. Existing valid persisted queue must not be overwritten.
Offline actual publisher initialization is allowed only for a verified empty journal;
existing nonempty schema is inspected before migrations/getters. New bootstrap schema40
is admitted before launch. Never treat arbitrary older/foreign schema as an upgrade grant.

Registry maps contain workflow wrappers and <temp>.step wrappers, plus queue/class/instance
and poller/Kafka registrations. DBOS constructor adds its fixed TEMP_SEND_WF_NAME wrapper;
launch adds internal queue and dynamic scheduler. Allow only captured owned objects and
the exact known runtime additions. Raw journal rejects internal/temporary workflow rows.
Refuse foreign instance, workflows, classes, instances, pollers, queue policy and ambient
DBOS cloud/version/executor overrides before touching DBOS. Disable admin/OTLP explicitly.

DBOS._destroy calls executor.shutdown(wait=False,cancel_futures=True), stops event loop,
then joins background threads with individual timeouts. Its return does not prove no live
worker. Capture actual executor/event-loop/background threads, stop scheduling, drain under
a finite caller deadline, and retain lease/engine if work remains. After quiescence destroy
only the captured owned instance and dispose the owned engine. Never destroy a foreign
singleton or remove foreign registrations/records. Close/retry must remain visible.

## Native Lifetime Lease And Same-Connection Admission

Reuse owner-private path/member checks. One permanent empty lock member per journal root,
opened without truncation and locked nonblocking with msvcrt on Windows or flock on POSIX;
do not delete it on release. Verify path and descriptor identity, access and root before
use. Kernel releases lease on process exit; inode substitution/permissions refuse rather
than repair. This is cooperative single-owner exclusion, not hostile-same-user isolation.

Own the SQLAlchemy engine with rw URI (never recreate a lost main database), NullPool,
native SQLite creator, explicit transaction event and private/binding fences. Extract
shared raw validation onto a caller-owned SQLite connection without commit/rollback or
query_only changes. Require the exact main database and no attachments/temp schema;
caller owns its transaction and progress handler. Owned engine fences before each DBOS
statement and commit using that same native connection. No second-connection snapshot
can replace this protection of uncommitted/in-flight rows or subsequent ORM reads.

Bounded inspection remains a row/encoded-byte/VM elapsed budget, not absolute RSS/I/O
deadline or cross-database atomicity. Keep canonical schema, portable JSON, NUL checks
and immutable outbox validation unchanged. No output is replay/publication permission.

## Scope And Next Adoption

This unit actually adopts raw inspection in an owned DBOS launch/lifecycle, exercised by
isolated inert subprocesses, restart and dispatch. It does not inject a paid runner into
HTTP or imply producer readiness. The next required ID-only worker must reconstruct exact
source/config/runtime/model/signed-authority/billing/attempt policy through shared builder;
then immutable revisions and authenticated exact-byte review/export. Canonical ASR remains
write-once. Real-model and independent evidence obligations remain, BLOCKED1/3/4/21/24/25.

Actual15-query Serena LSP map completed at this baseline; log/JSON retained. One _identity
query includes its function and PrivateDirectory's instance variable; imports use the
actual function. File-scope reference fallbacks are recorded, not hidden or inferred.

## Counterexamples And Reviewed Corrections - 2026-10-04

Native row/text callback factories can execute before validation. Same-connection API now
requires the exact native connection, str text decoder and absent/native Row factory before
any query, while retaining the caller's existing transaction, VM handler and PRAGMAs.

Pinned get_internal_queue creates/replaces its Queue on every call. Admit only its exact
known idle scalar policy and class; refresh its captured object without relaxing the fixed
studio queue identity. TEMP_SEND_WF_NAME is defined in _core. Class properties are not
methods. Initial setup failures are preserved separately from unsafe decoder counterexamples.

A genuine trace-coordinated second thread can install DBOS between the initial singleton
check and constructor. Before recording ownership, verify unique serializer, registry and
actual configured engine identities plus not-launched state. Refuse the returned foreign
singleton without listening filters, destruction or registry cleanup against it.

Owned native busy_timeout5000 and five-second inspection deadline intentionally differ
from the generic factory's30000ms. Pinned db_retry retries arbitrary errors containing its
lock phrase. Wrap native OperationalError without that phrase to expose bounded refusal,
not endless lock retry. No changes to generic CLI behavior or installed dependencies.

During draining a new dispatch is refused, retains reserved immutable identity and now
records its storage diagnostic. A failure of that diagnostic write must itself surface.
CLI lifetime controls use the real documented file-backed database: :memory: had a distinct
installed-library pool-argument failure, not a demonstrated studio defect or a claimed fix.

> [!WARNING] Contradiction
> Vault Decisions/Durable Execution via DBOS in HawEdit describes every pipeline stage
> as transactionally checkpointed and exact failed-stage resumption. Current durable_workflow.py
> wraps a coarse pipeline step; process death can re-enter that step. The real pending
> inert job restart expects two invocations, not exactly-once effects. Artifact checkpoints,
> billed-call reconciliation and publication idempotency remain separate required adoption.

These observations are local mechanism evidence, not arbitrary source/model readiness,
creator workflow, publication quality or sustained acceptance. Preserve all failed runs.

Official https://docs.dbos.dev/python/tutorials/workflow-tutorial re-read2026-10-04;
general last-completed-step recovery guidance supports the coarse-step distinction. The
live site includes3.0-era APIs: installed2.29.0 source and actual tests, not newer examples,
define this unit's signatures/behavior. No runtime/model upgrade inferred from live docs.
