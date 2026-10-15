"""Preparation for deliberate byte drift of a disposable copied executable."""

import math
import sys
import time
from pathlib import Path


def replace_test_executable(replacement: Path, binary: Path, *, timeout_s: float = 10.0) -> None:
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("Executable mutation requires a finite positive timeout")
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            replacement.replace(binary)
            return
        except PermissionError as exc:
            if sys.platform != "win32" or exc.winerror not in (5, 32):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.05, remaining))
