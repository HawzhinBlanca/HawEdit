"""Real owned lifecycle/recovery synchronization, not producer acceptance."""

from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest

from hawedit.studio_generation import GenerationRequest, ProducerSelection, prepare_generation
from hawedit.studio_private import PrivateSqlitePath, StudioStorageError
from hawedit.studio_runtime import OwnedStudioRuntime, studio_runtime_policy
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

WORKFLOW = "hawedit.studio.activation.inert"
MEDIA = Path(__file__).resolve().parent / "fixtures/kurdish-speech-3cuts.mp4"


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


@pytest.fixture
def fresh_runtime(private_root: Path) -> OwnedStudioRuntime:
    return OwnedStudioRuntime(
        PrivateSqlitePath(private_root / "dbos.sqlite"),
        SubmissionStore(private_root / "outbox.sqlite"),
        studio_runtime_policy(WORKFLOW),
    )


@pytest.fixture
def activation_job(private_root: Path) -> tuple[Path, str]:
    uploads = UploadStore(private_root / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("activation.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "activation-test-token-0001",
            "options": {},
        }
    )
    prepared = prepare_generation(
        request, uploads, private_root / "temporary", ProducerSelection("gemini")
    )
    store = SubmissionStore(private_root / "outbox.sqlite")
    job = store.reserve(prepared, "b" * 64, WORKFLOW)
    return private_root, job.job_id


