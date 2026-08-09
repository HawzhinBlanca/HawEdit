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

# A venv puts the interpreter in `bin/` on POSIX and `Scripts/` on Windows. hawapc01 — the
# box §6 names and §8.1 requires the benchmark to run on — is Windows, so hardcoding `bin/`
# made "one command from a fresh clone to a green gate" false on the one machine that has to
# run it. Both layouts, first match wins; PY still overrides for a deliberate interpreter.
if [[ -z "${PY:-}" ]]; then
  for candidate in "$here/.venv/bin/python" "$here/.venv/Scripts/python.exe"; do
    if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
  done
fi
if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "✗ no interpreter in .venv — run: bash scripts/setup.sh" >&2
  exit 2
fi

# The override refusal below is a whitelist of one, and `PY` was the hole in it: PY replaces
# every step at once, including the evidence step that exists so the exit code stops being the
# evidence. Measured 2026-08-09: `PY=/usr/bin/true.exe bash scripts/verify.sh` printed
# VERIFY OK in 1 second, exit 0, with no report written — five steps, all of them `true.exe`,
# one of them grading the other four. So an interpreter proves it can run *this* project
# before it is trusted to say whether this project works, and the shell checks the value
# rather than the exit code, because an exit code is what `true.exe` is good at. D-092.
#
# The same probe now also asks where the programs the steps consist of came from. A real PY was
# not enough: a 30-line `pytest/__main__.py` on PYTHONPATH wrote a clean 1,200-test report and
# the gate printed VERIFY OK in 4 seconds having run nothing — then ratcheted the committed
# floor 1155 -> 1200, so every honest run after it would fail a bar a forgery invented.
# Measured 2026-08-09. D-093.
_probe="$("$PY" -m hawedit.gate --check-tools 2>&1 || true)"
if [[ "$_probe" != *hawedit-interpreter-ok* ]]; then
  echo "REFUSED: $PY cannot import hawedit, or the gate's tools are not its own, so it is" >&2
  echo "not an interpreter that runs this project — a gate graded by something that cannot" >&2
  echo "run the code, or by a substituted program, proves nothing." >&2
  echo "It answered: ${_probe:-<nothing at all>}" >&2
  echo "Install the project into it (bash scripts/setup.sh), unset PY, or clear whatever is" >&2
  echo "shadowing the tool named above — PYTHONPATH is the usual one." >&2
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

LINT_CMD="${LINT_CMD-$PY -m ruff check src tests}"
FORMAT_CMD="${FORMAT_CMD-$PY -m ruff format --check src tests}"
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
