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

from hawedit.boundary import Boundary
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Output
from hawedit.learning import (
    DecisionOutcome,
    ReasonCode,
    read_decision_deltas,
    record_decision_delta,
)
from hawedit.proposals import (
    BoundaryRevisionProposal,
    CaptionRevisionProposal,
    RevisionRejected,
    commit_boundary_revision,
    commit_caption_revision,
    propose_boundary_revision,
    propose_caption_revision,
    replay_decision_deltas,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word

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


def _write_report(
    work_dir: Path,
    boundary: object = _DEFAULT_BOUNDARY,
    clip: object = None,
    selected_sentences: object = (),
) -> None:
    report: dict[str, object] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(work_dir),
        "complete": True,
        "skipped": [],
        "boundary": boundary,
        "candidates": [],
        "rejected": [],
        "clip": clip,
        "render": None,
        "delivery": None,
        "selected_sentences": selected_sentences,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


_WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
)


def _clip_dict(caption_style: str = "line") -> dict[str, object]:
    """A minimal but real `Clip.to_dict()`, valid enough for `propose_caption_revision` to read
    `output.caption_style` off — not a hand-typed shape that could drift from the real one."""
    boundary = Boundary(
        anchor_in_ms=100,
        anchor_out_ms=4100,
        final_in_ms=0,
        final_out_ms=4300,
        in_extended_by="vad_onset",
        out_extended_by="tail",
        sentence_complete=True,
        confidence=None,
    )
    clip = Clip(
        clip_id="fixture-0",
        media_id="fixture",
        media_sha256="a" * 64,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="ڕۆژنامەوانی کوردی.",
            norm_ckb="ڕۆژنامەوانی کوردی.",
            en_aux=None,
            words=_WORDS,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        output=Output(
            title_ckb="t",
            description_ckb="d",
            crop_target="9:16",
            caption_style=caption_style,
            durations=(30,),
        ),
    )
    return clip.to_dict()


def _selected_sentences_json() -> list[dict[str, object]]:
    import dataclasses

    return [dataclasses.asdict(Sentence(words=_WORDS, complete=True))]


def _write_caption_report(work_dir: Path, caption_style: str = "line") -> None:
    _write_report(
        work_dir,
        clip=_clip_dict(caption_style),
        selected_sentences=_selected_sentences_json(),
    )


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
            tmp_path,
            proposal,
            revision_id="r1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=confirm,
        )
    assert asked == [], "an invalid proposal must never reach the approval prompt"
    assert not (tmp_path / "revisions").exists()


def test_commit_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    with pytest.raises(RevisionRejected, match="unattributed"):
        commit_boundary_revision(
            tmp_path,
            proposal,
            revision_id="r1",
            approved_by="   ",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: True,
        )
    assert not (tmp_path / "revisions").exists()


