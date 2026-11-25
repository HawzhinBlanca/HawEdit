# D-325: Rooted Copied Consumer Image

Status: design approved by Wareen, 2026-10-10; implementation WIP.
Extends D-323, not change BLUEPRINT
model policy or replace the local Python/vanilla/DBOS/SQLite architecture.

The actual installed configuration loader consumed replacement bytes after
normalization escaped descriptor custody. Current snapshot verification only
attests its copied root, not arbitrary normalized consumer pathnames.

Propose explicit private process-root preparation using original descriptions,
complete copied declared image, read-only proc kernel interface, read-only
root, zero capabilities and existing irreversible namespace fence. Preserve
data-only default; add explicit executable bits only for the image and finite
128GiB aggregate ceiling without changing default1GiB/per-file32GiB bounds.
Resource admission, complete real runtime/model closure and lifetime/effect
proof remain separate and mandatory before model release.

Reject widening mutable-backed path/bind allowlists, metadata-ready flags,
global Path.resolve monkeypatching, ignoring missing imports/ELFs, dropping
hash/single-link checks or rebranding a smoke test as protected generation.

Kernel calibration proves only that this route is possible on the observed
host. Implementation needs actual consumer, mutation, namespace/owner-death,
refusal and full exact gate evidence. General malicious same-privilege/process
memory/kernel isolation is not established by chroot and must not be claimed.

Actual libffi retains a read-only binary description for callback trampoline
tables. Require explicit copied executable bytes and same original-description
proof, then rebind that handle to its private copy with the original offset.
Never blindly close the native library's handle or allow arbitrary host paths.
Unknown/writable/inheritable handles and outside directories refuse. Readback
also rejects same-inode/new-description substitution. Full rationale is D-325
in DECISIONS.md; actual callback allocation is a regression, not model admission.
