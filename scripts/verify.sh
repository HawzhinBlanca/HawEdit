#!/usr/bin/env bash
# hawedit gate — the single source of "does it work" for the Kurdish repurposing system.
#
# A task is DONE only when this exits 0. The agent never marks DONE by judgment.
# `--fast` runs lint + typecheck only (editor feedback); it can never print the full-gate
# success line, so a fast run can never be mistaken for a passing gate.
set -euo pipefail

FAST="${1:-}"
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

# A venv puts the interpreter in `bin/` on POSIX and `Scripts/` on Windows. The canonical gate
# has one trust root: this checkout's `.venv`. A caller-supplied executable used to be able to
# print the fixed probe token and then return success for every `-m` invocation, including the
# evidence grader. Normalize paths without executing PY, require an exact canonical path, then
# use the checkout spelling for every command. An external development venv can run individual
# tools, but it cannot produce canonical gate evidence.
canonical_interpreters=()
for candidate in "$here/.venv/bin/python" "$here/.venv/Scripts/python.exe"; do
  if [[ -x "$candidate" ]]; then canonical_interpreters+=("$candidate"); fi
done
if [[ ${#canonical_interpreters[@]} -eq 0 ]]; then
  echo "✗ no interpreter in .venv — run: bash scripts/setup.sh" >&2
  exit 2
fi

_normalized_interpreter() {
  local directory name
  directory="$(cd -P "$(dirname "$1")" 2>/dev/null && pwd -P)" || return 1
  name="$(basename "$1")"
  printf '%s/%s\n' "$directory" "$name"
}

selected="${PY:-${canonical_interpreters[0]}}"
selected_normalized="$(_normalized_interpreter "$selected" || true)"
matched=""
for candidate in "${canonical_interpreters[@]}"; do
  if [[ -n "$selected_normalized" &&
    "$selected_normalized" == "$(_normalized_interpreter "$candidate")" ]]; then
    matched="$candidate"
    break
  fi
done
if [[ -z "$matched" ]]; then
  echo "REFUSED: PY must be this checkout's canonical .venv interpreter." >&2
  echo "Got: ${PY:-<unset>}" >&2
  echo "Expected one of: ${canonical_interpreters[*]}" >&2
  echo "External interpreters cannot produce canonical gate evidence." >&2
  exit 3
fi
PY="$matched"

_lock_identity="$({ "$PY" -I - <<'PY'
import platform
import sys

system = platform.system().lower()
version = sys.version_info[:2]
if system not in {"linux", "windows"} or version not in {(3, 11), (3, 12)}:
    raise SystemExit(2)
print(f"{system}-py{version[0]}{version[1]}")
PY
} 2>/dev/null)" || {
  echo "REFUSED: canonical gate supports only CPython 3.11/3.12 on Linux/Windows" >&2
  exit 3
}
HOST_LOCK="$here/requirements/host-gate-${_lock_identity}.txt"
if [[ ! -f "$HOST_LOCK" ]]; then
  echo "REFUSED: canonical host dependency lock is missing: $HOST_LOCK" >&2
  exit 3
fi

# Path identity closes the executable-forgery hole; this second check closes environment drift.
# Importing *some* hawedit is insufficient: this checkout's shared venv was measured importing
# an editable install from another checkout, with duplicate HawEdit metadata and stale direct
# dependencies. Execute the current source check by absolute path under isolated startup. The
# token is now a response from the path-bound interpreter, not an authentication mechanism.
# Installed code therefore cannot grade the checkout whose source is about to run. D-104.
# `agentic` joins dev/media here for the same reason it joined the gate scope in
# `install-host.sh` and `_PROFILE_EXTRAS`: this probe asserts the venv matches the *gate*
# profile's lock, and that lock now carries dbos + pydantic-ai. The four sites must agree —
# `environment.py` refuses when they do not, which is how each partial edit was caught. D-A26.
_probe="$("$PY" -I "$here/src/hawedit/environment.py" \
  --project-root "$here" --extra dev --extra media --extra agentic --lock "$HOST_LOCK" 2>&1 || true)"
if [[ "$_probe" != hawedit-environment-ok ]]; then
  echo "REFUSED: $PY cannot verify the exact HawEdit environment for this checkout." >&2
  echo "A gate graded by another checkout, stale dependencies, or a non-Python executable" >&2
  echo "proves nothing." >&2
  echo "It answered: ${_probe:-<nothing at all>}" >&2
  echo "Rebuild this checkout's environment (bash scripts/setup.sh), or unset PY." >&2
  exit 3
fi

# Environment identity alone does not authenticate the programs invoked by `-m`. Measured on
# 2026-08-09, a 30-line fake pytest on PYTHONPATH forged a clean JUnit report and poisoned the
# committed floor. Run this probe without isolated startup so it resolves modules exactly as the
# later gate commands do, and require every gate tool to come from this locked environment.
_tool_probe="$("$PY" -m hawedit.gate --check-tools 2>&1 || true)"
if [[ "$_tool_probe" != *hawedit-interpreter-ok* ]]; then
  echo "REFUSED: canonical gate tools are missing or shadowed." >&2
  echo "It answered: ${_tool_probe:-<nothing at all>}" >&2
  echo "Clear PYTHONPATH/module shadowing or rebuild with bash scripts/setup.sh." >&2
  exit 3
