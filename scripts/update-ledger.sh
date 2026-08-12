#!/usr/bin/env bash
# Flips ONE task's row in specs/<feature>/tasks.md to [x] — and only if the gate passes.
# The gate decides done. The agent never does.
#
# Usage:  bash scripts/update-ledger.sh <feature> <TASK> <test_name[,test_name...]>
#   e.g.  bash scripts/update-ledger.sh caption-timing T3 test_caption_never_precedes_speech
#
# Three things have to be true before a row changes, and each closes a different hole:
#
#   1. `bash scripts/verify.sh` exits 0. Nothing else may stand in for it.
#   2. Every cited test appears BY NAME in the JUnit report that run just wrote. verify.sh
#      already deletes `.gate/last-test-run.xml`, re-runs pytest into it and has
#      `hawedit.gate` grade it for freshness and count, so a citation naming a test that does
#      not exist — or that exists and did not run — is caught here for free, against evidence
#      rather than against the agent's word. Citing a test is otherwise the easiest sentence in
#      the ledger to write and the hardest to check.
#   3. The row is matched exactly, within one feature's file. Features reuse T1..T4, and a
#      prefix match makes T1 flip T10 as well.
#
# What this is not: proof the work is finished. `## Definition of Done` in each tasks.md keeps
# CI on the pull request as the last line, because CI re-runs this gate from committed source
# on a clean runner and a local pass cannot speak for it.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

if [[ $# -lt 3 ]]; then
  echo "usage: bash scripts/update-ledger.sh <feature> <TASK> <test_name[,test_name...]>" >&2
  echo "   e.g. bash scripts/update-ledger.sh caption-timing T3 test_caption_never_precedes_speech" >&2
  exit 2
fi

feature="$1"
task="$2"
tests="$3"

ledger="specs/${feature}/tasks.md"
report=".gate/last-test-run.xml"

if [[ ! -f "$ledger" ]]; then
  echo "REFUSED: no ledger at ${ledger}." >&2
  exit 2
fi

# Task ids and test names go into regexes below. Constrained rather than escaped, because the
# set of things that belong here is small and known, and a rejected argument is a better
# outcome than a metacharacter quietly widening a match that decides what counts as done.
if [[ ! "$task" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "REFUSED: task id '${task}' is not [A-Za-z0-9_.-]+." >&2
  exit 2
fi

IFS=',' read -r -a cites <<< "$tests"
if [[ ${#cites[@]} -eq 0 ]]; then
  echo "REFUSED: no tests cited. A task is done because named tests pass, or it is not done." >&2
  exit 2
fi
for cite in "${cites[@]}"; do
  if [[ ! "$cite" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]]; then
    echo "REFUSED: cited test '${cite}' is not a plain test name." >&2
    echo "         Cite the function name as pytest reports it, e.g. test_render_refuses_empty." >&2
    exit 2
  fi
done

if ! grep -qE "^- \[[ xX]\] ${task}([[:space:]]|$)" "$ledger"; then
  echo "REFUSED: no row for task '${task}' in ${ledger}." >&2
  exit 2
fi

if grep -qE "^- \[[xX]\] ${task}([[:space:]]|$)" "$ledger"; then
  echo "Nothing to do: ${feature}/${task} is already marked done in ${ledger}."
  exit 0
fi

echo "==> gate"
if ! bash scripts/verify.sh; then
  echo "REFUSED: the gate is not green; ${feature}/${task} stays open." >&2
  exit 1
fi

echo "==> cited tests must appear in the report that run just wrote"
if [[ ! -f "$report" ]]; then
  echo "REFUSED: the gate passed but left no ${report} to check citations against." >&2
  exit 1
fi
for cite in "${cites[@]}"; do
  # Exact name, or the same name carrying a parametrisation suffix: pytest writes
  # name="test_x[case]" for every case of a parametrised test.
  if ! grep -qE "name=\"${cite}(\[[^\"]*\])?\"" "$report"; then
    echo "REFUSED: no test named '${cite}' ran in the gate that just passed." >&2
    echo "         A row cannot cite a test that does not exist or did not execute." >&2
    exit 1
  fi
  echo "    ok  ${cite}"
done

echo "==> flip"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
awk -v task="$task" '
  BEGIN { flipped = 0 }
  {
    if ($0 ~ "^- \\[ \\] " task "([ \t]|$)") {
      sub(/^- \[ \]/, "- [x]")
      flipped = 1
    }
    print
  }
  END { if (flipped != 1) exit 3 }
' "$ledger" > "$tmp"
cat "$tmp" > "$ledger"

# Provenance, written ONLY here and ONLY after all three checks passed. It is what lets a
# reader tell a row the gate flipped from a row somebody typed an x into.
printf 'TS=%s FEATURE=%s TASK=%s TESTS=%s VERIFY=pass REPORT=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$feature" "$task" "$tests" "$report" \
  >> "specs/${feature}/ledger.log"

echo "Ledger updated: ${feature}/${task} done (tests: ${tests}; gate green; provenance recorded)."
echo "Not finished until the required CI checks are green on the pull request."
