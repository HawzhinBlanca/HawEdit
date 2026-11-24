"""Native private SQLite namespace and recovery checks; no mocked filesystem policy."""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from hawedit.studio_private import PrivateSqlitePath
from hawedit.studio_submissions import StudioStorageError
from hawedit.windows_security import assert_private_windows_path, create_private_directory


def private_directory(path: Path) -> None:
    if os.name == "nt":
        create_private_directory(path)
    else:
        path.mkdir(mode=0o700)


def private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def directory_alias(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        assert link.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    else:
        link.symlink_to(target, target_is_directory=True)


def test_studio_private_new_journal_is_owner_private(tmp_path: Path) -> None:
    path = tmp_path / "new-private" / "billing.sqlite3"
    journal = PrivateSqlitePath(path)
    assert journal.path == path.absolute()
    assert path.read_bytes() == b""
    if os.name == "nt":
        assert_private_windows_path(path.parent, require_protected=True)
        assert_private_windows_path(path, require_protected=False)
    else:
        assert hasattr(os, "geteuid")
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.parent.stat().st_uid == path.stat().st_uid == os.geteuid()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE retained(value TEXT)")
        db.execute("INSERT INTO retained VALUES ('private fixture')")
    journal.verify()
    reopened = PrivateSqlitePath(path)
    with sqlite3.connect(reopened.path) as db:
        assert db.execute("SELECT value FROM retained").fetchall() == [("private fixture",)]


def test_studio_private_existing_public_storage_preserved(tmp_path: Path) -> None:
    root = tmp_path / "ordinary-root"
    root.mkdir()
    if os.name != "nt":
        root.chmod(0o755)
    path = root / "billing.sqlite3"
    path.write_bytes(b"original owner bytes must not be changed")
    before = root.stat().st_mode
    with pytest.raises(StudioStorageError, match="private"):
        PrivateSqlitePath(path)
    assert path.read_bytes() == b"original owner bytes must not be changed"
    assert root.stat().st_mode == before


@pytest.mark.parametrize("scope", ["root", "ancestor"])
def test_studio_private_directory_aliases_refused(tmp_path: Path, scope: str) -> None:
    actual = tmp_path / "actual-parent"
    actual.mkdir()
    original = PrivateSqlitePath(actual / "private-root" / "billing.sqlite3")
    link = tmp_path / "alias"
    directory_alias(link, original.root if scope == "root" else actual)
    path = (
        link / "billing.sqlite3" if scope == "root" else link / "private-root" / "billing.sqlite3"
    )
    with pytest.raises(StudioStorageError, match="linked|private"):
        PrivateSqlitePath(path)
    assert original.path.read_bytes() == b""
    original.verify()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("damage", ["hardlink", "directory"])
def test_studio_private_linked_sidecars_refused(tmp_path: Path, suffix: str, damage: str) -> None:
    journal = PrivateSqlitePath(tmp_path / "private-root" / "billing.sqlite3")
    sidecar = journal.path.with_name(journal.path.name + suffix)
    outside = tmp_path / "original-sidecar"
    if damage == "hardlink":
        outside.write_bytes(b"retain original recovery evidence")
        os.link(outside, sidecar)
    else:
        sidecar.mkdir()
    with pytest.raises(StudioStorageError, match="linked|private"):
        journal.verify()
    with pytest.raises(StudioStorageError, match="linked|private"):
        PrivateSqlitePath(journal.path)
    assert journal.path.read_bytes() == b""
    if damage == "hardlink":
        assert sidecar.read_bytes() == outside.read_bytes() == b"retain original recovery evidence"
    else:
        assert sidecar.is_dir()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_studio_private_orphan_sidecars_preserved(tmp_path: Path, suffix: str) -> None:
    root = tmp_path / "private-root"
    private_directory(root)
    path = root / "billing.sqlite3"
    sidecar = path.with_name(path.name + suffix)
    private_file(sidecar, b"orphan recovery evidence is not disposable")
    with pytest.raises(StudioStorageError, match="orphan"):
        PrivateSqlitePath(path)
    assert not path.exists()
    assert sidecar.read_bytes() == b"orphan recovery evidence is not disposable"


def test_studio_private_replacement_root_is_not_adopted(tmp_path: Path) -> None:
    journal = PrivateSqlitePath(tmp_path / "private-root" / "billing.sqlite3")
    retained = tmp_path / "retained-root"
    assert journal.root.parent.resolve() == retained.parent.resolve() == tmp_path.resolve()
    journal.root.rename(retained)
    private_directory(journal.root)
    private_file(journal.path, b"")
    with pytest.raises(StudioStorageError, match="root identity changed"):
        journal.verify()
    assert (retained / journal.path.name).read_bytes() == b""


def test_studio_private_missing_main_file_is_not_recreated(tmp_path: Path) -> None:
    journal = PrivateSqlitePath(tmp_path / "private-root" / "billing.sqlite3")
    assert journal.path.parent.parent.resolve() == tmp_path.resolve()
    journal.path.unlink()
    with pytest.raises(StudioStorageError, match="private"):
        journal.verify()
    assert not journal.path.exists()


@pytest.mark.parametrize(
    "name",
    ["CON.db", "NUL", "LPT1.db", "name:stream", "name.", "name ", "x" * 129],
)
def test_studio_private_nonportable_names_refused(tmp_path: Path, name: str) -> None:
    root = tmp_path / "must-not-be-created"
    with pytest.raises(StudioStorageError, match="filename"):
        PrivateSqlitePath(root / name)
    assert not root.exists()


@pytest.mark.parametrize("parent", ["parent.", "parent ", "parent/../other"])
def test_studio_private_parent_normalization_refused(tmp_path: Path, parent: str) -> None:
    with pytest.raises(StudioStorageError, match="filename"):
        PrivateSqlitePath(tmp_path / parent / "billing.sqlite3")
    assert not (tmp_path / "parent").exists()
    assert not (tmp_path / "parent.").exists()
    assert not (tmp_path / "parent ").exists()
    assert not (tmp_path / "other").exists()


def test_studio_private_real_wal_crash_recovers_without_deleting_evidence(tmp_path: Path) -> None:
    journal = PrivateSqlitePath(tmp_path / "private-root" / "billing.sqlite3")
    program = """
import os, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
db.execute('CREATE TABLE retained(value TEXT)')
db.execute("INSERT INTO retained VALUES ('committed before abrupt exit')")
db.commit()
os._exit(19)
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(journal.path)],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 19, result.stderr.decode("utf-8", "replace")
    wal = journal.path.with_name(journal.path.name + "-wal")
    before = wal.read_bytes()
    assert before
    journal.verify()
    assert wal.read_bytes() == before
    reopened = PrivateSqlitePath(journal.path)
    assert wal.read_bytes() == before
    with sqlite3.connect(reopened.path) as db:
        assert db.execute("SELECT value FROM retained").fetchall() == [
            ("committed before abrupt exit",)
        ]
    reopened.verify()
