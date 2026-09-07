"""Claim R2 verification: critical subprocess invocations must specify an explicit timeout.

Prevents unbounded hangs in long pipeline executions or automated soak tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ingest_run_has_timeout() -> None:
    """ingest._run must enforce a timeout on all ffmpeg / probe calls."""
    ingest_py = (ROOT / "src" / "hawedit" / "ingest.py").read_text(encoding="utf-8")
    tree = ast.parse(ingest_py)

    run_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_run":
            run_fn = node
            break

    assert run_fn is not None, "ingest._run not found"

    subprocess_calls = [
        call
        for call in ast.walk(run_fn)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "run"
    ]
    assert len(subprocess_calls) >= 1
    for call in subprocess_calls:
        has_timeout = any(kw.arg == "timeout" for kw in call.keywords)
        assert has_timeout, "subprocess.run in ingest._run missing timeout parameter"


def test_measure_subprocesses_have_timeouts() -> None:
    """measure.py subprocess invocations must specify explicit timeouts."""
    measure_py = (ROOT / "src" / "hawedit" / "measure.py").read_text(encoding="utf-8")
    tree = ast.parse(measure_py)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("run", "Popen")
    ]
    assert len(calls) >= 4, (
        f"expected at least 4 subprocess calls in measure.py, found {len(calls)}"
    )
    for call in calls:
        has_timeout = any(kw.arg == "timeout" for kw in call.keywords)
        assert has_timeout, f"subprocess call at line {call.lineno} in measure.py missing timeout"


def test_sanity_gate_subprocesses_have_timeouts() -> None:
    """sanity_gate.py audio inspection must specify explicit timeout."""
    gate_py = (ROOT / "src" / "hawedit" / "sanity_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(gate_py)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("run", "Popen")
    ]
    assert len(calls) >= 1
    for call in calls:
        has_timeout = any(kw.arg == "timeout" for kw in call.keywords)
        assert has_timeout, (
            f"subprocess call at line {call.lineno} in sanity_gate.py missing timeout"
        )
