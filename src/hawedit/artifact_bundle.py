"""Atomic publication for the five files that make one delivered clip.

Files are built in a unique hidden sibling directory. A completed bundle becomes visible by
renaming that non-empty directory into its final name only after the exact expected set exists,
is non-empty, and has been flushed. A failed or competing worker can discard only its private
directory; it cannot replace the published winner.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hawedit.transcripts import validate_media_id

__all__ = ["ArtifactBundle", "BundleAlreadyExists", "BundleError"]

_SUFFIXES: Final = ("ass", "mp4", "srt", "edl", "json")


class BundleError(RuntimeError):
    """A delivery bundle cannot be safely completed or cleaned up."""


class BundleAlreadyExists(BundleError):
    """Another completed bundle already owns the final name."""


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    root: Path
    bundle_id: str
    staging_dir: Path
    final_dir: Path

    @classmethod
    def create(cls, root: Path, bundle_id: str) -> ArtifactBundle:
        safe_id = validate_media_id(bundle_id)
        try:
            resolved_root = root.resolve()
            resolved_root.mkdir(parents=True, exist_ok=True)
            final_dir = resolved_root / safe_id
            if os.path.lexists(final_dir):
                raise BundleAlreadyExists(f"refusing to overwrite completed bundle {final_dir}")
            staging_dir = Path(
                tempfile.mkdtemp(prefix=f".{safe_id}.", suffix=".staging", dir=resolved_root)
            )
        except BundleAlreadyExists:
            raise
        except OSError as exc:
            raise BundleError(
                f"could not create private delivery bundle under {root}: {exc}"
            ) from exc
        return cls(resolved_root, safe_id, staging_dir, final_dir)

    @classmethod
    def final_paths_for(cls, root: Path, bundle_id: str) -> tuple[Path, ...]:
        safe_id = validate_media_id(bundle_id)
        final_dir = root / safe_id
        return tuple(final_dir / f"{safe_id}.{suffix}" for suffix in _SUFFIXES)

    @property
    def staging_paths(self) -> tuple[Path, ...]:
        return tuple(self.staging_dir / f"{self.bundle_id}.{suffix}" for suffix in _SUFFIXES)

    @property
    def final_paths(self) -> tuple[Path, ...]:
        return self.final_paths_for(self.root, self.bundle_id)

    def staged_path(self, suffix: str) -> Path:
        try:
            index = _SUFFIXES.index(suffix)
        except ValueError as exc:
            raise BundleError(f"{suffix!r} is not a delivery artifact suffix") from exc
        return self.staging_paths[index]

    def final_path(self, suffix: str) -> Path:
        try:
            index = _SUFFIXES.index(suffix)
        except ValueError as exc:
            raise BundleError(f"{suffix!r} is not a delivery artifact suffix") from exc
        return self.final_paths[index]

    def write_text(self, suffix: str, payload: str) -> Path:
        if not payload:
            raise BundleError(f"refusing to stage an empty {suffix} artifact")
        path = self.staged_path(suffix)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise BundleError(f"could not stage {suffix} artifact {path}: {exc}") from exc
        return path

    def _validate(self) -> None:
        expected = {path.name: path for path in self.staging_paths}
        try:
            actual = {path.name: path for path in self.staging_dir.iterdir()}
        except OSError as exc:
            raise BundleError(
                f"could not inspect private bundle {self.staging_dir}: {exc}"
            ) from exc
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            raise BundleError(
                f"private bundle is not the exact delivery set; missing={missing}, extra={extra}"
            )
        for name, path in actual.items():
            if path.is_symlink() or not path.is_file():
                raise BundleError(f"delivery artifact {name} is not a regular file")
            if path.stat().st_size <= 0:
                raise BundleError(f"delivery artifact {name} is empty")
            try:
                # Windows' FlushFileBuffers path rejects a read-only descriptor with EBADF.
                # These are private files owned by this writer, so r+b is safe and portable.
                with path.open("r+b") as artifact:
                    os.fsync(artifact.fileno())
            except OSError as exc:
                raise BundleError(f"could not flush delivery artifact {path}: {exc}") from exc

    def publish(self) -> tuple[Path, ...]:
        self._validate()
        if os.path.lexists(self.final_dir):
            raise BundleAlreadyExists(f"refusing to overwrite completed bundle {self.final_dir}")
        try:
            os.rename(self.staging_dir, self.final_dir)
        except OSError as exc:
            if os.path.lexists(self.final_dir):
                raise BundleAlreadyExists(
                    f"refusing to overwrite completed bundle {self.final_dir}; another worker won"
                ) from exc
            raise BundleError(
                f"could not atomically publish delivery bundle {self.final_dir}: {exc}"
            ) from exc
        return self.final_paths

    def discard(self) -> None:
        if not os.path.lexists(self.staging_dir):
            return
        expected_names = {path.name for path in self.staging_paths}
        try:
            children = tuple(self.staging_dir.iterdir())
        except OSError as exc:
            raise BundleError(
                f"could not inspect private bundle {self.staging_dir}: {exc}"
            ) from exc
        unexpected = [path for path in children if path.name not in expected_names or path.is_dir()]
        if unexpected:
            raise BundleError(
                "refusing to recursively remove unexpected private-bundle content: "
                + ", ".join(str(path) for path in unexpected)
            )
        try:
            for path in children:
                path.unlink(missing_ok=True)
            self.staging_dir.rmdir()
        except OSError as exc:
            raise BundleError(
                f"could not discard private bundle {self.staging_dir}: {exc}"
            ) from exc
