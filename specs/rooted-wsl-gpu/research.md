# Private WSL GPU Boundary Research

2026-10-11, local93d1c3e8c2c4a4d642c577f1af9ab57e2be5817d,
packagef9c3871bb6cd3d32cff0203f8d222b78bce61ed0fc965cfe64a5efe8aefabc6e.
BLUEPRINT §§3,5,7,8.1-8.3; approved rooted-linux-image T2; D-325/D-326;
BLOCKED #24/#25. This proposed extension is NOT covered by entropy approval.

## Actual Evidence

The original CUDA diagnostic expired without a consumer result and masked its
cause with unbound ready. A new external shared900s diagnostic recorded actual
39623-file/8654184337-byte inventory at519.3946576829767s, then copy deadline
refusal. Nine real Linux seqpacket controls pass; progress never means readiness.
Original failures and all old drivers retained. No production source changed.

A separate finite1800s complete diagnostic passes at the unchanged package:
inventory198.64289057801943s, copy663.2634903150029s,
native868.7878916949849s, observer869.3500059000216s. Timings: HawaPC01,
Windows26300/Python3.12.10; retained Python3.12.0/Clang17.0.1,
WSL6.18.40.1, torch2.8.0+cu128, transformers4.57.6. Sequential observations,
not a controlled cold/warm benchmark or creator-performance acceptance.

Actual GenerationConfig.from_pretrained(local_files_only=True) still reads
private beam1 despite outside config replacement2. Seventy mapped private files,
32 genuine entropy bytes, NoNewPrivs1 and zero capability sets checked. Actual
torch.cuda.init attempted with CUDA_VISIBLE_DEVICES=0, /dev/dxg absent; RuntimeError
reports no NVIDIA driver. CUDA stays uninitialized. This does not identify the
exact failed driver syscall, prove a missing host installation, or authorize a
new endpoint. No model weights, VRAM reservation or producer adoption verified.

Raw C:/Users/Wareen/HawEditRootedFullBudgetCUDA-20261011:
stdout SHA816af4e24fc61f7c0b9a928571444aa0460c58660815829b9ace704265f8b906;
terminal SHA61ee0dafe47c7f1b69df378c933248a651b177d09d053a6a3f0717a045053034.
Original scope drained; exact attempt root absent after strict cleanup.
Complete SDK manifest e94858d0f775a00c163a39486c9900082407e32bba69db12298c4d0b6c2e5563.
All resource/model/full-image/adoption admission flags remain false.

## Actual Callers And Constraints

Fresh installed Serena1.7.1.dev0/LSP finds nine definition/reference pairs at
the current SHA, unchanged watched files. Map:
C:/Users/Wareen/HawEditRootedGPUMap-20261011/serena-map.json,
SHA d828ac727685a681ac6fbc56015f5635cfde06a4e4270a8ee8fcbf0934f7f518.
Adjacent impact-map.md lists the actual callers; dynamic constructors inspected.

LinuxSnapshot._fence denies write-access opens globally for kernel_entropy.
Merely adding a device path cannot demonstrate compatible CUDA access. Actual
driver open flags have not been traced; do not claim O_RDWR was observed.
Snapshot already owns original-description anchors, private read-only/nodev
root, exact copied executable handles, zero capabilities and namespace fence.
Extend this behavior narrowly; never loosen entropy or default data-only policy.

Earlier metadata-only query observed Landlock ABI7 (not an installed policy),
and genuine /dev/dxg character identity10:258 (not opened/exposed). Revalidate
on the actual worker. No Landlock enforcement, device access or GPU allocation
has occurred in the private diagnostic.

## Primary Research

[Microsoft WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq) describes
/dev/dxg as routing to the Windows GPU, so exposure adds a host driver surface.
[Kernel Landlock documentation](https://docs.kernel.org/userspace-api/landlock.html)
describes leaf write/device-ioctl controls, inherited-policy behavior, and the
exemption for descriptions opened before restriction. ABI7 lacks thread-sync;
enforce while the existing initializer is single-threaded, before SDK imports.
[NVIDIA WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) warns
against installing a Linux display driver in WSL. No new installation is proposed.

Landlock is a candidate extra kernel layer, not a proven sandbox or substitute
for original FD custody, resource reservation, actual native controls or #24
qualified driver/runtime review. Proposed policy/implementation in plan.md.

## Approved Implementation Chronology

Wareen explicitly approved the private GPU isolation plan2026-10-11. Actual
metadata recheck: WSL6.18.40.1, ABI7 errno0, dxg character10:258 root-owned
mode0666 single-link in the host namespace. This is metadata, not inference.
Native test-first missing API22fail/1default positive. New fixed original O_PATH
device, copied private image and mandatory Landlock leaf controls now WIP.
Namespaces remap host-root UID0 to65534; Bootstrap already enters that namespace,
so host ownership must not be inferred from worker-relative UID. Original
device/type/no-follow/single-link/description checks preserved. Acquiring after
mount cloning (D-326) resolves actual EINVAL cross-namespace bind refusal.

36 native GPU controls pass, including actual copied fresh Python exec,
entropy O_RDWR EACCES and valid GPU O_RDWR, threads/fork, non-GPU ioctl denial,
real outside abstract socket (working parent positive), SCM_RIGHTS recvmsg
refusal, unavailable-policy syscalls, substituted/same-inode-reopened handles.
Then whole snapshot/rooted/entropy/GPU cohorts120pass/0fail/error/skip,
JUnit59.067s/observer60.276502799999435s on HawaPC01 Windows26300/Python3.12.10,
pytest9.1.1/ruff0.9.6/mypy1.15.0/dbos2.29.0, working package3a05e9ae5032ab38924ad00f288608de589807df616148f75b3ca67d7617857c.
Raw AppData/Local/HawEditEvidence/rooted-gpu-cohort-20261011:
XMLdbf22b9ea0e4bdae945f4fa1a7bfe91b48eed9fb4c5d6e890b42d015961588db;
stdout1a5e18c7a3a0d5bb05d1fe066cdcaca545405c0987300a5883b086af43208f9d.
Repository-wide --fast lint/typecheck390files passes; NOT the full gate.
Additional actual nonblocking-control regression then reproduced wrapper-state
gap; kernel F_GETFL correction plus fresh cohort/full gate required. Original
120-case result is not retroactively evidence for this later correction.
All source/fixture/golden/enforcement/VEX old evidence preserved, no test skips.
No CUDA allocation/model run/resource or producer adoption, cloud calls/spending,
installation, same-SHA CI, authenticated review, publication or10claim.

Final control correction:38 new GPU cases and84 existing cases all pass in
the four whole-file cohorts,122pass/0fail/error/skip. Separate actual kernel
nonblocking flag-at-acquisition and changed-original-flag regressions each
first reproduce admission, then refuse after F_GETFL checks at both boundaries.
Copied fresh Python exec remains an actual positive/negative control, not an
empty test. Final working package4b5e3ae91d0e73ee49e6ba08adaac04dd4db2380337dcf0fcc3e8c9126f293e8,
JUnit59.777s/observer61.11980990000302s, same recorded host/tools above.
Raw AppData/Local/HawEditEvidence/rooted-gpu-final-cohort-20261011:
XML84e5e2a12c3c12f70da506d2ac1e00d8e8dcec995899a55a35c7ed14d8d4dba2;
stdout5ec0fb67489cd9f5b3b78c5488f9edde04daa643161bc24ec4b561095d1dd260.
Exact --fast passes390files, format390files and git diff --check pass. These
are not the full gate; reviewed local-only commit/clean full verification next.
