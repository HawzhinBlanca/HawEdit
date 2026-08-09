"""Provision the wheel-safe WSL2 runtime for canonical OmniASR on Windows.

The official fairseq2 native extension is not published for Windows. HawEdit therefore keeps a
Linux runtime in the user's local application-data directory. Only HawEdit's pure Python package
is copied into a source-fingerprinted snapshot; native dependencies live in one shared Linux venv
inside WSL2. Upgrading the host package therefore cannot silently execute an older worker and
does not duplicate the multi-gigabyte environment.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final, cast

__all__ = [
    "WSL_MODEL_METADATA_DIRECTORY",
    "WslRuntimeError",
    "WslRuntimeProbe",
    "WslRuntimeReceipt",
    "default_wsl_runtime",
    "default_wsl_source",
    "load_wsl_runtime_receipt",
    "package_digest",
    "package_fingerprint",
    "probe_wsl_runtime",
    "provision_wsl_runtime",
    "wsl_path",
]


_RECEIPT_SCHEMA: Final = 2
_ENVIRONMENT_SCHEMA: Final = 1
_EXPECTED_PACKAGES: Final[Mapping[str, str]] = {
    "fairseq2": "0.6",
    "fonttools": "4.60.2",
    "klpt": "0.1.7",
    "omnilingual-asr": "0.2.0",
    "qwen-asr": "0.0.6",
    "torch": "2.8.0",
    "torchaudio": "2.8.0",
}
_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[Path, threading.Lock] = {}
_WINDOWS_LOCK_TIMEOUT_SECONDS: Final = 6 * 60 * 60
_WINDOWS_HOST: Final = os.name == "nt"
WSL_MODEL_METADATA_DIRECTORY: Final = ".hawedit-model-metadata"
_MODEL_METADATA_FILES: Final = ("sources.json", "revisions.json", "integrity.json")


class WslRuntimeError(RuntimeError):
    """A WSL receipt or its versioned environment generation is not trustworthy."""


@dataclass(frozen=True, slots=True)
class WslRuntimeReceipt:
    source_root: Path
    source_sha256: str
    generation: str
    generation_root: Path
    distro: str
    uid: int
    home: str
    python_version: str
    packages: Mapping[str, str]
    asset_cache: str
    asset_bytes: int
    cuda_device_count: int


@dataclass(frozen=True, slots=True)
class WslRuntimeProbe:
    receipt: WslRuntimeReceipt
    files_verified: int
    size_bytes: int


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _validate_plain_directory(path: Path, label: str) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise WslRuntimeError(f"cannot inspect {label} {path}: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse_or_symlink(path):
        raise WslRuntimeError(f"{label} must be an unlinked regular directory: {path}")


def _ensure_plain_directory(path: Path, label: str) -> None:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise WslRuntimeError(f"cannot create {label} {path}: {exc}") from exc
    _validate_plain_directory(path, label)


def _runtime_root_path(path: Path, *, create: bool) -> Path:
    unresolved = path.absolute()
    try:
        os.lstat(unresolved)
    except FileNotFoundError:
        if not create:
            return unresolved
        try:
            unresolved.mkdir(parents=True)
        except OSError as exc:
            raise WslRuntimeError(
                f"cannot create OmniASR runtime root {unresolved}: {exc}"
            ) from exc
    except OSError as exc:
        raise WslRuntimeError(f"cannot inspect OmniASR runtime root {unresolved}: {exc}") from exc
    _validate_plain_directory(unresolved, "OmniASR runtime root")
    return unresolved.resolve()


def _package_files(package_dir: Path, *, reject_bytecode_cache: bool) -> list[Path]:
    if not package_dir.is_dir() or _is_reparse_or_symlink(package_dir):
        raise RuntimeError(f"HawEdit worker source is not a regular directory: {package_dir}")
    files: list[Path] = []
    for path in package_dir.rglob("*"):
        relative = path.relative_to(package_dir)
        if "__pycache__" in relative.parts:
            if reject_bytecode_cache:
                raise RuntimeError(
                    f"HawEdit worker snapshot must not contain bytecode caches: {path}"
                )
            continue
        if _is_reparse_or_symlink(path):
            raise RuntimeError(f"HawEdit worker source must not contain links: {path}")
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix != ".py":
            raise RuntimeError(f"unexpected HawEdit worker source member: {path}")
        files.append(path)
    if not files:
        raise RuntimeError(f"no HawEdit Python modules found at {package_dir}")
    return sorted(files, key=lambda path: path.relative_to(package_dir).as_posix())


def _read_bound_regular_file(path: Path, label: str, *, require_single_link: bool) -> bytes:
    """Read one immutable input without following a link or accepting a raced pathname."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot safely open {label} {path}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (require_single_link and opened.st_nlink != 1)
            or (require_single_link and named.st_nlink != 1)
            or _is_reparse_or_symlink(path)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise RuntimeError(f"{label} must be one unlinked regular file: {path}")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            payload = stream.read()
            after = os.fstat(stream.fileno())
        current = os.lstat(path)
        descriptor_before = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        )
        descriptor_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        path_before = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            named.st_ctime_ns,
            named.st_nlink,
        )
        path_after = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
            current.st_nlink,
        )
        # Windows' CRT descriptor stat reports ``ctime`` as mtime while pathname stat reports
        # the filesystem creation/change time. Compare ctime only within the same API; the
        # cross-API binding deliberately uses fields whose meaning is consistent on Windows.
        descriptor_binding = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_nlink,
        )
        path_binding = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_nlink,
        )
        if (
            descriptor_before != descriptor_after
            or path_before != path_after
            or descriptor_binding != path_binding
        ):
            raise RuntimeError(f"{label} changed while it was read: {path}")
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _trusted_model_metadata_root(package_dir: Path) -> tuple[Path, bool]:
    """Locate code-owned checkpoint identity metadata, never the mutable weights root."""
    source = package_dir.resolve()
    adjacent = source.parent / WSL_MODEL_METADATA_DIRECTORY
    if os.path.lexists(adjacent):
        return adjacent, True

    candidates: list[Path] = []
    if len(source.parents) > 1:
        candidates.append(source.parents[1] / "models")
    current_checkout = Path(__file__).resolve().parents[2] / "models"
    if current_checkout not in candidates:
        candidates.append(current_checkout)
    candidates.append(Path(sys.prefix) / "share" / "hawedit" / "models")
    for candidate in candidates:
        if all((candidate / filename).is_file() for filename in _MODEL_METADATA_FILES):
            return candidate, False
    raise RuntimeError(
        "HawEdit's trusted checkpoint metadata is incomplete; expected "
        f"{', '.join(_MODEL_METADATA_FILES)} beside the checkout or installed wheel"
    )


