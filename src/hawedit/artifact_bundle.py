"""Atomic publication for the five files that make one delivered clip.

Files are built in a unique hidden sibling directory. A completed bundle becomes visible by
renaming that non-empty directory into its final name only after the exact expected set exists,
is non-empty, and has been flushed. A failed or competing worker can discard only its private
directory; it cannot replace the published winner.
"""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.transcripts import validate_media_id

__all__ = ["ArtifactBundle", "BundleAlreadyExists", "BundleError"]

_SUFFIXES: Final = ("ass", "mp4", "srt", "edl", "json")
_REPARSE_FLAG: Final = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_DirectoryIdentity = tuple[int, int]
_FileIdentity = tuple[int, int, int, int, int]


class BundleError(RuntimeError):
    """A delivery bundle cannot be safely completed or cleaned up."""


class BundleAlreadyExists(BundleError):
    """Another completed bundle already owns the final name."""


def _bound_directory(path: Path, *, label: str) -> _DirectoryIdentity:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise BundleError(f"could not inspect {label} {path}: {exc}") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_FLAG)
    ):
        raise BundleError(
            f"{label} must be one real directory, not a link or reparse point: {path}"
        )
    return metadata.st_dev, metadata.st_ino


def _assert_directory_identity(path: Path, expected: _DirectoryIdentity, *, label: str) -> None:
    actual = _bound_directory(path, label=label)
    if actual != expected:
        raise BundleError(f"{label} identity changed while the delivery bundle was active: {path}")


def _file_identity(metadata: os.stat_result) -> _FileIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_nlink,
    )


def _flush_bound_artifact(path: Path, *, name: str) -> _FileIdentity:
    """Flush one private regular file without following a replacement between checks."""
    try:
        before = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or bool(getattr(before, "st_file_attributes", 0) & _REPARSE_FLAG)
        ):
            raise BundleError(f"delivery artifact {name} is not one regular file")
        if before.st_nlink != 1:
            raise BundleError(f"delivery artifact {name} must not be hardlinked")
        if before.st_size <= 0:
            raise BundleError(f"delivery artifact {name} is empty")

        flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            expected = _file_identity(before)
            if (
                _file_identity(os.fstat(descriptor)) != expected
                or _file_identity(os.lstat(path)) != expected
            ):
                raise BundleError(
                    f"delivery artifact {name} identity changed while it was being validated"
                )
            os.fsync(descriptor)
            if (
                _file_identity(os.fstat(descriptor)) != expected
                or _file_identity(os.lstat(path)) != expected
            ):
                raise BundleError(f"delivery artifact {name} changed while it was being flushed")
        finally:
            os.close(descriptor)
    except BundleError:
        raise
    except OSError as exc:
        raise BundleError(f"could not validate delivery artifact {path}: {exc}") from exc
    return expected


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    root: Path
    bundle_id: str
    staging_dir: Path
    final_dir: Path
    _root_identity: _DirectoryIdentity
    _staging_identity: _DirectoryIdentity

    @classmethod
    def create(cls, root: Path, bundle_id: str) -> ArtifactBundle:
        safe_id = validate_media_id(bundle_id)
        lexical_root = Path(os.path.abspath(root))
        try:
            lexical_root.mkdir(parents=True, exist_ok=True)
            root_identity = _bound_directory(lexical_root, label="delivery root")
            final_dir = lexical_root / safe_id
            if os.path.lexists(final_dir):
                raise BundleAlreadyExists(f"refusing to overwrite completed bundle {final_dir}")
            staging_dir = Path(
                tempfile.mkdtemp(prefix=f".{safe_id}.", suffix=".staging", dir=lexical_root)
            )
            staging_identity = _bound_directory(staging_dir, label="private delivery bundle")
            _assert_directory_identity(lexical_root, root_identity, label="delivery root")
        except BundleAlreadyExists:
            raise
        except BundleError:
            raise
        except OSError as exc:
            raise BundleError(
                f"could not create private delivery bundle under {root}: {exc}"
            ) from exc
        return cls(
            lexical_root,
            safe_id,
            staging_dir,
            final_dir,
            root_identity,
            staging_identity,
        )

    def _assert_boundaries(self) -> None:
        _assert_directory_identity(self.root, self._root_identity, label="delivery root")
        _assert_directory_identity(
            self.staging_dir,
            self._staging_identity,
            label="private delivery bundle",
        )

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
        self._assert_boundaries()
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
            self._assert_boundaries()
        except BundleError:
            raise
        except OSError as exc:
            raise BundleError(f"could not stage {suffix} artifact {path}: {exc}") from exc
        return path

    def _validate(self) -> dict[str, _FileIdentity]:
        self._assert_boundaries()
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
        identities = {name: _flush_bound_artifact(path, name=name) for name, path in actual.items()}
        self._assert_boundaries()
        return identities

    def _validate_published(self, expected: dict[str, _FileIdentity]) -> None:
        for name, identity in expected.items():
            path = self.final_dir / name
            try:
                actual = os.lstat(path)
            except OSError as exc:
                raise BundleError(f"could not revalidate published artifact {path}: {exc}") from exc
            if _file_identity(actual) != identity:
                raise BundleError(f"published delivery artifact identity changed: {path}")

    def publish(self) -> tuple[Path, ...]:
        identities = self._validate()
        try:
            rename_directory_noreplace(self.staging_dir, self.final_dir)
        except FileExistsError as exc:
            raise BundleAlreadyExists(
                f"refusing to overwrite completed bundle {self.final_dir}; another worker won"
            ) from exc
        except OSError as exc:
            raise BundleError(
                f"could not atomically publish delivery bundle {self.final_dir}: {exc}"
            ) from exc
        _assert_directory_identity(self.root, self._root_identity, label="delivery root")
        _assert_directory_identity(
            self.final_dir,
            self._staging_identity,
            label="published delivery bundle",
        )
        self._validate_published(identities)
        _assert_directory_identity(self.root, self._root_identity, label="delivery root")
        _assert_directory_identity(
            self.final_dir,
            self._staging_identity,
            label="published delivery bundle",
        )
        return self.final_paths

    def discard(self) -> None:
        if not os.path.lexists(self.staging_dir):
            return
        self._assert_boundaries()
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
