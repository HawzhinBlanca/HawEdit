"""`render_boundary_revision` against a real pipeline run — not a synthetic `report.json`.

`test_proposals.py` covers `propose_boundary_revision`/`commit_boundary_revision` against
hand-built reports; that is the right level for functions whose whole job is reading fields off
a dict. Rendering is different: it drives `captions.py`'s `build_ass`, `render.py`'s
`render_clip`, real ffmpeg, real Kurdish shaping. A hand-built report could carry field names
this module reads correctly while still not proving a revised clip actually plays — only a real
`run_pipeline` call, a real fixture, and a real second MP4 do that.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hawedit.boundary import BoundaryInvariantViolated
from hawedit.captions import find_ffmpeg
from hawedit.clip import Qc
from hawedit.judge import JudgeVerdict
from hawedit.learning import ReasonCode
from hawedit.pipeline import PipelineRun, run_pipeline
from hawedit.proposals import (
    RevisionRejected,
    commit_boundary_revision,
    inspect_artifact,
    propose_boundary_revision,
    propose_render,
    render_boundary_revision,
)
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def a_transcript(media_id: str = "fixture") -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )


def a_verdict(clip_in_ms: int, clip_out_ms: int) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id="fixture-0",
        hook_score=0.8,
        self_contained=True,
        payoff_at_ms=(clip_in_ms + clip_out_ms) // 2,
        meaning_fidelity=0.9,
        misleading_edit_risk=0.05,
        cultural_landing=0.8,
        narrative_role="payoff",
        title_ckb="ڕۆژنامەوانی کوردی لە هەولێر",
        description_ckb="بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی",
        hashtags_ckb=("#کوردی",),
        judge="gemini-2.5-pro",
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
    )


@pytest.fixture(scope="module")
def real_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, PipelineRun]:
    """One real rendered run, its `report.json` written by hand here — this test suite exercises
    `render_boundary_revision` directly, not through `durable_workflow.py`'s step, so the report
    is written the same way that step writes it (`run.to_dict()`, `json.dumps`) without pulling
    in DBOS for a test that has nothing to do with durability."""
    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")
    work = tmp_path_factory.mktemp("revision-render")
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 4_100),
    )
    assert run.clip is not None, "fixture setup must produce a real clip to revise"
    (work / "report.json").write_text(
        json.dumps(run.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    return work, run


def _approve(work: Path, revision_id: str, final_in_ms: int, final_out_ms: int) -> None:
    proposal = propose_boundary_revision(work, final_in_ms, final_out_ms)
    assert proposal.valid, proposal.violation
    commit_boundary_revision(
        work,
        proposal,
        revision_id=revision_id,
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )


@needs_ffmpeg
def test_a_legal_revision_renders_a_real_second_mp4(
    real_run: tuple[Path, PipelineRun],
) -> None:
    work, run = real_run
    original_render_path = Path(run.to_dict()["render"]["path"])
    assert original_render_path.is_file(), "the original render must exist before revising it"

    # The fixture's anchor is 100..4100 ms and the source media is only 4162 ms long — the
    # original soft boundary (0..4162 ms) already covers the whole file, so there is no room to
    # extend either edge further outward without asking for more media than exists (measured:
    # render.py correctly refuses that, checked against the real file rather than the boundary
    # arithmetic alone). A *narrower* span within the legal range — final_in_ms up to
    # anchor_in_ms, final_out_ms down to anchor_out_ms — is still a legal revision under Kurdish
    # invariant #2 and stays inside the media.
    _approve(work, "narrower", final_in_ms=50, final_out_ms=4140)
    record = render_boundary_revision(work, "narrower")

    assert record["status"] == "rendered"
    render_path = Path(record["render_path"])
    assert render_path.is_file()
    assert render_path != original_render_path, "a revision must not overwrite the original"
    assert render_path.stat().st_size > 0
    # The original render is untouched — a revision is additive, never destructive.
    assert original_render_path.is_file()


@needs_ffmpeg
def test_the_revised_render_duration_matches_the_narrower_span(
    real_run: tuple[Path, PipelineRun],
) -> None:
    """Not just "a file exists" — the revision's own point: the encoded clip's real duration
    reflects the *requested* span (4140 - 50 = 4090 ms), read back from the file `render_clip`
    itself measured, not assumed from the boundary arithmetic that produced it."""
    from hawedit.ingest import probe_stream

    work, run = real_run
    original_duration_s = float(
        probe_stream(
            Path(run.to_dict()["render"]["path"]), "format=duration", None, video_only=False
        )
    )
    _approve(work, "measured-narrower", final_in_ms=50, final_out_ms=4140)
    record = render_boundary_revision(work, "measured-narrower")
    duration_s = float(
        probe_stream(Path(record["render_path"]), "format=duration", None, video_only=False)
    )
    assert duration_s < original_duration_s, (
        f"revised span (4090 ms requested) should render shorter than the original "
        f"({original_duration_s}s measured); got {duration_s}s"
    )
    assert 3.9 <= duration_s <= 4.2, f"expected roughly 4.09s, measured {duration_s}s"


@needs_ffmpeg
def test_a_valid_render_proposal_is_one_the_render_actually_accepts(
    real_run: tuple[Path, PipelineRun],
) -> None:
    """The direction that matters most: propose says ready, and the render agrees.

    `tests/test_exploration_tools.py` binds `propose_render`'s *refusals* to the render's
    refusals. This is the other half, and the dangerous one: a proposal an agent reports as
    ready for something the gate then throws out. That is precisely what `run_quality_checks`
    did after `main` tightened the QC gate — it called a clip shippable that
    `assert_renderable()` refused, and only its own equivalence test caught it (D-A26).

    Lives here rather than beside the refusal half because it needs a **real** run: the other
    file's report carries a placeholder source, and a proposal that clears every precondition
    and then cannot encode is still a proposal that promised more than it could keep.
    """
    work, _run = real_run
    _approve(work, "propose-agrees", final_in_ms=50, final_out_ms=4_140)

    proposal = propose_render(work, "propose-agrees")
    assert proposal.valid is True, f"the control must be valid, got: {proposal.violation}"

    record = render_boundary_revision(work, "propose-agrees")
    assert record["status"] in ("rendered", "rendered_without_delivery_sidecars"), (
        f"propose_render called this ready, but the render finished as {record['status']!r}."
    )


@needs_ffmpeg
def test_inspect_artifact_reports_the_span_the_render_actually_produced(
    real_run: tuple[Path, PipelineRun],
) -> None:
    """`inspect_artifact` claims to be "the same read every render function already trusts, not
    a second derivation that could disagree with what would actually be rendered". Until now
    that claim was checked only against hand-built revision records — ten tests, none of which
    had ever seen a real encode.

    This binds it to the bytes: the span it reports, against the measured duration of the MP4
    the render actually wrote. A tool that tells an agent "this artifact is 50..4140 ms" while
    the file on disk is some other length is the failure the claim exists to rule out.
    """
    from hawedit.ingest import probe_stream

    work, _run = real_run
    _approve(work, "inspected", final_in_ms=50, final_out_ms=4_140)
    record = render_boundary_revision(work, "inspected")
    assert record["status"] == "rendered"

    artifact = inspect_artifact(work, "inspected")
    assert artifact.found is True
    # `found` is the contract that the rest is populated - asserted rather than assumed, which
    # also narrows the Optionals the not-found case makes necessary.
    assert artifact.in_ms is not None and artifact.out_ms is not None
    assert (artifact.in_ms, artifact.out_ms) == (50, 4_140), (
        f"inspect_artifact resolved the revision to {artifact.in_ms}..{artifact.out_ms} ms, "
        f"but it was approved and rendered as 50..4140 ms."
    )
    # The render updates the record's status in place; the tool must report the new one, not
    # the `approved_pending_render` it was inspected as before.
    assert artifact.status == "rendered"

    measured_s = float(
        probe_stream(Path(record["render_path"]), "format=duration", None, video_only=False)
    )
    claimed_s = (artifact.out_ms - artifact.in_ms) / 1000
    assert abs(measured_s - claimed_s) < 0.25, (
        f"inspect_artifact claims a {claimed_s:.3f}s span; the encoded file measures "
        f"{measured_s:.3f}s. The tool and the artifact it describes disagree."
    )


@needs_ffmpeg
def test_render_also_produces_the_srt_and_edl_sidecars(real_run: tuple[Path, PipelineRun]) -> None:
    work, _run = real_run
    _approve(work, "sidecars", final_in_ms=50, final_out_ms=4140)
    record = render_boundary_revision(work, "sidecars")
    assert record["status"] == "rendered"
    assert Path(record["srt_path"]).is_file()
    assert Path(record["edl_path"]).is_file()
    assert Path(record["ass_path"]).is_file()


@needs_ffmpeg
def test_render_refuses_a_revision_that_was_never_approved(
    real_run: tuple[Path, PipelineRun],
) -> None:
    work, _run = real_run
    with pytest.raises(FileNotFoundError):
        render_boundary_revision(work, "never-proposed")


@needs_ffmpeg
def test_render_refuses_a_revision_that_failed_validation(
    real_run: tuple[Path, PipelineRun],
) -> None:
    """`commit_boundary_revision` already refuses an invalid proposal (`test_proposals.py`), so
    reaching this path at all means the record was hand-edited or came from elsewhere — the
    render gate re-checks rather than trusting the status string on disk."""
    work, _run = real_run
    proposal = propose_boundary_revision(work, final_in_ms=50, final_out_ms=4140)
    revisions_dir = work / "revisions"
    revisions_dir.mkdir(exist_ok=True)
    tampered = {
        **proposal.to_dict(),
        "revision_id": "tampered",
        "approved_by": "nobody-checked",
        "status": "approved_pending_render",
        "proposed_final_out_ms": 2000,  # rewritten to an illegal span after "approval"
    }
    (revisions_dir / "tampered.json").write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(BoundaryInvariantViolated):
        render_boundary_revision(work, "tampered")


@needs_ffmpeg
def test_render_refuses_a_revision_already_rendered(real_run: tuple[Path, PipelineRun]) -> None:
    work, _run = real_run
    _approve(work, "once-only", final_in_ms=50, final_out_ms=4140)
    render_boundary_revision(work, "once-only")
    with pytest.raises(ValueError, match="approved_pending_render"):
        render_boundary_revision(work, "once-only")


@needs_ffmpeg
def test_a_declined_revision_cannot_be_rendered(real_run: tuple[Path, PipelineRun]) -> None:
    work, _run = real_run
    proposal = propose_boundary_revision(work, final_in_ms=50, final_out_ms=4140)
    with pytest.raises(RevisionRejected):
        commit_boundary_revision(
            work,
            proposal,
            revision_id="declined",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: False,
        )
    with pytest.raises(FileNotFoundError):
        render_boundary_revision(work, "declined")


def test_render_refuses_a_run_with_no_persisted_selected_sentences(tmp_path: Path) -> None:
    """A run from before D-A7 — `selected_sentences` absent or empty — cannot be re-rendered
    from `report.json` alone, and must say so rather than render silent, empty captions."""
    report: dict[str, Any] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(tmp_path),
        "selected_sentences": [],
        "clip": {
            "clip_id": "fixture-old",
            "media_id": "fixture",
            "in_ms": 0,
            "out_ms": 4162,
            "discovery_path": "verbal",
            "boundary": {
                "anchor_in_ms": 100,
                "anchor_out_ms": 4100,
                "final_in_ms": 0,
                "final_out_ms": 4162,
                "in_extended_by": "vad_onset",
                "out_extended_by": "tail",
                "sentence_complete": True,
                "confidence": None,
            },
            "transcript": {
                "raw_ckb": "x",
                "norm_ckb": "x",
                "asr": {"canonical": "omniASR_LLM_7B_v2", "aligner": "ctc_viterbi"},
            },
            "speaker": None,
            "editorial": None,
            "output": None,
            "qc": None,
        },
    }
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "revisions").mkdir()
    (tmp_path / "revisions" / "old-run.json").write_text(
        json.dumps(
            {
                "media_id": "fixture",
                "proposed_final_in_ms": 50,
                "proposed_final_out_ms": 4140,
                "status": "approved_pending_render",
                "original": report["clip"]["boundary"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no persisted selected sentences"):
        render_boundary_revision(tmp_path, "old-run")
