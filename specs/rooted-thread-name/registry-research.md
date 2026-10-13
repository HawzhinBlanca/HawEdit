# Original Kernel Thread Registration

Date2026-10-13. Baseline a1ccc7dc768eb4c6125b47657cfd159f527e1cfa,
package68ccf11b206e663eb58fe87109a27d46d71a19252f1a044cee56d71ea8e86a09,
clean native Windows checkout before this documentation. Parent: approved
thread-name broker, D-325/326/327, BLUEPRINT sections2/3/5/8.1-8.3.
BLOCKED24 qualified current review and25 acceptance are not waived.

Current kernel6.18.54.1-microsoft-standard-WSL2, host Windows26300/Python3.12.10,
actual installed worker Python3.12.0/Clang17, LandlockABI7. Sequential unchanged
kernel diagnostics repeat original registration and genuine CUDA readback:

1. HawEditOriginalThreadRegistration-a1ccc7d-20261013: kernel-created original
   tasks2/3 are anchored before resumption, exact target VendorShape changes,
   both traced tasks are reaped, original private mounts disappear. Exit0,
   observer0.672s, stdoutSHA
   c3a15713e2a000a09e2314c00391151195a20d50dac9dd58542749b5e5ce8fe0.
2. HawEditThreadNameCUDA-a1ccc7d-20261013: cuInit0, actual two3090Ti devices,
  16-byte allocation/upload/readback/free/context destruction all0, readback
   [1.0,-2.5,3.25,0.125]. Readonly private root/proc, zero caps, worker mandatory
   Landlock, original cleanup. Exit0, observer2.937s, stdoutSHA
   052f0e368739cec75870bda690c99134c47af7105b87d28bf594e9bfade0403e.

These prove different things. The CUDA diagnostic still enumerates tasks when
handling a notification; it is NOT the original-birth registry or production
admission. The registration diagnostic proves kernel clone-event anchoring but
does not run CUDA. Combine neither into a fabricated full-runtime/model result.
They use bounded diagnostic tracing only; production tracing remains unapproved.
The unchanged replay wrapper verifies original script digests and updates only
source/package identities and new evidence destinations, never protocol/limits.

Actual six-pair Serena1.7.1.dev0 LSP map of constructor/proc/fence/policy/inspect/
cleanup at unchanged source: HawEditThreadCommandMap-a1ccc7d-20261013,
SHA0c696a1ce2344bf9a4d5ede4a50c14b80b003529552590d4e3c07478cf6ed489.
Existing parent impact-map records callers. Embedded native run_case/worker
programs require actual AST/source inspection in addition to LSP symbol lookup.

The constructor applies Landlock/fence in PID1 before returning. Forking a
broker afterward cannot obtain its narrow writable comm capability. Do not add
an unfenced public preparation mode or arbitrary callback. Proposed integration
uses a typed bounded command and a trusted original controller: private bytes
and root first, then a stopped direct worker, kernel birth/exec registration,
mandatory worker policy/listener before SDK release, bounded event servicing,
and complete original-member drain. Default construction remains unchanged.

Only controller PTRACE_CONT/SETOPTIONS/GETEVENTMSG for original members are
needed. PTRACE_SYSCALL, memory/register modification, attach/seize/detach and
foreign targets are not needed and must be refused by the real kernel. Worker
bootstraps TRACEME only before SDK release; thereafter its ptrace/process-fork
authority is refused, while original same-group threads remain possible.
This is a new production capability/lifecycle decision, hence pending approval.
No install, new endpoint, extra cloud spending, model-policy change or publication.

## Combined Registered Driver Corpus

External research program probe_hawedit_registered_cuda_20261013.py combines
real kernel birth anchors with the actual copied driver, atomic comm-FD broker
and16-byte CUDA readback. It does not edit/import a new production component or
release ASR/models. Actual controller filter allows CONT without signal injection,
exact TRACECLONE|EXITKILL SETOPTIONS and GETEVENTMSG only. Twelve unapproved
requests/options/signals/addresses return kernelEPERM, and controller targeting
returns kernelESRCH. Worker TRACEME after bootstrap returns kernelEPERM.
No syscall tracing or memory/register rewriting occurs in this corpus.

All v7 runs use the current kernel/runtime above and original driver inputs
recorded in each stdout. Raw roots C:/Users/Wareen/HawEditRegisteredCUDA-v7-<case>-a1ccc7d-20261013.

