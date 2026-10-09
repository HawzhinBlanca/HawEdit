"""Bounded audit bytes, not original Linux/effects or security admission."""

from __future__ import annotations

import hashlib
import os
import selectors
import shutil
import stat
import subprocess
import time
from pathlib import Path

from hawedit.native_io import NativeIOError, NativeIOResult, run_native

_MAX_OUTPUT = 16 * 1024**2
_CLEANUP_SECONDS = 5
_UNCERTAIN: list[object] = []


class AuditCaptureError(RuntimeError):
    """Capture refused; raw output cannot certify an accepted audit."""


def _windows_capture(
    command: list[str], deadline: float, stdout_limit: int, stderr_limit: int
) -> NativeIOResult:
    selected = shutil.which(command[0])
    if selected is None:
        raise AuditCaptureError(
            f"cannot start WSL audit process: executable not found: {command[0]}"
        )
    executable = Path(selected).resolve(strict=True)
    info = executable.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= 256 * 1024**2
    ):
        raise AuditCaptureError(
            "selected audit executable is not a regular single-link image under256MiB; "
            "configure --wsl-executable with the actual WSL application executable; "
            "no launcher substitution was performed"
        )
    digest = hashlib.sha256()
    with executable.open("rb") as stream:
        while chunk := stream.read(1024**2):
            if time.monotonic() >= deadline:
                raise AuditCaptureError("WSL audit process deadline expired before launch")
            digest.update(chunk)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AuditCaptureError("WSL audit process deadline expired before launch")
    try:
        return run_native(
            [str(executable), *command[1:]],
            cwd=Path.cwd(),
            environment=dict(os.environ),
            expected_executable_sha256=digest.hexdigest(),
            input_bytes=b"",
            timeout_seconds=remaining,
            output_limit_bytes=None,
            stdout_limit_bytes=stdout_limit,
            stderr_limit_bytes=stderr_limit,
        )
    except NativeIOError as exc:
        if executable.name.lower() == "wsl.exe":
            # A stopped original Windows Job does not prove Linux effect completion.
            _UNCERTAIN.append((executable, tuple(command), exc))
        raise AuditCaptureError(f"WSL audit process refused: {exc}") from exc


def _posix_capture(
    command: list[str], deadline: float, stdout_limit: int, stderr_limit: int
) -> NativeIOResult:
    set_blocking = getattr(os, "set_blocking", None)
    if not callable(set_blocking):
        raise AuditCaptureError("nonblocking audit descriptors unavailable before launch")
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
    )
    normal = False
    try:
        assert process.stdout is not None and process.stderr is not None
        captured = [bytearray(), bytearray()]
        limits = (stdout_limit, stderr_limit)
        with selectors.DefaultSelector() as selector:
            for index, stream in enumerate((process.stdout, process.stderr)):
                set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AuditCaptureError(
                        "WSL audit process deadline expired while capturing output"
                    )
                for key, _events in selector.select(remaining):
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fd)
                        continue
                    index = int(key.data)
                    if len(captured[index]) + len(chunk) > limits[index]:
                        name = "stdout" if index == 0 else "stderr"
                        raise AuditCaptureError(
                            f"WSL audit process exceeded its {name} output limit"
                        )
                    captured[index].extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AuditCaptureError("WSL audit process deadline expired before root completion")
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise AuditCaptureError(
                    "WSL audit process deadline expired waiting for original root"
                ) from exc
        normal = True
        return NativeIOResult(code, bytes(captured[0]), bytes(captured[1]))
    finally:
        failures: list[BaseException] = []
        if not normal:
            # Keep the original observation; root death is not descendant quiescence.
            _UNCERTAIN.append(process)
        for output_stream in (process.stdout, process.stderr):
            if output_stream is not None:
                try:
                    output_stream.close()
                except OSError as exc:
                    failures.append(exc)
        if not normal:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=_CLEANUP_SECONDS)
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append(exc)
        if failures:
            if normal:
                _UNCERTAIN.append(process)
            raise AuditCaptureError(
                "original audit IO/root cleanup uncertain; retained owner refuses further launches"
            ) from failures[0]


def capture_bounded(
    command: list[str], *, timeout_seconds: int, stdout_limit: int, stderr_limit: int
) -> NativeIOResult:
    """Capture exact finite streams; no success after EOF or root deadline expiry."""
    if type(timeout_seconds) is not int or not 0 < timeout_seconds <= 43200:
        raise AuditCaptureError("process timeout must be an exact integer in1..43200 seconds")
    if any(
        type(limit) is not int or not 0 < limit <= _MAX_OUTPUT
        for limit in (stdout_limit, stderr_limit)
    ):
        raise AuditCaptureError("each process output limit must be an exact integer in1..16MiB")
    if not command or any(
        not isinstance(part, str) or not part or "\0" in part for part in command
    ):
        raise AuditCaptureError("audit command must contain nonempty strings without NUL")
    if _UNCERTAIN:
        raise AuditCaptureError(
            "audit execution uncertain; reconcile before further owner launches"
        )
    deadline = time.monotonic() + timeout_seconds
    try:
        if os.name == "nt":
            return _windows_capture(command, deadline, stdout_limit, stderr_limit)
        if os.name == "posix":
            return _posix_capture(command, deadline, stdout_limit, stderr_limit)
        raise AuditCaptureError("bounded audit capture is unavailable on this platform")
    except (OSError, ValueError) as exc:
        raise AuditCaptureError(f"cannot capture WSL audit process: {exc}") from exc
