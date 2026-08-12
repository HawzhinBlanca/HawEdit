"""Phase 3's first mutating capability, checked at the point that matters most: the refusals.

`propose_boundary_revision` is read-only and gets ordinary coverage. `commit_boundary_revision`
is the only function in `proposals.py` that writes anything, and every test aimed at it is
aimed at one of the three things it must refuse: an invalid proposal, an unattributed approval,
or a declined one. A revision tool that *sometimes* enforces its gate is worse than one with no
gate at all — the failure only shows up on the one call nobody double-checked.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hawedit.proposals import (
    BoundaryRevisionProposal,
    RevisionRejected,
    commit_boundary_revision,
    propose_boundary_revision,
)

ROOT = Path(__file__).resolve().parents[1]

_DEFAULT_BOUNDARY: dict[str, object] = {
    "anchor_in_ms": 100,
    "anchor_out_ms": 4100,
    "final_in_ms": 0,
    "final_out_ms": 4300,
    "in_extended_by": "vad_onset",
    "out_extended_by": "tail",
    "sentence_complete": True,
    "confidence": None,
}


def _write_report(work_dir: Path, boundary: object = _DEFAULT_BOUNDARY) -> None:
    report: dict[str, object] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(work_dir),
        "complete": True,
        "skipped": [],
        "boundary": boundary,
        "candidates": [],
        "rejected": [],
        "clip": None,
        "render": None,
        "delivery": None,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


# --- propose: read-only, never touches disk ---------------------------------------------------


def test_propose_reads_the_runs_own_anchors_not_invented_ones(tmp_path: Path) -> None:
    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)
    assert isinstance(proposal, BoundaryRevisionProposal)
    assert proposal.original.anchor_in_ms == 100
    assert proposal.original.anchor_out_ms == 4100
    assert proposal.proposed_final_in_ms == 0
    assert proposal.proposed_final_out_ms == 4500
    assert not (tmp_path / "revisions").exists(), "propose must never create a revisions/ dir"


def test_propose_accepts_a_legal_outward_extension(tmp_path: Path) -> None:
    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)
    assert proposal.valid is True
    assert proposal.violation is None


def test_propose_rejects_a_span_that_would_cut_off_the_anchored_sentence(tmp_path: Path) -> None:
    _write_report(tmp_path)
    # anchor_out_ms is 4100; a proposed final_out_ms before that ends the clip mid-sentence.
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=3000)
    assert proposal.valid is False
    assert proposal.violation is not None
    assert "mid-sentence" in proposal.violation


def test_propose_rejects_a_span_that_starts_after_the_anchor(tmp_path: Path) -> None:
    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=200, final_out_ms=4500)
    assert proposal.valid is False
    assert "mid-sentence" in (proposal.violation or "")


def test_propose_raises_with_no_report(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="report.json"):
        propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)


def test_propose_raises_when_the_run_never_reached_a_boundary(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        boundary={
            "skipped": True,
            "stage": "boundary",
            "reason": "no complete sentence in the selection.",
            "blocked_by": (),
        },
    )
    with pytest.raises(ValueError, match="no boundary to revise"):
        propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)


def test_propose_raises_when_the_boundary_field_is_null(tmp_path: Path) -> None:
    _write_report(tmp_path, boundary=None)
    with pytest.raises(ValueError, match="no boundary to revise"):
        propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)


# --- commit: the only write, and its three refusals --------------------------------------------


def _approved_proposal(tmp_path: Path) -> BoundaryRevisionProposal:
    _write_report(tmp_path)
    return propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)


def test_commit_refuses_an_invalid_proposal_without_asking_for_approval(tmp_path: Path) -> None:
    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=3000)
    assert proposal.valid is False

    asked: list[str] = []

    def confirm(prompt: str) -> bool:
        asked.append(prompt)
        return True

    with pytest.raises(RevisionRejected, match="Kurdish invariant #2"):
        commit_boundary_revision(
            tmp_path, proposal, revision_id="r1", approved_by="hawa", confirm=confirm
        )
    assert asked == [], "an invalid proposal must never reach the approval prompt"
    assert not (tmp_path / "revisions").exists()


def test_commit_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    with pytest.raises(RevisionRejected, match="unattributed"):
        commit_boundary_revision(
            tmp_path, proposal, revision_id="r1", approved_by="   ", confirm=lambda _: True
        )
    assert not (tmp_path / "revisions").exists()


def test_commit_refuses_a_declined_approval_and_writes_nothing(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    with pytest.raises(RevisionRejected, match="declined"):
        commit_boundary_revision(
            tmp_path, proposal, revision_id="r1", approved_by="hawa", confirm=lambda _: False
        )
    assert not (tmp_path / "revisions").exists()


def test_commit_writes_the_approved_record_only_after_a_yes(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    path = commit_boundary_revision(
        tmp_path, proposal, revision_id="r1", approved_by="hawa", confirm=lambda _: True
    )
    assert path == tmp_path / "revisions" / "r1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["approved_by"] == "hawa"
    assert record["status"] == "approved_pending_render"
    assert record["proposed_final_out_ms"] == 4500
    assert record["original"]["final_out_ms"] == 4300


def test_commit_passes_the_real_diff_to_the_confirm_prompt(tmp_path: Path) -> None:
    """The approver must be shown the actual before/after, not a generic yes/no."""
    proposal = _approved_proposal(tmp_path)
    seen: list[str] = []

    def confirm(prompt: str) -> bool:
        seen.append(prompt)
        return True

    commit_boundary_revision(
        tmp_path, proposal, revision_id="r1", approved_by="hawa", confirm=confirm
    )
    assert seen and "0..4300" in seen[0] and "0..4500" in seen[0]


def test_two_commits_under_the_same_id_overwrite_the_prior_record(tmp_path: Path) -> None:
    """Documented behavior, not an accident: `revision_id` is the caller's idempotency key."""
    proposal = _approved_proposal(tmp_path)
    commit_boundary_revision(
        tmp_path, proposal, revision_id="r1", approved_by="hawa", confirm=lambda _: True
    )
    second = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4400)
    commit_boundary_revision(
        tmp_path, second, revision_id="r1", approved_by="hawa2", confirm=lambda _: True
    )
    record = json.loads((tmp_path / "revisions" / "r1.json").read_text(encoding="utf-8"))
    assert record["approved_by"] == "hawa2"
    assert record["proposed_final_out_ms"] == 4400


