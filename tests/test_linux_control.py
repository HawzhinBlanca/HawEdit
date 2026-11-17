"""Real Linux pipe protocol, not GPU/resource or delivery acceptance."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

DRIVER = r"""
import json,os,select,signal,struct,subprocess,sys,time
p=subprocess.Popen([sys.executable,'-I','-B','-c',SUBJECT],
 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
original=os.pidfd_open(p.pid,0)
assert p.stdin is not None and p.stdout is not None and p.stderr is not None
for stream in (p.stdin,p.stdout,p.stderr): os.set_blocking(stream.fileno(),False)
seen=bytearray()
def exact(n):
 data=bytearray(); end=time.monotonic()+5
 while len(data)<n:
  left=end-time.monotonic()
  assert left>0 and select.select([p.stdout],[],[],left)[0], 'read deadline'
  part=os.read(p.stdout.fileno(),n-len(data))
  assert part, 'unexpected child EOF'
  data.extend(part); seen.extend(part)
 return bytes(data)
def write(data):
 end=time.monotonic()+5
 while data:
  left=end-time.monotonic()
  assert left>0 and select.select([],[p.stdin],[],left)[1], 'write deadline'
  try: count=os.write(p.stdin.fileno(),data[:4096])
  except BlockingIOError: continue
  assert count>0
  data=data[count:]
def request(payload=b''):
 write(b'HEI1'+struct.pack('!I',len(payload))+payload)
def challenge():
 frame=exact(20); assert frame[:4]==b'HEC1'; return frame[4:]
def reply(nonce): write(b'HER1'+nonce)
try:
 ACTION
 assert select.select([original],[],[],5)[0], 'child exit deadline'
 p.wait(timeout=1)
 out=bytearray(); err=bytearray()
 for stream,target in ((p.stdout,out),(p.stderr,err)):
  while True:
   part=os.read(stream.fileno(),4096)
   if not part: break
   target.extend(part)
 print(json.dumps({'exit':p.returncode,'stderr':err.decode(),
  'seen':bytes(seen).hex(),'tail':bytes(out).hex()}))
finally:
 if not select.select([original],[],[],0)[0]:
  signal.pidfd_send_signal(original,signal.SIGKILL,None,0)
  assert select.select([original],[],[],3)[0]
 p.wait(timeout=1)
 for stream in (p.stdin,p.stdout,p.stderr): stream.close()
 os.close(original)
"""


def subject(body: str, *, exchange: float = 0.3, overall: float = 4.0) -> str:
    path = Path(__file__).parents[1] / "src/hawedit/linux_control.py"
    assert path.is_file(), "Linux owner endpoint API not implemented"
    source = path.read_text(encoding="utf-8")
    return (
        "import json,os,sys,threading,time\n"
        "ns={'__name__':'hawedit_linux_control_under_test'}\n"
        f"exec(compile({source!r},'linux_control.py','exec'),ns)\n"
        "Channel=ns['LinuxOwnerChannel']; Error=ns['LinuxOwnerError']\n"
        "channel=None\ntry:\n"
        f" channel=Channel(exchange_timeout_seconds={exchange!r},"
        f"overall_timeout_seconds={overall!r})\n"
        + "\n".join(" " + line for line in body.splitlines())
        + "\nexcept Error as exc:\n"
        " print(json.dumps({'refused':str(exc)}),file=sys.stderr,flush=True)\n"
        "finally:\n"
        " if channel is not None:\n"
        "  try: channel.close()\n"
        "  except Error as exc:\n"
        "   print(json.dumps({'cleanup':str(exc)}),file=sys.stderr,flush=True)\n"
    )


def execute(tmp_path: Path, code: str, *, control: bool = False, payload: bytes = b"") -> Any:
    if os.name == "nt":
        from hawedit.native_io import run_native
        from hawedit.studio_private import PrivateDirectory

        executable = Path("C:/Program Files/WSL/wsl.exe")
        private = PrivateDirectory(tmp_path / "execution", exclusive=True)
        return run_native(
            (str(executable), "--exec", "/usr/bin/python3", "-I", "-B", "-c", code),
            cwd=private.path,
            environment={
                "SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows"),
                "USERPROFILE": os.environ["USERPROFILE"],
            },
            expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            input_bytes=payload,
            timeout_seconds=15,
            output_limit_bytes=262144,
            control_channel=control,
            control_timeout_seconds=5,
        )
    assert not control, "Linux driver supplies original owner protocol"
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        timeout=15,
        check=False,
    )


def drive(tmp_path: Path, body: str, action: str, **options: float) -> dict[str, Any]:
    code = DRIVER.replace("SUBJECT", repr(subject(body, **options))).replace(
        " ACTION", "\n".join(" " + line for line in action.splitlines())
    )
    result = execute(tmp_path, code)
    exit_code = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert exit_code == 0, result.stderr.decode(errors="replace")
    record: dict[str, Any] = json.loads(result.stdout)
    assert record["exit"] == 0, record["stderr"]
    return record


def refused(record: dict[str, Any], phrase: str) -> None:
    records = [json.loads(line) for line in record["stderr"].splitlines()]
    assert any(phrase in item.get("refused", "") for item in records), records
    assert b"HED1" not in bytes.fromhex(record["tail"])


@pytest.mark.parametrize("value", [None, True, 0, -1, float("nan"), float("inf"), "1", 43201])
@pytest.mark.parametrize("name", ["exchange_timeout_seconds", "overall_timeout_seconds"])
def test_linux_owner_invalid_deadline(name: str, value: Any) -> None:
    module = importlib.import_module("hawedit.linux_control")
    with pytest.raises(module.LinuxOwnerError, match="deadline"):
        module.LinuxOwnerChannel(**{name: value})


def test_linux_owner_current_host_boundary() -> None:
    module = importlib.import_module("hawedit.linux_control")
    with pytest.raises(module.LinuxOwnerError, match="Linux|pipe"):
        module.LinuxOwnerChannel()


def test_linux_owner_regular_stdio_refuses(tmp_path: Path) -> None:
    record = drive(tmp_path, "pass", "request()")
    assert record["stderr"] == ""
    # The isolated child really replaces original STDIN with a regular /dev/null FD.
    code = subject("pass").replace(
        "channel=None",
        "fd=os.open('/dev/null',os.O_RDONLY); os.dup2(fd,0); os.close(fd)\nchannel=None",
    )
    driver = DRIVER.replace("SUBJECT", repr(code)).replace(" ACTION", " pass")
    (tmp_path / "regular").mkdir()
    result = execute(tmp_path / "regular", driver)
    assert getattr(result, "exit_code", getattr(result, "returncode", None)) == 0
    refused(json.loads(result.stdout), "pipe")


def test_linux_owner_native_interoperability(tmp_path: Path) -> None:
    body = (
        "assert channel.receive_request()==bytes(range(256))*256\n"
        "channel.exchange()\nchannel.finish()"
    )
    if os.name == "nt":
        result = execute(
            tmp_path, subject(body, exchange=5), control=True, payload=bytes(range(256)) * 256
        )
        assert result.exit_code == 0 and result.stderr == b""
        assert result.stdout[:4] == b"HEC1" and result.stdout[-4:] == b"HED1"
        assert len(result.stdout) == 24
    else:
        record = drive(
            tmp_path,
            body,
            "request(bytes(range(256))*256)\nreply(challenge())\n"
            "assert exact(4)==b'HED1'\np.stdin.close()",
        )
        assert record["stderr"] == "" and record["tail"] == ""


def test_linux_owner_fragmented_request(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "assert channel.receive_request()==b'abc\\x00'\nchannel.exchange()\nchannel.finish()",
        "for value in b'HEI1'+struct.pack('!I',4)+b'abc\\x00':\n"
        " write(bytes([value])); time.sleep(.002)\n"
        "reply(challenge())\nassert exact(4)==b'HED1'\np.stdin.close()",
    )
    assert record["stderr"] == "" and record["tail"] == ""


@pytest.mark.parametrize(
    "frame", [b"BAD!\0\0\0\0", b"HEI1\x01\x00\x00\x01", b"HE", b"HEI1\0\0\0\x02X"]
)
def test_linux_owner_invalid_request(tmp_path: Path, frame: bytes) -> None:
    record = drive(tmp_path, "channel.receive_request()", f"write({frame!r})\np.stdin.close()")
    refused(record, "request")


def test_linux_owner_real_exchanges(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\nfor _ in range(10): channel.exchange()\nchannel.finish()",
        "request()\nnonces=[]\nfor _ in range(10):\n"
        " nonce=challenge(); assert nonce not in nonces; nonces.append(nonce); reply(nonce)\n"
        "assert exact(4)==b'HED1'\np.stdin.close()",
    )
    assert record["stderr"] == "" and len(bytes.fromhex(record["seen"])) == 204


@pytest.mark.parametrize("reply_frame", [b"BAD!" + b"x" * 16, b"HER1" + b"x" * 16, b"HER"])
def test_linux_owner_bad_reply(tmp_path: Path, reply_frame: bytes) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\nchannel.exchange()",
        f"request()\nchallenge()\nwrite({reply_frame!r})\np.stdin.close()",
    )
    refused(record, "reply")


def test_linux_owner_replayed_reply(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\nchannel.exchange()\nchannel.exchange()",
        "request()\nfirst=challenge(); reply(first)\nassert challenge()!=first\nreply(first)",
    )
    refused(record, "reply")


def test_linux_owner_stalled_request(tmp_path: Path) -> None:
    record = drive(tmp_path, "channel.receive_request()", "pass")
    refused(record, "deadline")


def test_linux_owner_stalled_reply(tmp_path: Path) -> None:
    record = drive(
        tmp_path, "channel.receive_request()\nchannel.exchange()", "request()\nchallenge()"
    )
    refused(record, "deadline")


def test_linux_owner_nonreading_owner(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\nwhile True:\n"
        " try: os.write(channel._write_fd,b'X'*4096)\n"
        " except BlockingIOError: break\nchannel.exchange()",
        "request()",
    )
    refused(record, "deadline")


def test_linux_owner_overall_deadline(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\ntime.sleep(.3)\nchannel.exchange()",
        "request()",
        exchange=1.0,
        overall=0.2,
    )
    refused(record, "deadline")


@pytest.mark.parametrize(
    "body",
    [
        "channel.exchange()",
        "channel.finish()",
        "channel.receive_request()\nchannel.receive_request()",
        "channel.receive_request()\nchannel.finish()",
    ],
)
def test_linux_owner_invalid_order(tmp_path: Path, body: str) -> None:
    record = drive(tmp_path, body, "request()")
    refused(record, "order")


def test_linux_owner_single_lifetime(tmp_path: Path) -> None:
    record = drive(tmp_path, "channel.close()\nChannel()", "pass")
    refused(record, "lifetime")


def test_linux_owner_foreign_thread(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "errors=[]\ndef foreign():\n"
        " try: channel.receive_request()\n except Error as exc: errors.append(str(exc))\n"
        "thread=threading.Thread(target=foreign); thread.start(); thread.join(1)\n"
        "assert not thread.is_alive() and len(errors)==1 and 'creator' in errors[0]\n"
        "channel.receive_request()\nchannel.exchange()\nchannel.finish()",
        "request()\nreply(challenge())\nassert exact(4)==b'HED1'\np.stdin.close()",
    )
    assert record["stderr"] == ""


def test_linux_owner_foreign_process(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "pid=os.fork()\nif pid==0:\n"
        " try: channel.receive_request()\n"
        " except Error as exc: os._exit(0 if 'creator' in str(exc) else 2)\n"
        " os._exit(3)\nassert os.waitpid(pid,0)[1]==0\n"
        "channel.receive_request()\nchannel.exchange()\nchannel.finish()",
        "request()\nreply(challenge())\nassert exact(4)==b'HED1'\np.stdin.close()",
    )
    assert record["stderr"] == ""


def test_linux_owner_terminal_requires_owner_eof(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\nchannel.exchange()\nchannel.finish()",
        "request()\nreply(challenge())\nassert exact(4)==b'HED1'",
    )
    refused(record, "deadline")


def test_linux_owner_terminal_trailing_reply(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\nchannel.exchange()\nchannel.finish()",
        "request()\nreply(challenge())\nassert exact(4)==b'HED1'\nwrite(b'X')",
    )
    refused(record, "trailing")


def test_linux_owner_owned_descriptor_cleanup(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "assert not os.get_inheritable(channel._read_fd)\n"
        "assert not os.get_inheritable(channel._write_fd)\n"
        "assert not os.get_blocking(0) and not os.get_blocking(1)\n"
        "fds=(channel._read_fd,channel._write_fd)\nchannel.close()\n"
        "assert os.get_blocking(0) and os.get_blocking(1)\nfor fd in fds:\n"
        " try: os.fstat(fd)\n except OSError: pass\n"
        " else: raise AssertionError('duplicate retained')",
        "pass",
    )
    assert record["stderr"] == "" and record["tail"] == ""


def test_linux_owner_close_not_terminal(tmp_path: Path) -> None:
    record = drive(tmp_path, "channel.receive_request()\nchannel.close()", "request()")
    assert record["stderr"] == "" and record["tail"] == ""


def test_linux_owner_substituted_descriptor_retained(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "fd=channel._read_fd; os.close(fd)\nreplacement=os.open('/dev/null',os.O_RDONLY)\n"
        "assert replacement==fd\nfor operation in (channel.close,channel.close,Channel):\n"
        " try: operation()\n except Error: pass\n"
        " else: raise AssertionError('substitution adopted')\n"
        "assert os.fstat(replacement).st_ino==os.stat('/dev/null').st_ino",
        "pass",
    )
    assert "cleanup" in record["stderr"] and record["tail"] == ""


def test_linux_owner_named_pipe_refuses(tmp_path: Path) -> None:
    code = subject("pass").replace(
        "channel=None",
        "import tempfile\nprivate=tempfile.TemporaryDirectory()\n"
        "path=private.name+'/named'; os.mkfifo(path,0o600)\n"
        "peer=os.open(path,os.O_RDWR|os.O_NONBLOCK)\n"
        "fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK); os.dup2(fd,0); os.close(fd)\n"
        "channel=None",
    )
    driver = DRIVER.replace("SUBJECT", repr(code)).replace(" ACTION", " pass")
    result = execute(tmp_path, driver)
    assert getattr(result, "exit_code", getattr(result, "returncode", None)) == 0
    refused(json.loads(result.stdout), "pipe")


@pytest.mark.parametrize("phase", ["request", "reply"])
def test_linux_owner_unsolicited_reply(tmp_path: Path, phase: str) -> None:
    action = (
        "write(b'HEI1'+struct.pack('!I',0)+b'X')"
        if phase == "request"
        else "request()\nwrite(b'HER1'+challenge()+b'X')"
    )
    record = drive(tmp_path, "channel.receive_request()\nchannel.exchange()", action)
    refused(record, "unsolicited")


def test_linux_owner_refusal_sticky(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "channel.receive_request()\ntry: channel.exchange()\nexcept Error: pass\n"
        "else: raise AssertionError('bad reply accepted')\n"
        "for operation in (channel.receive_request,channel.exchange,channel.finish):\n"
        " try: operation()\n except Error as exc: assert 'refused/closed' in str(exc)\n"
        " else: raise AssertionError('refused channel resumed')",
        "request()\nchallenge()\nwrite(b'BAD!'+b'X'*16)",
    )
    assert record["stderr"] == "" and record["tail"] == ""


def test_linux_owner_preexisting_nonblocking_restored(tmp_path: Path) -> None:
    code = subject("channel.close()\nassert not os.get_blocking(0) and not os.get_blocking(1)")
    code = code.replace(
        "channel=None", "os.set_blocking(0,False); os.set_blocking(1,False)\nchannel=None"
    )
    driver = DRIVER.replace("SUBJECT", repr(code)).replace(" ACTION", " pass")
    result = execute(tmp_path, driver)
    assert getattr(result, "exit_code", getattr(result, "returncode", None)) == 0
    record = json.loads(result.stdout)
    assert record["exit"] == 0 and record["stderr"] == "" and record["tail"] == ""


def test_linux_owner_same_inode_reopen_retained(tmp_path: Path) -> None:
    record = drive(
        tmp_path,
        "fd=channel._read_fd; original=os.fstat(fd)\nos.close(fd)\n"
        "replacement=os.open('/proc/self/fd/0',os.O_RDONLY|os.O_NONBLOCK)\n"
        "assert replacement==fd and os.fstat(replacement).st_ino==original.st_ino\n"
        "for operation in (channel.close,channel.close,Channel):\n"
        " try: operation()\n except Error: pass\n"
        " else: raise AssertionError('same-inode replacement adopted')\n"
        "assert os.fstat(replacement).st_ino==original.st_ino",
        "pass",
    )
    assert "cleanup" in record["stderr"] and record["tail"] == ""


def test_linux_owner_recycled_thread_id_refuses(tmp_path: Path) -> None:
    code = subject(
        "box=[]\ndef created(): box.append(Channel())\n"
        "creator=threading.Thread(target=created); creator.start(); creator.join(1)\n"
        "assert not creator.is_alive() and len(box)==1\nchannel=box[0]\n"
        "results=[]\ndef attempt():\n"
        " same=threading.get_ident()==channel._creator[1]\n"
        " try: channel.close()\n"
        " except Error as exc: results.append((same,'creator' in str(exc)))\n"
        " else: results.append((same,False))\n"
        "for _ in range(256):\n"
        " thread=threading.Thread(target=attempt); thread.start(); thread.join(1)\n"
        " assert not thread.is_alive()\n"
        " if results[-1][0]: break\n"
        "assert any(same for same,_ in results), 'runtime did not recycle observed thread ID'\n"
        "assert all(refusal for _,refusal in results), 'recycled thread adopted creator channel'"
    )
    constructor = " channel=Channel(exchange_timeout_seconds=0.3,overall_timeout_seconds=4.0)\n"
    assert code.count(constructor) == 1
    code = code.replace(constructor, " pass\n")
    driver = DRIVER.replace("SUBJECT", repr(code)).replace(" ACTION", " pass")
    result = execute(tmp_path, driver)
    assert getattr(result, "exit_code", getattr(result, "returncode", None)) == 0
    record = json.loads(result.stdout)
    assert record["exit"] == 0, record["stderr"]
    assert "creator" in record["stderr"] and record["tail"] == ""