_CHILD = r"""
import ast,importlib,inspect,json,os,sys,textwrap,threading,time
from pathlib import Path
from dbos import DBOS
from hawedit.studio_private import PrivateSqlitePath,StudioStorageError
from hawedit.studio_queue import reconcile_studio_submission
from hawedit.studio_runtime import OwnedStudioRuntime,studio_runtime_policy
from hawedit.studio_submissions import SubmissionStore
root=Path(sys.argv[1]); mode=sys.argv[2]; job_id=sys.argv[3]
name="hawedit.studio.activation.inert"
entered=threading.Event(); done=threading.Event(); finish=threading.Event()
observed={}; triggered=[]; callback=None
def await_runtime(timeout):
    observed["before"]=runtime.state
    entered.set()
    try:
        runtime.await_activation(timeout_seconds=timeout)
    except BaseException as exc:
        observed.update(error=type(exc).__name__,diagnostic=str(exc),after=runtime.state)
    else:
        observed.update(after=runtime.state,verified=True)
    finally:
        done.set()
@DBOS.workflow(name=name)
def inert(job_id):
    if mode=="crash": os._exit(23)
    if mode=="draining":
        entered.set()
        assert finish.wait(12)
    else:
        await_runtime(5)
        assert observed.get("verified") is True, observed
    return {"job_id":job_id,"private":True}
runtime=OwnedStudioRuntime(PrivateSqlitePath(root/"dbos.sqlite"),
                          SubmissionStore(root/"outbox.sqlite"),studio_runtime_policy(name))
if mode in ("recover","timeout","failed","launch-thread"):
    lines,first=inspect.getsourcelines(OwnedStudioRuntime.launch)
    tree=ast.parse(textwrap.dedent("".join(lines)))
    assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign)
        and isinstance(n.value,ast.Constant) and n.value.value=="active"
        and any(isinstance(t,ast.Attribute) and t.attr=="_state" for t in n.targets)]
    assert len(assignments)==1
    activation_line=first+assignments[0].lineno-1
    def trace(frame,event,arg):
        global callback
        if frame.f_code is not OwnedStudioRuntime.launch.__code__: return None
        if event=="line" and frame.f_lineno==activation_line:
            sys.settrace(None); triggered.append(True)
            assert runtime.state=="starting"
            if mode=="launch-thread":
                try: runtime.await_activation(timeout_seconds=.1)
                except StudioStorageError as exc:
                    observed.update(error=type(exc).__name__,diagnostic=str(exc))
                else: raise AssertionError("launch thread was allowed to wait")
            else:
                if mode!="recover":
                    callback=threading.Thread(target=await_runtime,
                        args=(.05 if mode=="timeout" else 5,))
                    callback.start()
                assert entered.wait(8), "callback never entered controlled startup window"
                if mode=="timeout":
                    assert done.wait(2), "finite activation timeout did not return"
                    assert observed["after"]=="starting"
                else:
                    assert not done.wait(.05), "callback passed before actual activation"
                if mode=="failed": raise RuntimeError("controlled startup failure")
        return trace
    sys.settrace(trace)
try:
    runtime.launch()
except RuntimeError as exc:
    if mode!="failed" or str(exc)!="controlled startup failure": raise
    assert done.wait(2), "failed startup did not wake its waiter"
    assert observed["error"]=="StudioStorageError", observed
    assert "not accepting work" in observed["diagnostic"], observed
    assert runtime.state=="refused"
    assert not (root/"consumed.txt").exists()
    callback.join(2); assert not callback.is_alive()
    print(json.dumps(dict(observed,state=runtime.state,controlled=triggered==[True])))
    raise SystemExit(0)
finally:
    sys.settrace(None)
try:
    if mode=="crash":
        reconcile_studio_submission(runtime.submissions,job_id,inert)
        assert entered.wait(20), "crash process should exit before returning"
    elif mode=="recover":
        assert done.wait(5), "recovered callback did not pass after activation"
        assert observed=={"before":"starting","after":"active","verified":True}, observed
        assert triggered==[True]
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            status=DBOS.get_workflow_status(job_id)
            if status and status.status=="SUCCESS": break
            time.sleep(.02)
        else: raise AssertionError("actual recovered inert workflow did not complete")
        observed["dbos_status"]=status.status
    elif mode in ("timeout","launch-thread"):
        assert observed["error"]=="StudioStorageError", observed
        if callback is not None:
            callback.join(2); assert not callback.is_alive()
        assert not (root/"consumed.txt").exists()
        runtime.await_activation(timeout_seconds=.1)
        observed["eventual_state"]=runtime.state
    elif mode=="draining":
        reconcile_studio_submission(runtime.submissions,job_id,inert)
        assert entered.wait(8)
        try: runtime.close(timeout_seconds=.05)
        except StudioStorageError as exc: assert "remain live" in str(exc)
        else: raise AssertionError("live worker lease was released")
        assert runtime.state=="draining"
        try: runtime.await_activation(timeout_seconds=.1)
        except StudioStorageError as exc: observed["diagnostic"]=str(exc)
        else: raise AssertionError("draining runtime admitted")
        runtime._lease.verify()
        assert not runtime._owned_engine._closed
        observed.update(state=runtime.state,lease_retained=True)
        finish.set()
    elif mode=="closed":
        runtime.close()
        try: runtime.await_activation(timeout_seconds=.1)
        except StudioStorageError as exc: observed["diagnostic"]=str(exc)
        else: raise AssertionError("closed runtime admitted")
        observed["state"]=runtime.state
    elif mode.startswith("drift-"):
        kind=mode.removeprefix("drift-")
        registry=runtime._registry; instance=runtime._instance
        queue=runtime._queues["hawedit-studio-v1"]
        original=registry.workflow_info_map[name]
        if kind=="registry": registry.workflow_info_map[name]=lambda job_id: None
        elif kind=="queue": queue._worker_concurrency=2
        elif kind=="config": instance._config["runtimeConfig"]["max_executor_threads"]=2
        elif kind=="environment": os.environ["OTEL_STUDIO_ACTIVATION_TEST"]="changed"
        try:
            for verify in (runtime.await_activation,runtime.verify):
                try: verify()
                except StudioStorageError: pass
                else: raise AssertionError("actual runtime drift admitted")
        finally:
            registry.workflow_info_map[name]=original
            queue._worker_concurrency=1
            instance._config["runtimeConfig"]["max_executor_threads"]=1
            os.environ.pop("OTEL_STUDIO_ACTIVATION_TEST",None)
        runtime.await_activation(timeout_seconds=.1)
        observed.update(refused=True,restored=True,state=runtime.state)
    else:
        runtime.await_activation(timeout_seconds=.1)
        runtime.verify()
        observed.update(verified=True,state=runtime.state)
    print(json.dumps(observed))
finally:
    finish.set()
    runtime.close(timeout_seconds=5)
"""


