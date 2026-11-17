# Private Kernel Entropy Local Evidence

```yaml
commit: d4473d025ad1f00d87eaf8f3d07e70c5e70d3bd1
media_sha256: n/a
host: HawaPC01 Windows26300 Python3.12.10 WSLUbuntu Linux6.18.40.1 glibc2.43 x86_64
command: C:/Program Files/Git/bin/bash.exe scripts/verify.sh
```

2026-10-10, approved D-326 extension of D-325/rooted image T2.
Baseline2fa571038af8c79677f1a12214be9836be1e2b46 plus uncommitted entropy source,
current package8f72c12069d99450de1624a30cf81162e24449966ac8ac1b2685b0e35d631ba3.
HawaPC01 Windows11build26300/Python3.12.10/pytest9.1.1/ruff0.9.6/mypy1.15.0;
WSL6.18.40.1-microsoft-standard-WSL2/x86_64/glibc2.43.
No new installation/model policy, GPU/model import, inference, provider call,
publication, VEX renewal or ledger promotion.

## Kernel Regressions

Actual unchanged native helpers, no source-boundary/mount/fence mocks.
Kernel-test initializer Python3.14.4/GCC15.2.0; not the retained ASR runtime.
Final command: .venv/Scripts/python.exe -B -m pytest
tests/test_rooted_kernel_entropy.py tests/test_rooted_linux_image.py
tests/test_linux_snapshot.py tests/test_linux_bootstrap.py tests/test_linux_scope.py
--junitxml=C:/Users/Wareen/HawEdit-video-rating-20261010/rooted-entropy-typed-kernel-cohort.xml -q.

Reports under C:/Users/Wareen/HawEdit-video-rating-20261010; all0errors/skips:

| Report | Cases / Failures | SHA256 |
| --- | --- | --- |
| rooted-entropy-red.xml | 19 / 18 | 5a85bf2957232e3649a701fc3865154b4d365983c46acf3253517cbd4d071746 |
| rooted-entropy-first-implementation.xml | 19 / 8 | 88f70586eafb7d810e336775ba4c0b7ef50d1860e5b62b557ef001e4a2839fbd |
| rooted-entropy-mount-order.xml | 19 / 0 | 992dec7ce103d10f52d9122d4e4bcf1af8a9bdd9a7c67ecba2fdc67b93865f2b |
| rooted-entropy-kernel-cohort.xml | 154 / 1 | f700dd568e3421bea6461604c8d4444f5372e2456869b3425a718187a4d7e36d |
| rooted-entropy-async-red.xml | 22 / 2 | a15de84ddad41434b123b0d9e3dc724b8f3c41cd38d2bf80e55c6c7c30c2be97 |
| rooted-entropy-final-kernel-cohort.xml | 156 / 0 | 57a487b14c45ee8013508c3352f89639d647a0d4f7d8d24ea1d655a23a68e18d |
| rooted-entropy-typed-kernel-cohort.xml | 156 / 0 | 06e0a9b423e560d33dbec5f2e86c2d7334c233aa65eabd17ab592f41169f7507 |

Final typed cohort59.029JUnit seconds,22new cases plus134existing; not a full
gate/CI or proof of all possible kernel attack paths. Actual mount-only negative
control and genuine async-ring counterexamples explained in research.md.
Corrections preserve original assertions: post-clone original endpoint custody,
explicit installed mapped-library SONAME copies for new consumer calibration,
opt-in async refusals, Windows capability-helper accesses. Lint/typecheck pass
via exact scripts/verify.sh --fast; explicitly NOT the gate.

## Retained Copied Python3.12 Consumer

Fresh original-driver-preserving AST replay:
C:/Users/Wareen/probe_hawedit_rooted_python_entropy_final_20261010.py,
SHA2568ec1721044c70bab82c04b0c20120c0b932893f19204978f4f561f46315b11e0.
Original failed consumer and inventory template remain unchanged (2385e2d6...,
92fea37b...). Full original hashes and commands recorded in terminal receipts.

