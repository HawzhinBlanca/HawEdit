"""D-331: the :8000 pause wrapper always restores the server and only removes its own lock."""

from __future__ import annotations

import subprocess
from pathlib import Path

from test_fetch_scripts import _bash

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run-with-omniasr-paused.sh"


def _omniasr(tmp_path: Path) -> Path:
    root = tmp_path / "omniasr"
    (root / "app").mkdir(parents=True)
    (root / "scripts").mkdir()
    for name in ("stop_server", "restart_server"):
        (root / "scripts" / f"{name}.sh").write_text(
            f'echo {name} >> "$(dirname "$0")/../calls.log"\n', encoding="utf-8"
        )
    return root


def _run(root: Path, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_bash()), str(WRAPPER), *command],
        env={"OMNIASR_ROOT": root.as_posix(), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_pause_wrapper_restores_the_server_when_the_command_fails(tmp_path: Path) -> None:
    root = _omniasr(tmp_path)
    seen = tmp_path / "lock-during-command"
    result = _run(
        root, "bash", "-c", f'cat "$OMNIASR_ROOT/app/MAINTENANCE" > "{seen.as_posix()}"; exit 7'
    )
    assert result.returncode == 7, result.stderr
    assert (root / "calls.log").read_text(encoding="utf-8").split() == [
        "stop_server",
        "restart_server",
    ]
    assert seen.read_text(encoding="utf-8").strip().isdigit(), "the lock held the wrapper's PID"
    assert not (root / "app" / "MAINTENANCE").exists()


def test_pause_wrapper_refuses_an_existing_maintenance_lock(tmp_path: Path) -> None:
    root = _omniasr(tmp_path)
    (root / "app" / "MAINTENANCE").write_text("4242\n", encoding="utf-8")
    result = _run(root, "bash", "-c", "exit 0")
    assert result.returncode == 3
    assert "already exists" in result.stderr
    assert not (root / "calls.log").exists(), "nothing was stopped or restarted"
    assert (root / "app" / "MAINTENANCE").read_text(encoding="utf-8") == "4242\n"
