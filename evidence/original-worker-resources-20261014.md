# Original Worker Kernel Limits, WIP

Baseline15915027a9da2857dc8b6cabaa1e827cd8bca4f1. Approved PA2/D-329 unit;
BLUEPRINT sections2-5,8.1-8.3. No producer or editorial acceptance claim.

Hardware HawaPC01; canonical CPython3.12.10 AMD64, pytest9.1.1,
ruff0.9.6/mypy1.15.0. Actual Ubuntu WSL kernel
6.18.54.1-microsoft-standard-WSL2; copied existing CPython3.12.0. No installation.

Actual four-pair Serena map, unchanged source:
C:/Users/Wareen/HawEditWorkerResourcesMap-1591502-20261014/serena-map.json,
SHA256150f21955b070f84805b706ba40d6528004bae959a3e3adeea9592c8e64cfa75.
Research/callers/EARS: specs/protected-asr-producer/worker-resource-research.md.

Test-first19 failures in6.11s establish missing implementation. Raw
C:/Users/Wareen/HawEditWorkerResources-red-20261014.xml,
SHA2568b2d5b5630b3e012ad1469554e4ea17de1b1f4388e8071afcb50e3d278f3f0c0.
Initial implemented cohort46pass32.89s. Final12 caller modules334pass188.84s,
0failures/errors/skips. Command: canonical .venv/Scripts/python.exe -m pytest
tests/test_worker_resources.py tests/test_rooted_controller.py
tests/test_rooted_worker.py tests/test_linux_scope.py tests/test_linux_prepared_view.py
tests/test_linux_snapshot.py tests/test_rooted_linux_image.py
tests/test_rooted_kernel_entropy.py tests/test_rooted_wsl_gpu.py
tests/test_rooted_gpu_controller_policy.py tests/test_linux_thread_registry.py
tests/test_linux_thread_name.py --junitxml=C:/Users/Wareen/HawEditWorkerResources-callers-20261014.xml.
Raw XML SHA2569415bd723624a960bc5d4c0c8871c4a09cb66e3b8415d5c196fd2b3df8df68e5.

Genuine copied original worker reads back equal soft/hard128MiB RLIMIT_AS,
3s RLIMIT_CPU,64 RLIMIT_NOFILE and0 RLIMIT_CORE after exec. Raising each hard
limit fails; an original second thread sees the same limits. Actual256MiB
allocation raises MemoryError; descriptor exhaustion returns EMFILE. Separate
actual busy loop reaches kernel SIGKILL; original registry reaps TIDs2/3 before
final authenticated completion. CPU and GPU cases pass final Snapshot inspection;
GPU retains exact original-init acknowledgment/credentials. No mocked syscall,
transcript, model response or fabricated timing establishes this evidence.

Opt-in diagnostic ceilings64MiB-8GiB address space/1-30 CPU seconds/64-4096
descriptors. Default resources=None and existing30s/64KiB/4096files/64births/
32requests unchanged. Limits applied after capability drop, before copied exec;
trusted copy verification is separately bounded, not preparation-memory guarded.
No controller/shared limits, privileged cgroup change, writable root/proc or new
dependency. AS is virtual memory, not VRAM or an owned GPU effect guard.

Native Git Bash exact fast command passes lint/strict typecheck410files, not
full gate. Initial unqualified Windows bash selected WSL and refused a CR-suffixed
Windows lock pathname; retained raw log HawEditWorkerResources-fast-20261014.log
outside repo. Installed C:/Program Files/Git/bin/bash.exe avoids that shell
mismatch without gate modification or interpreter override. Full gate pending
at this recording. No DONE/ledger/CI claim.

PA3 actual five-pair unchanged map:
C:/Users/Wareen/HawEditCheckpointTransportMap-1591502-20261014/serena-map.json,
SHA256da1884f99f30a0bd198a47ee89f2c5f86f2ba306051ea51f1344ed7bfa0d4449.
Existing private/fsynced OperationJournal and final transcript are worker-written;
they cannot run unchanged in readonly root. Mapping is not transport implementation.

No complete SDK closure/CUDA tensor/model inference/producer/checkpoints/ZAR
reel/publication proved. Independent VEX remains expired/source-mismatched (#24).
NVIDIA WSL guide inspected2026-10-14 documents limited NVML queries:
https://docs.nvidia.com/cuda/wsl-user-guide/index.html#features-not-yet-supported.
Global GPU memory and allocator settings do not prove owned VRAM/effect drain.
