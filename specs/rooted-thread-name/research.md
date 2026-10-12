# Private Driver Thread-Name Research

Research state, 2026-10-11. Wareen explicitly approved the narrow broker plan;
T1 kernel feasibility is now in progress. Source base:
94d4639b148b41ab76e9236662b61e47464daeb2, package
4b5e3ae91d0e73ee49e6ba08adaac04dd4db2380337dcf0fcc3e8c9126f293e8.
Parent decisions: D-325 rooted image, D-326 entropy, D-327 private GPU;
BLUEPRINT sections 2, 3, 5 and 8.1-8.3; BLOCKED #24/#25 are not waived.

## Observations, Not Success Claims

The actual copied torch 2.8.0+cu128 consumer cannot initialize CUDA. Smaller
private Python 3.12.0 / genuine CUDA implementation / DXCore probes isolate
the failure without another full SDK image copy. Genuine /dev/dxg 10:258 opens
O_RDWR. Libraries load. cuInit returns 304; no GPU device/tensor/model result.
All original root/config substitution, entropy, capability and drain controls
remain active. Observer exit zero means the diagnostic captured a refusal.

Host: HawaPC01, Windows 26300, host Python 3.12.10, WSL 6.18.40.1,
Landlock ABI 7. No cloud calls, installation, publication or policy edits.
Raw roots below are under C:/Users/Wareen, not synthetic test fixtures.

| Experiment | Actual Result | Raw Terminal SHA256 |
| --- | --- | --- |
| HawEditPrivateCudaLogs-20261011 | cuInit 304; memory log only repeats that status, 97 bytes; observer 3.375s | 8a870371a93f75af94dcca0de592a753a6b961245b5197e01f28e307f99bf2a0 |
| HawEditPrivateCudaCpuInput-20261011 | Genuine copied 0-63 CPU-online data; still 304; 2564 files/515425863 bytes, observer 3.391s | fbe68b14c049b73c5e14c1aaa3a3b10bd777091da46a934a5ec1bb29a57d4341 |
| HawEditPrivateCudaTrace-v3-20261011 | 341 events/two original threads, comm open 0x241 -> EPERM; no GPU ioctl; observer 3.688s | 1a0be8fc69a5fce1f98bd1dc25db4ec0536c365d3d84a6f0d65ec7ff9431c33c |
| HawEditPrivateCudaTrace-v4-20261011 | Bounded 256-byte original stack; insufficient driver return addresses; observer 3.640s | 0a8b32f2742d9576b4151a9737aeeef34a08d5e39ba3a4576ce2e8e19ed1c2f8 |
| HawEditPrivateCudaTrace-v5-20261011 | Bounded 4096-byte original stack contains driver 0x33cc6e/0x12edcb4 return addresses; observer 3.609s | a1c9ffa51285f6f0349d9abd69f8eb2974fa5574d36b28c52817b667b0b3d65b |

Trace v3 preparation initially selected a short predicate literal as a helper
and raised IndentationError before execution. The selector was corrected;
the preparation defect is not a kernel result. Original prior scripts/results
remain intact. No tracing operation changes syscall results or policy.

## Identified Compatibility Conflict

The original driver thread calls openat on /proc/self/task/3/comm using
O_WRONLY|O_CREAT|O_TRUNC (0x241). LinuxSnapshot._fence intentionally refuses
creation/truncation. Proc is also readonly and Landlock grants no proc writes;
removing just the seccomp check is neither sufficient nor an acceptable fix.

Actual vendor library SHA256:
b0fc5b0c2265e2a81c6c8b39983ee9ff163628f5448c157c95c7901b4cb075b6.
HawEditCudaThreadNameCallsite-20261011/observation.json SHA256:
07bbefbc43f27dee3ea1989e0f3343c4cc18092deb0530fd9fc7acf60d388484.
Read-only installed readelf/objdump show executable virtual and file offsets
coincide. At 0x33cc69 fopen returns at observed 0x33cc6e; NULL branches to
0x33ccb6 and returns -1. Caller at 0x12edcaf returns at observed 0x12edcb4;
nonzero branches to 0x12edc0b, preserving initial ebx=0x130 (304), storing it
at 0x12edc23. This supports this refusal as an initialization-stopping cause.
It does NOT prove that fixing it suffices for GPU or model initialization.

CPU topology alone does not repair it. Harmless TCGETS2 failures on proc
status/maps are not GPU ioctls. No writable scratch, general proc write,
driver patch, environment disable flag or invented successful operation is
proposed.

## Kernel Constraints On A Narrow Fix

