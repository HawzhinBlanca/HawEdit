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