def test_commit_refuses_a_declined_approval_and_writes_nothing(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    with pytest.raises(RevisionRejected, match="declined"):
        commit_boundary_revision(
            tmp_path,
            proposal,
            revision_id="r1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: False,
        )
    assert not (tmp_path / "revisions").exists()


def test_commit_writes_the_approved_record_only_after_a_yes(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    path = commit_boundary_revision(
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
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
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=confirm,
    )
    assert seen and "0..4300" in seen[0] and "0..4500" in seen[0]


def test_two_commits_under_the_same_id_overwrite_the_prior_record(tmp_path: Path) -> None:
    """Documented behavior, not an accident: `revision_id` is the caller's idempotency key."""
    proposal = _approved_proposal(tmp_path)
    commit_boundary_revision(
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    second = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4400)
    commit_boundary_revision(
        tmp_path,
        second,
        revision_id="r1",
        approved_by="hawa2",
        reason_code=ReasonCode.UNDO,
        confirm=lambda _: True,
    )
    record = json.loads((tmp_path / "revisions" / "r1.json").read_text(encoding="utf-8"))
    assert record["approved_by"] == "hawa2"
    assert record["proposed_final_out_ms"] == 4400


def test_commit_writes_kind_boundary(tmp_path: Path) -> None:
    """`render_caption_revision` refuses a record whose `kind` is not `"caption"` — this pins
    what a real boundary commit actually writes, so that refusal is checked against reality."""
    proposal = _approved_proposal(tmp_path)
    path = commit_boundary_revision(
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    assert json.loads(path.read_text(encoding="utf-8"))["kind"] == "boundary"


# --- propose_caption_revision / commit_caption_revision (D-A12) --------------------------------


def test_caption_propose_reads_the_runs_own_style_not_an_invented_one(tmp_path: Path) -> None:
    _write_caption_report(tmp_path, caption_style="line")
    proposal = propose_caption_revision(tmp_path, "word_highlight")
    assert isinstance(proposal, CaptionRevisionProposal)
    assert proposal.original_caption_style == "line"
    assert proposal.proposed_caption_style == "word_highlight"
    assert not (tmp_path / "revisions").exists(), "propose must never create a revisions/ dir"


def test_caption_propose_accepts_a_real_style_change(tmp_path: Path) -> None:
    _write_caption_report(tmp_path, caption_style="line")
    proposal = propose_caption_revision(tmp_path, "word_highlight")
    assert proposal.valid is True
    assert proposal.violation is None


def test_caption_propose_rejects_an_unrecognized_style(tmp_path: Path) -> None:
    _write_caption_report(tmp_path, caption_style="line")
    proposal = propose_caption_revision(tmp_path, "subtitles_but_huge")
    assert proposal.valid is False
    assert "not a recognized caption style" in (proposal.violation or "")
    assert proposal.proposed_caption_style == "subtitles_but_huge"


def test_caption_propose_raises_with_no_report(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="report.json"):
        propose_caption_revision(tmp_path, "line")


def test_caption_propose_raises_with_no_clip(tmp_path: Path) -> None:
    _write_report(tmp_path)  # clip=None by default
    with pytest.raises(ValueError, match="no clip"):
        propose_caption_revision(tmp_path, "line")


def test_caption_propose_raises_with_no_selected_sentences(tmp_path: Path) -> None:
    _write_report(tmp_path, clip=_clip_dict(), selected_sentences=[])
    with pytest.raises(ValueError, match="predates D-A7"):
        propose_caption_revision(tmp_path, "line")


def _approved_caption_proposal(work_dir: Path) -> CaptionRevisionProposal:
    _write_caption_report(work_dir, caption_style="line")
    return propose_caption_revision(work_dir, "word_highlight")


def test_caption_commit_refuses_an_invalid_proposal_without_asking_for_approval(
    tmp_path: Path,
) -> None:
    _write_caption_report(tmp_path, caption_style="line")
    proposal = propose_caption_revision(tmp_path, "not_a_real_style")
    assert proposal.valid is False

    asked: list[str] = []

    def confirm(prompt: str) -> bool:
        asked.append(prompt)
        return True

    with pytest.raises(RevisionRejected, match="Kurdish invariant #4"):
        commit_caption_revision(
            tmp_path,
            proposal,
            revision_id="c1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=confirm,
        )
    assert asked == [], "an invalid proposal must never reach the approval prompt"
    assert not (tmp_path / "revisions").exists()


def test_caption_commit_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    proposal = _approved_caption_proposal(tmp_path)
    with pytest.raises(RevisionRejected, match="unattributed"):
        commit_caption_revision(
            tmp_path,
            proposal,
            revision_id="c1",
            approved_by=" ",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: True,
        )
    assert not (tmp_path / "revisions").exists()


def test_caption_commit_refuses_a_declined_approval_and_writes_nothing(tmp_path: Path) -> None:
    proposal = _approved_caption_proposal(tmp_path)
    with pytest.raises(RevisionRejected, match="declined"):
        commit_caption_revision(
            tmp_path,
            proposal,
            revision_id="c1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: False,
        )
    assert not (tmp_path / "revisions").exists()


def test_caption_commit_writes_the_approved_record_only_after_a_yes(tmp_path: Path) -> None:
    proposal = _approved_caption_proposal(tmp_path)
    path = commit_caption_revision(
        tmp_path,
        proposal,
        revision_id="c1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    assert path == tmp_path / "revisions" / "c1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["kind"] == "caption"
    assert record["approved_by"] == "hawa"
    assert record["status"] == "approved_pending_render"
    assert record["proposed_caption_style"] == "word_highlight"
    assert record["original_caption_style"] == "line"


def test_render_boundary_revision_refuses_a_caption_revision_record(tmp_path: Path) -> None:
    """The `kind` guard added in D-A12, checked from the boundary side."""
    from hawedit.proposals import render_boundary_revision

    proposal = _approved_caption_proposal(tmp_path)
    commit_caption_revision(
        tmp_path,
        proposal,
        revision_id="c1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    with pytest.raises(ValueError, match="not a boundary revision"):
        render_boundary_revision(tmp_path, "c1")


def test_render_caption_revision_refuses_a_boundary_revision_record(tmp_path: Path) -> None:
    """The same guard, checked from the caption side."""
    from hawedit.proposals import render_caption_revision

    _write_caption_report(tmp_path, caption_style="line")
    boundary_proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4300)
    assert boundary_proposal.valid, boundary_proposal.violation
    commit_boundary_revision(
        tmp_path,
        boundary_proposal,
        revision_id="b1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    with pytest.raises(ValueError, match="not a caption revision"):
        render_caption_revision(tmp_path, "b1")


# --- decision deltas: every outcome is recorded, not just approvals (D-A13) --------------------


def test_an_invalid_proposal_is_recorded_before_it_is_refused(tmp_path: Path) -> None:
    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=3000)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            tmp_path,
            proposal,
            revision_id="r1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: True,
        )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_INVALID
    assert delta.reason_code is None
    assert delta.approved_by is None


def test_an_unattributed_approval_attempt_is_recorded(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            tmp_path,
            proposal,
            revision_id="r1",
            approved_by="  ",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: True,
        )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_UNATTRIBUTED
    assert delta.reason_code is None


def test_a_decline_is_recorded_with_its_reason_code(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            tmp_path,
            proposal,
            revision_id="r1",
            approved_by="hawa",
            reason_code=ReasonCode.ACCIDENT,
            confirm=lambda _: False,
        )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.DECLINED
    assert delta.reason_code is ReasonCode.ACCIDENT
    assert delta.approved_by == "hawa"


def test_an_approval_is_recorded_with_its_reason_code(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    commit_boundary_revision(
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.UNDO,
        confirm=lambda _: True,
    )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.APPROVED
    assert delta.reason_code is ReasonCode.UNDO
    assert delta.kind == "boundary"
    assert delta.proposal["proposed_final_out_ms"] == 4500


def test_two_commit_attempts_on_the_same_run_both_land_in_the_ledger(tmp_path: Path) -> None:
    """Sequenced, not overwritten — unlike `revisions/<id>.json`, decisions are a log."""
    _write_report(tmp_path)
    bad = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=3000)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            tmp_path,
            bad,
            revision_id="r1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: True,
        )
    good = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)
    commit_boundary_revision(
        tmp_path,
        good,
        revision_id="r2",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    deltas = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert [d.outcome for d in deltas] == [
        DecisionOutcome.REFUSED_INVALID,
        DecisionOutcome.APPROVED,
    ]
    assert [d.sequence for d in deltas] == [1, 2]


def test_a_caption_approval_is_recorded_too(tmp_path: Path) -> None:
    proposal = _approved_caption_proposal(tmp_path)
    commit_caption_revision(
        tmp_path,
        proposal,
        revision_id="c1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.APPROVED
    assert delta.kind == "caption"


# --- offline replay (D-A13) ---------------------------------------------------------------------


def test_replay_raises_with_no_ledger(tmp_path: Path) -> None:
    _write_report(tmp_path)
    with pytest.raises(FileNotFoundError):
        replay_decision_deltas(tmp_path)


def test_replay_finds_nothing_when_todays_code_still_agrees(tmp_path: Path) -> None:
    proposal = _approved_proposal(tmp_path)
    commit_boundary_revision(
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    assert replay_decision_deltas(tmp_path) == ()


def test_replay_ignores_declined_and_refused_decisions(tmp_path: Path) -> None:
    """Only an APPROVED decision was ever applied; a decline or refusal has nothing for a
    validator regression to break, so replay must not report on it."""
    _write_report(tmp_path)
    bad = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=3000)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            tmp_path,
            bad,
            revision_id="r1",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: True,
        )
    declined = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            tmp_path,
            declined,
            revision_id="r2",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: False,
        )
    assert replay_decision_deltas(tmp_path) == ()


def test_replay_flags_an_approval_the_run_no_longer_supports(tmp_path: Path) -> None:
    """The regression case: approve a legal narrowing, then the run's own recorded anchors
    change (as they would if an upstream re-run corrected them) so the *same* proposal is no
    longer legal — replay must catch that, re-running the real validator rather than trusting
    the `valid` flag frozen into the original record."""
    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4300)
    assert proposal.valid, proposal.violation
    commit_boundary_revision(
        tmp_path,
        proposal,
        revision_id="r1",
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )
    # Tighten the anchor past what was approved — legal under §3 Stage 5 (anchors move only
    # when the run itself is redone), and now `final_out_ms=4300` ends before the anchor.
    tightened = dict(_DEFAULT_BOUNDARY)
    tightened["anchor_out_ms"] = 4301
    _write_report(tmp_path, boundary=tightened)

    (finding,) = replay_decision_deltas(tmp_path)
    assert finding.kind == "boundary"
    assert finding.media_id == "fixture"
    assert "mid-sentence" in finding.violation


