#!/usr/bin/env bash
# Install one exact, target-bound HawEdit host graph without invoking a live resolver.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: bash scripts/install-host.sh PYTHON {base|gate|models} [--dependencies-only]" >&2
  exit 2
fi

python="$1"
scope="$2"
mode="${3:-}"
if [[ "$scope" != base && "$scope" != gate && "$scope" != models ]]; then
  echo "REFUSED: host dependency scope must be base, gate or models, got: $scope" >&2
  exit 2
fi
if [[ -n "$mode" && "$mode" != --dependencies-only ]]; then
  echo "REFUSED: unknown install-host option: $mode" >&2
  exit 2
fi
if [[ ! -x "$python" ]]; then
  echo "REFUSED: host installer Python is not executable: $python" >&2
  exit 2
fi

identity="$({ "$python" -I - <<'PY'
import platform
import sys

system = platform.system().lower()
version = sys.version_info[:2]
if system not in {"linux", "windows"} or version not in {(3, 11), (3, 12)}:
    raise SystemExit(2)
print(f"{system}-py{version[0]}{version[1]}")
PY
} 2>/dev/null)" || {
  echo "REFUSED: HawEdit host locks support only CPython 3.11/3.12 on Linux/Windows" >&2
  exit 2
}
lock="$here/requirements/host-${scope}-${identity}.txt"
if [[ ! -f "$lock" ]]; then
  echo "REFUSED: target host dependency lock is missing: $lock" >&2
  exit 2
fi

extras=()
if [[ "$scope" == gate ]]; then extras=(--extra dev --extra media); fi
if [[ "$scope" == models ]]; then extras=(--extra models); fi

# Bind target + semantic dependency contract before the first network request. Running the
# checker by path under -I means this works in a brand-new venv and cannot import another clone.
"$python" -I "$here/src/hawedit/environment.py" \
  --validate-lock-only --project-root "$here" --lock "$lock" "${extras[@]}" >/dev/null

# Every package, including pip/setuptools, has one exact target wheel hash in the lock. No sdist
# build or unhashed transitive requirement is allowed. pip's hash mode fails if the graph grows.
"$python" -m pip install \
  --disable-pip-version-check --no-input --require-hashes --only-binary=:all: \
  -r "$lock"
"$python" -m pip check

if [[ "$mode" == --dependencies-only ]]; then
  exit 0
fi

# Build isolation would create a private environment and resolve build requirements again.
# The lock already installed the exact setuptools backend, so use it and install no dependencies.
"$python" -m pip install \
  --disable-pip-version-check --no-input --no-deps --no-build-isolation -e "$here"
"$python" -m pip check
"$python" -I "$here/src/hawedit/environment.py" \
  --project-root "$here" --lock "$lock" "${extras[@]}" >/dev/null

printf 'host environment locked: %s (%s)\n' "$identity" "$scope"
