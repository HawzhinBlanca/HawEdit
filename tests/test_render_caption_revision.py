"""`render_caption_revision` against a real pipeline run — not a synthetic `report.json`.

Same reasoning as `test_render_boundary_revision.py`: `test_proposals.py` covers
`propose_caption_revision`/`commit_caption_revision` against hand-built reports, the right level
for functions whose job is reading fields off a dict. Rendering drives `captions.py`'s
`build_ass`, `render.py`'s `render_clip`, real ffmpeg, real Kurdish shaping — only a real
`run_pipeline` call, a real fixture, and a real second MP4 prove a revised clip actually plays.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import Qc
from hawedit.judge import JudgeVerdict
from hawedit.learning import ReasonCode
from hawedit.pipeline import PipelineRun, StageSkipped, run_pipeline
from hawedit.proposals import (
    RevisionRejected,
    commit_caption_revision,
    propose_caption_revision,
    render_caption_revision,
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
    """One real rendered run — `report.json` written the same way `durable_workflow.py`'s step
    writes it (`run.to_dict()`, `json.dumps`), with a real `caption_style` (`judge.py`'s own
    default: `word_highlight`) to revise away from."""
    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")
    work = tmp_path_factory.mktemp("caption-revision-render")
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
    assert run.clip.output is not None
    (work / "report.json").write_text(
        json.dumps(run.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    return work, run


def _approve(work: Path, revision_id: str, caption_style: str) -> None:
    proposal = propose_caption_revision(work, caption_style)
    assert proposal.valid, proposal.violation
    commit_caption_revision(
        work,
        proposal,
        revision_id=revision_id,
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )


@needs_ffmpeg
def test_a_legal_style_change_renders_a_real_second_mp4(
    real_run: tuple[Path, PipelineRun],
) -> None:
    work, run = real_run
    original_render_path = Path(run.to_dict()["render"]["path"])
    assert original_render_path.is_file(), "the original render must exist before revising it"

    _approve(work, "to-line", caption_style="line")
    record = render_caption_revision(work, "to-line")

    assert record["status"] == "rendered"
    render_path = Path(record["render_path"])
    assert render_path.is_file()
    assert render_path != original_render_path, "a revision must not overwrite the original"
    assert render_path.stat().st_size > 0
    assert original_render_path.is_file(), "the original render is untouched"


@needs_ffmpeg
def test_the_revised_ass_actually_changes_style(real_run: tuple[Path, PipelineRun]) -> None:
    """Not just "a file exists" — the revision's own point: `word_highlight`'s karaoke `\\kf`
    tags are present in the original and absent from a revision to `line`, read back from the
    real `.ass` file `build_ass` wrote, not assumed from the requested style string."""
    work, run = real_run
    assert run.clip is not None
    # Derived from the path the run itself reports, not rebuilt from `work` and the clip id:
    # delivery became a published *directory* (`artifact_bundle.py`) rather than flat files in
    # the work dir, and a test that reconstructs a path cannot notice that move — this one
    # broke at the agentic merge for exactly that reason. D-A26.
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    published_dir = Path(run.render.path).parent
    (original_ass_path,) = published_dir.glob("*.ass")
    original_ass = original_ass_path.read_text(encoding="utf-8")
    assert "\\kf" in original_ass, "the fixture's own default style must be word_highlight"

    _approve(work, "measured-line", caption_style="line")
    record = render_caption_revision(work, "measured-line")
    revised_ass = Path(record["ass_path"]).read_text(encoding="utf-8")
    assert "\\kf" not in revised_ass, "a 'line' revision must not carry karaoke timing tags"


@needs_ffmpeg
def test_render_also_produces_the_srt_and_edl_sidecars(real_run: tuple[Path, PipelineRun]) -> None:
    work, _run = real_run
    _approve(work, "sidecars", caption_style="line")
    record = render_caption_revision(work, "sidecars")
    assert record["status"] == "rendered"
    assert Path(record["srt_path"]).is_file()
    assert Path(record["edl_path"]).is_file()
    assert Path(record["ass_path"]).is_file()


@needs_ffmpeg
def test_render_preserves_the_original_span(real_run: tuple[Path, PipelineRun]) -> None:
    """A caption revision changes style, never the cut points — asserted against the real
    revised clip's own duration, not merely against the record it wrote."""
    from hawedit.ingest import probe_stream

    work, run = real_run
    original_duration_s = float(
        probe_stream(
            Path(run.to_dict()["render"]["path"]), "format=duration", None, video_only=False
        )
    )
    _approve(work, "same-span", caption_style="line")
    record = render_caption_revision(work, "same-span")
    duration_s = float(
        probe_stream(Path(record["render_path"]), "format=duration", None, video_only=False)
    )
    assert abs(duration_s - original_duration_s) < 0.2, (
        f"a caption revision must not change the span: original {original_duration_s}s, "
        f"revised {duration_s}s"
    )


