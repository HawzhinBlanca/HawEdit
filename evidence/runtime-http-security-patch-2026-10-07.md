---
status: local-regressions-not-accepted
date: 2026-10-07
baseline: dddd065bd396059c1c4c49cdbef75f488ed7e70a
commit: dddd065bd396059c1c4c49cdbef75f488ed7e70a
media_sha256: n/a: dependency locks and actual downloaded wheels, no inference
host: HawaPC01 / Windows11 build26300 / Threadripper3990X / CPython3.12.10
command: .venv/Scripts/python.exe -B -m pytest tests/test_runtime_security_migration.py tests/test_dependency_security.py tests/test_wsl_setup.py tests/test_wsl_audit_locks.py tests/test_wsl_vex_gate.py
---

# Isolated WSL HTTP Utility Security Patch

Header HEAD is the actual parent during local diagnostics, not a committed
candidate or security acceptance. Owner "do all" approves the already proposed
isolated runtime migration; D-293 and research/spec/impact/plan precede edits.

Actual source-unchanged Serena maps and wheel evidence:
C:/Users/Wareen/AppData/Local/HawEditEvidence/runtime-migration-map-20261007/
serena-map.json and host-security-research-20261007/research.json.
Both wheels downloaded from PyPI's declared files.pythonhosted.org URLs;
actual size/SHA match release metadata, not just a copied expected string.
urllib3 2.8.0 (MIT),135717 bytes:
0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3.
Werkzeug 3.1.9 (BSD-3-Clause),228700 bytes:
6392e50c78460ba618e5b21f08a71f59c99ce99cdc6cf6e3dd7e6ccca8754fab.
Primary maintainer advisories and download metadata provenance in research.md.

Repository test-first4 cases:3 failures/1 pass,0errors/skips,pytest0.91s.
The two old pins and unchanged generation are the failing conditions. After
patch, complete five-module direct diagnostic77 passes,0failures/errors/skips,
pytest5.90s; pytest9.1.1,ruff0.9.6,mypy1.15.0,DBOS2.29.0 on the header host.
Raw test-first.xml and regressions.xml under runtime-migration-map-20261007.
These direct diagnostics do not carry a frozen-controller inventory.

New runtime lock SHA:
363be95a06518f21377693b81ceddf847091e0dd3db5db48a2092b02638a2f9e;
new generation Ubuntu-a218b3a5773a38323a6ecbf4, distinct from original
Ubuntu-33853eeafb05ecf1b998dc84. Regression reconstructs the original complete
runtime bytes and checks original SHA5e558b24e69da83e27e9ca5f49c13abdcfd03694080522e13b8688a827077e85.
No other requirement bytes, build/model pins, assets or old receipts change.

Real candidate provisioning, hostile-response tests, current exact full gate,
qualified VEX and same-SHA CI remain to be recorded externally after the local
commit/source freeze. Host utility locks and Transformers/Accelerate migration
remain open. No neural equivalence, security admission, studio completion, paid
call, publication, human benchmark or 10/10 claim.

After all T1 documentation edits, frozen six-module controller rerun (including
claims) passes144 cases,0failures/errors/skips,JUnit16.600s/controller18.6274404s.
All watched source/controller files, parent HEAD, package and dirty status stay
unchanged. Raw runtime-migration-candidate-20261007/regressions/terminal.json.
This is local diagnostic evidence, not an accepted full gate or CI claim.