The candidate is a genuine original-task comm descriptor broker, not a model
endpoint or broad file service. A successful response must inject an actually
opened kernel FD; never return a fabricated fd/status or CONTINUE after merely
checking a mutable user pathname. Original worker reads/executes immutable
inputs and keeps readonly proc/root plus mandatory Landlock.

Seccomp notifications support atomic ADDFD+SEND. Pointer data must be copied
before deciding, and aborted notifications require bounded failure handling.
[Linux seccomp documentation](https://docs.kernel.org/userspace-api/seccomp_filter.html).

Kernel comm writes require the writer and target to be in the same thread
group; a separate controller cannot itself perform this write. The worker must
write its own genuine injected descriptor. This is a design constraint, not
yet tested feasibility on the installed kernel.
[WSL kernel comm implementation](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.18.y/fs/proc/base.c).

Landlock checks open rights separately from later writes. Pre-opened/injected
handles therefore represent additional authority and must be admitted narrowly;
adding a later ruleset cannot relax an existing one.
[Linux Landlock documentation](https://docs.kernel.org/userspace-api/landlock.html).

An open original proc descriptor does not act on a new task after PID reuse.
Admission still needs original controller/member and namespace identity, not a
numeric PID, process name, status Boolean or freshly rediscovered path alone.
[Linux proc documentation](https://docs.kernel.org/filesystems/proc.html).

## Actual Symbol Map

Installed Serena 1.7.1.dev0 LSP, six definition/reference pairs at unchanged94:
C:/Users/Wareen/HawEditRootedGPUCompatibilityMap-20261011/serena-map.json,
SHA256 ffc4121de1821c0123f9cb01463e8a61adcecfeacad1ee1d5c498ffaa51a9741.
See impact-map.md. There are no source edits in this research unit.

The exact clean gate at this base remains 6179 passed/1 VEX failure/zero
errors/skips, exit1. The old source binding and September 8 expiry are preserved.
Wareen appointed Codex technical lead; our author/owner assessment is internal,
not independent security review or VEX renewal. No task DONE/CI/10/10 claim.

## Supplemental Original Lifecycle Research

Installed Serena ten-pair supplemental map SHA256
47ca2e95e65d6231cbd45e69874cf716d1f71f8a8ed79ba2795de945cb436210,
HawEditRootedBrokerLifecycleMap-20261011, unchanged94/package4b5. Inspect the
actual calls in impact-map.md. Static zero refs for generated entrypoints do
not establish absence of callers.

Existing __init__ applies mandatory Landlock/fence in the original PID1 before
forking an SDK consumer. A broker forked afterward inherits the same restrictions
and cannot obtain the needed write handle. This is an additional feasibility
constraint. The new design must prove an independently bounded trusted original
controller in the private namespace/root, with only its narrow original proc
authority, before proposing minimal integration. No deferred/unchecked worker
release or broader proc/scratch exception has been implemented. Original scope
uses genuine pidfds, namespace relationship ioctls and independent description
anchors; a newly rediscovered PID/status cannot substitute for those controls.

Fresh host canonical adapter identity, obtained with existing _open_adapter_bundle
without deserialization, is retained separately in
C:/Users/Wareen/HawEditChampionBundleIdentity-20261011/observation.json,
SHA256 acca6aac8c5f3b199b0aeea6b0de6e65eaaea5144e97205f763c5399d10b5bef.
Three members/79,861,281bytes; fingerprint
dfa6237a3b287b7ca6ef88d848a3540ffbf052f8900bd88e99b5e3495d65809d.
HawaPC01 Windows26300/Python3.12.10, identity1.485s/observer2.219s. It fills a
missing host identity inventory, not private copying, trusted pinning, model
lease/load, resource reservation or a GPU admission claim.

## T1 Real Kernel Feasibility

Wareen approved the narrow plan. A real WSL 6.18.40.1 calibration succeeded
without changing product source, driver or model state. A parent controller
receives a genuine seccomp NEW_LISTENER over an original UNIX SOCK_SEQPACKET
channel, copies at most128 bytes from the real worker notification, checks
openat/x86_64/AT_FDCWD/0x241 and the exact `/proc/self/task/<tid>/comm` string,
opens only its matching live original worker leaf, and atomic-ADDFD_SEND injects
the genuine descriptor. The worker's open returned FD4; a real10-byte write
changed its own kernel comm to HawEditT1. No continuation/fabricated response.

Raw v13 C:/Users/Wareen/HawEditThreadNameBrokerT1-v13-20261011 observation
SHA256 632ea60b281539c5a88c2255f4c078c7e268797d784f63b46d7ecbe0a0f08349;
stdout SHA256 58e990e56262b96c3ed10d6c599393d37519524ca735a829c8e67f1f010d0601;
worker114867/TID114868/FD4, observer5.437s. Host HawaPC01, Windows26300,
host Python3.12.10, WSL6.18.40.1. This is feasibility only, not private-root
Landlock integration, CUDA/model/producer/video proof.

Preserved v11 uses non-atomic ADD+SEND and is ineligible for implementation.
Initial v12 atomic failure was a probe constant error: header SEND is bit2,
while bit1 is SETFD. v13 uses the actual header definition and succeeds.
T1 negative/custody calibration and source tests remain; full gate remains
independently red6179/1 for VEX.

## Private-Root Negative Integration, 2026-10-12

An uncommitted, subsequently removed implementation experiment exercised the
approved narrow design against the real rooted WSL GPU harness. The external
atomic proof above remains valid. It does not transfer unchanged into the
private worker: an outer controller cannot `ADDFD_SEND` across the new user
namespace (`EINVAL`); a sibling controller with its own original task handle
can receive the listener but its attempted atomic injection also returns
`EINVAL`. The normal worker `/proc` is intentionally read-only (`EROFS`) and
must not be widened merely to satisfy this call.

The experiment was removed rather than leaving a partial kernel boundary in
the product. `tests/test_rooted_wsl_gpu.py` passed 38/38 afterward using the
checkout venv on HawaPC01. `bash scripts/verify.sh --fast` passed afterward.
This is not a full-gate or CI result; the known VEX policy failure remains.
No source, runtime, model, driver, worker root, cloud, spending, or ZAR output
was changed by this negative investigation. The next research unit must prove
why this kernel rejects the exact `ADDFD_SEND` operation under the rooted user
namespace and supply a same-SHA positive and refusal corpus before any new
production integration is proposed.

## Corrected Kernel Matrix, 2026-10-12

> [!WARNING] Contradiction
> The negative integration above attributed `EINVAL` to crossing the user
> namespace. Fresh isolated tests disprove that attribution. Preserve the
> failure itself; its integration cause remains unidentified.

At unchanged source `94d4639b148b41ab76e9236662b61e47464daeb2`, an actual
14-case calibration succeeds on HawaPC01, Windows 26300, host Python 3.12.10,
WSL 6.18.40.1, Landlock ABI 7. Baseline, nested user namespace, zero capabilities
and Landlock each permit atomic `ADDFD_SEND`. A dedicated original controller
also succeeds inside a fresh user/mount/PID namespace, with controller PID1,
worker PID2 and target TID3, an immutable private root, read-only proc, all five
capability sets zero, and controller network creation refused. The worker's
actual 10-byte write changes its independently read kernel comm to `HawUserns`.
The controller holds the original worker pidfd and checks kernel namespace
relationships, then uses its pre-remount anchored original task directory;
no general proc write rule is added to worker Landlock.

The corpus includes actual refusal of foreign controller paths, extra flags,
wrong dirfd, another proc leaf and 128-byte unterminated pathnames. Each returns
kernel EPERM, injects no FD and leaves the target comm unchanged. Listener loss
returns ENOSYS without rename. Original pidfd SIGKILL and observed exit make
both ID_VALID and atomic ADDFD_SEND refuse with ENOENT. A real pathname mutation
after the bounded copy still renames only the anchored original target; no
CONTINUE is used. Every private mount disappears on original scope exit and
the empty backing directory is removed.

Raw preserved code/results:
`C:/Users/Wareen/HawEditThreadNameUsernsMatrix-v8-20261012/`.
Observation SHA256 `1e5433c7f8bf24b18cfc1c51ea968a8cd4138a49d9a9fefb7f90425ecd419b26`;
stdout SHA256 `b23264bb45bbf26fa79f31f4d07905396f285ef36c98882779ed3ebdea1bbe77`;
probe source SHA256 `642eee0b39c479eead6157298efe29ac6340851a49798ff0f5775e286b6d4a0d`;
observer 0.672s. Earlier v1/v2/v6 probe defects are retained. v1 escaped newline
characters incorrectly; v2 sampled uid after unshare; v6 incorrectly expected
the child user namespace to equal its parent and let a failing child's packet
send unwind into the coordinator. v7 corrects those observer defects.

These measurements prove feasibility and the stated challenge outcomes. They
do not prove production controller integration, forced numeric PID reuse,
descriptor replacement, request/thread budget exhaustion, stronger-filter
precedence, actual CUDA/Torch, model admission, ZAR output or release quality.
The previous full-gate VEX failure and lack of same-SHA CI remain. T1 stays WIP
until the remaining contract coverage and required verification are recorded.

Kernel source inspection supports checking ioctl ABI/flags/state before
attributing EINVAL to isolation. The installed calibration, rather than a
branch-tip source page, establishes the measured kernel behavior:
https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.18.y/kernel/seccomp.c

## Committed Gate And Helper Correction

Local-only e243f66da8c7008f17d5b0de7bffd984b90862a5 records the first kernel
regressions. Exact `bash scripts/verify.sh` completed on HawaPC01 in 4365.61s:
6184 passed,7 failed,3 errors,1 warning. The source was held unchanged throughout
that run; `.gate/last-test-run.xml` was written only by the gate. Captured log:
`C:/Users/Wareen/HawEditThreadNameGate-e243f66-20261012.log`.

One new defect is owned by this unit: a literal test helper was placed in
scripts/studio_research, whose existing scope test permits exactly its named
historical tools. Move that literal helper to `tests/thread_name_kernel_probe.py`
and update its only dynamic loader; retain the original exact scope assertion.
Actual installed Serena three-pair map before that edit, unchanged e243:
HawEditThreadNameHelperMap-e243f66-20261012, SHA256
ed8b4ac8c8581b0bc076feadc89c3a8067f207958890abf3d811456c215d77d3.
The new kernel_matrix fixture and KERNEL_CODE definitions/callers, and existing
scope-test definition/callers, were mapped. No production symbol changes.

Other fresh failures are preserved: four wheel-build outcomes refuse the
pre-existing untracked `specs/openchatcut-assessment/research.md`; that unrelated
owner file remains untouched. An inherited audit stream exceeded2s, two NVENC
probes timed out at30s, empty-file ingest exceeded2s, and checked-in VEX still
binds old source81f6 rather than current package4b5. No assertion, threshold,
fixture, review expiry or policy binding is changed to manufacture a pass.

## Actual Vendor Request Shape

Captured unmodified vendor trace v3 shows syscall257 from main worker TID2,
requesting `/proc/self/task/3/comm`, flags577(0x241), mode438(0666). Its preserved
stdout SHA256 is c2473c4b570ce5a63fc9980bc90e662c97ebabe9eac3db5ccd1707189b2f5dbe.
The initial own-thread/0600 calibration is valid kernel feasibility but is not
the actual vendor contract. The approved plan permits only another live
original thread in that same registered worker; it does not require requester
and target TIDs to coincide. Foreign groups remain refused.

An additional actual libc `fopen("w")`/fwrite/fclose calibration on unchanged
e243 reproduces the vendor shape in private PID1/worker2/target3. Atomic FD4
injection lets main2 write12 bytes and independently measured target3 becomes
VendorShape; main2 stays python3. Root/proc remain readonly, both capability sets
are all zero, worker LandlockABI7 remains active, and private mounts disappear.
Raw HawEditThreadNameVendorShape-e243f66-20261012 observation SHA256
e2e45f94fd803610c32d26639cc66c266942ae481521cd57707b32c5c566cdd2;
stdout4dfb94c161e1b25a33893cc58ce8b1b9d3df6925aebd010ad8d60712eae4f4e1,
observer1.500s. Native Python3.14.4/glibc2.43/WSL6.18.40.1, hostPython3.12.10/
Windows26300. This is libc/vendor-call-shape proof, not actual cuInit, copied
Python3.12.0, Torch, model or producer success. Add a named regression alongside
the existing own-thread controls; do not weaken those controls.

The helper correction retains the existing exact historical-tool scope test.
The new helper lives under tests and now covers15 real kernel cases, including
the actual other-thread/0666 libc request. The kernel/research-scope/GPU caller
cohort exits0 (79 instances), and lint/mypy remain green. The untouched owner-
requested OpenChatCut research note was reviewed and preserved in a separate
local-only f239cae commit to address clean-build refusal; its bytes remain SHA256
6011046817ee058a19dd924cf08b86f6e07c475687198a390b00629a34ba7d68.
This preservation is not integration or licensing approval for OpenChatCut.

The original e243 canonical gate XML is copied without alteration to
C:/Users/Wareen/HawEditGateEvidence-e243f66-20261012/last-test-run.xml, SHA256
7b733605b9dcda6e0d241f319f39da522168b02b873680120584b17c6f512fd3.
Only the gate generated that report. Source/runtime/model/producer promotion
remains unproven; the actual owned controller integration is the next unit.