@needs_ffmpeg
def test_render_refuses_a_revision_that_was_never_approved(
    real_run: tuple[Path, PipelineRun],
) -> None:
    work, _run = real_run
    with pytest.raises(FileNotFoundError):
        render_caption_revision(work, "never-proposed")


@needs_ffmpeg
def test_render_refuses_a_revision_that_failed_validation(
    real_run: tuple[Path, PipelineRun],
) -> None:
    """`commit_caption_revision` already refuses an invalid proposal (`test_proposals.py`), so
    reaching this path at all means the record was hand-edited or came from elsewhere — the
    render gate re-checks the style rather than trusting the string on disk."""
    work, _run = real_run
    proposal = propose_caption_revision(work, "line")
    revisions_dir = work / "revisions"
    revisions_dir.mkdir(exist_ok=True)
    tampered = {
        **proposal.to_dict(),
        "kind": "caption",
        "revision_id": "tampered",
        "approved_by": "nobody-checked",
        "status": "approved_pending_render",
        "proposed_caption_style": "not_a_real_style",  # rewritten after "approval"
    }
    (revisions_dir / "tampered.json").write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="not_a_real_style"):
        render_caption_revision(work, "tampered")


@needs_ffmpeg
def test_render_refuses_a_revision_already_rendered(real_run: tuple[Path, PipelineRun]) -> None:
    work, _run = real_run
    _approve(work, "once-only", caption_style="line")
    render_caption_revision(work, "once-only")
    with pytest.raises(ValueError, match="approved_pending_render"):
        render_caption_revision(work, "once-only")


@needs_ffmpeg
def test_a_declined_revision_cannot_be_rendered(real_run: tuple[Path, PipelineRun]) -> None:
    work, _run = real_run
    proposal = propose_caption_revision(work, "line")
    with pytest.raises(RevisionRejected):
        commit_caption_revision(
            work,
            proposal,
            revision_id="declined",
            approved_by="hawa",
            reason_code=ReasonCode.PREFERENCE,
            confirm=lambda _: False,
        )
    with pytest.raises(FileNotFoundError):
        render_caption_revision(work, "declined")


def test_render_refuses_a_run_with_no_persisted_selected_sentences(tmp_path: Path) -> None:
    """A run from before D-A7 — `selected_sentences` absent or empty — cannot be re-rendered
    from `report.json` alone, and must say so rather than render silent, empty captions."""
    report: dict[str, object] = {
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
            "output": {
                "title_ckb": "t",
                "description_ckb": "d",
                "crop_target": "9:16",
                "caption_style": "word_highlight",
                "durations": [30],
                "hashtags_ckb": [],
            },
            "qc": None,
        },
    }
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "revisions").mkdir()
    (tmp_path / "revisions" / "old-run.json").write_text(
        json.dumps(
            {
                "kind": "caption",
                "media_id": "fixture",
                "original_caption_style": "word_highlight",
                "proposed_caption_style": "line",
                "status": "approved_pending_render",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no persisted selected sentences"):
        render_caption_revision(tmp_path, "old-run")
