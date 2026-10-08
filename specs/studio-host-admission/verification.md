# Verification

2026-10-08, HawaPC01 / Windows build 26300 / CPython 3.12.10 / pytest 9.1.1.
Current unit remains WIP. This is development evidence, not release acceptance.

- Initial test-first missing-module run: one failure and 26 setup errors; module
  absence, not proof of a behavioral regression. Raw red.xml preserved externally.
- Initial composition: 27 passes. Follow-up genuine file-mutation counterexamples:
  28/30 passes, two DID NOT RAISE failures, zero errors/skips. VEX changed during
  real OpenSSH verification; raw trust policy changed after real transport creation.
  Repaired by final source/VEX/evidence checks and complete raw-proof comparison.
- Complete affected authorization, billing, generation, execution-input, claims
  and host suites: 298 passes, zero failures/errors/skips, pytest 247.866 seconds.
  A subsequent type-only annotation and two additional tests mean this diagnostic
  is not the exact frozen final-source report. Report SHA256
  d0d183a1bf35a09d26cecb9849364e34818d108f48ce0866cec9474ff965c470.
- Final host file: 32 passes, zero failures/errors/skips, pytest 54.361 seconds.
  Report SHA256 e41c27b2de6cfada67c2cf030d024649b6f7c023641f2aa7344b9668bd611d1a.
  Real OpenSSH and private SQLite; runtime/model/security observations are explicitly
  synthetic test boundaries, not native producer or qualified security acceptance.
- Fast check through the established Git Bash gate path: lint and strict mypy
  pass for 353 files. Whole formatting check passes. This is not the full gate.
  The initial bare `bash` resolved to WSL and refused a CR-bearing Windows lock
  path; it is retained as a launcher refusal, not a successful gate or source bug.

Raw evidence root:
C:/Users/Wareen/AppData/Local/HawEditEvidence/studio-host-map-673160f-20261008.
Actual Serena map hashes and callers are recorded in research.md/impact-map.md.
No harness, fixture/golden, VEX, protected model metadata or ledger promotion edits.

Next required observations: clean frozen local commit, exact `bash scripts/verify.sh`
through the established Git Bash interpreter, and unmodified native studio admission.
Required same-SHA CI is not dispatched or claimed. Media tooling, owned ID-only
worker/effects supervision, HTTP, review/revision/export and sustained evaluation
remain required. No paid call, production owner enrollment or publication claimed.
