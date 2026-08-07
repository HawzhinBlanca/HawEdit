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

PY_BIN="${PY_BIN:-python3}"
step() { printf '\n==> %s\n' "$1"; }

step "python"
"$PY_BIN" --version
if ! "$PY_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "✗ hawedit needs Python 3.11+ (pyproject requires-python). Set PY_BIN to a newer one." >&2
  exit 2
fi

step "virtualenv"
if [[ ! -x .venv/bin/python ]]; then
  "$PY_BIN" -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip

step "dependencies (including the §3 Stage 0 media stack)"
# CPU wheels on purpose: §6 puts Stage 0 on CPU by design, and the CUDA build of torch is ~2 GB
# of kernels nothing here calls. A GPU box that wants the CUDA build can install it after.
# The media extra is NOT optional here even though pyproject makes it optional — without it the
# Stage 0 tests skip, and a skipped test is the quiet green this project is written against.
.venv/bin/pip install --quiet \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  -e '.[dev,media]'

step "ffmpeg with a verified RTL stack (§4.3)"
# fetch-ffmpeg.sh is idempotent and refuses a build that cannot shape Arabic script.
bash scripts/fetch-ffmpeg.sh

step "§7 model readiness"
# Reports rather than fails: most §7 components need weights this environment may not reach,
# and that is a fact about the machine, not an error in the checkout.
.venv/bin/python -m hawedit.models || true

step "gate"
bash scripts/verify.sh

cat <<'DONE'

Setup complete. The checkout is ready and the gate is green.

Run the pipeline over a video:

  .venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work

It will exit non-zero and name every §3 stage it could not run — the models at the middle of
the pipeline need credentials and hardware (see BLOCKED.md). Supply a transcript and a verdict
in their place to go all the way to a rendered clip:

  .venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work \
    --transcript t.json --sentences 0,1 --qc-pass
DONE
