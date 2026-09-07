"""Stage checkpoint and resume engine — Claim R3.

Records atomic completion markers (`work/<stage>.done`) with input hashes so
interrupted pipeline executions can resume seamlessly without recomputing completed stages.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any


def hash_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class StageCheckpoint:
    schema: int = 1
    stage_name: str = ""
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    input_hashes: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageCheckpoint:
        return cls(
            schema=int(data.get("schema", 1)),
            stage_name=str(data.get("stage_name", "")),
            completed_at=str(data.get("completed_at", "")),
            input_hashes=dict(data.get("input_hashes", {})),
            metadata=dict(data.get("metadata", {})),
        )


def checkpoint_path_for(work_dir: Path, stage_name: str) -> Path:
    """Return the checkpoint marker path for a given stage."""
    return work_dir / f"{stage_name}.done"


def save_stage_checkpoint(
    work_dir: Path,
    stage_name: str,
    input_hashes: dict[str, str],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Atomically record a stage completion marker."""
    work_dir.mkdir(parents=True, exist_ok=True)
    target = checkpoint_path_for(work_dir, stage_name)
    staging = work_dir / f".{stage_name}.done.tmp"

    checkpoint = StageCheckpoint(
        stage_name=stage_name,
        input_hashes=input_hashes,
        metadata=metadata or {},
    )
    staging.write_text(checkpoint.to_json(), encoding="utf-8")
    staging.replace(target)
    return target


def is_stage_complete(
    work_dir: Path,
    stage_name: str,
    input_hashes: dict[str, str],
) -> bool:
    """Check whether a stage was completed with matching input hashes."""
    target = checkpoint_path_for(work_dir, stage_name)
    if not target.is_file():
        return False

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        saved = StageCheckpoint.from_dict(data)
    except (json.JSONDecodeError, OSError, ValueError):
        return False

    if saved.stage_name != stage_name:
        return False

    # All expected input hashes must match the recorded checkpoint
    for key, expected_hash in input_hashes.items():
        if not expected_hash:
            continue
        if saved.input_hashes.get(key) != expected_hash:
            return False

    return True


def load_stage_checkpoint(work_dir: Path, stage_name: str) -> StageCheckpoint | None:
    """Load a stage checkpoint if valid, or return None."""
    target = checkpoint_path_for(work_dir, stage_name)
    if not target.is_file():
        return None

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return StageCheckpoint.from_dict(data)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def clear_stage_checkpoint(work_dir: Path, stage_name: str) -> bool:
    """Remove a stage checkpoint marker if present."""
    target = checkpoint_path_for(work_dir, stage_name)
    if target.is_file():
        target.unlink(missing_ok=True)
        return True
    return False
