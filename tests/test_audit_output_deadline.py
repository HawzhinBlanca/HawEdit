"""Real subprocess/pipe faults in separate owners; no runner or IO doubles."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from hawedit.bounded_audit_io import AuditCaptureError, _windows_capture, capture_bounded


def _observe(code: str, **options: Any) -> dict[str, Any]:
    source = str(Path(__file__).resolve().parents[1] / "src")
    arguments = dict(timeout_seconds=10, stdout_limit=8192, stderr_limit=8192)
    arguments.update(options)
    owner = f"""
import hashlib,json,os,pathlib,sys,time
sys.path.insert(0,{source!r})
from hawedit import wsl_vex_gate as gate
exe=getattr(sys,'_base_executable',sys.executable)
started=time.monotonic()
try:
    result=gate._run_bounded([exe,'-I','-B','-c',{code!r}],**{arguments!r})
except gate.LiveVexGateError as exc:
    report={{'error':str(exc),'elapsed':time.monotonic()-started}}
    if os.name!='nt':
        try:
            gate._run_bounded([exe,'-I','-B','-c','raise SystemExit(0)'],
                timeout_seconds=1,stdout_limit=1,stderr_limit=1)
        except gate.LiveVexGateError as retry:
            report['retry_error']=str(retry)
else:
    report={{'code':result.returncode,'elapsed':time.monotonic()-started}}
    for name in ('stdout','stderr'):
        value=getattr(result,name)
        report[name+'_size']=len(value)
        report[name+'_sha256']=hashlib.sha256(value).hexdigest()
        if len(value)<=4096: report[name+'_hex']=value.hex()
print(json.dumps(report),flush=True)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", owner],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert not result.stderr
    report: dict[str, Any] = json.loads(result.stdout)
    return report


@pytest.mark.parametrize("stream", [1, 2])
@pytest.mark.parametrize("timeout_root", [False, True])
def test_audit_deadline_covers_inherited_stream(stream: int, timeout_root: bool) -> None:
    descendant = "import time; time.sleep(4)"
    code = (
        "import os,subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-I','-B','-c',{descendant!r}],"
        f"stdout={'None' if stream == 1 else 'subprocess.DEVNULL'},"
        f"stderr={'None' if stream == 2 else 'subprocess.DEVNULL'}); "
        + ("time.sleep(10)" if timeout_root else "raise SystemExit(0)")
    )
    report = _observe(code, timeout_seconds=1)
    assert "error" in report, report
    assert "deadline" in report["error"] or "seconds" in report["error"]
    assert report["elapsed"] <= 2, report
    if "retry_error" in report:
        assert "uncertain" in report["retry_error"].lower()


def test_audit_eof_does_not_complete_live_root() -> None:
    report = _observe("import os,time; os.close(1); os.close(2); time.sleep(10)", timeout_seconds=1)
    assert "error" in report and report["elapsed"] <= 2, report


def test_audit_binary_control_and_nonzero_exit() -> None:
    payload = bytes(range(256))
    report = _observe(
        "import sys; p=bytes(range(256)); sys.stdout.buffer.write(p); "
        "sys.stderr.buffer.write(p[::-1]); raise SystemExit(7)"
    )
    assert report["code"] == 7
    assert bytes.fromhex(report["stdout_hex"]) == payload
    assert bytes.fromhex(report["stderr_hex"]) == payload[::-1]


@pytest.mark.parametrize("sizes", [(1, 1), (4096, 64), (8192, 8192)])
def test_audit_exact_independent_bounds(sizes: tuple[int, int]) -> None:
    stdout, stderr = sizes
    report = _observe(
        f"import sys; sys.stdout.buffer.write(b'A'*{stdout}); "
        f"sys.stderr.buffer.write(b'B'*{stderr})",
        stdout_limit=stdout,
        stderr_limit=stderr,
    )
    assert report["code"] == 0, report
    assert report["stdout_size"] == stdout and report["stderr_size"] == stderr
    assert report["stdout_sha256"] == hashlib.sha256(b"A" * stdout).hexdigest()
    assert report["stderr_sha256"] == hashlib.sha256(b"B" * stderr).hexdigest()


def test_audit_full_scanner_output_contract() -> None:
    stdout, stderr = 16 * 1024**2, 65536
    report = _observe(
        f"import sys; sys.stdout.buffer.write(b'A'*{stdout}); "
        f"sys.stderr.buffer.write(b'B'*{stderr})",
        timeout_seconds=30,
        stdout_limit=stdout,
        stderr_limit=stderr,
    )
    assert report["code"] == 0, report
    assert report["stdout_size"] == stdout and report["stderr_size"] == stderr
    assert report["stdout_sha256"] == hashlib.sha256(b"A" * stdout).hexdigest()
    assert report["stderr_sha256"] == hashlib.sha256(b"B" * stderr).hexdigest()


@pytest.mark.parametrize("stream", [1, 2])
def test_audit_one_byte_overflow(stream: int) -> None:
    name = "stdout" if stream == 1 else "stderr"
    report = _observe(f"import os; os.write({stream},b'X'*65)", stdout_limit=64, stderr_limit=64)
    assert "error" in report and f"{name} output limit" in report["error"], report
    if "retry_error" in report:
        assert "uncertain" in report["retry_error"].lower()


@pytest.mark.parametrize("name", ["timeout_seconds", "stdout_limit", "stderr_limit"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_audit_invalid_budget_before_launch(tmp_path: Path, name: str, value: Any) -> None:
    marker = tmp_path / "must-not-exist.txt"
    report = _observe(
        f"import pathlib; pathlib.Path({str(marker)!r}).write_text('launched')", **{name: value}
    )
    assert "error" in report, report
    assert not marker.exists()


@pytest.mark.parametrize("command", [[], [""], ["bad\0name"], ["valid", 0], ["valid", ""]])
def test_audit_invalid_command_refuses_before_launch(command: Any) -> None:
    with pytest.raises(AuditCaptureError, match="command"):
        capture_bounded(command, timeout_seconds=1, stdout_limit=1, stderr_limit=1)


def test_audit_linked_executable_refuses_actionably(tmp_path: Path) -> None:
    image = tmp_path / "generated-invalid-image.exe"
    image.write_bytes(b"MZ-not-an-executable\n")
    image.chmod(0o700)
    alias = tmp_path / "retained-image.exe"
    os.link(image, alias)
    assert image.stat().st_nlink == 2
    with pytest.raises(AuditCaptureError, match="configure --wsl-executable"):
        _windows_capture([str(image)], time.monotonic() + 1, 1, 1)
    assert image.read_bytes() == alias.read_bytes() == b"MZ-not-an-executable\n"
