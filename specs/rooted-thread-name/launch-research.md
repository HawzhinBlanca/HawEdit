# Typed Rooted Launch Research

Baseline1fe64a60caa9d6a74357b4d50852c19dfbd75cf3, clean source,
package5e9b82817aeb9d670e593754f4d94e6e4181aafce25ebbbfdf42194afed7dc55.
Previous goal turn was progress: production registry/broker and real driver
execution, not just test counts. Current goal still requires an actual high-grade
ZAR38 audiovisual result; no new reel/ASR execution is evidenced.

## Actual Boundaries

Actual16pair Serena map:
C:/Users/Wareen/HawEditRootedLaunchDesignMap-1fe64a6-20261013/serena-map.json,
SHAef2c09a571dbb0461824a28e6a848ea6f3066668e3838db4e56549012199b85f.
Snapshot constructor/outside descriptions/initialize/drop_caps/GPU policy/fence/
inspect; Scope admit/inspect/live; Bootstrap exec; WslOmniAsrProducer.transcribe;
asr_worker.run_request; owned studio launch; studio queue submit; live VEX gate.
Source/ref/status unchanged. Definitions and exact callers retained in artifact.

Snapshot initial admission requires zero effective/permitted/inheritable/ambient
caps and NNP, but deliberately excludes CapBnd from that early zero requirement.
_initialize establishes private user/mount view and UID/GID mappings; _drop_caps
is later, after exact file copies/mount setup/root transition. Current constructor
then enforces GPU Landlock and seccomp before returning. Forking a comm broker
after return inherits that write refusal. Do not add defer_fence or callbacks.

Scope._admit initially verifies direct original PID/user namespace relationships,
sender credentials/nonce/EOF and every original pidfd. _inspect later checks
original OFDs, not a complete new prepared namespace transition. That is not
permission to skip prepared-view verification. Rooted launch must authenticate
original PID1/PID2 before copy, then separately re-observe and bind their prepared
private view through original kernel handles before SDK release. No numeric
late discovery and no weakening of generic Scope admission/EOF rules.

WslOmniAsrProducer.transcribe currently builds a shared-directory request and
calls subprocess.run on the host-selected WSL interpreter/source. It is not the
new protected transport. asr_worker.run_request creates output/checkpoint files;
it cannot simply run unchanged in the approved readonly/no-scratch image.
Protected producer adoption must retain canonical adapter/validator/completion/
alignment contracts and publish/checkpoint via the owned host, not permit worker
writes or silently use this existing unprotected route. No such adoption yet.

Studio queue is pinned DBOS2.29.0/concurrency1 and takes a registered ID-only
workflow. OwnedStudioRuntime.launch owns DBOS machinery, not producer authority.
web.py expressly refuses generation while the protected producer is unconnected.
studio_host.capture_studio_deployment performs actual model/champion/runtime and
live VEX checks; receipts/affirmative flags cannot replace them. Current VEX
source differs and review expired2026-09-08. BLOCKED #24 remains unchanged.

## Preserved Failed Probe

C:/Users/Wareen/HawEditOriginalNamespaceJoin-1fe64a6-20261013 captures genuine
uid_map EPERM before the join or SDK challenge, coordinator72/root cleanup.
The prototype mapped UID0 and dropped all capabilities before creating its
second namespace; this differs from the production map-current-user/Snapshot
preparation lifecycle. Kernel rules additionally restrict mapping parent UID0
without appropriate CAP_SETFCAP provenance. No one-factor causal proof is
claimed; failure does not establish broken Snapshot or successful namespace join.
Do not patch its gate or run further diagnostics until this design is fixed.

Primary sources consulted2026-10-13:
https://man7.org/linux/man-pages/man7/user_namespaces.7.html
https://man7.org/linux/man-pages/man2/setns.2.html
Joining a descendant user namespace grants capabilities there; mount joining
requires appropriate target/current capabilities and unshared filesystem state.
Hence only trusted pre-fence bootstrap may join exact original prepared handles;
drop all caps and refuse every subsequent setns/unshare before copied SDK exec.
These are design constraints, not measured feasibility/admission results.

## Approval Reconciliation

registry-plan.md approves typed stopped-worker integration but does not spell out
this pre-preparation owner handoff and pre-SDK private namespace transition.
Record that transition explicitly in launch-plan.md with Approved-by:pending;
ask narrow approval before changing production symbols. Existing registry/broker/
root/entropy/GPU approvals and all independent admission obligations remain.

## Read-Only Closure Preparation While Approval Pending

Actual selected existing base/SDK inventory and critical binary identities are
recorded in launch-closure.md. No SDK import or further namespace diagnostic.
Python loader/base layout and Torch/NVIDIA relative DSO tree were observed
with trusted static readelf2.46, not inferred from successful import. Complete
copy/input/resource admission and fresh fenced execution remain separate.

