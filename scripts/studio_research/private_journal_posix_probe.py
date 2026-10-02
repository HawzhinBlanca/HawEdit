"""Bounded native POSIX storage probe; no pytest install, provider or model execution."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from hawedit.studio_private import PrivateSqlitePath
from hawedit.studio_submissions import StudioStorageError
from hawedit.wsl_setup import package_digest


def main() -> None:
    assert os.name == "posix" and hasattr(os, "geteuid")
    root = Path(tempfile.mkdtemp(prefix="hawedit-private-probe-", dir="/tmp"))
    observations: list[dict[str, object]] = []

    def refused(path: Path, name: str) -> None:
        try:
            PrivateSqlitePath(path)
        except StudioStorageError as exc:
            observations.append({"case": name, "result": "refused", "message": str(exc)})
        else:
            raise AssertionError(f"Unsafe native path accepted: {name}")

    private = PrivateSqlitePath(root / "private-root" / "billing.sqlite3")
    assert stat.S_IMODE(private.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(private.path.stat().st_mode) == 0o600
    assert private.path.stat().st_uid == os.geteuid()
    observations.append({"case": "new owner-private journal", "result": "passed"})

    ordinary = root / "ordinary"
    ordinary.mkdir(mode=0o755)
    ordinary.chmod(0o755)
    old = ordinary / "billing.sqlite3"
    old.write_bytes(b"original bytes")
    refused(old, "shared root")
    assert old.read_bytes() == b"original bytes"
    assert stat.S_IMODE(ordinary.stat().st_mode) == 0o755

    private.path.chmod(0o644)
    refused(private.path, "shared file")
    assert stat.S_IMODE(private.path.stat().st_mode) == 0o644
    private.path.chmod(0o600)

    alias = root / "alias"
    alias.symlink_to(private.root, target_is_directory=True)
    refused(alias / private.path.name, "symbolic root alias")

    linked = root / "linked-main"
    os.link(private.path, linked)
    refused(private.path, "multiply-linked main")
    linked.unlink()
    private.verify()

    for suffix in ("-wal", "-shm", "-journal"):
        outside = root / ("retained" + suffix)
        outside.write_bytes(b"retained evidence")
        sidecar = private.path.with_name(private.path.name + suffix)
        os.link(outside, sidecar)
        refused(private.path, "multiply-linked sidecar " + suffix)
        assert outside.read_bytes() == sidecar.read_bytes() == b"retained evidence"
        sidecar.unlink()
        orphan_root = root / ("orphan" + suffix)
        orphan_root.mkdir(mode=0o700)
        main_path = orphan_root / "billing.sqlite3"
        orphan = main_path.with_name(main_path.name + suffix)
        orphan.write_bytes(b"orphan recovery state")
        orphan.chmod(0o600)
        refused(main_path, "orphan " + suffix)
        assert not main_path.exists()
        assert orphan.read_bytes() == b"orphan recovery state"

    program = """
import os,sqlite3,sys
db=sqlite3.connect(sys.argv[1])
assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
db.execute('CREATE TABLE retained(value TEXT)')
db.execute("INSERT INTO retained VALUES ('committed before crash')")
db.commit()
os._exit(19)
"""
    crashed = subprocess.run(
        [sys.executable, "-c", program, str(private.path)],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert crashed.returncode == 19, crashed.stderr
    wal = private.path.with_name(private.path.name + "-wal")
    retained = wal.read_bytes()
    assert retained
    private.verify()
    reopened = PrivateSqlitePath(private.path)
    assert wal.read_bytes() == retained
    with sqlite3.connect(reopened.path) as db:
        assert db.execute("SELECT value FROM retained").fetchall() == [("committed before crash",)]
    reopened.verify()
    observations.append({"case": "real committed WAL crash/reopen", "result": "passed"})

    filesystem = subprocess.run(
        ["stat", "-f", "-c", "%T", str(root)],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    package = Path(__file__).resolve().parents[2] / "src" / "hawedit"
    result = {
        "schema": 1,
        "scope": "Bounded POSIX probe only; not a canonical gate or production mount certificate",
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "filesystem": filesystem,
        "temporary_root": str(root),
        "source_package_sha256": package_digest(package),
        "observations": observations,
        "provider_calls": 0,
        "model_inference": False,
    }
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{len(observations)} native POSIX observations passed; {filesystem}")


if __name__ == "__main__":
    main()
