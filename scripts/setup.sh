#!/usr/bin/env bash
# One command from a fresh clone to a green gate.
#
# The README used to list four separate commands, and the order between them mattered in ways
# nothing enforced: install the media extra after running the gate once and §3 Stage 0's tests
# had already skipped, silently, on a run that printed VERIFY OK. Setup that can half-succeed
# is how a checkout ends up with less coverage than the person running it believes.
#
# So this does the whole thing and finishes by running the gate. If it exits 0, the checkout is
# genuinely ready. If it does not, the last thing printed is what is missing.
#
# Usage:  bash scripts/setup.sh
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

step() { printf '\n==> %s\n' "$1"; }

step "python"
# `python3` is the right name on POSIX and a Microsoft Store stub on Windows: present on PATH,
# prints "Python was not found", installs nothing, exits non-zero. Trusting the name puts the
# one command this README promises face-down on hawapc01. So each candidate is asked whether
# it is a real 3.11+ and the first that answers yes wins — capability, not spelling. PY_BIN
# still overrides, and is then the only candidate so a deliberate choice cannot be silently
# replaced by a fallback.
if [[ -n "${PY_BIN:-}" ]]; then candidates=("$PY_BIN"); else candidates=(python3 python py); fi
# Two conditions, and the second is not fussiness. `python` on this box resolves to another
# tool's virtualenv, and `python -m venv` from inside one died at `ensurepip` — so "is a 3.11+"
# was true and "can build the venv this script is about to build" was false. A base
# interpreter is what the next line actually needs, so that is what gets asked for.
_usable='import sys; raise SystemExit(0 if sys.version_info >= (3, 11)
  and sys.prefix == sys.base_prefix else 1)'
PY_BIN=""
for candidate in "${candidates[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c "$_usable" >/dev/null 2>&1; then
    PY_BIN="$candidate"
    break
  fi
done
if [[ -z "$PY_BIN" ]]; then
  echo "✗ no usable Python found. Tried: ${candidates[*]}" >&2
  echo "  hawedit needs a base (non-virtualenv) Python 3.11+ — pyproject requires-python, and" >&2
  echo "  a venv built from inside another venv fails at ensurepip." >&2
  echo "  Set PY_BIN to one, e.g. PY_BIN=/usr/bin/python3.12 bash scripts/setup.sh" >&2
  exit 2
fi
"$PY_BIN" --version

step "virtualenv"
# `bin/` on POSIX, `Scripts/` on Windows. hawapc01 is Windows and this script claimed to take
# a fresh clone to a green gate there; it stopped at the first `.venv/bin/pip`.
venv_python() {
  for candidate in .venv/bin/python .venv/Scripts/python.exe; do
    if [[ -x "$candidate" ]]; then printf '%s\n' "$candidate"; return 0; fi
  done
  return 1
}
if ! venv_python >/dev/null; then
  "$PY_BIN" -m venv .venv
fi
VENV_PY="$(venv_python)" || { echo "✗ venv created but no interpreter inside it" >&2; exit 2; }
# `python -m pip`, not the pip shim: on Windows pip cannot replace its own running .exe.
"$VENV_PY" -m pip install --quiet --upgrade pip

step "dependencies (including the §3 Stage 0 media stack)"
# CPU wheels on purpose: §6 puts Stage 0 on CPU by design, and the CUDA build of torch is ~2 GB
# of kernels nothing here calls. A GPU box that wants the CUDA build can install it after.
# The media extra is NOT optional here even though pyproject makes it optional — without it the
# Stage 0 tests skip, and a skipped test is the quiet green this project is written against.
"$VENV_PY" -m pip install --quiet \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  -e '.[dev,media]'

step "ffmpeg with a verified RTL stack (§4.3)"
# fetch-ffmpeg.sh is idempotent and refuses a build that cannot shape Arabic script.
bash scripts/fetch-ffmpeg.sh

step "§7 model readiness"
# Reports rather than fails: most §7 components need weights this environment may not reach,
# and that is a fact about the machine, not an error in the checkout.
"$VENV_PY" -m hawedit.models || true

step "gate"
bash scripts/verify.sh

# `$VENV_PY`, not a hardcoded `.venv/bin/python`: this is the last thing printed and the first
# thing anyone copies, and on Windows that path does not exist.
cat <<DONE

Setup complete. The checkout is ready and the gate is green.

Run the pipeline over a video:

  ${VENV_PY} -m hawedit.pipeline VIDEO.mp4 --work-dir work

It will exit non-zero and name every §3 stage it could not run — the models at the middle of
the pipeline need credentials and hardware (see BLOCKED.md). Supply a transcript and a verdict
in their place to go all the way to a rendered clip:

  ${VENV_PY} -m hawedit.pipeline VIDEO.mp4 --work-dir work \\
    --transcript t.json --verdict verdict.json --sentences 0,1 --qc-pass
DONE
