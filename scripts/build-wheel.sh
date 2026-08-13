#!/usr/bin/env bash
# Build the hawedit wheel reproducibly, and print the digest that identifies it.
#
# Two `pip wheel` runs at one unchanged commit used to produce the same 333,362 bytes and two
# different SHA-256s, because nothing set SOURCE_DATE_EPOCH and every ZIP entry carried the
# mtime of the moment it was written. `AUDIT_REPORT.md` recorded that as the reason it quotes a
# byte count and no digest: a hash would have identified one build at one instant rather than
# this code. Measured 2026-08-09, a7c3b2f1c280aff4 and 38d1d2475c46e120 for the same tree.
#
# The epoch is the commit's own author date — derived, never invented — so the same commit built
# on any machine on any day yields the same bytes. Outside a git checkout there is no commit to
# derive it from, and this refuses rather than substituting `now`, which would silently restore
# exactly the behaviour it exists to remove. D-120.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

OUT="${1:-$here/dist}"
# The single argument is the output directory. Guarded because `build-wheel.sh --help` otherwise
# creates a directory called `--help` — measured, it did, and git then reported it as untracked.
if [[ "$OUT" == -* ]]; then
  echo "✗ usage: bash scripts/build-wheel.sh [OUTPUT_DIR]   (no flags; PY overrides the" >&2
  echo "  interpreter). Got: $OUT" >&2
  exit 2
fi

if [[ -z "${PY:-}" ]]; then
  for candidate in "$here/.venv/bin/python" "$here/.venv/Scripts/python.exe"; do
    if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
  done
fi
if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "✗ no interpreter in .venv — run: bash scripts/setup.sh" >&2
  exit 2
fi

if ! epoch="$(git -C "$here" log -1 --format=%ct 2>/dev/null)" || [[ -z "$epoch" ]]; then
  echo "✗ no commit to take SOURCE_DATE_EPOCH from: this is not a git checkout, or it has no" >&2
  echo "  commits. Building anyway would stamp the wheel with the current time and the result" >&2
  echo "  would not be reproducible — which is the whole point of this script." >&2
  exit 2
fi

if [[ -n "$(git -C "$here" status --porcelain)" ]]; then
  echo "! the tree is dirty, so this wheel is not the commit it will be stamped with" >&2
fi

export SOURCE_DATE_EPOCH="$epoch"
mkdir -p "$OUT"

# `--no-build-isolation` means setuptools stages into this repo's own build/ rather than a
# private temporary one, and bdist_wheel finishes by *renaming* the egg-info onto
# build/bdist.<plat>/wheel/<name>.dist-info. On Windows a rename onto an existing directory is
# WinError 183, so a build that was interrupted — or a second one racing it, which BLOCKED #12
# says this checkout gets — leaves that directory behind and wedges every build after it. It
# did: three tests in test_build.py failed identically until this line existed, on a tree whose
# only change was two new tests in another file. Only the staging directory goes; build/lib is
# the incremental cache and is not what collides. A clean runner has neither, which is why CI
# could not have caught this.
rm -rf "$here"/build/bdist.*

"$PY" -m pip wheel --no-deps --no-build-isolation -q -w "$OUT" "$here"

"$PY" - "$OUT" <<'PY'
import hashlib
import pathlib
import sys

wheels = sorted(pathlib.Path(sys.argv[1]).glob("hawedit-*.whl"))
if not wheels:
    raise SystemExit("✗ pip wheel wrote no hawedit wheel")
wheel = max(wheels, key=lambda path: path.stat().st_mtime)
data = wheel.read_bytes()
print(f"{wheel.name}  {len(data):,} bytes")
print(f"sha256  {hashlib.sha256(data).hexdigest()}")
PY

echo "SOURCE_DATE_EPOCH=$epoch (commit $(git -C "$here" rev-parse --short HEAD))"
