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
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from hawedit.learning import DecisionOutcome, ReasonCode, read_decision_deltas
from hawedit.workflow_control import (
    CancelRunProposal,
    ResumeRunProposal,
    StartPipelineProposal,
    WorkflowRejected,
    _delta_media_id_for,
    commit_cancel_run,
    commit_resume_run,
    commit_start_pipeline,
    dbos_run_id_for,
    propose_cancel_run,
    propose_resume_run,
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


@pytest.mark.parametrize("bad", ["../../escape", "a/b", "a\\b", "..", "", "  ", "."])
def test_propose_rejects_a_media_id_the_run_would_refuse(tmp_path: Path, bad: str) -> None:
    """`run_pipeline` validates `media_id` — but only once the run is executing, after a human
    approved it and compute started. A proposal reporting `valid=True` for an id certain to be
    refused is the same over-promise `propose_render` was fixed for.

    `media_id` is agent-suppliable (`propose_start_pipeline_tool` on `workflow_agent`), and it
    reaches path construction downstream, so plan-time is where it belongs. D-A28.
    """
    proposal = propose_start_pipeline(tmp_path, FIXTURE, media_id=bad)
    assert proposal.valid is False, f"media_id {bad!r} was accepted at plan time"
    assert "not usable as a run identifier" in (proposal.violation or "")


def test_propose_still_accepts_an_ordinary_media_id(tmp_path: Path) -> None:
    """The control: the guard must not refuse the ids real runs actually use."""
    proposal = propose_start_pipeline(tmp_path, FIXTURE, media_id="episode-1")
    assert proposal.valid is True, proposal.violation


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


# --- dbos_run_id_for: pure, deterministic, no dbos import needed ------------------------------


def test_dbos_run_id_for_is_stable_for_the_same_work_dir(tmp_path: Path) -> None:
    assert dbos_run_id_for(tmp_path) == dbos_run_id_for(tmp_path)


def test_dbos_run_id_for_differs_between_work_dirs(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert dbos_run_id_for(a) != dbos_run_id_for(b)


def test_dbos_run_id_for_agrees_across_a_relative_and_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "work"
    target.mkdir()
    monkeypatch.chdir(tmp_path)
    assert dbos_run_id_for(Path("work")) == dbos_run_id_for(target)


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
def test_commit_start_pipeline_registers_the_deterministic_run_id(tmp_path: Path) -> None:
    """The D-A20 prerequisite, proven directly: a completed run is discoverable by
    `dbos_run_id_for(work_dir)` alone, with nothing else to look up."""
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    commit_start_pipeline(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True)
    status = dbos.DBOS.get_workflow_status(dbos_run_id_for(tmp_path))
    assert status is not None
    assert status.status == "SUCCESS"


# --- cancel_run / resume_run: propose against a work_dir with no run started yet ---------------


def test_propose_cancel_run_reports_no_workflow_before_any_run_started(tmp_path: Path) -> None:
    proposal = propose_cancel_run(tmp_path)
    assert proposal.valid is False
    assert proposal.current_status is None
    assert "no DBOS workflow found" in (proposal.violation or "")


def test_propose_resume_run_reports_no_workflow_before_any_run_started(tmp_path: Path) -> None:
    proposal = propose_resume_run(tmp_path)
    assert proposal.valid is False
    assert proposal.current_status is None
    assert "nothing to resume" in (proposal.violation or "")


# --- cancel_run / resume_run: commit refusals, provable without a real pipeline run ------------


def test_commit_cancel_run_refuses_an_invalid_proposal_without_asking_for_approval(
    tmp_path: Path,
) -> None:
    proposal = propose_cancel_run(tmp_path)
    asked: list[str] = []

    def confirm(prompt: str) -> bool:
        asked.append(prompt)
        return True

    with pytest.raises(WorkflowRejected, match="cannot cancel"):
        commit_cancel_run(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=confirm)
    assert asked == [], "an invalid proposal must never reach the approval prompt"
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_INVALID
    assert delta.kind == "cancel_run"


def test_commit_resume_run_refuses_an_invalid_proposal_without_asking_for_approval(
    tmp_path: Path,
) -> None:
    proposal = propose_resume_run(tmp_path)
    with pytest.raises(WorkflowRejected, match="cannot resume"):
        commit_resume_run(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True)
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_INVALID
    assert delta.kind == "resume_run"


def test_delta_media_id_for_falls_back_to_work_dir_when_the_name_is_whitespace_only() -> None:
    """`work_dir.name` is truthy even when it is only whitespace (`"   "` is a non-empty
    string) — a pure test, deliberately not exercised through a real whitespace-named directory
    on disk: Windows normalizes a trailing-space path component away on `Path.mkdir`, so a real
    directory named `"   "` cannot be relied on to exist the way this check needs it to look."""
    work_dir = Path("some") / "work" / "   "
    assert work_dir.name.strip() == ""
    assert _delta_media_id_for(work_dir) == str(work_dir)


def test_delta_media_id_for_uses_the_real_name_when_it_is_not_blank() -> None:
    work_dir = Path("some") / "work" / "episode-1"
    assert _delta_media_id_for(work_dir) == "episode-1"


def _synthetic_valid_cancel_proposal(work_dir: Path) -> CancelRunProposal:
    """A hand-built, structurally valid proposal naming a run_id nothing has started — legal
    because `commit_cancel_run` only touches DBOS *after* the approval gate passes, so the
    refusal-path tests below never need a real running pipeline to exercise that gate."""
    return CancelRunProposal(
        work_dir=str(work_dir),
        run_id=dbos_run_id_for(work_dir),
        valid=True,
        current_status="PENDING",
        violation=None,
    )


def _synthetic_valid_resume_proposal(work_dir: Path) -> ResumeRunProposal:
    return ResumeRunProposal(
        work_dir=str(work_dir),
        run_id=dbos_run_id_for(work_dir),
        valid=True,
        current_status="CANCELLED",
        violation=None,
    )


def test_commit_cancel_run_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    proposal = _synthetic_valid_cancel_proposal(tmp_path)
    with pytest.raises(WorkflowRejected, match="unattributed"):
        commit_cancel_run(tmp_path, proposal, "  ", ReasonCode.PREFERENCE, confirm=lambda _: True)
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_UNATTRIBUTED


def test_commit_cancel_run_refuses_a_decline(tmp_path: Path) -> None:
    proposal = _synthetic_valid_cancel_proposal(tmp_path)
    with pytest.raises(WorkflowRejected, match="declined"):
        commit_cancel_run(tmp_path, proposal, "hawa", ReasonCode.ACCIDENT, confirm=lambda _: False)
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.DECLINED


def test_commit_resume_run_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    proposal = _synthetic_valid_resume_proposal(tmp_path)
    with pytest.raises(WorkflowRejected, match="unattributed"):
        commit_resume_run(tmp_path, proposal, "  ", ReasonCode.PREFERENCE, confirm=lambda _: True)
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_UNATTRIBUTED


def test_commit_resume_run_refuses_a_decline(tmp_path: Path) -> None:
    proposal = _synthetic_valid_resume_proposal(tmp_path)
    with pytest.raises(WorkflowRejected, match="declined"):
        commit_resume_run(tmp_path, proposal, "hawa", ReasonCode.ACCIDENT, confirm=lambda _: False)
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.DECLINED


def test_commit_cancel_run_approved_calls_the_real_dbos_api_and_no_ops_on_a_missing_id(
    tmp_path: Path,
) -> None:
    """The approved path really calls `DBOS.cancel_workflow`, proven against the real installed
    package rather than trusted from the source — cancelling a workflow ID DBOS has never seen
    is a real, measured no-op (`_sys_db.py::cancel_workflows`' UPDATE matches zero rows), not an
    error, so this is safe to exercise without a real pipeline run."""
    proposal = _synthetic_valid_cancel_proposal(tmp_path)
    result = commit_cancel_run(
        tmp_path, proposal, "hawa", ReasonCode.ACCIDENT, confirm=lambda _: True
    )
    assert result["run_id"] == dbos_run_id_for(tmp_path)
    assert result["status"] is None
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.APPROVED
    assert delta.kind == "cancel_run"


def test_commit_resume_run_approved_calls_the_real_dbos_api_and_raises_on_a_missing_id(
    tmp_path: Path,
) -> None:
    """Unlike cancel, `DBOS.resume_workflow` on an ID it has never seen raises
    `DBOSNonExistentWorkflowError` (`_sys_db.py::resume_workflows` checks existence explicitly)
    — measured, not assumed, and proof the approved path really reaches the real DBOS call."""
    proposal = _synthetic_valid_resume_proposal(tmp_path)
    with pytest.raises(dbos.error.DBOSNonExistentWorkflowError):
        commit_resume_run(tmp_path, proposal, "hawa", ReasonCode.UNDO, confirm=lambda _: True)
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.APPROVED, (
        "the decision was recorded before the DBOS call failed — an approval that never "
        "reached DBOS is still a real approval, matching commit_start_pipeline's own ordering."
    )


# --- cancel_run / resume_run: propose against a finished run -----------------------------------


@needs_ffmpeg
def test_propose_cancel_run_refuses_a_finished_run(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    commit_start_pipeline(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True)
    cancel_proposal = propose_cancel_run(tmp_path)
    assert cancel_proposal.valid is False
    assert cancel_proposal.current_status == "SUCCESS"
    assert "already finished" in (cancel_proposal.violation or "")


@needs_ffmpeg
def test_propose_resume_run_refuses_a_finished_run(tmp_path: Path) -> None:
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    commit_start_pipeline(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True)
    resume_proposal = propose_resume_run(tmp_path)
    assert resume_proposal.valid is False
    assert resume_proposal.current_status == "SUCCESS"
    assert "already finished" in (resume_proposal.violation or "")


# --- cancel_run / resume_run: the real lifecycle, against a run genuinely cancelled mid-flight --


def _poll_until(predicate: object, timeout: float = 15.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(interval)
    return False


@needs_ffmpeg
def test_a_run_cancelled_mid_flight_keeps_computing_and_can_then_be_resumed(
    tmp_path: Path,
) -> None:
    """The full, real lifecycle in one test — expensive (a real pipeline run), so this proves
    every claim in the module docstring's numbered list at once rather than three times over:
    (1) cancelling mid-flight does not stop the underlying compute, (2) the awaiter still sees
    the cancellation, (3) resuming afterward finalizes the already-completed work as SUCCESS
    without this test ever re-triggering `_build_and_run`."""
    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    outcome: dict[str, object] = {}

    def _run() -> None:
        try:
            outcome["result"] = commit_start_pipeline(
                tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=lambda _: True
            )
        except Exception as exc:  # captured across a thread boundary, not swallowed
            outcome["error"] = exc

    run_id = dbos_run_id_for(tmp_path)
    thread = threading.Thread(target=_run)
    thread.start()
    try:
        found = _poll_until(lambda: dbos.DBOS.get_workflow_status(run_id) is not None)
        assert found, "the run never registered a DBOS workflow status in time"

        cancel_proposal = propose_cancel_run(tmp_path)
        assert cancel_proposal.valid is True, cancel_proposal.violation
        assert cancel_proposal.current_status == "PENDING"

        still_pending = propose_resume_run(tmp_path)
        assert still_pending.valid is False
        assert still_pending.current_status == "PENDING"
        assert "already pending" in (still_pending.violation or "")

        cancel_result = commit_cancel_run(
            tmp_path, cancel_proposal, "hawa", ReasonCode.ACCIDENT, confirm=lambda _: True
        )
        assert cancel_result["status"] == "CANCELLED"
    finally:
        thread.join(timeout=120)
    assert not thread.is_alive(), "the background run never finished"

    assert isinstance(outcome.get("error"), dbos.error.DBOSAwaitedWorkflowCancelledError), (
        f"expected the cancelled awaiter to raise; got {outcome!r}"
    )
    assert (tmp_path / "report.json").is_file(), (
        "cancelling must not have stopped the underlying compute — the real run finished and "
        "wrote its report despite DBOS refusing to record it as a success"
    )

    already_cancelled = propose_cancel_run(tmp_path)
    assert already_cancelled.valid is False
    assert already_cancelled.current_status == "CANCELLED"
    assert "already cancelled" in (already_cancelled.violation or "")

    resume_proposal = propose_resume_run(tmp_path)
    assert resume_proposal.valid is True, resume_proposal.violation
    assert resume_proposal.current_status == "CANCELLED"
    resume_result = commit_resume_run(
        tmp_path, resume_proposal, "hawa", ReasonCode.UNDO, confirm=lambda _: True
    )
    assert resume_result["media_id"] == FIXTURE.stem
    final_status = dbos.DBOS.get_workflow_status(run_id)
    assert final_status is not None
    assert final_status.status == "SUCCESS"


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


def test_cli_cancel_help_does_not_require_dbos_installed() -> None:
    result = _run_cli(["cancel", "--help"])
    assert result.returncode == 0
    assert "--reason-code" in result.stdout


def test_cli_resume_help_does_not_require_dbos_installed() -> None:
    result = _run_cli(["resume", "--help"])
    assert result.returncode == 0
    assert "--reason-code" in result.stdout


def test_cli_cancel_takes_no_source_positional() -> None:
    """`dbos_run_id_for` (D-A20) made a run-reference positional unnecessary — `--work-dir`
    alone is the whole address. Proven by the parser itself refusing an extra positional, not
    by reading the parser and trusting there is none. Every other required flag is supplied so
    the positional is isolated as the one thing argparse can complain about."""
    result = _run_cli(
        [
            "cancel",
            "somefile.mp4",
            "--work-dir",
            "work",
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ]
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_cli_cancel_reports_an_invalid_proposal_and_never_prompts(tmp_path: Path) -> None:
    result = _run_cli(
        [
            "cancel",
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


def test_cli_resume_reports_an_invalid_proposal_and_never_prompts(tmp_path: Path) -> None:
    result = _run_cli(
        [
            "resume",
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


def test_cli_cancel_requires_a_reason_code() -> None:
    result = _run_cli(["cancel", "--work-dir", "work", "--approved-by", "hawa"])
    assert result.returncode == 2
    assert "--reason-code" in result.stderr
