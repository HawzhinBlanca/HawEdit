#!/usr/bin/env bash
# Checkout wrapper for the installed-wheel provisioning command.
#
# The transaction lives in hawedit.model_fetch so a wheel user and a source-checkout user execute
# identical registry, revision, staging, byte-verification and no-replace publication rules.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -z "${PY:-}" ]]; then
  for candidate in "$here/.venv/bin/python" "$here/.venv/Scripts/python.exe"; do
    if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
  done
fi
if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "no interpreter in .venv - run: bash scripts/setup.sh" >&2
  exit 2
fi

exec "$PY" -m hawedit.model_fetch "$@"
