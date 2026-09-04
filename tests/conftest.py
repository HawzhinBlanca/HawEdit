"""Pytest conftest hook for HawEdit statement coverage tracing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hawedit.gate import CoverageTracer

_tracer = CoverageTracer()


def pytest_sessionstart(session: Any) -> None:
    _tracer.start()


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    _tracer.stop()
    root = Path(session.config.rootdir)
    gate_dir = root / ".gate"
    _tracer.save_report(gate_dir / "coverage-report.json", root)
