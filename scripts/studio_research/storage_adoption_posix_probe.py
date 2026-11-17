"""Real POSIX directory/metadata/outbox checks, without pytest or model execution."""

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

from hawedit.studio_private import PrivateDirectory, StudioStorageError, write_text_atomic
from hawedit.studio_submissions import SubmissionStore
from hawedit.wsl_setup import package_digest


def main() -> None:
    assert os.name == "posix" and hasattr(os, "geteuid")
    root = Path(tempfile.mkdtemp(prefix="hawedit-storage-adoption-", dir="/tmp"))
    observations: list[dict[str, object]] = []

    def refused(action: object, case: str) -> None:
        assert callable(action)
        try:
            action()
        except StudioStorageError as exc:
            observations.append({"case": case, "result": "refused", "message": str(exc)})
        else:
            raise AssertionError(f"Unsafe storage accepted: {case}")

    directory = PrivateDirectory(root / "private")
    assert stat.S_IMODE(directory.path.stat().st_mode) == 0o700
    assert directory.path.stat().st_uid == os.geteuid()
    record = directory.path / "record.json"
    write_text_atomic(record, '{"actual":"private record"}')
    write_text_atomic(record, '{"actual":"updated record"}')
    assert record.read_bytes() == b'{"actual":"updated record"}'
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    assert record.stat().st_uid == os.geteuid()
    assert [item.name for item in directory.path.iterdir()] == [record.name]
    observations.append({"case": "private leaf and actual atomic metadata", "result": "passed"})

    original = record.read_bytes()
    linked = root / "retained-original"
    os.link(record, linked)
    refused(lambda: write_text_atomic(record, "must not replace"), "linked metadata")
    assert record.read_bytes() == linked.read_bytes() == original
    linked.unlink()

    shared = root / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    owner = shared / "original-owner-data"
    owner.write_bytes(b"original owner bytes")
    refused(lambda: PrivateDirectory(shared), "shared directory")
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert owner.read_bytes() == b"original owner bytes"

    alias = root / "alias"
    alias.symlink_to(directory.path, target_is_directory=True)
    refused(lambda: PrivateDirectory(alias), "symbolic directory alias")

    stage = directory.child("incoming", create=True, exclusive=True)
    with stage.open_new_file("source.mp4") as stream:
        stream.write(b"owned transfer evidence, not a media-quality fixture")
    identity = stage.member_identity("source.mp4")
    retained = directory.path / "retained-original-transfer"
    stage.path.rename(retained)
    stage.path.symlink_to(shared, target_is_directory=True)
    refused(lambda: stage.remove_owned("source.mp4", identity), "changed staging cleanup")
    assert owner.read_bytes() == b"original owner bytes"
    assert (
        retained / "source.mp4"
    ).read_bytes() == b"owned transfer evidence, not a media-quality fixture"

    store = SubmissionStore(root / "outbox" / "requests.sqlite3")
    assert store.pending() == []
    assert SubmissionStore(store.path).pending() == []
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    observations.append({"case": "private native outbox reopen", "result": "passed"})
    store.path.unlink()
    refused(store.pending, "missing outbox main file")
    assert not store.path.exists()

    filesystem = subprocess.run(
        ["stat", "-f", "-c", "%T", str(root)],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    package = Path(__file__).resolve().parents[2] / "src" / "hawedit"
    result = {
        "schema": 1,
        "scope": "Bounded POSIX observations, not a canonical Linux gate or mount certificate",
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
    destination = Path(sys.argv[1])
    if destination.exists():
        raise RuntimeError("Refusing to overwrite earlier POSIX evidence")
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{len(observations)} actual native POSIX observations passed; {filesystem}")


if __name__ == "__main__":
    main()
