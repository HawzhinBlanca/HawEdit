# Verification record

Date: 2026-09-09. Source SHA: `532e6efb1708e8dc2c3d14dde4fb7927f5115006`.

The unchanged canonical command `C:/Program Files/Git/bin/bash.exe scripts/verify.sh` exited **0**. Both the start and post-run checkout were clean at the same SHA. Audit artifacts were kept outside the checkout until this gate finished, avoiding the dirty-tree release-test failure from the prior audit.

Observed result:

* Ruff lint, mypy and formatting passed.
* **3,688 passed, 1 warning in 1,098.86 seconds** (pytest-reported duration, this Windows/Threadripper/Python 3.12.10 environment).
* Gate evidence: **3,688 collected, 3,688 passed, 0 skipped**.
* Coverage evidence: **5,281 / 5,545 statements, 95.2%**.
* Final line: `VERIFY OK — hawedit gate green`.
* Terminal session exit code was retrieved only after the verified gate child processes had finished: **0**.

The warning was a pydantic_graph deprecation warning about no current event loop in `test_the_manifest_actually_reaches_the_model`.

This is a valid local gate result. It does not establish that the new audit probes pass: their outputs reproduce failures outside the existing suite. The audit added no tests to the canonical suite and did not weaken any assertion or change a fixture.

`HAWEDIT_MEDIA_ROOT` was unset. `tests/conftest.py` excludes `tests/media` during collection in that state. Thus zero skipped among collected tests is not proof that the optional real-media suite ran.

The exact-SHA GitHub check-runs request returned HTTP 422: “No commit found for SHA: 532e6efb1708e8dc2c3d14dde4fb7927f5115006.” Required hosted CI is not established. No feature/task ledger was marked complete.

After verification, only audit documentation/evidence was added under `specs/robustness-audit-532e6ef-2026-09-09/`, and a new Obsidian audit note was captured. Application source, tests, gate scripts and fixtures remain unchanged by this audit. The local gate result applies to the clean source SHA, not a future implementation of the proposed fixes.
