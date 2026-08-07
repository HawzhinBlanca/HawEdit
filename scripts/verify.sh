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

LINT_CMD="${LINT_CMD-$PY -m ruff check src tests}"
FORMAT_CMD="${FORMAT_CMD-$PY -m ruff format --check src tests}"
TYPECHECK_CMD="${TYPECHECK_CMD-$PY -m mypy}"
TEST_CMD="${TEST_CMD-$PY -m pytest}"

# Anti-cheat: a *_CMD that resolves to a no-op would make this gate print green while running
# nothing. Refuse loudly BEFORE running anything. Only the steps that will actually run are
# checked. (Same reasoning as the host repo's scripts/verify.sh.)
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
run_step "tests"     "$TEST_CMD"

echo "VERIFY OK — hawedit2 gate green"
