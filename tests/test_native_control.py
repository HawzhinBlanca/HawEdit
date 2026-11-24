"""Actual fixed-control bytes; not Linux/model/provider acceptance."""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from hawedit.native_io import NativeIOError, run_native
from hawedit.studio_private import PrivateDirectory


def execute(tmp_path: Path, code: str, **options: Any) -> Any:
    private = PrivateDirectory(tmp_path / "execution", exclusive=True)
    executable = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    defaults: dict[str, Any] = dict(
        input_bytes=b"", timeout_seconds=4, output_limit_bytes=131072, control_channel=True
    )
    defaults.update(options)
    return run_native(
        (str(executable), "-I", "-B", "-c", code),
        cwd=private.path,
        environment={"SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows")},
        expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        **defaults,
    )


PREAMBLE = """import os,struct,sys,time
def exact(n):
    data=bytearray()
    while len(data)<n:
        part=os.read(0,n-len(data))
        if not part: raise RuntimeError('premature owner EOF')
        data.extend(part)
    return bytes(data)
assert exact(4)==b'HEI1'
payload=exact(struct.unpack('!I',exact(4))[0])
nonce=os.urandom(16)
"""


def available(tmp_path: Path) -> bool:
    if os.name == "nt":
        return True
    with pytest.raises(NativeIOError, match="Windows"):
        execute(tmp_path, "raise RuntimeError('must not launch')")
    return False


def test_native_control_binary_request(tmp_path: Path) -> None:
    if not available(tmp_path):
        return
    payload = bytes(range(256)) * 256
    result = execute(
        tmp_path,
        PREAMBLE
        + "assert payload==bytes(range(256))*256\n"
        + "os.write(1,b'HEC1'+nonce)\nassert exact(20)==b'HER1'+nonce\n"
        "os.write(1,b'HED1')\nassert os.read(0,1)==b''\n",
        input_bytes=payload,
    )
    assert result.exit_code == 0
    assert result.stdout[:4] == b"HEC1" and result.stdout[-4:] == b"HED1"
    assert len(result.stdout) == 24 and result.stderr == b""
    assert not hasattr(result, "completed") and not hasattr(result, "ready")


def test_native_control_fragmented_challenge(tmp_path: Path) -> None:
    if not available(tmp_path):
        return
    result = execute(
        tmp_path,
        PREAMBLE + "for value in b'HEC1'+nonce:\n os.write(1,bytes([value])); time.sleep(.005)\n"
        "assert exact(20)==b'HER1'+nonce\n"
        "for value in b'HED1':\n os.write(1,bytes([value])); time.sleep(.005)\n"
        "assert os.read(0,1)==b''\n",
    )
    assert result.exit_code == 0 and len(result.stdout) == 24 and result.stderr == b""


@pytest.mark.parametrize("invalid", [None, 0, 1, "yes", (), []])
def test_native_control_invalid_mode_never_launches(tmp_path: Path, invalid: Any) -> None:
    marker = tmp_path / "unexpected.txt"
    with pytest.raises(NativeIOError, match="control"):
        execute(
            tmp_path,
            f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            control_channel=invalid,
        )
    assert not marker.exists()


@pytest.mark.parametrize("invalid", [None, True, 0, -1, float("nan"), float("inf"), "1", 43201])
def test_native_control_invalid_exchange_deadline_never_launches(
    tmp_path: Path, invalid: Any
) -> None:
    marker = tmp_path / "unexpected.txt"
    with pytest.raises(NativeIOError, match="control"):
        execute(
            tmp_path,
            f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            control_timeout_seconds=invalid,
        )
    assert not marker.exists()


