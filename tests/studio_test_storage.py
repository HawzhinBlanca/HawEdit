"""Create new native private test storage, independently of the binding under test."""

from __future__ import annotations

import os
from pathlib import Path

from hawedit.windows_security import create_private_directory


def create_private_test_root(parent: Path) -> Path:
    root = parent / "private-test-storage"
    make_private_directory(root)
    return root


def make_private_directory(path: Path) -> None:
    if os.name == "nt":
        create_private_directory(path)
    else:
        path.mkdir(mode=0o700)


def seed_private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
