"""`start_pipeline`, checked at the point that matters most: the refusals and the record.

`propose_start_pipeline` is read-only and gets ordinary coverage. `commit_start_pipeline` is the
only function in `workflow_control.py` that writes anything (a decision delta always, a real
run on success) — every refusal test here mirrors `test_proposals.py`'s own shape for
`commit_boundary_revision`, since D-A19 deliberately reuses that module's conventions rather
than inventing new ones.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from hawedit.learning import DecisionOutcome, ReasonCode, read_decision_deltas
from hawedit.workflow_control import (
    StartPipelineProposal,
    WorkflowRejected,
    commit_start_pipeline,
    propose_start_pipeline,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


# --- propose: read-only, never touches disk ---------------------------------------------------


def test_propose_accepts_a_real_source(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    assert proposal.valid is True
    assert proposal.violation is None
    assert proposal.source == str(FIXTURE)


def test_propose_rejects_a_missing_source(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, tmp_path / "does-not-exist.mp4")
    assert proposal.valid is False
    assert "no file at" in (proposal.violation or "")


def test_propose_rejects_a_missing_transcript(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, FIXTURE, transcript=tmp_path / "no.json")
    assert proposal.valid is False
    assert "no transcript file" in (proposal.violation or "")


def test_propose_rejects_a_work_dir_with_a_completed_run(tmp_path: Path) -> None:
    (tmp_path / "report.json").write_text("{}", encoding="utf-8")
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    assert proposal.valid is False
    assert "already has a completed run" in (proposal.violation or "")


def test_propose_never_creates_anything(tmp_path: Path) -> None:
    propose_start_pipeline(tmp_path, FIXTURE)
    assert list(tmp_path.iterdir()) == []


def test_propose_carries_media_id_and_transcript_through(tmp_path: Path) -> None:
    transcript = tmp_path / "t.json"
    transcript.write_text("{}", encoding="utf-8")
    proposal = propose_start_pipeline(tmp_path, FIXTURE, media_id="ep1", transcript=transcript)
    assert proposal.valid is True
    assert proposal.media_id == "ep1"
    assert proposal.transcript == str(transcript)


# --- commit: refusals, and every outcome recorded as a decision delta -------------------------


def _valid_proposal(tmp_path: Path) -> StartPipelineProposal:
    return propose_start_pipeline(tmp_path, FIXTURE)


def test_commit_refuses_an_invalid_proposal_without_asking_for_approval(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, tmp_path / "missing.mp4")
    asked: list[str] = []

    def confirm(prompt: str) -> bool:
        asked.append(prompt)
        return True

    with pytest.raises(WorkflowRejected, match="invalid"):
        commit_start_pipeline(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=confirm)
    assert asked == [], "an invalid proposal must never reach the approval prompt"
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_INVALID
    assert delta.kind == "start_pipeline"
    assert delta.reason_code is None


def test_commit_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    proposal = _valid_proposal(tmp_path)
    with pytest.raises(WorkflowRejected, match="unattributed"):
        commit_start_pipeline(
            tmp_path, proposal, "  ", ReasonCode.PREFERENCE, confirm=lambda _: True
        )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_UNATTRIBUTED


def test_commit_refuses_a_decline_and_starts_nothing(tmp_path: Path) -> None:
    proposal = _valid_proposal(tmp_path)
    with pytest.raises(WorkflowRejected, match="declined"):
        commit_start_pipeline(
            tmp_path, proposal, "hawa", ReasonCode.ACCIDENT, confirm=lambda _: False
        )
    assert not (tmp_path / "report.json").exists()
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.DECLINED
    assert delta.reason_code is ReasonCode.ACCIDENT
    assert delta.approved_by == "hawa"


def test_commit_passes_the_real_source_path_to_the_confirm_prompt(tmp_path: Path) -> None:
    proposal = _valid_proposal(tmp_path)
    seen: list[str] = []

    def confirm(prompt: str) -> bool:
        seen.append(prompt)
        return False

    with pytest.raises(WorkflowRejected):
        commit_start_pipeline(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=confirm)
    assert seen and FIXTURE.name in seen[0] and str(tmp_path) in seen[0]


def test_decision_delta_media_id_falls_back_to_the_source_stem(tmp_path: Path) -> None:
    """`proposal.media_id` is optional; the delta still needs a non-blank `media_id` — falls
    back to the source's own filename stem, matching `pipeline.py`'s own derivation
    (`identifier = media_id or source.stem`)."""
    proposal = propose_start_pipeline(tmp_path, tmp_path / "missing.mp4")
    with pytest.raises(WorkflowRejected):
        commit_start_pipeline(
            tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True
        )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.media_id == "missing"


# --- commit: the real thing, against a real fixture and a real DBOS instance -------------------

dbos = pytest.importorskip("dbos")
from hawedit.captions import find_ffmpeg  # noqa: E402
from hawedit.durable_workflow import configure_dbos  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")


@pytest.fixture(scope="module", autouse=True)
def _dbos_instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    db_path = tmp_path_factory.mktemp("dbos") / "test.sqlite"
    configure_dbos(system_database_url=f"sqlite:///{db_path}")
    yield
    dbos.DBOS.destroy()


@needs_ffmpeg
def test_an_approved_commit_actually_starts_a_real_run(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    result = commit_start_pipeline(
        tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True
    )
    assert result["media_id"] == FIXTURE.stem
    assert (tmp_path / "report.json").is_file()
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.APPROVED


@needs_ffmpeg
def test_a_second_proposal_into_the_same_work_dir_is_now_refused(tmp_path: Path) -> None:
    """The `report.json`-conflict check, proven against a run this test itself just started —
    not merely a hand-written file standing in for one."""
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    commit_start_pipeline(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True)
    second = propose_start_pipeline(tmp_path, FIXTURE)
    assert second.valid is False
    assert "already has a completed run" in (second.violation or "")


# --- the CLI, run as a real subprocess so --help never depends on dbos being installed ---------


def _run_cli(argv: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hawedit.workflow_control", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=30,
    )


def test_cli_help_names_itself_correctly() -> None:
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "hawedit.workflow_control" in result.stdout


def test_cli_start_help_does_not_require_dbos_installed() -> None:
    """The claim `workflow_control.py`'s own docstring makes about the deferred import — proven
    by actually running `--help` as a subprocess, not by reading the source and trusting it."""
    result = _run_cli(["start", "--help"])
    assert result.returncode == 0
    assert "--reason-code" in result.stdout


def test_cli_declines_on_a_blank_answer_and_writes_nothing(tmp_path: Path) -> None:
    result = _run_cli(
        [
            "start",
            str(FIXTURE),
            "--work-dir",
            str(tmp_path),
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ],
        input_text="\n",
    )
    assert result.returncode == 1, result.stderr
    assert not (tmp_path / "report.json").exists()


def test_cli_reports_an_invalid_proposal_and_never_prompts(tmp_path: Path) -> None:
    result = _run_cli(
        [
            "start",
            str(tmp_path / "missing.mp4"),
            "--work-dir",
            str(tmp_path),
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ],
        input_text="",
    )
    assert result.returncode == 1
    assert "invalid" in result.stderr


def test_cli_requires_a_reason_code() -> None:
    result = _run_cli(
        [
            "start",
            str(FIXTURE),
            "--work-dir",
            "work",
            "--approved-by",
            "hawa",
        ]
    )
    assert result.returncode == 2
    assert "--reason-code" in result.stderr