# --- the CLI, run as a real subprocess so --help never depends on the agentic extra -----------


def _run_cli(argv: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hawedit.proposals", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=30,
    )


def test_cli_help_names_itself_correctly() -> None:
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert result.stdout.startswith("usage: hawedit.proposals ") or "hawedit.proposals" in (
        result.stdout.splitlines()[0] if result.stdout else ""
    )


def test_cli_declines_on_a_blank_answer_and_writes_nothing(tmp_path: Path) -> None:
    _write_report(tmp_path)
    result = _run_cli(
        [
            str(tmp_path),
            "--final-in-ms",
            "0",
            "--final-out-ms",
            "4500",
            "--revision-id",
            "r1",
            "--approved-by",
            "hawa",
        ],
        input_text="\n",
    )
    assert result.returncode == 1, result.stderr
    assert not (tmp_path / "revisions").exists()


def test_cli_commits_on_an_explicit_yes(tmp_path: Path) -> None:
    _write_report(tmp_path)
    result = _run_cli(
        [
            str(tmp_path),
            "--final-in-ms",
            "0",
            "--final-out-ms",
            "4500",
            "--revision-id",
            "r1",
            "--approved-by",
            "hawa",
        ],
        input_text="y\n",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "revisions" / "r1.json").is_file()


def test_cli_reports_an_invalid_proposal_and_never_prompts(tmp_path: Path) -> None:
    _write_report(tmp_path)
    result = _run_cli(
        [
            str(tmp_path),
            "--final-in-ms",
            "0",
            "--final-out-ms",
            "3000",
            "--revision-id",
            "r1",
            "--approved-by",
            "hawa",
        ],
        input_text="",
    )
    assert result.returncode == 1
    assert "invalid" in result.stderr
    assert not (tmp_path / "revisions").exists()