def _model_metadata_bytes(package_dir: Path) -> dict[str, bytes]:
    root, require_exact = _trusted_model_metadata_root(package_dir)
    if not root.is_dir() or _is_reparse_or_symlink(root):
        raise RuntimeError(f"trusted checkpoint metadata is not a regular directory: {root}")
    if require_exact:
        try:
            members = tuple(root.iterdir())
        except OSError as exc:
            raise RuntimeError(
                f"cannot inspect checkpoint metadata snapshot {root}: {exc}"
            ) from exc
        actual = {member.name for member in members}
        expected = set(_MODEL_METADATA_FILES)
        if actual != expected:
            raise RuntimeError(
                f"checkpoint metadata snapshot must contain exactly {_MODEL_METADATA_FILES!r}: "
                f"{root}: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
    return {
        filename: _read_bound_regular_file(
            root / filename,
            f"HawEdit checkpoint metadata {filename}",
            require_single_link=require_exact,
        )
        for filename in _MODEL_METADATA_FILES
    }


def package_digest(package_dir: Path | None = None, *, reject_bytecode_cache: bool = False) -> str:
    """Full SHA-256 identity of worker code and its checkpoint identity metadata."""
    source = package_dir or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in _package_files(source, reject_bytecode_cache=reject_bytecode_cache):
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    for filename, payload in _model_metadata_bytes(source).items():
        digest.update(f"{WSL_MODEL_METADATA_DIRECTORY}/{filename}".encode())
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_source_snapshot(source: Path, snapshot: Path) -> None:
    expected_files = {
        path.relative_to(source) for path in _package_files(source, reject_bytecode_cache=False)
    }
    expected_directories = {
        parent for relative in expected_files for parent in relative.parents if parent != Path(".")
    }
    actual_files: set[Path] = set()
    for path in snapshot.rglob("*"):
        relative = path.relative_to(snapshot)
        if _is_reparse_or_symlink(path):
            raise RuntimeError(f"HawEdit worker snapshot must not contain links: {path}")
        if path.is_dir():
            if relative not in expected_directories:
                raise RuntimeError(f"unexpected HawEdit worker snapshot directory: {path}")
            continue
        if not path.is_file() or path.suffix != ".py" or relative not in expected_files:
            raise RuntimeError(f"unexpected HawEdit worker snapshot member: {path}")
        actual_files.add(relative)
    if actual_files != expected_files:
        missing = sorted((expected_files - actual_files), key=lambda path: path.as_posix())
        raise RuntimeError(f"HawEdit worker snapshot is missing source files: {missing!r}")
    snapshot_root = snapshot.parent
    expected_top_level = {snapshot.name, WSL_MODEL_METADATA_DIRECTORY}
    actual_top_level = {path.name for path in snapshot_root.iterdir()}
    if actual_top_level != expected_top_level:
        raise RuntimeError(
            f"HawEdit worker snapshot must contain only code and checkpoint metadata: "
            f"missing={sorted(expected_top_level - actual_top_level)}, "
            f"extra={sorted(actual_top_level - expected_top_level)}"
        )
    expected_metadata = _model_metadata_bytes(source)
    copied_metadata = _model_metadata_bytes(snapshot)
    if copied_metadata != expected_metadata:
        raise RuntimeError("copied HawEdit checkpoint metadata does not match the host package")


def _publish_source_snapshot(source: Path, source_root: Path) -> Path:
    """Stage an exact package tree and atomically publish it under a unique name."""
    snapshots = source_root / "snapshots"
    _ensure_plain_directory(snapshots, "OmniASR source snapshots directory")
    staged_path = Path(tempfile.mkdtemp(prefix=".staging-", dir=snapshots))
    staged: Path | None = staged_path
    try:
        package = staged_path / "hawedit"
        package.mkdir()
        for source_file in _package_files(source, reject_bytecode_cache=False):
            relative = source_file.relative_to(source)
            destination = package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
        metadata = staged_path / WSL_MODEL_METADATA_DIRECTORY
        metadata.mkdir()
        for filename, payload in _model_metadata_bytes(source).items():
            (metadata / filename).write_bytes(payload)
        _validate_source_snapshot(source, package)
        digest = package_digest(source)
        if package_digest(package, reject_bytecode_cache=True) != digest:
            raise RuntimeError(
                f"the staged OmniASR worker source at {package} does not match the host package"
            )
        snapshot = snapshots / f"{digest}-{staged_path.name.removeprefix('.staging-')}"
        os.replace(staged_path, snapshot)
        staged = None
        return snapshot
    finally:
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)


