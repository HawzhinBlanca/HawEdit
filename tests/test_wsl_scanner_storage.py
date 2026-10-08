from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hawedit.wsl_scanner_storage import STORAGE_SCRIPT, scanner_directory_identity


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-c", STORAGE_SCRIPT, *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _create() -> tuple[str, ...] | None:
    result = _run("create")
    if sys.platform != "linux":
        assert result.returncode != 0
        assert "Linux directory descriptors are required" in result.stderr
        assert result.stdout == ""
        return None
    assert result.returncode == 0, result.stderr
    return tuple(scanner_directory_identity(result.stdout.encode()).arguments())


def test_scanner_storage_create_and_cleanup() -> None:
    identity = _create()
    if identity is None:
        return
    root = Path(identity[0])
    assert root.stat().st_mode & 0o777 == 0o700
    (root / "nested").mkdir()
    (root / "nested" / "wheel.whl").write_bytes(b"real temporary bytes")
    result = _run("cleanup", *identity)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not root.exists()


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b"[]",
        b'{"path":"/tmp/hawedit-wsl-audit.A1b2C3d4E5","device":1,"inode":2,"uid":true}',
        b'{"path":"/tmp/../etc","device":1,"inode":2,"uid":1000}',
        b'{"path":"/tmp/hawedit-wsl-audit.A1b2C3d4E5","device":1,"inode":0,"uid":1000}',
        b'{"path":"/tmp/hawedit-wsl-audit.A1b2C3d4E5","device":1,"inode":2,"uid":1000,"extra":1}',
        b'{"path":"/tmp/hawedit-wsl-audit.A1b2C3d4E5","path":"/tmp/hawedit-wsl-audit.A1b2C3d4E5","device":1,"inode":2,"uid":1000}',
    ],
)
def test_scanner_directory_identity_rejects_invalid_receipts(payload: bytes) -> None:
    with pytest.raises(ValueError, match="scanner directory identity"):
        scanner_directory_identity(payload)


def test_scanner_directory_identity_preserves_exact_identity() -> None:
    identity = scanner_directory_identity(
        b'{"path":"/tmp/hawedit-wsl-audit.A1b2C3d4E5","device":1,"inode":2,"uid":1000}\n'
    )
    assert identity.arguments() == ["/tmp/hawedit-wsl-audit.A1b2C3d4E5", "1", "2", "1000"]


def test_scanner_storage_refuses_changed_identity() -> None:
    identity = _create()
    if identity is None:
        return
    root = Path(identity[0])
    sentinel = root / "keep"
    sentinel.write_bytes(b"not approved for deletion")
    try:
        altered = (identity[0], identity[1], str(int(identity[2]) + 1), identity[3])
        result = _run("cleanup", *altered)
        assert result.returncode != 0
        assert "scanner directory identity changed" in result.stderr
        assert sentinel.read_bytes() == b"not approved for deletion"
    finally:
        assert _run("cleanup", *identity).returncode == 0


def test_scanner_storage_refuses_symlink_root(tmp_path: Path) -> None:
    identity = _create()
    if identity is None:
        return
    root = Path(identity[0])
    root.rmdir()
    sentinel = tmp_path / "keep"
    sentinel.write_bytes(b"foreign target")
    root.symlink_to(tmp_path, target_is_directory=True)
    try:
        result = _run("cleanup", *identity)
        assert result.returncode != 0
        assert root.is_symlink()
        assert sentinel.read_bytes() == b"foreign target"
    finally:
        root.unlink()


def test_scanner_storage_unlinks_child_symlink_without_following(tmp_path: Path) -> None:
    identity = _create()
    if identity is None:
        return
    root = Path(identity[0])
    sentinel = tmp_path / "keep"
    sentinel.write_bytes(b"foreign target")
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    result = _run("cleanup", *identity)
    assert result.returncode == 0, result.stderr
    assert not root.exists()
    assert sentinel.read_bytes() == b"foreign target"


def test_scanner_storage_bounds_recursive_work() -> None:
    identity = _create()
    if identity is None:
        return
    root = Path(identity[0])
    directories: list[Path] = []
    leaf = root
    try:
        for _ in range(130):
            leaf = leaf / "d"
            leaf.mkdir()
            directories.append(leaf)
        result = _run("cleanup", *identity)
        assert result.returncode != 0
        assert "depth limit exceeded" in result.stderr
        assert leaf.is_dir()
    finally:
        for directory in reversed(directories):
            directory.rmdir()
        assert _run("cleanup", *identity).returncode == 0


@pytest.mark.parametrize("path", ["/tmp", "/", "/tmp/../etc", "/tmp/hawedit-wsl-audit.x"])
def test_scanner_storage_rejects_unsafe_cleanup_paths(path: str) -> None:
    result = _run("cleanup", path, "1", "2", str(os.getuid() if hasattr(os, "getuid") else 0))
    assert result.returncode != 0
    assert result.stdout == ""
