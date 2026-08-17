#!/usr/bin/env bash
# CODYSTEM Stop hook. Runs the gate when the agent tries to end its turn, and translates the
# gate's exit code into the one Claude Code acts on.
#
# WHY A WRAPPER, AND NOT `bash scripts/verify.sh` DIRECTLY.
#
# Claude Code's hook contract gives exit code 2 a specific meaning — block, and feed stderr
# back to the agent — while every other non-zero code is a non-blocking notice shown to the
# user. verify.sh already uses 2 for something else entirely: "no interpreter in .venv". Wired
# up raw, the two codes land exactly backwards. A failing test suite (exit 1) would be a notice
# the agent never sees and can stop straight through, while a checkout that has merely not run
# scripts/setup.sh yet would block the agent on a condition it was told nothing about. The
# mapping below is the whole reason this file exists.
#
#   verify.sh 0  green                                  -> 0  stop normally
#   verify.sh 1  a step failed (lint/type/format/tests)  -> 2  BLOCK; the agent must fix it
#   verify.sh 2  no interpreter in .venv                 -> 1  notice; a setup fact, not a defect
#   verify.sh 3  interpreter cannot run this project     -> 2  BLOCK; recoverable via setup.sh
#   verify.sh 4  nested gate invocation                  -> 1  notice; cannot mean much at Stop
#   verify.sh 5  gate steps overridden                   -> 2  BLOCK; a bypass to undo
#   anything else                                        -> 2  BLOCK; unknown is not green
#
# Loop safety: Claude Code sets stop_hook_active on the payload when the agent is already
# continuing because of a previous Stop hook. Blocking again there is how a hook turns a red
# gate into an agent that cannot stop at all, so the second pass always lets go and leaves the
# failure on screen for a human.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

payload="$(cat 2>/dev/null || true)"

# A plain text match rather than a JSON parse. This needs exactly one boolean, the guard beside
# it already carries the reader-detection for the fields that genuinely need parsing, and a
# Stop hook that fails to start is a Stop hook that silently stops gating.
if printf '%s' "$payload" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

rc=0
bash scripts/verify.sh || rc=$?

case "$rc" in
  0)
    exit 0
    ;;
  2)
    echo "CODYSTEM: the gate could not run — this checkout has no interpreter in .venv." >&2
    echo "          Run: bash scripts/setup.sh" >&2
    echo "          Nothing was verified, so nothing here is done." >&2
    exit 1
    ;;
  4)
    echo "CODYSTEM: nested gate invocation at Stop; the gate did not run its test step." >&2
    exit 1
    ;;
  *)
    echo "" >&2
    echo "CODYSTEM: bash scripts/verify.sh exited ${rc} — the gate is NOT green." >&2
    echo "          Fix the failure above and re-run it. Do not mark anything done, and do not" >&2
    echo "          weaken a test, skip one, or edit a golden to match the output: AGENTS.md" >&2
    echo "          treats those as violations rather than shortcuts, and CI re-runs this same" >&2
    echo "          gate from committed source on a clean runner." >&2
    exit 2
    ;;
esac
