#!/usr/bin/env bash
# hawedit2 gate — the single source of "does it work" for the Kurdish repurposing system.
#
# A task is DONE only when this exits 0. The agent never marks DONE by judgment.
# `--fast` runs lint + typecheck only (editor feedback); it can never print the full-gate
# success line, so a fast run can never be mistaken for a passing gate.
set -euo pipefail

FAST="${1:-}"
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

PY="${PY:-$here/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "✗ no interpreter at $PY — run: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 2
fi

# `${VAR-default}` (no colon) substitutes only when VAR is UNSET. An explicitly empty
# override therefore stays empty and is caught by _noop_check below. With `${VAR:-default}`
# an empty value would be silently replaced by the default, so `LINT_CMD=` would look like a
# configured gate while expressing the intent to run nothing.
# §4.3.6's golden render test runs only when an ffmpeg with libass/HarfBuzz is reachable.
# Auto-discover one fetched by scripts/fetch-ffmpeg.sh so the safeguard is on by default
# rather than opt-in — a golden test nobody remembers to enable protects nothing.
if [[ -z "${HAWEDIT2_FFMPEG:-}" && -x "${here}/.ffmpeg/ffmpeg" ]]; then
  export HAWEDIT2_FFMPEG="${here}/.ffmpeg/ffmpeg"
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

# Anti-cheat, layer 1: a *_CMD that resolves to a no-op would make this gate print green while
# running nothing. Refuse loudly BEFORE running anything. Only the steps that will actually run
# are checked. (Same reasoning as the host repo's scripts/verify.sh.)
_noop_check() {
  local name="$1" trimmed
  trimmed="$(printf '%s' "$2" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  case "$trimmed" in
    "" | ":" | "true" | "/bin/true" | "/usr/bin/true")
      echo "REFUSED: ${name} resolves to a no-op ('${trimmed}') — the gate would pass while running nothing." >&2
      exit 3 ;;
  esac
}
_noop_check "LINT_CMD" "$LINT_CMD"
_noop_check "TYPECHECK_CMD" "$TYPECHECK_CMD"
if [[ "$FAST" != "--fast" ]]; then
  _noop_check "FORMAT_CMD" "$FORMAT_CMD"
  _noop_check "TEST_CMD" "$TEST_CMD"
fi

# Anti-cheat, layer 2 (audit finding #5). The blacklist above knows five spellings of "do
# nothing"; TEST_CMD="echo skipped" is a sixth, and `pytest -k nothing_matches` a seventh. No
# blacklist of ways to run nothing can be complete, so the rule is inverted: the gate's steps
# are not configurable. A replaced step is refused outright rather than judged on its content.
if [[ ${#_overridden[@]} -gt 0 ]]; then
  echo "REFUSED: ${_overridden[*]} overridden — the gate's steps are not configurable." >&2
  echo "A run with a replaced step proves nothing about this project, so it cannot be green." >&2
  echo "For a partial check use: bash scripts/verify.sh --fast" >&2
  exit 5
fi

# Recursion guard. The test suite invokes this gate to assert its refusal behaviour, so a
# nested full run would fork-bomb: gate -> pytest -> gate -> pytest. A nested invocation may
# lint and typecheck, but must never reach the test step.
GATE_DEPTH="${HAWEDIT2_GATE_DEPTH:-0}"
export HAWEDIT2_GATE_DEPTH=$((GATE_DEPTH + 1))

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

run_step "test evidence" "\"$PY\" -m hawedit2.gate \"$TEST_REPORT\" \"$TEST_FLOOR\" \"$started_at\""

echo "VERIFY OK — hawedit2 gate green"