@pytest.mark.parametrize(
    "tail",
    [
        "os.write(1,b'HED1'); time.sleep(20)",
        "os.write(1,b'BAD!'+nonce); time.sleep(20)",
        "os.write(1,b'HEC1'+nonce+b'HEC1'+os.urandom(16)); time.sleep(20)",
        "os.write(1,b'HEC1'+nonce); assert exact(20)==b'HER1'+nonce; "
        "os.write(1,b'HEC1'+nonce); time.sleep(20)",
        "os.write(1,b'HEC1'+nonce[:8])",
        "os.write(1,b'HEC1'+nonce); assert exact(20)==b'HER1'+nonce; "
        "os.write(1,b'HED1TRAIL'); time.sleep(20)",
    ],
    ids=[
        "premature-terminal",
        "bad-frame",
        "unsolicited-batch",
        "replayed-challenge",
        "truncated-eof",
        "trailing-terminal",
    ],
)
def test_native_control_malformed_exchange_refuses(tmp_path: Path, tail: str) -> None:
    with pytest.raises(NativeIOError, match="control|Windows"):
        execute(tmp_path, PREAMBLE + tail)


def test_native_control_stalled_supervisor(tmp_path: Path) -> None:
    with pytest.raises(NativeIOError, match="deadline|Windows"):
        execute(tmp_path, PREAMBLE + "time.sleep(20)", timeout_seconds=0.4)


def test_native_control_nonreader_deadline(tmp_path: Path) -> None:
    with pytest.raises(NativeIOError, match="deadline|Windows"):
        execute(
            tmp_path, "import time; time.sleep(20)", input_bytes=b"X" * 65536, timeout_seconds=0.4
        )


def test_native_control_shared_output_limit(tmp_path: Path) -> None:
    with pytest.raises(NativeIOError, match="output limit|Windows"):
        execute(
            tmp_path,
            PREAMBLE + "os.write(1,b'HEC1'+nonce); assert exact(20)==b'HER1'+nonce; "
            "os.write(2,b'X'*1048576); time.sleep(20)",
            output_limit_bytes=24,
        )


def test_native_control_terminal_not_scope_completion(tmp_path: Path) -> None:
    with pytest.raises(NativeIOError, match="deadline|Windows"):
        execute(
            tmp_path,
            PREAMBLE + "os.write(1,b'HEC1'+nonce); assert exact(20)==b'HER1'+nonce; "
            "os.write(1,b'HED1'); os.close(1); os.close(2); time.sleep(20)",
            timeout_seconds=0.4,
        )


def test_native_control_multiple_exchanges(tmp_path: Path) -> None:
    if not available(tmp_path):
        return
    result = execute(
        tmp_path,
        PREAMBLE + "for _ in range(10):\n"
        " nonce=os.urandom(16)\n"
        " for value in b'HEC1'+nonce:\n"
        "  os.write(1,bytes([value])); time.sleep(.001)\n"
        " assert exact(20)==b'HER1'+nonce\n"
        "os.write(1,b'HED1'); assert os.read(0,1)==b''\n",
    )
    assert result.exit_code == 0 and len(result.stdout) == 204 and result.stderr == b""


def test_native_control_exchange_deadline(tmp_path: Path) -> None:
    with pytest.raises(NativeIOError, match="control.*deadline|Windows"):
        execute(
            tmp_path,
            PREAMBLE + "os.write(1,b'HEC1'+nonce[:1]); time.sleep(20)",
            timeout_seconds=4,
            control_timeout_seconds=0.2,
        )


def test_native_control_missing_terminal(tmp_path: Path) -> None:
    with pytest.raises(NativeIOError, match="control|Windows"):
        execute(tmp_path, PREAMBLE)


@pytest.mark.parametrize("payload", [b"", bytes(range(256)) * 256], ids=["empty", "binary"])
def test_native_control_false_preserves_binary_eof(tmp_path: Path, payload: bytes) -> None:
    if not available(tmp_path):
        return
    result = execute(
        tmp_path,
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        input_bytes=payload,
        control_channel=False,
    )
    assert result.exit_code == 0 and result.stdout == payload and result.stderr == b""


def test_native_control_parser_nonce_budget() -> None:
    # Pure framing-state test, not an independent native scope or model run.
    control = importlib.import_module("hawedit.native_io")._ControlExchange(b"", 43200)
    control.written(8)
    for nonce in range(65536):
        assert not control.receive(b"HEC1" + nonce.to_bytes(16, "big"))
        control.written(20)
    with pytest.raises(NativeIOError, match="control.*budget"):
        control.receive(b"HEC1" + (65536).to_bytes(16, "big"))
