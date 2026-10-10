# Rooted Kernel Entropy Plan

Approved-by: Wareen, 2026-10-10, explicit "Approve the private entropy endpoint plan" reply.

This narrow T2 extension needs an explicit owner decision because the approved
copied-image boundary did not expose a kernel character endpoint. No new
installation, external service, model change or privileged host modification.

1. Preserve actual copied-Python failure and successful fenced getrandom probe.
   Research/EARS/current genuine caller map/proposed ADR/WIP ledger first.
2. After approval, test-first add an explicit rooted-only opt-in to LinuxSnapshot.
   Admit only the real original /dev/urandom character endpoint (major1/minor9),
   using no-follow read-only noninheritable original FD/description anchors.
   No caller-supplied device/path allowlist. Reserve its private path against
   declaration collisions. Bind only that original endpoint, never /dev or any
   host directory, before the existing irreversible capability drop/fence.
3. Remount that endpoint read-only/nosuid/noexec while leaving the rest of the
   image nodev/read-only. Verify original-description custody, actual private
   path device identity and effective mount flags; inability to prove any
   property refuses. Cleanup must not close substituted foreign descriptions.
   A read-only mount alone does not prohibit writing a character device. For
   this explicit read-only image opt-in, extend the existing x86_64 seccomp
   fence to refuse write/create/truncate opens via open/openat/creat and refuse
   openat2 (uninspectable flags pointer). Preserve read-only opens, the original
   namespace fence and data-only/non-opt-in behavior. Refuse preexisting writable
   entropy descriptions. Test actual syscall paths, not just mount metadata.
   Future SDK scratch/device needs remain explicit T2 work; never loosen this
   requirement silently to make an import run.
   Also refuse asynchronous io_uring setup/enter/register and retained ring
   descriptions for this opt-in, because async file opens bypass normal syscall
   entry. Do not change default non-opt-in contracts or claim host exploitation
   from source inspection alone.
4. Genuine copied-interpreter positive and deliberately damaged controls:
   default absence, opt-in startup/random reads, data-only/untyped/collision
   refusal, wrong or substituted endpoint, same-inode reopened descriptions,
   kernel mount/admission refusal, forbidden writes and unchanged source.
   Keep all134existing rooted/snapshot/bootstrap/scope cases and old assertions.
5. Run exact bash scripts/verify.sh after the source unit, reviewed local-only
   commit, clean committed verification and applicable same-SHA CI. Only the
   prescribed ledger script may promote a row. Independent current-package
   security evidence (#24) remains required; never self-rebind it.
6. Re-run the actual retained Python consumer, then continue T2's full real
   SDK/model/input closure, original controller/member/resource admission.
   No model/provider release from an entropy test or guessed readiness flag.

No source/test implementation until Approved-by is supplied by a trusted owner
reply. Other previously approved work/research can continue while awaiting it.
