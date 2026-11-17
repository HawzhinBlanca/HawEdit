"""Actual isolated native handle faults; no mocked API or model/provider claims."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from hawedit.native_io import NativeIOError, run_native
from hawedit.studio_private import PrivateDirectory


@pytest.mark.parametrize(
    "field", ["_job", "_process", "_thread", "_observed-stop", "_observed-close"]
)
def test_native_release_failure_preserves_original_capabilities(tmp_path: Path, field: str) -> None:
    private = PrivateDirectory(tmp_path / "fault", exclusive=True)
    executable = Path(sys.executable).resolve()
    source = r"""import ctypes,gc,hashlib,json,msvcrt,os,pathlib,sys,time,weakref
from ctypes import wintypes as w
from hawedit.native_process import NativeJob,NativeProcessError
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.SetHandleInformation.argtypes=[w.HANDLE,w.DWORD,w.DWORD]; k.SetHandleInformation.restype=w.BOOL
k.GetHandleInformation.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
k.GetHandleInformation.restype=w.BOOL
k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]; k.WaitForSingleObject.restype=w.DWORD
exe=pathlib.Path(sys._base_executable).resolve()
streams=[open(os.devnull,'rb'),open(os.devnull,'wb'),open(os.devnull,'wb')]
field=sys.argv[1]
worker='raise SystemExit(0)'
if field.startswith('_observed'):
 member_code=("import os,pathlib,time; p=pathlib.Path.cwd(); "
              "(p/'member-ready').write_text(str(os.getpid())); deadline=time.monotonic()+10\n"
              "while not (p/'release-member').exists() and time.monotonic()<deadline: "
              "time.sleep(.01)\nassert (p/'release-member').exists()")
 worker=("import subprocess,sys,time; subprocess.Popen([sys.executable,'-I','-B','-c',"
         +repr(member_code)+"]); time.sleep(20)")
args=dict(argv=(str(exe),'-I','-B','-c',worker),cwd=pathlib.Path.cwd(),
 environment={'SystemRoot':os.environ['SystemRoot']},
 expected_executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
 stdin=streams[0],stdout=streams[1],stderr=streams[2])
job=NativeJob.create(**args); job.resume()
member=None
if field.startswith('_observed'):
 deadline=time.monotonic()+5
 barrier=pathlib.Path.cwd()/'member-ready'
 while not barrier.exists() and time.monotonic()<deadline: time.sleep(.01)
 assert barrier.exists()
 member=int(barrier.read_text()); job._retain_members()
 assert member in job._observed and member in job.members()
 original=job._observed[member]
else:
 assert job.wait(5)==0 and job.members()==()
 original=getattr(job,field)
image=job._image
image_handle=msvcrt.get_osfhandle(image.fileno()); reference=weakref.ref(job)
assert k.SetHandleInformation(original,2,2)
if member is not None:
 (pathlib.Path.cwd()/'release-member').write_text('release')
 assert k.WaitForSingleObject(original,5000)==0
try:
 try:
  job.stop() if field=='_observed-stop' else job.close()
 except NativeProcessError as exc:
  message=str(exc)
 else:
  raise AssertionError('Protected original release unexpectedly succeeded')
 flags=w.DWORD(); actual_open=bool(k.GetHandleInformation(original,ctypes.byref(flags)))
 saved_original=((job._observed.get(member)==original) if member is not None
                 else getattr(job,field)==original)
 print(json.dumps({'fault_field':field,'state':job._state,'saved_original':saved_original,
  'actual_original_open':actual_open,'release_error':message}),flush=True)
 assert actual_open and flags.value&2
 assert job._state=='uncertain' and saved_original
 assert job._image is image and not image.closed
 assert k.GetHandleInformation(image_handle,ctypes.byref(w.DWORD()))
 assert job._finalizer is None or not job._finalizer.alive
 assert k.SetHandleInformation(original,2,0)
 try:
  job.close()
 except NativeProcessError as exc:
  assert 'uncertain' in str(exc).lower() or 'retained' in str(exc).lower()
 else:
  raise AssertionError('Restored native handle incorrectly cleared uncertainty')
 replacement=None
 try:
  replacement=NativeJob.create(**args)
 except NativeProcessError as exc:
  assert 'uncertain' in str(exc).lower() or 'retained' in str(exc).lower()
 else:
  replacement.close()
  raise AssertionError('New native launch admitted after uncertain release')
 del job; gc.collect()
 assert reference() is not None and k.GetHandleInformation(original,ctypes.byref(w.DWORD()))
 print(json.dumps({'outcome':'original-capabilities-retained-no-retry-or-reentry','fault_field':field}),flush=True)
finally:
 assert k.SetHandleInformation(original,2,0)
 # The isolated original owner exits; no late PID lookup or uncertain-object retry.
 for stream in streams: stream.close()
"""
    arguments = (str(executable), "-I", "-B", "-c", source, field)
    options: dict[str, Any] = dict(
        cwd=private.path,
        environment={"SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows")},
        expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        input_bytes=b"",
        timeout_seconds=20,
        output_limit_bytes=65536,
    )
    if os.name != "nt":
        with pytest.raises(NativeIOError, match="Windows"):
            run_native(arguments, **options)
        return
    result = run_native(arguments, **options)
    assert result.exit_code == 0, result.stderr.decode("utf-8", "replace")
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows[0]["actual_original_open"] and rows[0]["saved_original"]
    assert rows[0]["state"] == "uncertain"
    assert rows[1] == {
        "outcome": "original-capabilities-retained-no-retry-or-reentry",
        "fault_field": field,
    }
    assert result.stderr == b""