fi

# `${VAR-default}` (no colon) substitutes only when VAR is UNSET. An explicitly empty
# override therefore stays empty and is caught by _noop_check below. With `${VAR:-default}`
# an empty value would be silently replaced by the default, so `LINT_CMD=` would look like a
# configured gate while expressing the intent to run nothing.
# §4.3.6's golden render test runs only when an ffmpeg with libass/HarfBuzz is reachable.
# Auto-discover one fetched by scripts/fetch-ffmpeg.sh so the safeguard is on by default
# rather than opt-in — a golden test nobody remembers to enable protects nothing.
if [[ -z "${HAWEDIT_FFMPEG:-}" && -x "${here}/.ffmpeg/ffmpeg" ]]; then
  export HAWEDIT_FFMPEG="${here}/.ffmpeg/ffmpeg"
fi

TEST_REPORT="$here/.gate/last-test-run.xml"
TEST_FLOOR="$here/scripts/test-count.floor"

# Which steps did the caller replace? Recorded BEFORE the defaults are filled in, because
# filling a default sets the variable and would make every step look overridden.
# `${VAR+set}` is true for any assignment including the empty one, so this cannot be dodged
# by passing an empty value.
_overridden=()
for _var in LINT_CMD FORMAT_CMD TYPECHECK_CMD TEST_CMD; do
  if [[ -n "${!_var+set}" ]]; then _overridden+=("$_var"); fi
done

# `scripts` joined `src tests` in D-161. It had been checked by nothing: measured, `ruff` and
# `mypy` both saw 0 of the directory's Python while `README.md` calls this step "lint +
# typecheck + format + tests" without qualification. Adding it cost nothing — both pass on the
# wider scope today — and `tests/test_gate.py` now derives the scope from this line, so a
# directory of Python that no step reads fails rather than going quietly unchecked.
LINT_CMD="${LINT_CMD-$PY -m ruff check src tests scripts}"
FORMAT_CMD="${FORMAT_CMD-$PY -m ruff format --check src tests scripts}"
TYPECHECK_CMD="${TYPECHECK_CMD-$PY -m mypy}"
TEST_CMD="${TEST_CMD-$PY -m pytest --junitxml=$TEST_REPORT}"

# Anti-cheat (audit finding #5). There was a blacklist here first, knowing five spellings of
# "do nothing"; TEST_CMD="echo skipped" is a sixth and `pytest -k nothing_matches` a seventh.
# No blacklist of ways to run nothing can be complete, so the rule is inverted: the gate's
# steps are not configurable. A replaced step is refused outright rather than judged on its
# content — which also made the blacklist unreachable, since every value it could have caught
# is an override, and overrides are refused here first.
if [[ ${#_overridden[@]} -gt 0 ]]; then
  echo "REFUSED: ${_overridden[*]} overridden — the gate's steps are not configurable." >&2
  echo "A run with a replaced step proves nothing about this project, so it cannot be green." >&2
  echo "For a partial check use: bash scripts/verify.sh --fast" >&2
  exit 5
fi

# Recursion guard. The test suite invokes this gate to assert its refusal behaviour, so a
# nested full run would fork-bomb: gate -> pytest -> gate -> pytest. A nested invocation may
# lint and typecheck, but must never reach the test step.
GATE_DEPTH="${HAWEDIT_GATE_DEPTH:-0}"
export HAWEDIT_GATE_DEPTH=$((GATE_DEPTH + 1))

run_step() {
  echo "==> $1"
  eval "$2"
}

run_step "lint"      "$LINT_CMD"
run_step "typecheck" "$TYPECHECK_CMD"

if [[ "$FAST" == "--fast" ]]; then
  echo "fast checks OK (lint + typecheck only — NOT the full gate, tests did not run)"
  exit 0
fi

if [[ "$GATE_DEPTH" -gt 0 ]]; then
  echo "REFUSED: nested gate invocation (depth ${GATE_DEPTH}) — running the test step here would recurse into this gate. Use --fast, or override TEST_CMD, in a nested call." >&2
  exit 4
fi

run_step "format"    "$FORMAT_CMD"

# Layer 3 (audit finding #5). Refusing overrides closes the *deliberate* bypass. It does not
# close the accidental one: a testpaths typo, a stray -k in addopts, or a collection error a
# plugin swallowed all make pytest exit 0 having run nothing, with the command exactly right.
# So the exit code stops being the evidence. Delete the report, run, read it back.
mkdir -p "$here/.gate"
rm -f "$TEST_REPORT"
started_at="$("$PY" -c 'import time; print(time.time())')"

run_step "tests"     "$TEST_CMD"

run_step "test evidence" "\"$PY\" -m hawedit.gate \"$TEST_REPORT\" \"$TEST_FLOOR\" \"$started_at\""

echo "VERIFY OK — hawedit gate green"