| Case | Actual result | Observer seconds | Stdout SHA256 |
| --- | --- | --- | --- |
| positive | cuInit0, original tasks2-6 anchored/reaped, finite16-byte exact readback, root cleanup | 2.672 | 9a31f9ad12a0048e02b9881290d9888ab445d8fe26399aeba0190583442fd9ff |
| foreign | Actual fopen(/proc/self/task/1/comm,w) refusedEPERM/no descriptor; subsequent real driver/readback passes, tasks2-6 drain | 2.672 | 9fa4635e9483fdd8b12fbefbc64a7616f522164af1c58fa1cab6858b1f5c90be |
| substituted | Actual taskFD replaced by a different private controller task description; no injection; foreign handle survives registry cleanup, original worker killed via pidfd/tasks2-3 reaped | 2.297 | 0d9ca97637c823e23e148ceaa3e8c2661a1f8f4680dc9413a1a7312534b2ab68 |
| reopened | Actual same-inode reopened task description refuses via description custody, not inode equality; no injection, foreign handle retained, original tasks2-3 drain | 2.234 | f248ec7a2d458712a054d28bea955c1ebc5e50e13c5ad35fcd178496f7cc8812 |
| stale | Original pidfd kill and complete trace-member drain precede genuine ID_VALID/ADDFD_SEND; both returnENOENT2, no descriptor, tasks2-3 drain | 2.312 | a442e2ffac89fc1219d39a2c0ffb516fd325477fff3d9d697ec7251c34dfd423 |
| listener-loss | Both original listener descriptions close; genuine driver cuInit304/CUDA_ERROR_OPERATING_SYSTEM, no tensor/readback claim, tasks2-3 drain | 2.281 | dc8550e832bc9ac24a501c2d1a2f879f331dedc78067307214252c2f4b0da919 |

Every observer/native coordinator exits0 in these v7 cases, original source/
package/status unchanged, private mounts removed. Negative worker exits-9 are
expected original-pidfd refusal drains, not successful CUDA initialization.
Preserve earlier failures: v1 invalid filter branch refusedEINVAL before CUDA;
v2 mistakenly treated already anchored child startup as a reused number;
v4 substituted challenge tried O_NOFOLLOW on /proc/self symlink and refused
before substitution; v6 stale cleanup referenced a substitution-only variable.
All raw observers, partial reports and actual failure evidence remain intact.

Additional actual11-pair Serena lifecycle map before source edits:
HawEditRegistryLifetimeMap-a1ccc7d-20261013,
SHAb06b9e1798097cb446be93f98b18668d1d7dcf8e3932073bc3683203f0856ca7.
These are diagnostic measurements, not named production regressions, completed
ledger rows, fresh copied Python/Torch, model/resources, DBOS/HTTP adoption,
ZAR output, qualified security review, CI, publication or10 acceptance.

## Approved Component Implementation, 2026-10-13

Owner explicitly approved the original-thread registry plan. D-328 records the
boundary; earlier pending statements are historical, not a renewed permission
question. Actual helper map SHA2bb5acdb9b90dee7ddd8a5b80fb8b903eabd1020f9ee89dd6c03a1c932aebba0,
new component map SHAda3137e2e1b00d0001f8061c0f1820c56b6468a4b5fb721f5408710108b8bd41
precede corrections. Definitions/callers and unchanged source hashes retained.

Test-first:16 failures before the module existed. First real implementation
exposed readonly proc winning before the calibration's Landlock check. The
test setup now enforces/observes Landlock before sealing the root, then performs
TRACEME. Next exposed glibc clone3 requiring the existing ENOSYS contract rather
than EPERM. Thread clone flags are whitelisted, including explicit rejection of
UNTRACED/PTRACE escapes; process forks remain kernel-refused. A controller-side
comm write correctly returned EINVAL. Positive now executes actual libc fopen,
copied request validation and genuine ADDFD_SEND; only the original worker
performs the write and the task's measured name changes. No fabricated success.

Production registry real-kernel cases cover kernel birth anchoring, foreign/
unregistered targets, different-task and same-inode description substitution,
closed primary slot, live deadline, budget refusal/cancellation,15 forbidden
ptrace forms, seven worker authority refusals, sealed actual exec(exit42) and
eight concurrent native thread births. Kernel6.18.54.1/WSL2, host HawaPC01/
Windows26300/Python3.12.10/pytest9.1.1; this is not media quality or ASR evidence.
Final whole registry/thread-name/Bootstrap/Scope/Snapshot/rooted/entropy/GPU
cohort235passed in91.94s. Exact --fast passes lint/mypy397files, NOT full gate.
Raw logs C:/Users/Wareen/HawEditRegistry-{red,first,second,third,fourth,fifth,
sixth,cohort,cohort-corrected,final-cohort,fast}-20261013.log retain failures.
Initial cohort command named nonexistent files and ran no tests; corrected
whole cohort is the cited result. No tests/fixtures/thresholds are weakened.

Default Snapshot remains unchanged. The new production registry is not yet
connected to the typed command or protected producer; fresh copied interpreter/
Torch/model/input/resource/owner admission and new ZAR reels remain unfinished.
Full clean committed-source gate and applicable CI remain required; the expired
VEX policy and all WIP rows are unchanged. No model/cloud/publication was run.
