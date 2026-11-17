# Linux Owner Protocol Unit

```yaml
commit: 49b2649106f04b232a5e22635ce3d1f9a0aaec7e
media_sha256: n/a - CPU protocol tests, no model inference or rendered media
host: HawaPC01, Windows11 build26300, Python3.12.10, pytest9.1.1, ruff0.9.6, mypy1.15.0, DBOS2.29.0
command: .venv/Scripts/python.exe -m pytest tests/test_linux_control.py tests/test_native_control.py tests/test_native_io.py tests/test_native_process.py tests/test_native_capability_retention.py --junitxml=C:/Users/Wareen/HawEdit-linux-owner-final-native-v2-20261009.xml
```

The cited commit contains the final exact module bytes. The five-module test
run preceded that commit on the effective package recorded below; it is not
relabeled a clean committed run. The separate full gate did run at that commit.

2026-10-09 Asia/Baghdad. Baseline ed2840cc039f673b0ac5f3413d5e2a23d64ecb18.
Final effective package ec8097601c4f7bd3f331f0292930dff87cce08fdeaea56923afe489ae4295f86.
D-313; parent-approved T3. Local engineering evidence only, WIP.

## Host And Commands

HawaPC01, Windows11 build26300, Python3.12.10, pytest9.1.1, ruff0.9.6,
mypy1.15.0, DBOS2.29.0. CPU protocol tests, no inference/cloud/GPU benchmark.
Windows bridge uses the actual admitted C:/Program Files/WSL/wsl.exe image,
private native pipes and /usr/bin/python3 -I -B -c. Linux CI uses actual pipes
directly. Compile exact module bytes, not a replacement protocol implementation.
No excluded/skipped/weakened tests or altered protected fixtures/harness.

- .venv/Scripts/python.exe -m pytest tests/test_linux_control.py
- Final five complete modules: linux_control, native_control, native_io,
  native_process, native_capability_retention, with external JUnit destination.
- ruff check src tests scripts; mypy src tests scripts;
  ruff format --check src tests scripts:367files, all pass.

Current separate CPU inventory after tests: system Python3.14.4, Linux
6.18.40.1-microsoft-standard-WSL2, glibc2.43. Actual kernel self query1 and
distinct query0; immutable Windows executable hash
ceb41baa9fd67621e3126e1d6a6ec23d96158ab6ae1dca1982517f62f5f5daba.
This inventory is not per-test/model runtime admission; Python3.14 compilation
does not satisfy the package's supported3.11/3.12 runtime CI obligation.
Raw inventory C:/Users/Wareen/AppData/Local/HawEditEvidence/linux-owner-inventory-20261009/terminal.json,
SHA25667466516cfb98b9ffe31b365e5bdf93ae1a8a704055c58ab3fa42f3c1b30a039.

## Results And Provenance

Initial whole module45failures were missing API preparation failures, not
executed Linux bugs. JUnit b6228b2c20792b26532f52f6754f13669e3135a5a951cb391860d5479baee258.
First implementation44pass/1private-parent test preparation failure; fix that
preparation without weakening its real descriptor-refusal assertions.
Actual named-FIFO49pass/1failure report
af6c3e18e0a3882f7cee01dde50f2cdc748f3c947ca947bb43a712174af3bf85.
Actual same-inode reopen/thread-ID reuse50pass/2failure report
bd7c0bbf90cee674ca844b31250b823885319ac868863e0011639d25c3ce8ace.
These latter three are genuine executed Linux faults, now covered by regressions.

Earlier unchanged17complete modules574pass/0failure/error/skip,455.92s pytest
output, baseline effective package494ce6a526d91e05b57510569e67afb43aa78852195703d38e1999a3b8e16efe.
Terminal C:/Users/Wareen/AppData/Local/HawEditEvidence/linux-owner-affected-20261009/terminal.json,
SHA256d8d7e4eecb46765e51d484442a2e9ed32fe2e81ec234d1fb61879ef5590af1f3.
Original processes7416/60036/52584 absent before session closure and edits.
This earlier baseline is not relabelled final hardening evidence.

Final five complete native/control modules163pass/0failure/error/skip,
25.06s pytest output, current effective package above.
C:/Users/Wareen/HawEdit-linux-owner-final-native-v2-20261009.xml,
SHA2561b739ef5a40bf6ed240ead822915d75ed682cb1722f49b8d2688356598adb9d8.
The new endpoint contributes52cases:17host/option refusals and35real Linux
pipe cases, including Windows-native interoperability. Related cases are not
independent reliability/editorial observations. All required commands finished.

Current actual Serena maps/hashes and affected callers are in impact-map.md.
Exact clean committed bash scripts/verify.sh at49b2649 finished with5701pass,
3fail/0error/skip, JUnit2243.777s / observer2254.352706800011s on the host above.
Source, package, observer and checkout status remained unchanged. Failures:
the missing evidence header, missing README module-map row, and stale qualified
VEX source binding. The two documentation regressions are being corrected;
no test or security assertion is changed. The FFmpeg replacement fault from
the previous gate did not reproduce here; this is not its root-cause repair.
Terminal C:/Users/Wareen/AppData/Local/HawEditEvidence/linux-owner-clean-gate-20261009/terminal.json,
SHA256dfc5b30b3ece841359cf6c426d90ea89159ff17aa2fe52264f5d795ce1f1da31;
JUnitb531c9e084c2481f2eea18e9da2c64138a2c5ddc1ee69c1b97d868c3ed2e48d4.
Whole unchanged claims replay:65pass/2same-documentation failures/0error/skip,
11.068s JUnit /11.64s pytest, report
C:/Users/Wareen/HawEdit-linux-owner-claims-red-20261009.xml,
SHA2561f3d8ad32dbe7e4bb57d15b4575f6ede4f550da33e24e9e9fe74de826cd9c099.
All original gate/claims processes exited before edits. Corrected clean
committed full gate remains required; same-SHA CI pending.
After the documentation repair, complete unchanged tests/test_claims.py has
67pass/0failure/error/skip,10.977s JUnit /11.51s pytest, same host/runtime.
Command: .venv/Scripts/python.exe -m pytest tests/test_claims.py
--junitxml=C:/Users/Wareen/HawEdit-linux-owner-claims-fixed-20261009.xml.
Report SHA256a065f4f7315d0c3a8717a5d346e6ece38e91ef6e6ecf15eee1532f01ac6acc3f.
Documentation was uncommitted during this partial replay; package unchanged.
No ledger promotion, qualified VEX rebind/signature, new canonical ASR/reel,
GPU/provider drain, protected producer/HTTP generation or10/10 claim.

## Remaining Full-System Work

Adopt original Linux namespace/member capabilities and admitted utility/runtime/
source/model bytes; fixed ID-only DBOS producer, sticky effect/result fences,
resource/billing uncertainty reconciliation, HTTP recovery. Then real review,
immutable revision and verified export. The original ZAR20.8s word warning still
needs acoustic/editorial investigation; do not clamp its clock or rewrite raw ASR.
#1/#3/#4/#24/#25 and independent creator/editor/security/CI/sustained obligations
remain; #21 stays closed. This unit does not shrink the approved product goal.
