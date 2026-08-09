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
models_root="${HAWEDIT_MODELS_DIR:-$here/models}"
export HAWEDIT_MODELS_DIR="$models_root"

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
failures=0

# --- what does §7 actually require, and is any of it unfetchable? ---------------------------
if ! plan="$("$PY" - "$models_root" "${1:-}" <<'PYEOF'
import sys
from pathlib import Path
from hawedit.models import ModelStore, SourceNotConfigured
from hawedit.registry import REGISTRY, Provisioning, assert_commercially_usable

root, only = Path(sys.argv[1]).resolve(), (sys.argv[2] if len(sys.argv) > 2 else "")
store = ModelStore(root=root)
if only:
    requested = REGISTRY.get(only)
    if requested is None or requested.provisioning is not Provisioning.WEIGHTS:
        print(f"REFUSED: {only!r} is not a downloadable checkpoint", file=sys.stderr)
        raise SystemExit(1)

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
)"; then
  echo "✗ could not build a verified model provisioning plan" >&2
  "$PY" -m hawedit.models
  exit 1
fi

if grep -q '^UNCONFIGURED' <<<"$plan"; then
  failures=1
  names="$(grep '^UNCONFIGURED' <<<"$plan" | cut -f2)"
  echo "⚠ no download source configured for: ${names}" >&2
  echo "  §7 names these as checkpoints, not repository ids, and this script will not guess." >&2
  echo "  Add them to ${models_root}/sources.json, e.g." >&2
  echo '    { "Qwen3-VL-Embedding-2B": "<org>/<repo>" }' >&2
  echo >&2
  plan="$(grep -v '^UNCONFIGURED' <<<"$plan")"
fi

if [[ -z "${plan//[[:space:]]/}" ]]; then
  echo "nothing to fetch — every targeted configured checkpoint is verified."
  "$PY" -m hawedit.models
  exit "$failures"
fi

# --- capacity, before an hour is spent finding out ------------------------------------------
free_gb="$(df -BG --output=avail "$models_root" | tail -1 | tr -dc '0-9')"
echo "==> ${free_gb} GB free at ${models_root}; the full §7 set is roughly 50 GB"
if (( free_gb < 55 )); then
  echo "⚠ this may not be enough for every checkpoint — fetching what fits, in order." >&2
fi

"$PY" -c 'from importlib.metadata import version; raise SystemExit(version("huggingface_hub") != "0.36.2")' 2>/dev/null || {
  echo "==> installing huggingface_hub 0.36.2 (Apache-2.0)"
  if ! "$PY" -m pip install -q "huggingface_hub==0.36.2"; then
    echo "✗ failed to install the pinned Hugging Face download client" >&2
    "$PY" -m hawedit.models
    exit 1
  fi
}

while IFS=$'\t' read -r model_id source gated dest; do
  [[ -z "$model_id" ]] && continue
  echo
  echo "==> ${model_id}"
  echo "    from ${source} -> ${dest}"
  if [[ "$gated" == "1" && -z "${HF_TOKEN:-}" ]]; then
    echo "    SKIPPED: ${source} is a gated repo (§3 Stage 0) and HF_TOKEN is not set." >&2
    echo "    Accept the licence on Hugging Face, then export HF_TOKEN." >&2
    failures=1
    continue
  fi
  if ! "$PY" - "$model_id" "$source" "$dest" <<'PYEOF'
import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

from hawedit.models import (
    ModelStore,
    RevisionNotPinned,
    _path_is_reparse,
    _publish_checkpoint_directory,
    checkpoint_publish_lock,
)

model_id, source, destination = sys.argv[1], sys.argv[2], Path(sys.argv[3])
store = ModelStore()
# Without `revision=` this resolves whatever the branch head points at today, so two machines
# hold different weights under one name and every number measured against them is about
# weights nobody can identify. Refused rather than resolved silently, exactly as an
# unconfigured repo id is (D-022, D-073).
try:
    revision = store.revision_for(source)
except RevisionNotPinned as exc:
    print(f"    REFUSED: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
print(f"    revision {revision}")
with checkpoint_publish_lock(destination):
    if os.path.lexists(destination):
        if _path_is_reparse(destination) or not destination.is_dir():
            print(
                f"    REFUSED: existing final path is not a regular checkpoint directory: "
                f"{destination}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        try:
            store.verify_checkpoint(model_id, destination)
        except Exception as exc:
            print(
                f"    REFUSED: existing final checkpoint is invalid and was preserved: "
                f"{type(exc).__name__}: {exc}"[:800],
                file=sys.stderr,
            )
            print(
                "    Move or quarantine that directory explicitly before retrying; HawEdit "
                "will not overwrite user data.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        print(f"    already verified: {destination}")
        raise SystemExit(0)

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.download-{revision}")
    if os.path.lexists(staging):
        if _path_is_reparse(staging) or not staging.is_dir():
            print(f"    REFUSED: unsafe private staging path: {staging}", file=sys.stderr)
            raise SystemExit(1)
        print(f"    resuming private staging: {staging}")
    else:
        staging.mkdir(mode=0o700)
    print(f"    private staging: {staging}")
    try:
        snapshot_download(
            repo_id=source,
            revision=revision,
            local_dir=str(staging),
            resume_download=True,
        )
        report = store.verify_checkpoint(model_id, staging)
        _publish_checkpoint_directory(staging, destination)
    except Exception as exc:  # network, auth, verification, publication, or a repo that moved
        print(f"    FAILED: {type(exc).__name__}: {exc}"[:400], file=sys.stderr)
        print(
            "    Check network access to huggingface.co, HF_TOKEN for gated repos, that "
            "the repo id in models/sources.json is right, and that the pinned revision in "
            "models/revisions.json still exists in that repo.",
            file=sys.stderr,
        )
        print(f"    Preserved private staging for diagnosis/resume: {staging}", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        f"    done: {destination} ({report.files_verified} files, {report.size_bytes} bytes)"
    )
PYEOF
  then
    echo "    (continuing with the remaining components)" >&2
    failures=1
  fi
done <<<"$plan"

echo
"$PY" -m hawedit.models
exit "$failures"