def test_replay_skips_workflow_lifecycle_kinds_instead_of_crashing(tmp_path: Path) -> None:
    """`start_pipeline`/`cancel_run`/`resume_run` deltas (`workflow_control.py`) have no
    deterministic content validator to replay against — before the `elif`/`else: continue` fix,
    any kind that was not literally `"boundary"` fell into the caption branch by default and
    read a key (`proposed_caption_style`) that does not exist on these proposals' dicts,
    raising `KeyError` rather than skipping cleanly."""
    _write_report(tmp_path)
    for kind, proposal in (
        ("start_pipeline", {"source": "x.mp4", "media_id": None, "valid": True}),
        ("cancel_run", {"work_dir": str(tmp_path), "run_id": "r", "valid": True}),
        ("resume_run", {"work_dir": str(tmp_path), "run_id": "r", "valid": True}),
    ):
        record_decision_delta(
            tmp_path,
            "fixture",
            kind,
            DecisionOutcome.APPROVED,
            proposal,
            reason_code=ReasonCode.PREFERENCE,
            approved_by="hawa",
        )
    assert replay_decision_deltas(tmp_path) == ()


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
            "--reason-code",
            "preference",
        ],
        input_text="\n",
    )
    assert result.returncode == 1, result.stderr
    assert not (tmp_path / "revisions").exists()


