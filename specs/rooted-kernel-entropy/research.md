# Rooted Kernel Entropy Research

2026-10-10; source2fa571038af8c79677f1a12214be9836be1e2b46,
package532a8b6db1cfaac876e0a02b681ef61bac0bd4a605e58a96e501d4e8380eadad.
T2 of the approved rooted-linux-image plan, BLUEPRINT sections2-5/8, D-325.
No new source/test edit. Kernel device exposure is a separately proposed
boundary extension, not silently covered by a copied regular-file declaration.

## Actual Retained Interpreter Consumer

The real retained Python3.12.0/Clang17.0.1 copied its separate uv interpreter,
stdlib, observed native dependencies and a private test JSON input through
LinuxSnapshot. 2561 explicit files,486679890bytes, bounded512MiB/6000files.
The private root transition, zero capabilities and namespace fence succeeded.
Outside original input was replaced with num_beams2; private input retained1.
Re-execution of the actual copied Python then failed before consuming JSON:
_Py_HashRandomization_Init could not obtain random bytes.

Within the same fenced private root, actual libc.getrandom returned32bytes;
the kernel entropy call was not blocked. The retained build reports
HAVE_GETRANDOM=0, HAVE_GETRANDOM_SYSCALL=0 and HAVE_GETENTROPY=0; os.getrandom
is absent. /dev/urandom is not present in the private root. This isolates the
failure to the retained interpreter's device-based entropy path, not a reason
to relax seccomp or disable Python hash randomization.

Raw original diagnostic, unchanged true, native1/controller2.6574929999769665s:
C:/Users/Wareen/HawEditRootedPythonConsumer-entropy-proof-20261010/terminal.json,
SHA256fd526f78aae020ee602bda46bbc65a05f2bd85d2738ecfcf2fc3f9f12774d7aa.
stderr SHA256033120777a503fcf9417d5df5ad9b03852404d81116bb97c30c2f92498038b05.
Host HawaPC01 Windows26300/Python3.12.10, WSL kernel6.18.40.1/glibc2.43.
This is bounded consumer research during a concurrent gate, not performance
acceptance, a complete SDK/model image, resource reservation or production
controller/member lifetime. No model/GPU import/inference/cloud/publication.

Earlier prototype failures are preserved: unavailable portable os.pidfd_open
wrapper (corrected using the existing real libc pattern, no identity guess);
opaque consumer status (corrected by capturing the original worker stderr).
Their original terminal hashes are b5f3078325d9b4a63e704c4c1507162ae5e69eb509c8a1d7df041d2cf8be7dc3,
57f2ddc830a53fa8826fd0b73db247d048c19cfef0d3005068618fbb86193006 and
8a10dde7e05c727120e6525c2a7c15fe8c720713e5a099a64037d20e16f6b819.
No source, fixtures, assertions or approved checkpoint choices changed.

## Primary Sources

CPython3.12 bootstrap_hash.c uses conditional kernel entropy support and a
device path when those compiled capabilities are absent. That matches the
actual build/consumer observations above:
https://github.com/python/cpython/blob/v3.12.0/Python/bootstrap_hash.c.
The official Linux device registry assigns character major1/minor9 to urandom:
https://docs.kernel.org/admin-guide/devices.html.
These sources do not certify our endpoint mount/custody; actual positive and
damaged kernel tests plus independent security review are still required.

## Alternatives And Limits

Do not replace the pinned interpreter, rebuild/install it, disable entropy,
reuse a regular file of random bytes, inject an LD_PRELOAD shim or mount /dev.
Propose only an explicit opt-in, read-only, original-description-bound genuine
/dev/urandom endpoint in the private mount namespace. Preserve all default
data-only/rooted behavior when it is not requested. This is not permission for
GPU devices, other host files, cloud spending/publication or VEX self-renewal.
SDK/GPU access, complete copied closure and resource/lifetime admission remain
separate T2 questions. The US$5 transcript-only approval remains unchanged.

Actual current Serena16definition/reference pairs, unchanged true:
C:/Users/Wareen/HawEditKernelEntropyMap-20261010/serena-map.json,
SHA2564b64894133a40f5ed28785d28f8e585c8a218c0704580cf91a5f9f8c28c76bdc.
See impact-map.md. No source implementation before this extension is approved.

## Subsequent Approval And Read-Only Device Semantics

Wareen explicitly approved the private entropy endpoint plan on2026-10-10.
This supersedes the preceding pending implementation condition, not any
other security/model/device/publication prerequisite.

