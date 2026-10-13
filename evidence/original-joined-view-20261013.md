---
date: 2026-10-13
baseline_sha: a530ab2221345689227f47fad6be240a4a709d8a
status: WIP component, not video or release acceptance
host: HawaPC01, Threadripper3990X, Windows26300, CPython3.12.10; WSL6.18.54.1-microsoft-standard-WSL2, trusted system Python3.14.4/GCC15.2.0
libraries: pytest9.1.1, ruff0.9.6, mypy1.15.0
---

# Original Joined-Worker Observation

Approved launch-plan step6/RT2A and D-329. Actual seven-pair unchanged Serena
map and SHA in launch-impact-map.md precede production edits. Scope defaults,
Snapshot, producer and canonical model remain unchanged.

Pre-edit red: all11 initial native tests fail for absent verify_joined; genuine
join fixture reaches the missing API. Preserved C:/Users/Wareen/
HawEditJoinedView-red-20261013.xml and matching .log. Red XML SHA256:
837ecc940a3fc95a1b584ccbe1eb4e02fd2f5ac4b5617f831461b56db622d7d7.
First implementation passes all56 joined/prepared cases. Stronger tests initially expose three fixture-only
root-variable shadowing errors in cleanup, not a production security defect;
fixed test variable without removing/weakening any assertions. Full first-cohort
invocation also recorded nonexistent guessed test paths: no tests ran; not a
pass. Both failed invocations remain in external logs.

Final affected cohort:328 passed,0failed,0errors,0skips,112.52s;18new native
cases. XML/log: C:/Users/Wareen/HawEditJoinedView-cohort-final-20261013.*.
XML SHA256:2ed959e06651081ce3deb8cf32dbbefbc796771609d48dd78310b65516d49084;
JUnit suite112.092s, host pytest wall112.52s.
Command: .venv/Scripts/python.exe -m pytest tests/test_linux_joined_view.py
tests/test_linux_scope.py tests/test_linux_preparation_boundary.py
tests/test_linux_prepared_view.py tests/test_linux_bootstrap.py
tests/test_linux_thread_registry.py tests/test_linux_thread_name.py
tests/test_linux_snapshot.py tests/test_rooted_linux_image.py
tests/test_rooted_kernel_entropy.py tests/test_rooted_wsl_gpu.py
--junitxml=C:/Users/Wareen/HawEditJoinedView-cohort-final-20261013.xml

Fast lint/typecheck403files and full403file formatting pass. Exact committed
full gate and applicable same-SHA CI still required; no row promotion. Existing
expired independent VEX source/runtime review has not been renewed or rebound.
No actual copied Python/Torch/model, new ASR, media quality or ZAR acceptance.
No cloud call, added spending, install, push, publication or model substitution.

The trusted fixtures join exact namespace handles and enter genuine readonly
tmpfs/proc. Observation checks only original kernel identity/view/capabilities;
it does not inspect retained outside handles or establish Landlock/seccomp.
Those missing obligations stay explicit in RT2B, not affirmative flags.