def test_cli_commits_on_an_explicit_yes_with_no_render(tmp_path: Path) -> None:
    """`--no-render` isolates the approval step from a real source file being present at
    all — the render path itself is `test_render_boundary_revision.py`'s job, against a real
    fixture."""
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
            "--reason-code",
            "preference",
            "--no-render",
        ],
        input_text="y\n",
    )
    assert result.returncode == 0, result.stderr
    record = json.loads((tmp_path / "revisions" / "r1.json").read_text(encoding="utf-8"))
    assert record["status"] == "approved_pending_render"


def test_cli_reports_a_render_failure_as_its_own_outcome(tmp_path: Path) -> None:
    """Without `--no-render`, the CLI attempts to render right after committing — and a source
    that does not exist (`_write_report`'s default `"x.mp4"`) fails *rendering*, distinctly
    from a declined or invalid proposal. The approval itself must still be on disk: a render
    failure is not grounds to un-approve a legal, human-approved change."""
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
            "--reason-code",
            "preference",
        ],
        input_text="y\n",
    )
    assert result.returncode == 1, result.stderr
    assert "render failed" in result.stderr
    record = json.loads((tmp_path / "revisions" / "r1.json").read_text(encoding="utf-8"))
    assert record["approved_by"] == "hawa", "a render failure must not erase the approval record"


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
            "--reason-code",
            "preference",
        ],
        input_text="",
    )
    assert result.returncode == 1
    assert "invalid" in result.stderr
    assert not (tmp_path / "revisions").exists()