Raw C:/Users/Wareen/HawEditRootedPythonConsumer-approved-entropy-final-20261010:
terminal.json records native exit0, unchanged true, controller2.6532081000041217s;
stdout.json SHA256cc9d8f7a5bf816668885da3cb4ce598963bcf207d14e75763c9bf4fc758ff78c,
empty stderr SHA256e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.
Actual retained Python3.12.0/Clang17.0.1:2561files/486679890bytes copied,
512MiB/6000file bounds; manifest83e1e961cb2b7bf9927b7e5f124898b1ee4e183a16612504cccc2038524d473c.
Re-executed /runtime/bin/python3.12 with private prefix/normalized config,
32genuine entropy bytes, zero capabilities/NoNewPrivs, mapped-file private
identities, outside replacement unable to change copied num_beams1, original
pidfd-owned controller/member drain and no mount left in outside creator.
No SDK/model/GPU/resource admission; timing is calibration, not performance.

Initial approved entropy replay at package64f68834... passed; subsequent typed
replay's consumer also passed but its external observer footer failed from
shared exec-global variable clobbering. Preserve that raw receipt under
approved-entropy-typed-20261010; do not call the whole observer successful.
The final fresh replay isolates observer globals and returns0 without changing
the consumer assertions, source or old reports.

## Acceptance Status

Exact full gate for this unit pending; independent current-package VEX #24
and applicable same-SHA CI #25 still required. No DONE or 10/10 claim.
T2 full SDK/model/input closure/resource/production lifetime and T3 producer
admission remain open; entropy startup alone does not authorize the ZAR run.
Cloud permission remains an aggregate US$5 maximum, transcript text only,
not frames/audio/video or published deliverables.

## Exact Committed Gate Verdict

At committedd4473d0/package8f72c120..., exact clean scripts/verify.sh finished
6117cases:6115pass/2fail/0errors/0skips,2338.763JUnit seconds,
observer2351.276006900007s; all source/HEAD/package/checkout/observer unchanged.
The new evidence document lacked the prescribed YAML header (corrected above);
the other failure is existing independent VEX binding #24, reviewed81f6f606...
versus current8f72c120.... Never self-renew/rebind that review or call this green.
No ledger promotion/same-SHA CI. Original raw evidence:
C:/Users/Wareen/AppData/Local/HawEditEvidence/rooted-kernel-entropy-clean-gate-20261010,
terminalSHA25611570a3aa42ea10654d2f80738fe57298e14a32f3b34fa2f46f2e9f13479e06f,
JUnitSHA256f42482e9593e34080540dc5351abc20aa96e76bd4221d73f817255adfe61adc4.

Subsequent T2 actual SDK calibration preserved at
C:/Users/Wareen/HawEditRootedSDKConfigConsumer-20261010: native1/unchanged true,
controller900.8503457999905s. Its declare/inventory phase exceeded the900s
budget before snapshot creation; SDK/model/GPU execution was NOT reached.
This is neither a passed copied-SDK closure nor an observed writable-scratch
failure. Do not increase admission claims from the earlier Python-only pass.
Actual selected static ELF research and its counterexamples are retained at
C:/Users/Wareen/HawEditRootedSDKELFCompact-20261010/research-verdict.md.

Header correction checked with the whole tests/test_claims.py file:67pass,
0fail/errors/skips,12.193JUnit seconds. Raw
C:/Users/Wareen/HawEdit-video-rating-20261010/rooted-entropy-evidence-header-regressions.xml,
SHA256c5f35c281508b3ff8a218e85f172e584d5f3f2ba7d5c4635eb1a6e1d029f993f.
This focused check does not turn the preceding full gate green or supply CI.
SDK failed terminalSHA2569f3859752c20ba24393126f422387417a548533576221e8519a02b8eeb7d6a12.
