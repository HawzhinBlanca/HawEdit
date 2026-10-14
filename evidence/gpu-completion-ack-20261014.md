---
commit: 75f3a58fa9b9135d0daf6d51a3590f2e5d5a572d
media_sha256: n/a (real native copied controller and acknowledgment fault tests)
host: HawaPC01 Threadripper3990X Windows26300 CPython3.12.10; copied CPython3.12.0 WSL6.18.54.1
command: .venv/Scripts/python.exe -m pytest tests/test_rooted_controller.py
libraries: pytest9.1.1 ruff0.9.6 mypy1.15.0
status: WIP; authenticated native diagnostics pass; no canonical gate/CI, CUDA or ASR claim
---

# Authenticated GPU Completion

Header identifies baseline; subsequent ordinary test/record correction only.
Production package remains030ce9d4fe881dddde8ede55ecafc1f3ae2d2f1be1925143eab51b06050d164d.
Actual Serena current _controller_run and callers before edits, unchanged source:
C:/Users/Wareen/HawEditGPUAckMap-75f3a58-20261014/serena-map.json,
SHA25607a809969ed6db8b29ae0727b628b69bc597e068908662d4279dcca4828dc036.

Verification gap: null stderr is required by GPU descriptor isolation but hides
late init failures. Original parent merely observed worker exit and could falsely
pass even if init died before final confirmation. Actual native init exit73
reproduces a false pass; new refusal regression first fails DID NOT RAISE,
3.49s. Red XML C:/Users/Wareen/HawEditGPUAck-red-20261014.xml,
SHA2566b7eae3281d0fffea8646d96121d498cb76ef19ddd584998d800e6ce52a333b8.
This is real process death, not mocked syscalls or a simulated timeout.

Exact in-flight75f3a58 gate cancelled for correction by verified actual pytest
child37968 created2026-10-14 18:32:43 local, full matching gate argv. No Ctrl+C,
console-wide signal or unrelated process stopped. Session terminates exit1.
No fresh completed JUnit exists; never reuse old XML as its result. Cancelled
log C:/Users/Wareen/HawEditGate-75f3a58-20261014.log,
SHA256e9950e42a2d12b1995f728c14cb8cb9a2fa7b7f5a6becf9bbcf81c593421de74.

Fixed test fixture uses a separate original unnamed SEQPACKET pair through
existing exact control_fds rules, not a new production grant. Original init
acknowledges only after all actual result/denial/drain/final Snapshot assertions.
Parent requires exact case-bound bytes, flags and original init SCM_CREDENTIALS
derived from held Scope custody. Worker receives no acknowledgment channel at
exec. Real premature init exit73 and corrupt final frame are both refused.
Original CPU/GPU comm/device/final-policy checks remain, not weakened or skipped.

Authenticated first module26passed21.22s; added real corrupt-frame case then
complete thirteen affected kernel/adapter modules336passed157.25s. Raw
C:/Users/Wareen/HawEditGPUAck-callers-20261014.xml,
SHA25641b39a31b3d1523366aba1c610a22914da226ec65d00ab8142556fffeec67207.
Exact --fast passes lint/strict409files; not the full gate. Earlier unacknowledged
GPU green observations retained with explicit warning, not accepted as final
GPU proof. Current source full gate and required CI remain required. No ledger
promotion, qualified VEX renewal, model import, inference, caption/reel or release.
