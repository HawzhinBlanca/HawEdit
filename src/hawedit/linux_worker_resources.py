"""Finite process-local diagnostic limits; not VRAM or production admission."""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hawedit.linux_snapshot import LinuxSnapshotError

if TYPE_CHECKING or sys.platform == "linux":
    import resource


@dataclass(frozen=True)
class WorkerResourceLimits:
    """Explicit diagnostic bounds, distinct from copied-image byte quotas."""

    address_space_bytes: int
    cpu_seconds: int
    open_files: int

    def __post_init__(self) -> None:
        if (
            type(self.address_space_bytes) is not int
            or not 64 * 1024**2 <= self.address_space_bytes <= 8 * 1024**3
            or type(self.cpu_seconds) is not int
            or not 1 <= self.cpu_seconds <= 30
            or type(self.open_files) is not int
            or not 64 <= self.open_files <= 4096
        ):
            raise LinuxSnapshotError("Rooted worker resource declaration refused")

    def apply(self) -> None:
        """Lower only original PID2 hard limits, before any copied execution."""
        self.__post_init__()
        if (
            sys.platform != "linux"
            or os.getpid() != 2
            or os.getppid() != 1
            or threading.get_native_id() != 2
            or len(tuple(os.scandir("/proc/self/task"))) != 1
        ):
            raise LinuxSnapshotError("Rooted worker resource original context refused")
        with open("/proc/self/status", encoding="ascii") as stream:
            fields = dict(line.split(":", 1) for line in stream if ":" in line)
        if any(
            int(fields[key].strip(), 16)
            for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        ):
            raise LinuxSnapshotError("Rooted worker resource capabilities not dropped")
        if any(int(name) >= self.open_files for name in os.listdir("/proc/self/fd")):
            raise LinuxSnapshotError("Rooted worker resource existing descriptor exceeds bound")
        limits = (
            (resource.RLIMIT_AS, self.address_space_bytes),
            (resource.RLIMIT_CPU, self.cpu_seconds),
            (resource.RLIMIT_NOFILE, self.open_files),
            (resource.RLIMIT_CORE, 0),
        )
        try:
            # Refuse a requested relaxation of stricter inherited policy before any change.
            for kind, value in limits:
                _, hard = resource.getrlimit(kind)
                if hard != resource.RLIM_INFINITY and value > hard:
                    raise LinuxSnapshotError("Rooted worker resource inherited hard bound stricter")
            for kind, value in limits:
                resource.setrlimit(kind, (value, value))
            if any(resource.getrlimit(kind) != (value, value) for kind, value in limits):
                raise LinuxSnapshotError("Rooted worker resource kernel readback differs")
        except (OSError, ValueError) as exc:
            raise LinuxSnapshotError("Rooted worker resource enforcement refused") from exc
