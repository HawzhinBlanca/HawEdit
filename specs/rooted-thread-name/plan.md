# Original Worker Thread-Name Broker Plan

Approved-by: Wareen, 2026-10-11, explicit "Approve the narrow thread-name broker plan" reply.

This is an additional narrow kernel capability under D-327, not covered by the
existing readonly entropy/fixed GPU approval. Codex takes technical lead;
Wareen retains architecture/release ownership. No independent qualification
is inferred from that appointment.

1. Preserve current red CUDA evidence and real caller map. Freeze the EARS
   tests/ledger. Record a proposed ADR after approval, without modifying
   BLUEPRINT, VEX dispositions, fixtures, thresholds or existing failures.
2. T1, sequential test-first kernel feasibility. Demonstrate a dedicated trusted
   original controller, with zero capabilities, no network and private immutable
   root, can supply an original live worker-thread comm FD through a genuine
   seccomp listener. Worker proc/root remain readonly and Landlocked. No general
   host directory is exposed. Use original scope/member/namespace custody and
   anchored proc task descriptors; no re-discovered PID-only authorization.
3. Copy at most128 pathname bytes. Accept only observed open/openat operation,
   AT_FDCWD, exact /proc/self/task/<TID>/comm spelling and the required0x241
   flags (allow CLOEXEC only when requested). Target must be a live original
   thread of the registered worker, never controller/other process. Open the
   existing anchored kernel comm leaf O_WRONLY|O_NOFOLLOW|O_CLOEXEC without
   creation or truncation; verify procfs and original leaf/task custody. Inject
   only that genuine FD with atomic ADDFD+SEND, no fixed replacement fd and no
   CONTINUE. The worker's real write updates the real kernel thread name.
4. Calibrate listener/notification ABI and actual same-thread-group behavior
   before source integration. Preserve cancellation/stale-ID outcomes. Bound
   feasibility at64 original threads,32 admitted opens,30seconds and64KiB
   evidence. Unknown flags/path/target, uncertain identity, task exit/reuse,
   listener loss or exhausted limits refuse and drain the original scope.
   No fake rename success. If this mechanism cannot satisfy the boundaries,
   retain its failure and STOP this design for a separately reviewed decision.
5. T2, only after T1 proves feasibility, extend existing LinuxSnapshot narrowly
   with a typed default-off broker contract. Install notification handling before
   the conflicting errno fence; a notification cannot defeat a pre-existing
   stronger seccomp result. Preserve all default/GPU/entropy/root/namespace/FD
   refusals and map every changed helper before editing. A trusted controller
   outside worker Landlock needs explicitly limited original proc capability;
   implementation must prove that capability is not handed to SDK/model code.
6. T3, run actual vendor driver initialization, then actual copied Torch tiny
   tensor. Neither exit0 nor a driver FD is admission. Observe actual devices,
   finite allocation/readback and original cleanup. Preserve any new refusal;
   no automatic extra endpoint/scratch/JIT/runtime/model-policy change.
7. Run whole affected cohorts, exact bash scripts/verify.sh and reviewed
   local-only commit. Do not forge a green gate by rebinding expired VEX. Only
   prescribed ledger script after green gate AND applicable same-SHA CI.
8. Continue parent T2 model/controller/resource closure then T3 protected DBOS
   producer and fresh ZAR evaluation. This unit itself cannot authorize model
   deserialization, production, publication, licences, spending or a10 verdict.

No dependency installation, host kernel/driver patch, cloud call, increased
US$5 scope/cap, writable scratch directory, push or publication. No blanket
writable /proc, task directory or arbitrary descriptor broker. Approval of this
plan does not predict that CUDA or the full pipeline will succeed.