Linux6.18's inode permission code applies read-only filesystem write refusal
to regular files/directories/symlinks, not character devices; may_open treats
character devices separately. Therefore mount read-only metadata cannot alone
prove an unwritable entropy endpoint. Source inspected:
[Linux6.18 namei.c](https://github.com/torvalds/linux/blob/v6.18/fs/namei.c),
sb_permission/may_open. This informs the design, not a local kernel pass.

Preserve the existing namespace fence and add an opt-in-only read-only-open
restriction: deny write/create/truncate flags for open/openat, deny creat,
and deny openat2 because its pointer-carried flags cannot be inspected by
classic seccomp. Genuine reads and existing non-opt-in contracts remain.
Verify actual syscall refusals and reject preexisting writable entropy handles;
never chmod a host device, expose /dev, claim a read-only FD restricts reopening,
or remove these controls to make an SDK import succeed. The root is already
read-only; future private writable scratch is separate explicit T2 work.

Actual kernel negative control confirms this on WSL6.18.40.1: original genuine
character1/9 is opened read-only/no-follow, bound into a private user/mount
namespace, and remounted readonly/nosuid/noexec. Readback flags all hold, yet
O_WRONLY opens successfully. The control closes that descriptor without writing
any bytes or changing host-device permissions. Original namespace PID1 is
owned/drained by the unchanged bootstrap test helper; this calibration does
not invoke/admit a completed LinuxSnapshot or a model consumer.
JUnit `C:/Users/Wareen/HawEdit-video-rating-20261010/entropy-mount-negative-control.xml`,
SHA256 `ed2b12cf15336cb4c516162255d7e268171fa2cb7840295d178b689cad7f4bd4`,
one diagnostic pass in1.03pytest seconds at2fa5710 on HawaPC01/Windows26300,
Python3.12.10 controller/Python3.14.4 native kernel-test initializer.
External test `C:/Users/Wareen/probe_hawedit_entropy_mount_semantics_20261010.py`
retains the exact action. No source/test fixture mutation/model/provider call.

## Implementation Counterexamples Preserved

First test-first cohort:19cases/18red/1default pass. First implementation:
endpoint bind failed with actual EINVAL because its source descriptor belonged
to the pre-clone mount namespace. Move acquisition after private namespace
initialization, then anchor/bind the original description from that namespace.
No host-path allowlist, fallback mount or fence relaxation. The resulting
19cases pass, including direct syscall write-open refusals and foreign/same-inode
description substitution controls.

Expanded154case kernel cohort:153pass/1failure/0errors/skips,56.920JUnit seconds.
The failure is the new copied-interpreter closure: mapped libz's versioned path
was copied but its actual installed SONAME symlink alias was not flattened into
an explicit declared regular copy. Repair that calibration closure, preserving
all consumption/root/entropy/changed-parent assertions. All134old cases pass.
Raw reports remain under C:/Users/Wareen/HawEdit-video-rating-20261010.

Linux6.18 io_uring/openclose.c calls the internal file-open path for async opens,
not ordinary open/openat syscall entry. Inference: syscall-only write flags
cannot suffice if an asynchronous ring remains available. Opt-in must deny
io_uring setup/enter/register and reject retained ring handles; defaults remain
unchanged. Source inspected:
[Linux6.18 async open implementation](https://github.com/torvalds/linux/blob/v6.18/io_uring/openclose.c).
This source reasoning is not a demonstrated host async exploit or model gate.

## Implemented Local Evidence, Not Release Acceptance

The two actual async admission controls first failed (20pass/2fail), then both
passed after opt-in syscall denial and retained-ring refusal. No submissions,
write bytes, model inference or provider calls. Final156case kernel cohort
passes on the Windows-compatible capability-helper source;22new cases plus
all134existing cases,0fail/errors/skips,59.029JUnit seconds. Exact full gate
and same-SHA CI remain required. Original reports/hashes and limitations:
evidence/rooted-kernel-entropy-20261010.md.

The retained copied Python3.12.0 now actually re-executes successfully, reads
32genuine private entropy bytes and consumes the unchanged copied num_beams1
configuration despite outside replacement with2. All mapped paths match actual
private file device/inode identities; zero capabilities/NoNewPrivs/original
controller drain hold. Its SDK/model closure is still NOT admitted. Final
replay at package8f72c12069d99450de1624a30cf81162e24449966ac8ac1b2685b0e35d631ba3,
dirty baseline2fa5710, unchanged true, native0/controller2.6532081000041217s,
is a startup calibration, not performance acceptance or protected ZAR inference.
