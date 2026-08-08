#!/usr/bin/env bash
# Download §7's model weights into models/ — driven by the registry, not by a hard-coded list.
#
# The list of what may be fetched comes from `hawedit.registry.REGISTRY`, so this script
# cannot download a model the blueprint does not permit, and cannot silently skip one it
# requires. NonCommercial licences are refused before any bytes move.
#
# Usage:
#   bash scripts/fetch-models.sh              # everything §7 needs
#   bash scripts/fetch-models.sh --status     # what is already here
#   bash scripts/fetch-models.sh <model_id>   # one component
#
# Requirements:
#   - network access to huggingface.co
#   - HF_TOKEN in the environment for gated repos (§3 Stage 0: Community-1 is gated)
#   - ~50 GB free disk for the full §7 set
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
models_root="${HAWEDIT_MODELS:-$here/models}"

# `bin/` on POSIX, `Scripts/` on Windows — and hawapc01, the box that will actually hold 50 GB
# of §7 weights, is Windows. Deliberately spelled out here rather than sourced from a shared
# file: verify.sh is the gate and must stand alone, so this stays the same six lines in both
# places instead of one of them growing a dependency the other cannot have.
if [[ -z "${PY:-}" ]]; then
  for candidate in "$here/.venv/bin/python" "$here/.venv/Scripts/python.exe"; do
    if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
  done
fi
if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  echo "✗ no interpreter in .venv — run: bash scripts/setup.sh" >&2
  exit 2
fi

if [[ "${1:-}" == "--status" ]]; then
  exec "$PY" -m hawedit.models
fi

mkdir -p "$models_root"

# --- what does §7 actually require, and is any of it unfetchable? ---------------------------
plan="$("$PY" - "$models_root" "${1:-}" <<'PYEOF'
import sys
from pathlib import Path
from hawedit.models import ModelStore, SourceNotConfigured
from hawedit.registry import Provisioning, assert_commercially_usable

root, only = Path(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "")
store = ModelStore(root=root)

unconfigured, lines = [], []
for entry in store.missing_weights():
    if only and entry.model_id != only:
        continue
    # NonCommercial is a hard reject — checked before a single byte moves.
    assert_commercially_usable(entry)
    try:
        source = store.source_for(entry)
    except SourceNotConfigured:
        unconfigured.append(entry.model_id)
        continue
    lines.append(f"{entry.model_id}\t{source}\t{int(entry.gated)}\t{store.path_for(entry)}")

if unconfigured:
    print("UNCONFIGURED\t" + ",".join(unconfigured))
print("\n".join(lines))
PYEOF
)"

if grep -q '^UNCONFIGURED' <<<"$plan"; then
  names="$(grep '^UNCONFIGURED' <<<"$plan" | cut -f2)"
  echo "⚠ no download source configured for: ${names}" >&2
  echo "  §7 names these as checkpoints, not repository ids, and this script will not guess." >&2
  echo "  Add them to ${models_root}/sources.json, e.g." >&2
  echo '    { "Qwen3-VL-Embedding-2B": "<org>/<repo>" }' >&2
  echo >&2
  plan="$(grep -v '^UNCONFIGURED' <<<"$plan")"
fi

if [[ -z "${plan//[[:space:]]/}" ]]; then
  echo "nothing to fetch — every configured §7 checkpoint is already present."
  exec "$PY" -m hawedit.models
fi

# --- capacity, before an hour is spent finding out ------------------------------------------
free_gb="$(df -BG --output=avail "$models_root" | tail -1 | tr -dc '0-9')"
echo "==> ${free_gb} GB free at ${models_root}; the full §7 set is roughly 50 GB"
if (( free_gb < 55 )); then
  echo "⚠ this may not be enough for every checkpoint — fetching what fits, in order." >&2
fi

"$PY" -c 'from importlib.metadata import version; raise SystemExit(version("huggingface_hub") != "0.36.2")' 2>/dev/null || {
  echo "==> installing huggingface_hub 0.36.2 (Apache-2.0)"
  "$PY" -m pip install -q "huggingface_hub==0.36.2"
}

while IFS=$'\t' read -r model_id source gated dest; do
  [[ -z "$model_id" ]] && continue
  echo
  echo "==> ${model_id}"
  echo "    from ${source} -> ${dest}"
  if [[ "$gated" == "1" && -z "${HF_TOKEN:-}" ]]; then
    echo "    SKIPPED: ${source} is a gated repo (§3 Stage 0) and HF_TOKEN is not set." >&2
    echo "    Accept the licence on Hugging Face, then export HF_TOKEN." >&2
    continue
  fi
  if ! "$PY" - "$source" "$dest" <<'PYEOF'
import sys
from huggingface_hub import snapshot_download

from hawedit.models import ModelStore, RevisionNotPinned

source, dest = sys.argv[1], sys.argv[2]
# Without `revision=` this resolves whatever the branch head points at today, so two machines
# hold different weights under one name and every number measured against them is about
# weights nobody can identify. Refused rather than resolved silently, exactly as an
# unconfigured repo id is (D-022, D-073).
try:
    revision = ModelStore().revision_for(source)
except RevisionNotPinned as exc:
    print(f"    REFUSED: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
print(f"    revision {revision}")
try:
    snapshot_download(repo_id=source, revision=revision, local_dir=dest)
except Exception as exc:  # network, auth, or a repo that moved
    print(f"    FAILED: {type(exc).__name__}: {exc}"[:400], file=sys.stderr)
    print(
        "    Check network access to huggingface.co, HF_TOKEN for gated repos, that "
        "the repo id in models/sources.json is right, and that the pinned revision in "
        "models/revisions.json still exists in that repo.",
        file=sys.stderr,
    )
    raise SystemExit(1) from None
print(f"    done: {dest}")
PYEOF
  then
    echo "    (continuing with the remaining components)" >&2
  fi
done <<<"$plan"

echo
exec "$PY" -m hawedit.models
