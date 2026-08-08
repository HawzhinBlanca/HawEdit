"""Build and publish a reproducible HawEdit wheel from one clean Git revision.

A successful ``pip wheel`` exit is not release evidence. This command derives
``SOURCE_DATE_EPOCH`` from the source commit, builds twice in independent directories, requires
the wheel bytes to have the same SHA-256, inspects the archive for HawEdit's runtime data, and
only then atomically publishes a directory containing the wheel, ``SHA256SUMS`` and stable
provenance JSON.

The output directory is write-once. Re-running against an existing release refuses instead of
replacing an artifact that may already have been distributed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["ReleaseArtifact", "ReleaseError", "build_reproducible_wheel", "main"]

_REQUIRED_WHEEL_MEMBERS: Final = (
    "hawedit/release.py",
    "share/hawedit/assets/fonts/NotoNaskhArabic-Regular.ttf",
    "share/hawedit/assets/fonts/OFL.txt",
    "share/hawedit/models/sources.json",
)


class ReleaseError(RuntimeError):
    """The source or artifact is not strong enough to publish as a release."""


@dataclass(frozen=True, slots=True)
class ReleaseArtifact:
    output_dir: Path
    wheel: Path
    checksum_file: Path
    provenance_file: Path
    revision: str
    source_date_epoch: int
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "output_dir": str(self.output_dir),
            "wheel": str(self.wheel),
            "checksum_file": str(self.checksum_file),
            "provenance_file": str(self.provenance_file),
            "revision": self.revision,
            "source_date_epoch": self.source_date_epoch,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ReleaseError(f"could not run {command[0]!r}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2_000:]
        raise ReleaseError(
            f"command failed with exit {result.returncode}: {' '.join(command)}\n{detail}"
        )
    return result.stdout.strip()


def _source_identity(project_root: Path) -> tuple[str, int]:
    if not (project_root / "pyproject.toml").is_file():
        raise ReleaseError(f"no pyproject.toml at release root {project_root}")

    top = Path(_run(["git", "rev-parse", "--show-toplevel"], cwd=project_root)).resolve()
    if top != project_root:
        raise ReleaseError(
            f"release root {project_root} is not the Git root {top}; build the whole checkout"
        )

    dirty = _run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=project_root)
    if dirty:
        paths = ", ".join(line[3:] for line in dirty.splitlines()[:8])
        raise ReleaseError(
            f"refusing to release a dirty checkout ({paths}); commit explicit source paths first"
        )

    revision = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=project_root)
    epoch_text = _run(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=project_root)
    try:
        epoch = int(epoch_text)
    except ValueError as exc:
        raise ReleaseError(f"Git returned an invalid commit timestamp {epoch_text!r}") from exc
    if epoch < 315_532_800:  # ZIP timestamps cannot precede 1980-01-01.
        raise ReleaseError(f"commit timestamp {epoch} predates the wheel/ZIP timestamp range")
    return revision, epoch


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_once(project_root: Path, destination: Path, python: Path, epoch: int) -> Path:
    destination.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "SOURCE_DATE_EPOCH": str(epoch),
            "PYTHONHASHSEED": "0",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    _run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            str(project_root),
            "--no-deps",
            "--no-build-isolation",
            "--no-cache-dir",
            "--wheel-dir",
            str(destination),
        ],
        cwd=project_root,
        env=env,
    )
    wheels = tuple(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise ReleaseError(
            f"one source tree must produce exactly one wheel, found {len(wheels)} in {destination}"
        )
    return wheels[0]


def _validate_hawedit_wheel(wheel: Path) -> None:
    try:
        with zipfile.ZipFile(wheel) as archive:
            corrupt = archive.testzip()
            names = tuple(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError(f"built wheel is not a readable ZIP archive: {wheel}") from exc
    if corrupt is not None:
        raise ReleaseError(f"built wheel contains a corrupt member: {corrupt}")
    if not any(name.endswith(".dist-info/METADATA") for name in names):
        raise ReleaseError("built wheel has no .dist-info/METADATA")
    missing = [
        required
        for required in _REQUIRED_WHEEL_MEMBERS
        if not any(name.endswith(required) for name in names)
    ]
    if missing:
        raise ReleaseError("built wheel is missing runtime files: " + ", ".join(missing))


def _copy_synced(source: Path, destination: Path) -> None:
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        outgoing.flush()
        os.fsync(outgoing.fileno())


def _write_synced(payload: bytes, destination: Path) -> None:
    with destination.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _publish_directory(staging: Path, output: Path) -> None:
    if os.path.lexists(output):
        raise ReleaseError(f"refusing to overwrite release directory {output}")
    try:
        # Staging is a sibling, so the rename is one-filesystem and atomic. A populated winner
        # cannot be replaced by os.rename on POSIX or Windows.
        os.rename(staging, output)
    except OSError as exc:
        if os.path.lexists(output):
            raise ReleaseError(
                f"refusing to overwrite release directory {output}; another build published it"
            ) from exc
        raise ReleaseError(
            f"could not atomically publish release directory {output}: {exc}"
        ) from exc


def build_reproducible_wheel(
    project_root: Path,
    output_dir: Path | None = None,
    *,
    python: Path = Path(sys.executable),
) -> ReleaseArtifact:
    """Build twice from clean HEAD and atomically publish only byte-identical wheels."""
    root = project_root.resolve()
    revision, epoch = _source_identity(root)
    output = (
        output_dir.resolve()
        if output_dir is not None
        else root / "dist" / f"hawedit-{revision[:12]}"
    )
    if output == root or output.is_relative_to(root / ".git"):
        raise ReleaseError(f"unsafe release output directory {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(output):
        raise ReleaseError(f"refusing to overwrite release directory {output}")

    with tempfile.TemporaryDirectory(prefix="hawedit-wheel-build-") as temporary:
        temporary_root = Path(temporary)
        first = _build_once(root, temporary_root / "first", python, epoch)
        second = _build_once(root, temporary_root / "second", python, epoch)
        first_digest = _sha256(first)
        second_digest = _sha256(second)
        if first.name != second.name or first_digest != second_digest:
            raise ReleaseError(
                "wheel build is not reproducible: "
                f"{first.name} {first_digest} != {second.name} {second_digest}"
            )
        _validate_hawedit_wheel(first)

        # Refuse if HEAD or the worktree changed while the two builds were running.
        if _source_identity(root) != (revision, epoch):
            raise ReleaseError("source revision changed during the release build")

        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
        try:
            staged_wheel = staging / first.name
            _copy_synced(first, staged_wheel)
            size = staged_wheel.stat().st_size
            checksum_name = "SHA256SUMS"
            provenance_name = "release-provenance.json"
            _write_synced(f"{first_digest}  {first.name}\n".encode(), staging / checksum_name)
            provenance = {
                "schema": 1,
                "revision": revision,
                "source_date_epoch": epoch,
                "wheel": first.name,
                "sha256": first_digest,
                "size_bytes": size,
            }
            _write_synced(
                (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode(),
                staging / provenance_name,
            )
            _publish_directory(staging, output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    return ReleaseArtifact(
        output_dir=output,
        wheel=output / first.name,
        checksum_file=output / "SHA256SUMS",
        provenance_file=output / "release-provenance.json",
        revision=revision,
        source_date_epoch=epoch,
        sha256=first_digest,
        size_bytes=size,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="build HawEdit twice and publish only a byte-reproducible wheel"
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        artifact = build_reproducible_wheel(args.project_root, args.output_dir)
    except ReleaseError as exc:
        parser.exit(1, f"REFUSED: {exc}\n")
    print(json.dumps(artifact.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the installed entry point
    raise SystemExit(main())