## Approved Preparation Work, 2026-10-13

Owner explicitly approved "Approve the typed private-view handoff plan".
The prior pending statements above preserve their historical observation time.
Current source unit adds only the original pre-copy preparation check; D-329.
Fresh four-pair Serena map is recorded in launch-impact-map.md, source unchanged
during mapping. require_preparation_ready has no existing production caller.

Linux v6.18 primary pidfd UAPI defines GET_MNT_NAMESPACE as 0xFF03 and
version-zero GET_INFO with64bytes. The kernel fills PID/credential mask bits
even when not requested; the implementation still requires both bits. Query
results refer to the original pidfd target, but can become stale after return:
https://raw.githubusercontent.com/torvalds/linux/v6.18/include/uapi/linux/pidfd.h
https://raw.githubusercontent.com/torvalds/linux/v6.18/fs/pidfs.c
Hence this additive check is point-in-time and never a reusable release token.
Prepared-view proof and final launch policies remain RT2A/RT2B work.

## RT2A Prepared-View Witness

Baseline2065b078ae30b4b65fc1e4dc5452e95c96ca857a. The approved original
preparation check is present, but no prepared-root witness or producer adopts
it. Fresh nine-pair actual Serena map:
C:/Users/Wareen/HawEditPreparedViewMap-2065b07-20261013/serena-map.json,
SHAabac3fa7f26efa620e98a741cd1775186fe99e998261aa26d258f72e0e15b326,
unchanged inspected source/status. Includes exports, Scope/preparation member/
guard/liveness/creator and kernel identity helpers. Caller impact below.

Primary Linux sources rechecked2026-10-13: pidfd.h GET_MNT/GET_USER/GET_PID;
ioctl_nsfs type/parent/owner relationships; proc_pid_root documents that root
provides the actual target mount view and requires READ_FSCREDS access:
https://raw.githubusercontent.com/torvalds/linux/v6.18/include/uapi/linux/pidfd.h
https://man7.org/linux/man-pages/man2/ioctl_nsfs.2.html
https://man7.org/linux/man-pages/man5/proc_pid_root.5.html
Do not substitute host directory names for that view. Original pidfd-derived
task directories must be captured before preparation, retained and rechecked.
Failure to observe the genuine root/namespace is refusal, not permission bypass.

Implementation under approved launch-plan: additive LinuxPreparedView retains
baseline original task/root/mount descriptions before any preparation release.
A separate original anonymous SEQPACKET channel carries only a fresh nonce and
three SCM_RIGHTS (private user, mount, root), actual original PID1 credentials
and sealed EOF. Generic Scope admission/EOF behavior stays unchanged. Namespace
types/direct child/owner binding, fresh original PID1 pidfd observations, actual
chroot/cwd, new readonly tmpfs root, genuine readonly proc for original PID1 and
still-stopped original PID2 are checked. Independent OFD anchors detect later
substitution, including same-inode reopening. Repeated verification is required;
no boolean, path, callback, namespace-joining or executable grant is exposed.
Thirty-second maximum bounded observation; all rights/queries accounted for.
Close preserves substituted foreign slots and reports uncertain cleanup.

This observer does not prove complete manifest bytes, final worker fencing,
Landlock, resources, copied-runtime execution or model admission. Root proof is
one component of RT2A; trusted typed RT2B must perform and re-observe the original
worker join with all protections before any SDK execution. No approval expansion.

Source implementation now preserves original FD witnesses and re-observes the
genuine prepared PID1 view. Stronger actual controls reproduced two source
defects: post-preparation PID1 could gain a second thread without rejection,
and restoration of a substituted slot erased prior uncertainty. Both are fixed.
Real RLIMIT_NOFILE pressure then reproduced two leaked delivered rights when
the first anchor allocation failed; all delivered rights are now collected
before adoption and pending originals closed even on failure. Reports retained,
no syscall mocking or modified production response. Original Scope lineage
predicate extracted unchanged for shared PID1 verification. WIP remains.
# Joined-Worker Observation Refinement, 2026-10-13

Approved launch-plan RT2A step 6 still lacks outside-owner re-observation after
the original held worker joins the prepared view. Implement this missing check
before Snapshot adoption. It is observation only, not a fence/exec grant.
Use the retained original pidfd/task/root descriptions; require exact prepared
user/mount/root/cwd, original PID/parent/credentials, stopped single-thread NNP
worker and zero effective/permitted/inheritable/bounding/ambient capabilities.
Keep verify_prepared's original unjoined contract unchanged. Failures are sticky.
Real kernel fixtures exercise setns/chroot/capability drop and damaged transitions.
No SDK, model, cloud call, Snapshot return change or release-authority claim.

Actual seven-pair Serena map at unchanged a530ab2:
C:/Users/Wareen/HawEditJoinedViewMap-a530ab2-20261013/serena-map.json.