# --- CLI dispatch between boundary and caption revisions (D-A12) -------------------------------


def test_cli_requires_one_revision_kind() -> None:
    result = _run_cli(
        ["work", "--revision-id", "r1", "--approved-by", "hawa", "--reason-code", "preference"]
    )
    assert result.returncode == 2
    assert "give either" in result.stderr


def test_cli_refuses_both_revision_kinds_at_once() -> None:
    result = _run_cli(
        [
            "work",
            "--final-in-ms",
            "0",
            "--final-out-ms",
            "100",
            "--caption-style",
            "line",
            "--revision-id",
            "r1",
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ]
    )
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr


def test_cli_refuses_a_lone_final_in_ms() -> None:
    result = _run_cli(
        [
            "work",
            "--final-in-ms",
            "0",
            "--revision-id",
            "r1",
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ]
    )
    assert result.returncode == 2
    assert "must both be given" in result.stderr


def test_cli_refuses_an_unrecognized_caption_style() -> None:
    result = _run_cli(
        [
            "work",
            "--caption-style",
            "subtitles_but_huge",
            "--revision-id",
            "c1",
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ]
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_cli_requires_a_reason_code() -> None:
    """`--reason-code` is required unconditionally (D-A13), the same way `--approved-by` is."""
    result = _run_cli(
        [
            "work",
            "--final-in-ms",
            "0",
            "--final-out-ms",
            "100",
            "--revision-id",
            "r1",
            "--approved-by",
            "hawa",
        ]
    )
    assert result.returncode == 2
    assert "--reason-code" in result.stderr


def test_cli_commits_a_caption_revision_with_no_render(tmp_path: Path) -> None:
    """`--no-render` isolates the approval step, matching the boundary CLI test — the render
    path itself is `test_render_caption_revision.py`'s job, against a real fixture."""
    _write_caption_report(tmp_path, caption_style="line")
    result = _run_cli(
        [
            str(tmp_path),
            "--caption-style",
            "word_highlight",
            "--revision-id",
            "c1",
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
            "--no-render",
        ],
        input_text="y\n",
    )
    assert result.returncode == 0, result.stderr
    record = json.loads((tmp_path / "revisions" / "c1.json").read_text(encoding="utf-8"))
    assert record["kind"] == "caption"
    assert record["status"] == "approved_pending_render"


def test_cli_declines_a_caption_revision_on_a_blank_answer_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """Matches `test_cli_declines_on_a_blank_answer_and_writes_nothing`'s coverage of the
    boundary CLI. A well-formed choice `argparse` accepts but `CaptionStyle` still rejects is
    not reachable through this CLI — the `choices=` list is generated from the same enum
    `propose_caption_revision` parses — so the invalid-*proposal* path is exercised through the
    function directly, in `test_caption_propose_rejects_an_unrecognized_style` above."""
    _write_caption_report(tmp_path, caption_style="line")
    result = _run_cli(
        [
            str(tmp_path),
            "--caption-style",
            "word_highlight",
            "--revision-id",
            "c1",
            "--approved-by",
            "hawa",
            "--reason-code",
            "preference",
        ],
        input_text="\n",
    )
    assert result.returncode == 1, result.stderr
    assert not (tmp_path / "revisions").exists()
