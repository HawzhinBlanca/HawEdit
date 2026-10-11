# Private WSL GPU Extension Plan

Approved-by: Wareen, 2026-10-11, explicit "Approve the private GPU isolation plan" reply.

This adds a new kernel endpoint and unprivileged Landlock policy. Prior rooted
image/readonly entropy approval did not authorize GPU exposure; the owner has
now explicitly approved this extension. Map/test before sequential source edits.
No installation, privileged host change, cloud scope/spending increase, push or
publication. /dev/dxg routes into the Windows GPU driver; risk is not zero.

1. Preserve actual deadline failures and new completed private SDK/CUDA refusal.
   Revalidate actual mapped symbols/callers and live kernel/device metadata.
   Record the architectural ADR in DECISIONS.md only after owner approval.
2. Test-first extend existing LinuxSnapshot with a default-off, rooted-only typed
   GPU option, requiring genuine readonly entropy and mandatory kernel policy.
   Admit only fixed genuine /dev/dxg10:258 through original no-follow O_PATH FD/
   anchor custody. No caller device/path allowlist or host directory exposure.
   Reserve dev/dxg against file/directory collisions. Unknown, writable, inherited,
   substituted or same-inode-reopened descriptions still refuse.
3. Bind only that original endpoint into the private read-only image; verify
   identity/mount policy while retaining original root/proc/capability rules.
   Before SDK import/GPU I/O, apply unprivileged Landlock with required ABI>=6
   rights/scopes. Handle write/create/truncate/remove/refer/device-ioctl actions;
   grant image read/execute and GPU-leaf read/write/device-ioctl only. Entropy
   remains read-only, including reopen via proc-FD routes. Preexisting descriptors
   are not retroactively restricted: admit only proven originals, keep GPU
   custody O_PATH (no I/O), and make runtime I/O opens after enforcement.
4. GPU mode alone may replace the global open access-mode denial only AFTER
   successful leaf enforcement; never globally allow writes on an assertion.
   Preserve create/truncate/append, openat2, io_uring and namespace/clone fences.
   Deny new non-AF_UNIX sockets and scope outside abstract-UNIX access/signals;
   reject foreign retained sockets, while preserving original control channels.
   Fail closed on unavailable policy/rights or uncertain enforcement. Existing
   default/data-only/entropy-only behavior and every old test remain unchanged.
5. Actual native positive/damaged controls: original device identity/substitution,
   O_RDWR/reopens, entropy/regular-file write and device-ioctl refusal, fork/exec/
   threads, async syscalls, policy failure, root/member/FD drift, external-network
   refusal and safe original-only cleanup. Trace actual CUDA requirements rather
   than adding speculative devices/scratch/libraries. Any further host endpoint,
   directory, writable scratch or installation requires a new owner decision.
6. Full existing cohorts/static/format, reviewed local-only commit and exact clean
   committed bash scripts/verify.sh. No test skip/golden change/harness weakening.
   Only prescribed ledger script after green gate AND applicable same-SHA CI.
   #24 qualified current driver/runtime VEX review remains independent; never
   self-rebind/renew. Native tests alone do not authorize production admission.
7. Tiny bounded actual CUDA tensor/synchronization probe with configured existing
   runtime, original config-substitution/root/bytes proofs and failure recording.
   Canonical model/ZAR execution only AFTER T2 complete model/source/input closure,
   genuine reserved resources and original-controller/member lifetime proof.
   Then T3 protected DBOS/HTTP, actual reviewed revisions/export and unchanged
   editorial/native benchmark/reliability/AA/performance/30day sign-off obligations.

## Proposed ADR

Use a default-off fixed private GPU endpoint plus mandatory unprivileged leaf
policy to preserve entropy/file protection when runtime device opens need write
access. Retain copied-byte/root/original-FD/namespace controls as independent
layers. ABI metadata, GPU presence, is_available, small tensors or config loading
are never model/resource/worker admission. No permissive compatibility fallback.
