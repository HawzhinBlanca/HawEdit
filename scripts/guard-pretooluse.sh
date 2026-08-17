#!/usr/bin/env bash
# CODYSTEM PreToolUse guard. Reads Claude Code hook JSON on stdin; exit 2 blocks the call.
#
# Two boundaries, deliberately different in strength:
#
#   HARD-PROTECTED paths are never writable by an agent, with no escape. Secrets, the venv,
#   fetched binaries, downloaded weights, build output — and `.gate/`, which is where the gate
#   writes the test report it then grades itself against. D-093 moved the evidence out of the
#   exit code and into that report precisely so a run that executed nothing could not print
#   VERIFY OK; an agent able to hand-write `.gate/last-test-run.xml` would put the forgery back.
#
#   ENFORCEMENT paths are the gate, this guard, the ledger flipper, the hook config, CI, the
#   committed test-count floor, `src/hawedit/gate.py`, and the golden/fixture corpus. Editing
#   these is sometimes legitimate — improving the harness is real work — so they are escapable,
#   but only via a sentinel file that is visible in `git status` and names itself in the diff.
#
# HONEST LIMITATION, stated because this repo does not accept a safeguard that overstates
# itself: an unrestricted Bash tool runs arbitrary code, so the command scanning below is a
# tripwire for obvious cases, not a security boundary. The exact boundary is the file_path
# check for Edit/Write/MultiEdit, plus filesystem permissions. The REAL gate is
# `.github/workflows/gate.yml` on a clean runner, re-running from committed source with no
# shell of the agent's — which no local edit can fake.
set -euo pipefail

input="$(cat)"

# jq first, Python second. Codystem's original required jq; hawedit's contributors are
# guaranteed a Python 3.11+ (pyproject requires-python) and are not guaranteed jq — notably on
# the Windows box scripts/setup.sh and scripts/verify.sh both go out of their way to support.
# A guard that silently does not run on one of the project's two supported platforms is worse
# than no guard, because it reads as protection in the settings file either way.
JSON_TOOL=""
JSON_KIND=""
if command -v jq >/dev/null 2>&1; then
  JSON_TOOL="jq"
  JSON_KIND="jq"
else
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import json" >/dev/null 2>&1; then
      JSON_TOOL="$candidate"
      JSON_KIND="python"
      break
    fi
  done
fi

if [[ -z "$JSON_TOOL" ]]; then
  # Fail OPEN, loudly. Failing closed would block every tool call on a machine missing both
  # readers, making the checkout unusable for a reason no error message would connect to this
  # file. The warning goes to stderr so it is visible rather than assumed.
  echo "WARNING: CODYSTEM guard inactive — neither jq nor a Python with json was found." >&2
  echo "         Tool calls are NOT being checked against AGENTS.md boundaries." >&2
  exit 0
fi

# Extract one dotted field as a string; empty when absent, on any parse error, or when the
# value is not a string. Never fails the script: a malformed payload must not wedge the agent.
read_field() {
  local key="$1"
  if [[ "$JSON_KIND" == "jq" ]]; then
    printf '%s' "$input" | jq -r ".${key} // empty" 2>/dev/null || true
  else
    printf '%s' "$input" | "$JSON_TOOL" -c '
import json, sys
try:
    node = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for part in sys.argv[1].split("."):
    node = node.get(part) if isinstance(node, dict) else None
    if node is None:
        break
print(node if isinstance(node, str) else "")
' "$key" 2>/dev/null || true
  fi
}

path="$(read_field 'tool_input.file_path')"
cmd="$(read_field 'tool_input.command')"

ROOT_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd || echo .)"
SENTINEL="${ROOT_DIR}/.codystem-allow-self-edit"