def _run(root: Path, mode: str, job_id: str = "", *, expected: int = 0) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, str(root), mode, job_id],
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    if expected:
        return {}
    observation = json.loads(result.stdout.strip().splitlines()[-1])
    assert isinstance(observation, dict)
    return observation


@pytest.mark.parametrize(
    "timeout", [True, False, 0, -1, 10.01, float("inf"), float("-inf"), float("nan"), "1", None]
)
def test_activation_wait_rejects_invalid_timeout(
    fresh_runtime: OwnedStudioRuntime, timeout: object
) -> None:
    with pytest.raises(ValueError, match="finite"):
        fresh_runtime.await_activation(timeout_seconds=cast(float, timeout))
    assert fresh_runtime.state == "new"
    assert not (fresh_runtime.storage.root / "studio-supervisor.lock").exists()


def test_activation_wait_refuses_unlaunched_runtime(fresh_runtime: OwnedStudioRuntime) -> None:
    with pytest.raises(StudioStorageError, match="not accepting work"):
        fresh_runtime.await_activation(timeout_seconds=0.05)
    assert fresh_runtime.state == "new"


def test_activation_signal_is_not_authority(fresh_runtime: OwnedStudioRuntime) -> None:
    fresh_runtime._activation.set()
    with pytest.raises(StudioStorageError, match="not accepting work"):
        fresh_runtime.await_activation(timeout_seconds=0.05)
    with pytest.raises(StudioStorageError, match="not accepting work"):
        fresh_runtime.verify()


def test_activation_wait_verifies_actual_runtime_before_return(private_root: Path) -> None:
    assert _run(private_root, "active") == {"verified": True, "state": "active"}


@pytest.mark.parametrize("kind", ["registry", "queue", "config", "environment"])
def test_activation_wait_refuses_runtime_drift(private_root: Path, kind: str) -> None:
    assert _run(private_root, "drift-" + kind) == {
        "refused": True,
        "restored": True,
        "state": "active",
    }


def test_activation_wait_handles_actual_pending_recovery(activation_job: tuple[Path, str]) -> None:
    root, job_id = activation_job
    _run(root, "crash", job_id, expected=23)
    with closing(sqlite3.connect(root / "dbos.sqlite")) as connection:
        assert connection.execute(
            "SELECT status FROM workflow_status WHERE workflow_uuid=?", (job_id,)
        ).fetchone() == ("PENDING",)
    assert _run(root, "recover", job_id) == {
        "before": "starting",
        "after": "active",
        "verified": True,
        "dbos_status": "SUCCESS",
    }


def test_activation_wait_timeout_is_bounded(private_root: Path) -> None:
    result = _run(private_root, "timeout")
    assert result["before"] == result["after"] == "starting"
    assert "activation timed out" in result["diagnostic"]
    assert result["eventual_state"] == "active"


def test_activation_wait_does_not_deadlock_launch_thread(private_root: Path) -> None:
    result = _run(private_root, "launch-thread")
    assert "launch thread" in result["diagnostic"]
    assert result["eventual_state"] == "active"


def test_activation_wait_refuses_failed_startup(private_root: Path) -> None:
    result = _run(private_root, "failed")
    assert result["before"] == "starting"
    assert result["after"] in ("draining", "closed", "refused")
    assert result["state"] == "refused"
    assert result["controlled"] is True


@pytest.mark.parametrize("mode", ["draining", "closed"])
def test_activation_wait_refuses_draining_and_closed(
    activation_job: tuple[Path, str], mode: str
) -> None:
    root, job_id = activation_job
    result = _run(root, mode, job_id)
    assert result["state"] == mode
    assert "not accepting work" in result["diagnostic"]
    if mode == "draining":
        assert result["lease_retained"] is True
