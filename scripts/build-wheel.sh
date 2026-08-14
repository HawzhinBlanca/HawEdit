#!/usr/bin/env bash
# Build one clean Git revision twice with HawEdit's hash-locked private builder.
#
# PY is only the bootstrap interpreter used to create the private builder. The actual frontend
# and backend come from requirements/release-build.txt, are installed with --require-hashes, and
# are measured in the JSON result. The production release command adds exact-SHA CI verification,
# provenance, SBOM and attestation; this helper deliberately publishes only a local wheel candidate.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

OUT="${1:-$here/dist/local-hawedit-$(git -C "$here" rev-parse --short=12 HEAD 2>/dev/null || true)}"
if [[ -z "$OUT" || "$OUT" == -* ]]; then
  echo "usage: bash scripts/build-wheel.sh [OUTPUT_DIR]   (no flags; PY selects the" >&2
  echo "  bootstrap interpreter). Got: $OUT" >&2
  exit 2
fi

if [[ -z "${PY:-}" ]]; then
  for candidate in "$here/.venv/bin/python" "$here/.venv/Scripts/python.exe"; do
    if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
  done
fi
if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "no bootstrap interpreter in .venv - run: bash scripts/setup.sh" >&2
  exit 2
fi

PYTHONPATH="$here/src" "$PY" - "$here" "$OUT" <<'PY'
import json
import sys
from pathlib import Path

from hawedit.release import ReleaseError, build_local_reproducible_wheel

try:
    artifact = build_local_reproducible_wheel(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        python=Path(sys.executable),
    )
except ReleaseError as exc:
    raise SystemExit(f"REFUSED: {exc}") from exc

print(json.dumps(artifact.to_dict(), indent=2, sort_keys=True))
PY
