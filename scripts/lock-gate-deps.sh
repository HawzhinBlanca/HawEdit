#!/usr/bin/env bash
# Recompile the gate's hashed dependency lock.
#
# `requirements/gate-linux-py311.txt` is what CI installs with `--require-hashes`, so it has to
# be regenerable rather than a file nobody can reproduce. It targets the gate's exact platform —
# Linux, CPython 3.11, PyTorch CPU wheels — because that is the gate of record, and a lock
# resolved for this Windows host would pin different wheels.
#
# Run this after changing any dependency in pyproject.toml's `dev` or `media` extras, and commit
# the result in the same commit. D-139.
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to compile the lock: https://docs.astral.sh/uv/" >&2
  exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/requirements/gate-linux-py311.txt"
mkdir -p "$root/requirements"

# --index-strategy unsafe-best-match: torch's CPU build lives on download.pytorch.org while
# everything else is on PyPI, and the default strategy will not look past the first index that
# has *a* version of a name.
uv pip compile "$root/pyproject.toml" \
  --extra dev --extra media \
  --generate-hashes \
  --python-platform linux \
  --python-version 3.11 \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match \
  -o "$out"

pins=$(grep -cE '^[A-Za-z0-9._-]+==' "$out")
hashes=$(grep -c -- '--hash=sha256:' "$out")
echo "wrote $out"
echo "  $pins distributions pinned, $hashes sha256 hashes"

# A pin with no hash is the one thing this file must never contain: `--require-hashes` would
# reject the whole install, and a silent partial lock is worse than none.
if grep -E '^[A-Za-z0-9._-]+==\S+$' "$out" | grep -qv '\\$'; then
  echo "REFUSED: a pin has no continuation line, so it carries no hash" >&2
  exit 1
fi
