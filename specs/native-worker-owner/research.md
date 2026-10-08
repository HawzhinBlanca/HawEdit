# Research

Baseline c898073a8d43372776e09e3ed7ad473c68f3415f,2026-10-08. Vault context:
HawEdit selected caption context repair2026-10-08 and worker containment experiments.
Approved evidence-based studio phases1-2; BLUEPRINT2-5/8.1-8.3, D-263/D-274/
D-305/D-306. No source changes during the preceding frozen caption gate.

Actual20 Serena definition/reference pairs at this SHA, every mapped source/
observer/HEAD/status unchanged: AppData/Local/HawEditEvidence/owned-producer-map-
c898073-20261008/serena-map.json SHA256
e474c3feab30a9d90aae1dff1808ab61f1a6ad2bc90d87741a96617bfc7a285f.
Host transport, execution reconstruction, OwnedStudioRuntime, AttemptStore
begin/append/finish, signed transport/effects, WSL ASR, shared pipeline, event
writer, queue and checkpoint admission mapped; private storage verify/open/member
methods also mapped. Existing native_process module/API does not exist.

OwnedStudioRuntime owns DBOS connections/threads and supervisor exclusion, not
native/Linux model lifetime. AttemptStore.finish releases the unique running
slot; it must not be called on a root exit or report before actual scope drain
and billed-effect reconciliation. Current finish callers are tests, not a
connected HTTP producer. Keep that API disconnected while ownership is incomplete.

Actual previous native/nested/parent-death probes retain original Windows process
handles; Linux/combined faults hold original pidfds and namespace FDs. See
C:/Users/Wareen/HawEdit-worker-lifetime-research-20261008.md for all raw commands,
hashes/failures/limits. Their results are not adopted production machinery.
HawaPC01/Windows11build26300/CPython3.12.10. Selected native launcher probes used
CPython3.11.15, not a claim of complete SDK/model readiness.

Use public suspended CreateProcessW, explicit STD HANDLE_LIST, non-inherited
private kill-on-close job and original creation handles. Existing Windows ACL
module establishes the ctypes loader/error style; do not add a third-party package.
Require an actual held executable read lease and expected hash before creation,
then compare actual process image before resume. Hash binding is not model/licence/
transitive-loader or owner authority. Job membership/accounting are live kernel
observations, not persisted PID/JSON capabilities. Never assign or kill the app.

New primary documentation check: PeekNamedPipe on a synchronous handle can block
in a multi-threaded process; do NOT advertise naive anonymous-pipe polling as
bounded DBOS output handling. Separate lifetime T1 from a correctly bounded IO T2.
Until T2 plus Linux original-capability ownership and worker/billing integration
are verified, the native lifetime component cannot enable generation.

References read2026-10-08:
[Jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[creation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw),
[handle list](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute),
[attribute allocation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-initializeprocthreadattributelist),
[pipe peek limits](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe).
WMI/service-created children and Linux processes are not universally contained
by a Windows Job; this is not a malicious same-privilege code sandbox.

Current qualified VEX #24/model metadata exception/owner cloud cap+scope+proof/
reviewers/independent corpus+studies/CI+sustained acceptance remain separate.
#1/#3/#4/#24/#25 open, #21 closed. No new permission/paid call/model run/publication.

## Real Shutdown Race

First new module collection failed while its implementation was absent. First
implementation26cases:23pass/3fail; actual descendant child scripts had an extra
closing brace. Corrected scripts and strict typing:25pass/1fail. The unchanged
launcher-exit assertion observed an empty job but the held descendant still
returned WAIT_TIMEOUT. Preserve both raw external JUnit reports; do not weaken
the original-handle assertion to accept job accounting alone.

Fresh actual correction23pairs and shutdown16pairs plus finalizer1pair map
unchanged source/HEAD/status. Add original observation-only handles for currently
verified native members; verify their signaling before returning wait/stop. No
PID-based kill/assignment or durable completion authority is introduced. Waiting
can refuse if a member disappears before it can be safely observed. Ephemeral
unobserved processes still require the complete protected producer resource
handshake; this T1 observer is NOT general all-descendant teardown proof.

Microsoft primary APIs reviewed again2026-10-08:
[termination](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject),
[original-handle wait](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject).