def package_fingerprint(package_dir: Path | None = None) -> str:
    """Short cache label; security comparisons use :func:`package_digest`."""
    return package_digest(package_dir)[:16]


def default_wsl_runtime(package_dir: Path | None = None) -> Path:
    """Stable host path shared with WSL; never inside a wheel's site-packages."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "HawEdit" / "wsl-asr"


def default_wsl_source(package_dir: Path | None = None, runtime_root: Path | None = None) -> Path:
    """Fingerprint-specific Python source; the multi-GB Linux venv remains shared."""
    return (runtime_root or default_wsl_runtime()) / "sources" / package_fingerprint(package_dir)


def _prefix(distro: str | None, executable: str = "wsl.exe") -> list[str]:
    prefix = [executable]
    if distro:
        prefix.extend(("--distribution", distro))
    prefix.append("--")
    return prefix


def wsl_path(path: Path, distro: str | None = None, executable: str = "wsl.exe") -> str:
    """Translate without the backslash-loss bug in ``wsl.exe`` argument forwarding."""
    result = subprocess.run(
        [*_prefix(distro, executable), "wslpath", "-a", "-u", path.resolve().as_posix()],
        capture_output=True,
        check=False,
    )
    value = result.stdout.decode("utf-8", "replace").strip()
    if result.returncode != 0 or not value:
        error = result.stderr.decode("utf-8", "replace")[-600:]
        raise RuntimeError(f"WSL could not translate {path}: {error or 'no path returned'}")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise WslRuntimeError(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _string(document: Mapping[str, object], key: str, label: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise WslRuntimeError(f"{label} {key!r} must be a non-empty string")
    return value


def _integer(document: Mapping[str, object], key: str, label: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WslRuntimeError(f"{label} {key!r} must be an integer")
    return value


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}-",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _create_runtime_candidate(source_root: Path) -> tuple[Path, tuple[int, int]]:
    """Create the unguessable, empty file that the WSL validator may populate once."""
    candidate: Path | None = None
    identity: tuple[int, int] | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=".runtime-candidate-",
            suffix=".json",
            dir=source_root,
            delete=False,
        ) as stream:
            candidate = Path(stream.name)
            opened = os.fstat(stream.fileno())
            identity = (opened.st_dev, opened.st_ino)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        if candidate is not None and identity is not None:
            _unlink_owned_runtime_candidate(candidate, identity)
        raise WslRuntimeError(
            f"cannot create private WSL runtime validation result in {source_root}: {exc}"
        ) from exc
    if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
        _unlink_owned_runtime_candidate(candidate, identity)
        raise WslRuntimeError(f"private WSL runtime validation result is unsafe: {candidate}")
    return candidate, identity


def _publish_runtime_candidate(path: Path, document: Mapping[str, object]) -> None:
    """Populate the pre-created candidate through a no-follow, single-link descriptor."""
    payload = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise WslRuntimeError(
            f"cannot safely open WSL runtime validation result {path}: {exc}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or opened.st_nlink != 1
            or named.st_nlink != 1
            or _is_reparse_or_symlink(path)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise WslRuntimeError(
                f"WSL runtime validation result must be one unlinked regular file: {path}"
            )
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            after = os.fstat(stream.fileno())
        current = os.lstat(path)
        if (
            not stat.S_ISREG(after.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or after.st_nlink != 1
            or current.st_nlink != 1
            or _is_reparse_or_symlink(path)
            or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
            or after.st_size != len(payload)
            or current.st_size != len(payload)
        ):
            raise WslRuntimeError(f"WSL runtime validation result changed while writing: {path}")
    except OSError as exc:
        raise WslRuntimeError(
            f"cannot publish WSL runtime validation result {path}: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_bound_json(path: Path, label: str) -> dict[str, object]:
    try:
        payload = _read_bound_regular_file(path, label, require_single_link=True)
        raw: object = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise WslRuntimeError(f"cannot read {label} {path}: {exc}") from exc
    return _object(raw, str(path))


def _unlink_owned_runtime_candidate(path: Path, identity: tuple[int, int]) -> None:
    """Best-effort cleanup that refuses to unlink a path substituted by another process."""
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError:
        return
    if (
        stat.S_ISREG(current.st_mode)
        and current.st_nlink == 1
        and not _is_reparse_or_symlink(path)
        and (current.st_dev, current.st_ino) == identity
    ):
        with suppress(OSError):
            path.unlink()


def _validate_lock_file(stream: BinaryIO, lock_path: Path) -> None:
    descriptor = stream.fileno()
    opened = os.fstat(descriptor)
    try:
        named = os.lstat(lock_path)
    except OSError as exc:
        raise WslRuntimeError(f"OmniASR setup lock path disappeared: {lock_path}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(named, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or opened.st_nlink != 1
        or named.st_nlink != 1
        or attributes & reparse_flag
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise WslRuntimeError(
            f"OmniASR setup lock must be one unlinked regular file without reparse points: "
            f"{lock_path}"
        )


@contextmanager
def _open_lock_file(lock_path: Path) -> Iterator[BinaryIO]:
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise WslRuntimeError(f"cannot safely open OmniASR setup lock {lock_path}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "r+b") as stream:
            descriptor = -1
            _validate_lock_file(stream, lock_path)
            try:
                if stream.seek(0, os.SEEK_END) == 0:
                    stream.write(b"\0")
                    stream.flush()
                    os.fsync(stream.fileno())
                    _validate_lock_file(stream, lock_path)
                stream.seek(0)
            except OSError as exc:
                raise WslRuntimeError(
                    f"cannot initialize OmniASR setup lock {lock_path}: {exc}"
                ) from exc
            yield stream
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unlock_windows_file(stream: BinaryIO, msvcrt: object) -> None:
    stream.seek(0)
    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]


@contextmanager
def _windows_file_lock(stream: BinaryIO, lock_path: Path, msvcrt: object) -> Iterator[None]:
    deadline = time.monotonic() + _WINDOWS_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            stream.seek(0)
        except OSError as exc:
            raise WslRuntimeError(f"cannot position OmniASR setup lock {lock_path}: {exc}") from exc
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            break
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise WslRuntimeError(
                    f"timed out waiting for OmniASR setup lock {lock_path}"
                ) from exc
            time.sleep(0.25)
    try:
        _validate_lock_file(stream, lock_path)
        yield
    except BaseException:
        with suppress(OSError):
            _unlock_windows_file(stream, msvcrt)
        raise
    else:
        try:
            _unlock_windows_file(stream, msvcrt)
        except OSError as exc:
            raise WslRuntimeError(f"cannot release OmniASR setup lock {lock_path}: {exc}") from exc


@contextmanager
def _posix_file_lock(stream: BinaryIO, lock_path: Path, fcntl: object) -> Iterator[None]:
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
    except OSError as exc:
        raise WslRuntimeError(f"cannot acquire OmniASR setup lock {lock_path}: {exc}") from exc
    try:
        _validate_lock_file(stream, lock_path)
        yield
    except BaseException:
        with suppress(OSError):
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        raise
    else:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        except OSError as exc:
            raise WslRuntimeError(f"cannot release OmniASR setup lock {lock_path}: {exc}") from exc


@contextmanager
def _runtime_transaction_lock(runtime: Path) -> Iterator[None]:
    """Serialize every source, venv and receipt mutation across threads and processes."""
    resolved = runtime.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    with _LOCKS_GUARD:
        local_lock = _PROCESS_LOCKS.setdefault(resolved, threading.Lock())
    with local_lock:
        lock_path = resolved / ".setup.lock"
        with _open_lock_file(lock_path) as stream:
            if _WINDOWS_HOST:
                msvcrt = importlib.import_module("msvcrt")
                with _windows_file_lock(stream, lock_path, msvcrt):
                    yield
            else:
                fcntl = importlib.import_module("fcntl")
                with _posix_file_lock(stream, lock_path, fcntl):
                    yield


def _environment_digest() -> str:
    payload = json.dumps(
        {"schema": _ENVIRONMENT_SCHEMA, "packages": _EXPECTED_PACKAGES},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _generation_name(distro: str | None) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", distro or "default").strip("-.")
    if not label:
        label = "default"
    return f"{label}-{_environment_digest()[:24]}"


def _parse_runtime_payload(value: object, label: str) -> dict[str, object]:
    from hawedit.omni_assets import OMNI_ASSETS

    payload = _object(value, label)
    if payload.get("schema") != _ENVIRONMENT_SCHEMA:
        raise WslRuntimeError(
            f"{label} has unsupported schema {payload.get('schema')!r}; "
            f"expected {_ENVIRONMENT_SCHEMA}"
        )
    packages = _object(payload.get("packages"), f"{label}: packages")
    if packages != dict(_EXPECTED_PACKAGES):
        raise WslRuntimeError(
            f"{label} package set drifted: expected {dict(_EXPECTED_PACKAGES)!r}, got {packages!r}"
        )
    if _integer(payload, "cuda_device_count", label) < 2:
        raise WslRuntimeError(f"{label} does not prove two visible CUDA devices")
    assets = payload.get("assets")
    if not isinstance(assets, list) or len(assets) != 3:
        raise WslRuntimeError(f"{label} must contain exactly three verified OmniASR assets")
    expected_assets = {asset.name: (asset.size, asset.sha256) for asset in OMNI_ASSETS}
    actual_assets: dict[str, tuple[int, str]] = {}
    total = 0
    for index, raw_asset in enumerate(assets):
        asset = _object(raw_asset, f"{label}: asset {index}")
        name = _string(asset, "name", f"{label}: asset {index}")
        size = _integer(asset, "size", f"{label}: asset {index}")
        digest = _string(asset, "sha256", f"{label}: asset {index}")
        if size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WslRuntimeError(f"{label}: asset {index} has an invalid byte identity")
        _string(asset, "path", f"{label}: asset {index}")
        if name in actual_assets:
            raise WslRuntimeError(f"{label} repeats OmniASR asset {name!r}")
        actual_assets[name] = (size, digest)
        total += size
    if actual_assets != expected_assets:
        raise WslRuntimeError(f"{label} OmniASR asset identities drifted: {actual_assets!r}")
    if total != 43_546_500_168:  # defensive readability beside the reviewed identities
        raise WslRuntimeError(f"{label} verifies {total} OmniASR bytes; expected 43546500168")
    return payload


def _read_json(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise WslRuntimeError(f"{label} is missing or not a regular file: {path}")
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WslRuntimeError(f"cannot read {label} {path}: {exc}") from exc
    return _object(raw, str(path))


_FONTOOLS_VERSION = "4.60.2"

_SETUP_SCRIPT = r"""
set -euo pipefail
venv="$HAWEDIT_WSL_VENV"
if [[ "$HAWEDIT_WSL_ENV_REUSE" != 1 ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 "$venv"
    uv pip install --python "$venv/bin/python" \
      'torch==2.8.0' 'torchaudio==2.8.0' \
      'omnilingual-asr==0.2.0' 'fairseq2==0.6' \
      'qwen-asr==0.0.6' 'klpt==0.1.7' \
      'fonttools==__FONTOOLS_VERSION__'
  elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv "$venv"
    "$venv/bin/python" -m pip install --upgrade pip
    "$venv/bin/python" -m pip install \
      'torch==2.8.0' 'torchaudio==2.8.0' \
      'omnilingual-asr==0.2.0' 'fairseq2==0.6' \
      'qwen-asr==0.0.6' 'klpt==0.1.7' \
      'fonttools==__FONTOOLS_VERSION__'
  else
    printf '%s\n' 'Install uv or Python 3.12 inside WSL2.' >&2
    exit 1
  fi
fi
PYTHONPATH="$HAWEDIT_WSL_SOURCE" "$venv/bin/python" - <<'PY'
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

from hawedit.omni_assets import (
    assert_effective_omni_cards,
    assert_omni_card_integrity,
    freeze_fairseq2_asset_overrides,
    provision_omni_assets,
)
from hawedit.wsl_setup import _publish_runtime_candidate

# Download into fairseq2's exact cache layout, but publish nothing until HawEdit's
# application-owned size and SHA-256 identities match. The worker hashes them again
# immediately before model construction.
assets = provision_omni_assets()
assert_omni_card_integrity()
freeze_fairseq2_asset_overrides()

import torch
import torchaudio
from fairseq2.assets import get_asset_store
from hawedit.asr_worker import run_request
from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
from qwen_asr import Qwen3ASRModel

assert_effective_omni_cards(get_asset_store())

torch_version = torch.__version__.split("+", 1)[0]
torchaudio_version = torchaudio.__version__.split("+", 1)[0]
if torch_version != "2.8.0" or torchaudio_version != "2.8.0":
    raise SystemExit(
        f"Stage 1 requires matched torch/torchaudio 2.8.0, got "
        f"{torch_version}/{torchaudio_version}"
    )
del run_request, ASRInferencePipeline, Qwen3ASRModel, provision_omni_assets, torchaudio
if not torch.cuda.is_available():
    raise SystemExit("OmniASR installed, but CUDA is not visible inside WSL2")
if torch.cuda.device_count() < 2:
    raise SystemExit("HawEdit OmniASR needs two visible GPUs (LLM cuda:0, CTC cuda:1)")
packages = {
    name: importlib.metadata.version(name)
    for name in (
        "fairseq2",
        "fonttools",
        "klpt",
        "omnilingual-asr",
        "qwen-asr",
        "torch",
        "torchaudio",
    )
}
receipt = {
    "schema": 1,
    "distro": os.environ.get("WSL_DISTRO_NAME", ""),
    "uid": os.getuid(),
    "home": str(Path.home().resolve()),
    "python": sys.executable,
    "python_version": platform.python_version(),
    "packages": packages,
    "cuda_device_count": torch.cuda.device_count(),
    "asset_cache": str(assets[0].path.parents[1]),
    "assets": [
        {
            "name": report.name,
            "path": str(report.path),
            "size": report.size,
            "sha256": report.sha256,
        }
        for report in assets
    ],
}
_publish_runtime_candidate(Path(os.environ["HAWEDIT_WSL_RECEIPT_CANDIDATE"]), receipt)
print(f"OmniASR import OK; CUDA GPUs visible: {torch.cuda.device_count()}")
PY
""".replace("__FONTOOLS_VERSION__", _FONTOOLS_VERSION).strip()


def _build_receipt(
    *,
    source_root: Path,
    source_snapshot: Path,
    source: Path,
    generation: str,
    generation_root: Path,
    requested_distro: str | None,
    payload: Mapping[str, object],
) -> dict[str, object]:
    parsed = _parse_runtime_payload(payload, "WSL runtime validation result")
    actual_distro = _string(parsed, "distro", "WSL runtime validation result")
    if requested_distro and actual_distro.casefold() != requested_distro.casefold():
        raise WslRuntimeError(
            f"WSL setup targeted {requested_distro!r}, but the runtime identified itself as "
            f"{actual_distro!r}"
        )
    python_version = _string(parsed, "python_version", "WSL runtime validation result")
    if not python_version.startswith("3.12."):
        raise WslRuntimeError(f"canonical ASR requires Python 3.12, got {python_version!r}")
    return {
        "schema": _RECEIPT_SCHEMA,
        "source_sha256": package_digest(source),
        "source_directory": source_root.name,
        "source_snapshot": source_snapshot.name,
        "generation": generation,
        "environment_sha256": _environment_digest(),
        "requested_distro": requested_distro or "",
        "runtime": dict(parsed),
    }


def _generation_is_complete(path: Path, generation: str) -> bool:
    marker = path / ".complete.json"
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        document = _read_json(marker, "WSL environment generation receipt")
        return (
            document.get("schema") == _ENVIRONMENT_SCHEMA
            and document.get("generation") == generation
            and document.get("environment_sha256") == _environment_digest()
        )
    except WslRuntimeError:
        return False


def _generation_runtime(path: Path) -> dict[str, object]:
    document = _read_json(path / ".complete.json", "WSL environment generation receipt")
    return _parse_runtime_payload(document.get("runtime"), "WSL environment generation runtime")


def load_wsl_runtime_receipt(
    *,
    distro: str | None = None,
    runtime_root: Path | None = None,
    package_source: Path | None = None,
    executable: str = "wsl.exe",
) -> WslRuntimeReceipt:
    """Validate the current source receipt and versioned WSL environment generation."""
    source = (package_source or Path(__file__).resolve().parent).resolve()
    runtime = _runtime_root_path(runtime_root or default_wsl_runtime(source), create=False)
    source_root = default_wsl_source(source, runtime)
    marker = source_root / ".ready"
    receipt = _read_json(marker, "OmniASR WSL readiness receipt")
    if receipt.get("schema") != _RECEIPT_SCHEMA:
        raise WslRuntimeError(
            f"{marker} has unsupported schema {receipt.get('schema')!r}; "
            f"legacy ready markers must be replaced by running hawedit-asr-setup"
        )
    expected_digest = package_digest(source)
    if receipt.get("source_sha256") != expected_digest:
        raise WslRuntimeError("OmniASR WSL worker source receipt does not match the host package")
    if receipt.get("source_directory") != source_root.name:
        raise WslRuntimeError("OmniASR WSL receipt points at a different source generation")
    snapshot_name = _string(receipt, "source_snapshot", str(marker))
    if not re.fullmatch(r"[0-9a-f]{64}-[A-Za-z0-9_-]+", snapshot_name):
        raise WslRuntimeError(f"unsafe WSL worker snapshot in {marker}: {snapshot_name!r}")
    snapshot_path = source_root / "snapshots" / snapshot_name
    if _is_reparse_or_symlink(snapshot_path):
        raise WslRuntimeError(f"WSL worker snapshot must not be a link: {snapshot_path}")
    source_snapshot = snapshot_path.resolve()
    try:
        source_snapshot.relative_to((source_root / "snapshots").resolve())
    except ValueError as exc:
        raise WslRuntimeError(
            f"WSL worker snapshot escapes its source root: {source_snapshot}"
        ) from exc
    copied_source = source_snapshot / "hawedit"
    try:
        _validate_source_snapshot(source, copied_source)
        copied_digest = package_digest(copied_source, reject_bytecode_cache=True)
    except (OSError, RuntimeError) as exc:
        raise WslRuntimeError(
            f"cannot verify the copied OmniASR WSL worker source at {copied_source}: {exc}"
        ) from exc
    if copied_digest != expected_digest:
        raise WslRuntimeError(
            "copied OmniASR WSL worker source does not match the receipt and host package"
        )
    generation = _string(receipt, "generation", str(marker))
    if Path(generation).name != generation:
        raise WslRuntimeError(f"unsafe WSL environment generation in {marker}: {generation!r}")
    if receipt.get("environment_sha256") != _environment_digest():
        raise WslRuntimeError("OmniASR WSL dependency specification changed; rerun setup")
    generation_root = (runtime / "venvs" / generation).resolve()
    try:
        generation_root.relative_to((runtime / "venvs").resolve())
    except ValueError as exc:
        raise WslRuntimeError(
            f"WSL generation escapes the runtime root: {generation_root}"
        ) from exc
    if not _generation_is_complete(generation_root, generation):
        raise WslRuntimeError(f"WSL environment generation is incomplete: {generation_root}")
    runtime_payload = _parse_runtime_payload(receipt.get("runtime"), f"{marker}: runtime")
    generation_runtime = _generation_runtime(generation_root)
    if runtime_payload != generation_runtime:
        raise WslRuntimeError(
            "OmniASR WSL receipt runtime does not match its versioned environment generation"
        )
    actual_distro = _string(runtime_payload, "distro", f"{marker}: runtime")
    requested = receipt.get("requested_distro")
    if not isinstance(requested, str):
        raise WslRuntimeError(f"{marker} requested_distro must be a string")
    if distro is not None and actual_distro.casefold() != distro.casefold():
        raise WslRuntimeError(
            f"OmniASR was provisioned in WSL distro {actual_distro!r}, not {distro!r}"
        )
    try:
        translated_generation = wsl_path(generation_root, actual_distro, executable)
        interpreter = f"{translated_generation}/bin/python"
        interpreter_probe = subprocess.run(
            [
                *_prefix(actual_distro, executable),
                interpreter,
                "-c",
                _IDENTITY_PROBE_SCRIPT,
            ],
            capture_output=True,
            check=False,
        )
    except (OSError, RuntimeError) as exc:
        raise WslRuntimeError(
            f"cannot inspect WSL environment interpreter in {actual_distro!r}: {exc}"
        ) from exc
    if interpreter_probe.returncode != 0:
        error = interpreter_probe.stderr.decode("utf-8", "replace")[-800:]
        raise WslRuntimeError(
            f"WSL environment interpreter is missing or unusable: {interpreter}: "
            f"{error or 'no detail'}"
        )
    try:
        live_identity = _object(
            json.loads(interpreter_probe.stdout.decode("utf-8")),
            "WSL environment identity probe",
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WslRuntimeError(f"invalid WSL environment identity output: {exc}") from exc
    expected_identity = {
        "uid": _integer(runtime_payload, "uid", f"{marker}: runtime"),
        "home": _string(runtime_payload, "home", f"{marker}: runtime"),
        "python": _string(runtime_payload, "python", f"{marker}: runtime"),
        "python_version": _string(runtime_payload, "python_version", f"{marker}: runtime"),
        "packages": _object(runtime_payload.get("packages"), f"{marker}: packages"),
    }
    if live_identity != expected_identity:
        raise WslRuntimeError(
            "live WSL interpreter identity or package versions drifted from the receipt"
        )
    packages = _object(runtime_payload.get("packages"), f"{marker}: packages")
    assets = cast(list[object], runtime_payload["assets"])
    return WslRuntimeReceipt(
        source_root=source_snapshot,
        source_sha256=expected_digest,
        generation=generation,
        generation_root=generation_root,
        distro=actual_distro,
        uid=_integer(runtime_payload, "uid", f"{marker}: runtime"),
        home=_string(runtime_payload, "home", f"{marker}: runtime"),
        python_version=_string(runtime_payload, "python_version", f"{marker}: runtime"),
        packages={key: cast(str, value) for key, value in packages.items()},
        asset_cache=_string(runtime_payload, "asset_cache", f"{marker}: runtime"),
        asset_bytes=sum(_integer(_object(asset, "asset"), "size", "asset") for asset in assets),
        cuda_device_count=_integer(runtime_payload, "cuda_device_count", f"{marker}: runtime"),
    )


_IDENTITY_PROBE_SCRIPT: Final = r"""
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

distributions = (
    "fairseq2",
    "fonttools",
    "klpt",
    "omnilingual-asr",
    "qwen-asr",
    "torch",
    "torchaudio",
)
print(json.dumps({
    "uid": os.getuid(),
    "home": str(Path.home().resolve()),
    "python": sys.executable,
    "python_version": platform.python_version(),
    "packages": {
        distribution: importlib.metadata.version(distribution)
        for distribution in distributions
    },
}, sort_keys=True))
""".strip()


_PROBE_SCRIPT: Final = r"""
import json
import torch
from hawedit.omni_assets import assert_omni_asset_integrity, assert_omni_card_integrity

assert_omni_card_integrity()
reports = assert_omni_asset_integrity()
print(json.dumps({
    "files_verified": len(reports),
    "size_bytes": sum(report.size for report in reports),
    "cuda_device_count": torch.cuda.device_count(),
}, sort_keys=True))
""".strip()


def probe_wsl_runtime(
    *,
    distro: str | None = None,
    runtime_root: Path | None = None,
    package_source: Path | None = None,
    executable: str = "wsl.exe",
) -> WslRuntimeProbe:
    """Re-hash the live WSL assets; a setup-time receipt alone cannot prove mutable bytes."""
    receipt = load_wsl_runtime_receipt(
        distro=distro,
        runtime_root=runtime_root,
        package_source=package_source,
        executable=executable,
    )
    runtime_python = wsl_path(receipt.generation_root, receipt.distro, executable) + "/bin/python"
    runtime_source = wsl_path(receipt.source_root, receipt.distro, executable)
    result = subprocess.run(
        [
            *_prefix(receipt.distro, executable),
            "env",
            f"PYTHONPATH={runtime_source}",
            runtime_python,
            "-c",
            _PROBE_SCRIPT,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace")[-1_200:]
        raise WslRuntimeError(f"OmniASR WSL live verification failed: {error or 'no detail'}")
    try:
        payload = _object(json.loads(result.stdout.decode("utf-8")), "WSL probe output")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WslRuntimeError(f"invalid OmniASR WSL probe output: {exc}") from exc
    files = _integer(payload, "files_verified", "WSL probe output")
    size = _integer(payload, "size_bytes", "WSL probe output")
    devices = _integer(payload, "cuda_device_count", "WSL probe output")
    if files != 3 or size != receipt.asset_bytes or devices < 2:
        raise WslRuntimeError(
            f"OmniASR WSL probe drifted: files={files}, bytes={size}, CUDA devices={devices}"
        )
    return WslRuntimeProbe(receipt, files, size)


def provision_wsl_runtime(
    *,
    distro: str | None = None,
    runtime_root: Path | None = None,
    package_source: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Publish an exact source snapshot over a serialized, versioned WSL venv."""
    if (platform_name or os.name) != "nt":
        raise RuntimeError("the WSL2 OmniASR setup command is only for Windows hosts")
    source = (package_source or Path(__file__).resolve().parent).resolve()
    runtime = _runtime_root_path(runtime_root or default_wsl_runtime(source), create=True)
    with _runtime_transaction_lock(runtime):
        sources_root = runtime / "sources"
        _ensure_plain_directory(sources_root, "OmniASR sources directory")
        source_root = default_wsl_source(source, runtime)
        _ensure_plain_directory(source_root, "OmniASR source generation")
        ready = source_root / ".ready"
        candidate: Path | None = None
        candidate_identity: tuple[int, int] | None = None
        source_snapshot: Path | None = None
        receipt_published = False
        try:
            source_snapshot = _publish_source_snapshot(source, source_root)
            generation = _generation_name(distro)
            venvs_root = runtime / "venvs"
            _ensure_plain_directory(venvs_root, "OmniASR venvs directory")
            generation_root = venvs_root / generation
            try:
                os.lstat(generation_root)
            except FileNotFoundError:
                pass
            else:
                _validate_plain_directory(generation_root, "OmniASR venv generation")
            complete = _generation_is_complete(generation_root, generation)
            if generation_root.exists() and not complete:
                shutil.rmtree(generation_root)
            _ensure_plain_directory(generation_root, "OmniASR venv generation")
            translated = wsl_path(runtime, distro)
            translated_source = wsl_path(source_snapshot, distro)
            translated_generation = wsl_path(generation_root, distro)
            candidate, candidate_identity = _create_runtime_candidate(source_root)
            translated_candidate = wsl_path(candidate, distro)
            result = subprocess.run(
                [
                    *_prefix(distro),
                    "env",
                    f"HAWEDIT_WSL_RUNTIME={translated}",
                    f"HAWEDIT_WSL_SOURCE={translated_source}",
                    f"HAWEDIT_WSL_VENV={translated_generation}",
                    f"HAWEDIT_WSL_ENV_REUSE={int(complete)}",
                    f"HAWEDIT_WSL_RECEIPT_CANDIDATE={translated_candidate}",
                    "bash",
                    "-l",
                    "-s",
                ],
                input=_SETUP_SCRIPT.encode("utf-8"),
                capture_output=False,
                check=False,
            )
            if result.returncode != 0:
                if not complete and generation_root.exists():
                    shutil.rmtree(generation_root)
                raise RuntimeError(f"OmniASR WSL2 setup failed with exit code {result.returncode}")
            payload = _read_bound_json(candidate, "WSL runtime validation result")
            receipt = _build_receipt(
                source_root=source_root,
                source_snapshot=source_snapshot,
                source=source,
                generation=generation,
                generation_root=generation_root,
                requested_distro=distro,
                payload=payload,
            )
            parsed_payload = _parse_runtime_payload(payload, "runtime generation")
            if complete and _generation_runtime(generation_root) != parsed_payload:
                raise WslRuntimeError(
                    "versioned WSL venv generation validation changed; configure a separate "
                    "HAWEDIT_WSL_RUNTIME or remove the unused generation before reprovisioning"
                )
            if not complete:
                _atomic_json(
                    generation_root / ".complete.json",
                    {
                        "schema": _ENVIRONMENT_SCHEMA,
                        "generation": generation,
                        "environment_sha256": _environment_digest(),
                        "runtime": dict(parsed_payload),
                    },
                )
            _atomic_json(ready, receipt)
            receipt_published = True
            return runtime
        finally:
            if candidate is not None and candidate_identity is not None:
                _unlink_owned_runtime_candidate(candidate, candidate_identity)
            if source_snapshot is not None and not receipt_published:
                shutil.rmtree(source_snapshot, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision HawEdit's official OmniASR runtime inside WSL2"
    )
    parser.add_argument("--distribution", help="optional WSL distribution name")
    args = parser.parse_args(argv)
    runtime = provision_wsl_runtime(distro=args.distribution)
    print(f"READY: OmniASR WSL2 runtime at {runtime}")
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())
