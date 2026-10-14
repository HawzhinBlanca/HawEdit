---
commit: 5723617b80b1161ffaa910d6ee498b1a787e40ab
media_sha256: n/a (copied ELF/base interpreter diagnostic, not video or model inference)
host: HawaPC01, Threadripper3990X, Windows26300, host CPython3.12.10; WSL6.18.54.1-microsoft-standard-WSL2, trusted bootstrap Python3.14.4, copied base Python3.12.0
command: .venv/Scripts/python.exe -m pytest tests/test_rooted_worker.py tests/test_linux_joined_view.py tests/test_linux_prepared_view.py tests/test_linux_scope.py tests/test_linux_preparation_boundary.py tests/test_linux_bootstrap.py tests/test_linux_thread_registry.py tests/test_linux_thread_name.py tests/test_linux_snapshot.py tests/test_rooted_linux_image.py tests/test_rooted_kernel_entropy.py tests/test_rooted_wsl_gpu.py tests/test_claims.py --junitxml=C:/Users/Wareen/HawEditRootedWorker-final-20261014.xml
libraries: pytest9.1.1, ruff0.9.6, mypy1.15.0; no Torch/model import in copied Python diagnostic
status: WIP worker component, not production controller/model/producer or release acceptance
---

# Fenced Original Copied Worker

Approved launch-plan steps6--7, D-329. Source bytes measured in WIP are identical
to this code commit. Actual baseline9pair plus introduced6/7pair Serena maps and
hashes are in launch-impact-map.md. All report unchanged inspected sources.

Final affected cohort423pass/0failures/errors/skips,142.89s;JUnit142.341s.
Includes28new worker cases and67claims cases. Native original Scope before copy,
prepared/joined View, actual Snapshot and original registry are exercised.
Copied132byte ELF produces a real exec event and exit42. Exact existing copied
base Python3.12.0 executes a declared script under -I/-B, reports version and
checks genuine /proc caps/NNP/seccomp plus readonly root. Owner sees exactly
three null streams, original channel and copied executable before exec.
Worker/controller notification ordering uses actual libc opens, source registry
and genuine broker ADDFD; unknown targets/shapes refuse. All original members
are drained. No syscall-result/memory rewrite, test skip or assertion weakening.

Final XML SHA256:
ca6116b51686d15c25a2d6c69073f772116aa5a6cd92f8a47a0d94e7c3bd3e74.
Artifact: C:/Users/Wareen/HawEditRootedWorker-final-20261014.xml and matching log.
Source linux_snapshot.py SHA256:
10258fb04417019b391ba654085ddb26cf04e88dae0cf011c2c7f8cfc3f168db.
Source linux_rooted_worker.py SHA256:
ffb397ff0c375b6c4a9457ba87e590e4d68d027761168f01824e34c51dacece3.
Test test_rooted_worker.py SHA256:
f2ec997a2294e40fa4e58c141eb966c6eceb5fc7ebdb8bd53a02b71d71e94534.

Failure provenance, external HawEditRootedWorker-* logs preserved:
- Initial10cases fail for absent module; native initializer cannot reach Scope
  admission. This is missing-API red, not a successful namespace negative test.
- First implementation fixture forgot stat; four native cases fail before
  admission. Six command validation cases pass. Correct fixture import.
- Cold worker then genuinely refuses unknown ASCII codec after root entry.
  Materialize trusted ASCII/UTF8 codecs before the join; do not expose host dirs.
- Foreign-user negative fixture cannot open original worker ns/user after parent
  capability drop. Transfer the actual outside Scope's retained original user
  FD after copy instead; do not remove the negative case or relax permissions.
- Five controller cases expose ctypes prctl pointer truncation (EFAULT); bind the
  true native ABI. Then positive injection exposes distinct registry open flags;
  allow its exact anchored O_WRONLY/NOFOLLOW/CLOEXEC shape, not general writes.
- New module initially omitted README/ledger accounting; add initial WIP rows,
  not promotion. Existing claims suite catches both and passes after correction.

Fast lint/type405files and full405file formatting pass. Exact committed full
gate and applicable same-SHA CI still required; no row is promoted. Current
independent VEX source review has not been renewed/rebound or waived.

The controller is a native diagnostic fixture, not production typed Snapshot
adoption. Its ordinary CPU Snapshot already returns fenced; interim source
controller role is separately exercised by kernel broker fixtures. Complete
production controller ownership/final fence/all-member/result/billing drain
must still be integrated. The standalone entry relies on that outside owner
for execution lifetime/result limits; it is not model-release authority.
Only base Python/standard-library probe closure is copied, not complete Cortex
SDK, Torch/model/input/resources. No CUDA tensor, protected ASR, new ZAR reel,
native-editor/holdout/CI acceptance, publication or10/10 result is claimed.
