"""The declared Python range must match setup, CI, and release promotion."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_declares_only_the_resolvable_python_range() -> None:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert document["project"]["requires-python"] == ">=3.11,<3.13"


def test_setup_accepts_311_and_312_but_refuses_313_and_a_stale_venv() -> None:
    setup = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
    support_check = "(3, 11) <= sys.version_info < (3, 13)"
    assert setup.count(support_check) == 2
    assert '"$VENV_PY" -c "$_supported"' in setup
    assert "existing .venv is not Python 3.11 or 3.12" in setup


def test_required_gate_cannot_pass_until_the_full_python_312_gate_passes() -> None:
    workflow = (ROOT / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
    compatibility = workflow.split("  python-312-compat:\n", 1)[1].split("\n  gate:\n", 1)[0]
    gate = workflow.split("\n  gate:\n", 1)[1]
    assert 'python-version: "3.12"' in compatibility
    assert "bash scripts/fetch-ffmpeg.sh" in compatibility
    assert "bash scripts/verify.sh" in compatibility
    assert "needs: python-312-compat" in gate
    assert workflow.count("\n  gate:\n") == 1
