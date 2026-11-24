"""Portable declaration refusal, with native enforcement in rooted-controller tests."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from hawedit.linux_rooted_worker import RootedCommand
from hawedit.linux_snapshot import LinuxSnapshotError, SnapshotFile


@pytest.mark.parametrize(
    ("memory", "cpu", "fds"),
    [
        (True, 1, 64),
        (64 * 1024**2 - 1, 1, 64),
        (8 * 1024**3 + 1, 1, 64),
        (128 * 1024**2, 0, 64),
        (128 * 1024**2, 31, 64),
        (128 * 1024**2, True, 64),
        (128 * 1024**2, 1.0, 64),
        (128 * 1024**2, 1, 63),
        (128 * 1024**2, 1, 4097),
        (128 * 1024**2, 1, True),
    ],
)
def test_rooted_worker_resource_declarations_refuse(memory: int, cpu: int, fds: int) -> None:
    from hawedit.linux_worker_resources import WorkerResourceLimits

    with pytest.raises(LinuxSnapshotError, match="resource declaration"):
        WorkerResourceLimits(memory, cpu, fds)


def test_rooted_worker_resource_defaults_unchanged(tmp_path: Path) -> None:
    file = SnapshotFile(tmp_path / "absent", "bin/probe", "0" * 64, 1, True)
    command = RootedCommand((file,), "bin/probe")
    assert command.resources is None
    assert not file.source.exists()


@pytest.mark.parametrize("invalid", [True, False, 1, (), {}])
def test_rooted_command_rejects_untyped_resources(tmp_path: Path, invalid: object) -> None:
    file = SnapshotFile(tmp_path / "absent", "bin/probe", "0" * 64, 1, True)
    with pytest.raises(LinuxSnapshotError, match="resource declaration"):
        RootedCommand((file,), "bin/probe", resources=invalid)  # type: ignore[arg-type]
    assert not file.source.exists()


def test_rooted_worker_resource_declaration_is_frozen() -> None:
    from hawedit.linux_worker_resources import WorkerResourceLimits

    limits = WorkerResourceLimits(128 * 1024**2, 3, 64)
    with pytest.raises(FrozenInstanceError):
        limits.cpu_seconds = 4  # type: ignore[misc]


def test_rooted_command_revalidates_mutated_resource_declaration(tmp_path: Path) -> None:
    from hawedit.linux_worker_resources import WorkerResourceLimits

    limits = WorkerResourceLimits(128 * 1024**2, 3, 64)
    object.__setattr__(limits, "cpu_seconds", True)
    file = SnapshotFile(tmp_path / "absent", "bin/probe", "0" * 64, 1, True)
    with pytest.raises(LinuxSnapshotError, match="resource declaration"):
        RootedCommand((file,), "bin/probe", resources=limits)


def test_rooted_worker_resources_cannot_mutate_host_limits() -> None:
    from hawedit.linux_worker_resources import WorkerResourceLimits

    with pytest.raises(LinuxSnapshotError, match="original context"):
        WorkerResourceLimits(128 * 1024**2, 3, 64).apply()