# Each entry carries an absolute (`*/dir/*`) and a relative (`dir/*`) form, because the agent
# writes `.gate/x` as often as it writes `/home/me/HawEdit/.gate/x`, and a glob anchored only
# at `*/` matches neither reliably.
is_protected_path() {
  # models/ is ignored by .gitignore except for two files that must be identical on every
  # checkout — sources.json says which repository each §7 checkpoint comes from, revisions.json
  # pins the commit (D-073). Those are editable; the weights beside them are not.
  case "$1" in
    */models/sources.json|models/sources.json \
    |*/models/revisions.json|models/revisions.json)
      return 1 ;;
  esac
  case "$1" in
    *.env|*.env.*|*.pem \
    |*/secrets/*|secrets/* \
    |*/.venv/*|.venv/* \
    |*/.venv-wsl/*|.venv-wsl/* \
    |*/.gate/*|.gate/* \
    |*/.ffmpeg/*|.ffmpeg/* \
    |*/models/*|models/* \
    |*/build/*|build/* \
    |*/dist/*|dist/* \
    |*.egg-info/* \
    |*/node_modules/*|node_modules/*)
      return 0 ;;
  esac
  return 1
}

is_enforcement_path() {
  case "$1" in
    */scripts/verify.sh|scripts/verify.sh \
    |*/scripts/guard-pretooluse.sh|scripts/guard-pretooluse.sh \
    |*/scripts/guard-test.sh|scripts/guard-test.sh \
    |*/scripts/claude-stop-verify.sh|scripts/claude-stop-verify.sh \
    |*/scripts/update-ledger.sh|scripts/update-ledger.sh \
    |*/scripts/test-count.floor|scripts/test-count.floor \
    |*/src/hawedit/gate.py|src/hawedit/gate.py \
    |*/.claude/settings.json|.claude/settings.json \
    |*/.github/*|.github/* \
    |*/tests/golden/*|tests/golden/* \
    |*/tests/fixtures/*|tests/fixtures/*)
      return 0 ;;
  esac
  return 1
}

# 0 = block, 1 = allow. Emits the reason on the way out either way.
should_block() {
  local p="$1"
  if is_protected_path "$p"; then
    echo "BLOCKED: $p is a protected path (AGENTS.md hard boundary)." >&2
    return 0
  fi
  if is_enforcement_path "$p"; then
    if [[ -f "$SENTINEL" ]]; then
      echo "AUDIT: SELF-EDIT of CODYSTEM enforcement file '$p' permitted via the .codystem-allow-self-edit sentinel." >&2
      return 1
    fi
    echo "BLOCKED: '$p' is a CODYSTEM enforcement file — the gate, this guard, the ledger, CI," >&2
    echo "         the committed test floor, or the golden corpus. A deliberate self-edit needs" >&2
    echo "         the .codystem-allow-self-edit sentinel, which shows up in git status." >&2
    echo "         Note: the real gate is CI on a clean runner, which no local edit can fake." >&2
    return 0
  fi
  return 1
}

# --- Edit/Write/MultiEdit -----------------------------------------------------
if [[ -n "$path" ]] && should_block "$path"; then
  exit 2
fi

if [[ -n "$cmd" ]]; then
  # --- Dangerous commands -----------------------------------------------------
  # Flag reordering, wget/fetch, `+ref` and --force-with-lease force-pushes, and the
  # --no-verify family are all covered because each is an equivalent spelling of one already
  # here. Gate-step overrides (LINT_CMD=, TEST_CMD=, PY=) are deliberately NOT duplicated:
  # verify.sh refuses them itself with exits 3 and 5, and a second half-correct copy of that
  # rule here would drift from the one that decides.
  if printf '%s' "$cmd" | grep -Eq \
      -e 'rm[[:space:]]+-[a-zA-Z]*([rR][a-zA-Z]*[fF]|[fF][a-zA-Z]*[rR])' \
      -e 'rm[[:space:]].*--recursive.*--force' \
      -e 'rm[[:space:]].*--force.*--recursive' \
      -e 'git[[:space:]]+push[[:space:]].*(--force|--force-with-lease)' \
      -e 'git[[:space:]]+push[[:space:]].*[[:space:]]\+' \
      -e 'git[[:space:]]+reset[[:space:]]+--hard' \
      -e 'git[[:space:]]+(commit|push)[[:space:]].*--no-verify' \
      -e 'git[[:space:]]+(commit|push)[[:space:]]+-n([[:space:]]|$)' \
      -e 'git[[:space:]]+.*-c[[:space:]]+core\.hooksPath' \
      -e '(curl|wget|fetch|base64)[[:space:]].*\|[[:space:]]*(sh|bash|zsh)' \
      -e '(python[0-9]*|node|perl|ruby|deno)[[:space:]]+-(c|e)[[:space:]].*(os\.system|subprocess|child_process|popen|system\(|exec\(|write\()'; then
    echo "BLOCKED: dangerous command pattern detected (AGENTS.md 'never run')." >&2
    exit 2
  fi

  # --- Write-target scan ------------------------------------------------------
  # Without this, the file_path boundary above is one shell redirect wide: `: > .gate/x` and
  # `cp /tmp/x .env` reach protected paths without ever being an Edit.
  candidates=$(
    {
      # Redirections: >, >>, 1>, 2>, &>, >|
      printf '%s\n' "$cmd" \
        | grep -oE '[0-9]*&?>>?\|?[[:space:]]*[^[:space:]<>|&;()]+' \
        | sed -E 's/^[0-9]*&?>>?\|?[[:space:]]*//'
      # dd of=FILE
      printf '%s\n' "$cmd" | grep -oE 'of=[^[:space:]<>|&;()]+' | sed -E 's/^of=//'
      # Writing commands: treat every token as a candidate, over-inclusively. Only emitted
      # when such a command is present, so plain reads (cat/grep/ls) stay untouched.
      if printf '%s' "$cmd" | grep -Eq '(^|[|&;[:space:]])(cp|mv|install|ln|tee)([[:space:]]|$)'; then
        printf '%s\n' "$cmd" | tr ' \t|&;()' '\n'
      fi
    } 2>/dev/null
  )
  if [[ -n "$candidates" ]]; then
    while IFS= read -r target; do
      [[ -z "$target" ]] && continue
      if should_block "$target"; then
        exit 2
      fi
    done <<< "$candidates"
  fi
fi

exit 0
