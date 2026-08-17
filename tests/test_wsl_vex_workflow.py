"""The live WSL vulnerability check is a release gate, not an operator suggestion."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / ".github" / "workflows" / "gate.yml"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


def _wsl_job() -> str:
    workflow = GATE.read_text(encoding="utf-8")
    return workflow.split("  wsl-asr-security:\n", 1)[1].split("\n  gate:\n", 1)[0]


def test_official_main_pushes_require_the_live_source_bound_wsl_gate() -> None:
    workflow = GATE.read_text(encoding="utf-8")
    job = _wsl_job()
    assert "github.repository == 'HawzhinBlanca/HawEdit'" in job
    assert "github.event_name == 'push'" in job
    assert "github.ref == 'refs/heads/main'" in job
    assert "runs-on: [self-hosted, Windows, X64, hawedit-gpu]" in job
    assert 'python-version: "3.12"' in job
    assert "persist-credentials: false" in job
    assert "python -m hawedit.wsl_vex_gate --distro Ubuntu --evidence $evidence" in job
    assert "hawedit.wsl_setup" not in job, "the security gate must not mutate what it audits"
    assert "needs: [python-312-compat, wsl-asr-security]" in workflow
    assert "needs.wsl-asr-security.result == 'success'" in workflow
    assert "needs.wsl-asr-security.result == 'skipped'" in workflow


def test_live_wsl_evidence_is_an_exact_sha_named_non_overwriting_artifact() -> None:
    job = _wsl_job()
    assert "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in job
    assert "name: hawedit-wsl-asr-vex-${{ github.sha }}" in job
    assert "wsl-asr-vex-${{ github.sha }}.json" in job
    assert "if-no-files-found: error" in job
    assert "overwrite: false" in job


def test_installed_wheel_exposes_and_smokes_the_same_gate() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    release = RELEASE.read_text(encoding="utf-8")
    assert 'hawedit-wsl-vex = "hawedit.wsl_vex_gate:main"' in project
    assert "hawedit-wsl-vex" in release
