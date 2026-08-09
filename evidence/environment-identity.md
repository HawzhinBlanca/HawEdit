# Gate environment identity - 2026-08-09

## Reproduced bypass

`PY` prefixed every gate command, including the probe and JUnit evidence reader. An arbitrary
executable that always printed the expected token and exited zero could therefore make the script
print `VERIFY OK` without running Python or producing JUnit. A real stale shared venv also passed
source tests while its editable HawEdit distribution pointed at a different checkout and its
declared tool versions were stale.

## Enforced boundary

`scripts/verify.sh` now resolves the checkout's canonical `.venv` interpreter without executing
the requested override and refuses any non-identical `PY` before it runs. `hawedit.environment`
then checks Python 3.11/3.12, the project version, exact active base/dev/media requirements and the
installation identity. Source mode requires one authoritative editable distribution rooted at the
current checkout; only its expected same-version egg-info may coexist. PEP 508 markers are
evaluated for the audited interpreter, so inactive Linux ASR pins do not falsely reject Windows.

The shared stale venv is now intentionally rejected for pointing at `Desktop/HawEdit` rather than
the audited readiness checkout. A clean Python 3.12.13 canonical venv with 37 packages passes the
preflight and `pip check`; its full gate passed 1,525/1,525 with zero skips and accepted fresh JUnit
evidence.

## Controls and limit

Tests cover token-forging/no-op executables, external interpreters, duplicate/wrong-root metadata,
version drift, active/inactive markers and malformed non-exact requirements. This proves the local
gate grades its declared checkout/environment. Runtime transitive artifacts are not yet hash-locked;
that remains M3.7's dependency-supply-chain shortfall.
