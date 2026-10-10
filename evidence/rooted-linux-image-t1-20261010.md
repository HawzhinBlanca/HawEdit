# Rooted Image T1 Verification Checkpoint

```yaml
commit: d7aede0ba533fc92d02102a01e59eec93cd2ae28
media_sha256: n/a
host: HawaPC01 Windows26300 nativePython3.12.10 WSLUbuntu Linux6.18.40.1 glibc2.43 x86_64
command: C:/Program Files/Git/bin/bash.exe scripts/verify.sh
```

2026-10-10, working-tree implementation, not a committed clean gate or CI pass.
Approved rooted architecture: plan.md, direct Wareen approval on this date.
BLUEPRINT sections 2-5/8, D-325. Whole output-quality goal remains active.

## Source And Caller Custody

Edited package SHA256
532a8b6db1cfaac876e0a02b681ef61bac0bd4a605e58a96e501d4e8380eadad.
linux_snapshot.py raw SHA256
2c0835606c28afa2e24c28add3c820616eb5409d38544b15e1aadb8646aff3a9;
test_rooted_linux_image.py
5613d4a8a6d006564b0d07faaea54d6a05bef32ef2a7cff485403df69f8f5825.
Source/tests stayed unchanged during the full gate. Genuine pre-edit 19-pair
Serena map is recorded in impact-map.md; subsequent edited-boundary/follow-up
15-pair map, unchanged true:
C:/Users/Wareen/HawEditRootedFollowup-20261010/serena-map.json,
SHA256 8802fb11226f287955d7af07098a1f04ff95932b69410daa5b942f3bac26b60d.

## Actual Kernel Cohort

Command: .venv/Scripts/python.exe -B -m pytest tests/test_rooted_linux_image.py
tests/test_linux_snapshot.py tests/test_linux_bootstrap.py tests/test_linux_scope.py
--junitxml=C:/Users/Wareen/HawEdit-video-rating-20261010/rooted-image-kernel-cohort.xml
-q --tb=short.
134 passed, zero failures/errors/skips, JUnit 44.753 seconds.
Report SHA256 8a238507b133187d1bf1ae81ec3152e9176a7f038c25cfa3cca2cad7624df8e4.
pytest9.1.1; real kernel initializer Python3.14.4/GCC15.2.0/glibc2.43,
host/controller Python3.12.10. No model inference/GPU allocation/cloud calls.

Coverage includes independent copied ELF consumption under the real private
root, inaccessible replaced outside parent, readonly root/proc, actual
capability/namespace fence, native denied initialization, changed cwd,
same-inode reopened root/library descriptions, foreign thread/fork authority,
declared bounds/types, and retained runtime-FD offset/custody. Actual libffi
callback tables remain usable after rebinding; 5000 callback allocations are
a runtime regression test, not output quality or throughput. Prior failing
reports remain in the same external directory; no fixtures/skips weakened.

## Exact Full Working-Tree Gate

Git Bash invocation ran canonical scripts/verify.sh, without command overrides.
Lint/typecheck/format passed (ruff0.9.6/mypy1.15.0). Full pytest:
6095 cases, 6090 passed, 2 failed, 3 setup errors, zero skips;
JUnit2213.319 seconds, one existing event-loop deprecation warning. Exit1.
Original processes ended; session11219 closed only after process absence.
Preserved raw report:
C:/Users/Wareen/HawEdit-video-rating-20261010/rooted-image-primary-full-gate.xml,
SHA256 e2573af9aa15c1be4602cabca2a73a9ec21c6b2d17972053d2fcbbf7217b88f1.

All nonpassing cases, without omissions:
- tests.test_build.test_two_builds_of_one_commit_are_byte_identical: setup error,
  release builder refused dirty checkout.
- tests.test_build.test_every_entry_carries_the_commits_timestamp_not_the_clock:
  same setup refusal.
- tests.test_build.test_build_script_reports_the_hash_locked_private_builder:
  same setup refusal.
- tests.test_build.test_the_wheel_contains_every_file_the_audit_report_says_it_does:
  failed on the same dirty-checkout refusal.
- tests.test_vex.test_checked_in_policy_binds_current_lock_and_assets_and_closes_report:
  reviewed package81f6f606f89115ddedcba38941aad0b3f86cc59187a52b21b2a8a4f609bc5eba
  does not bind the current edited package above (BLOCKED #24).

Preserve guards unchanged. A reviewed local-only commit plus clean worktree
verification addresses the build-state refusal. It cannot renew the independent
security review. No ledger promotion, release, publication or same-SHA CI claim.

## Remaining Scope

T2 still requires actual complete copied interpreter/SDK/ELF/source/model/input
closure, resource admission and original controller/member lifetime. T3 requires
protected DBOS/HTTP adoption and genuine ZAR generation/review/revision/export.
Static ELF research is in C:/Users/Wareen/HawEditRootedELFClosure-20261010,
not complete dynamic closure or immutable-model admission.
ZAR source framing and listener-contract counterexample are research, not a
fresh output reel or labelled speaker-accuracy measurement.

Explicit owner cloud decision now permits aggregate US$5 for this ZAR test,
transcript text only, no audio/video/frames upload or publication. Existing
cloud Stage4 requires keyframes, so it is outside this scope; no silent text-only
visual verdict. Actual spending is zero in this session. Approval does not
manufacture signed authority, governance references, security/editor review or
runner registration. Every original release and sustained threshold remains.
