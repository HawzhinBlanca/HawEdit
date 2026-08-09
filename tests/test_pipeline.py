"""The runner that joins §3's stages into one command — and says what it could not run.

Until now every stage worked and nothing joined them, so "does this system work" was a
question you answered by reading the test suite. This is the thing you can point at a video.

What makes it worth building while three stages are still blocked is the shape of the answer.
A pipeline that quietly skipped what it could not do would produce a clip and a green log, and
you would have to already know that no ASR ran to understand what you were looking at. So
every stage produces either a result or a `StageSkipped` naming the blocker, the run report
carries both, and `PipelineRun.complete` is false whenever anything was skipped. §1: fail
visible, not silent.

The end-to-end path that *does* run is real. Two stages are stood in for — a transcript for
Stage 1 and a verdict for Stage 4 — and the second of those is not optional scaffolding: the
render gate refuses a clip with no editorial block, so without a verdict the runner builds a
clip and stops. That is audit finding #3's fix reaching all the way out to the runner, and a
test asserts it rather than routing around it.

Given both, this normalizes the transcript (§4.1), indexes it (§2), segments it into sentences
using VAD pauses from Stage 0 (§4.2), takes §5 anchors, fuses a boundary against Stage 0's real
shot cuts (§3 Stage 5), and renders a vertical clip with burned-in Kurdish captions (§3 Stage
6, §4.3) — six stages against real media in one call, and the tests below run it.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import DiscoveryPath, Qc
from hawedit.discovery import MergedCandidate
from hawedit.judge import JudgeVerdict
from hawedit.pipeline import (
    PipelineRun,
    StageSkipped,
    assert_devices_available,
    build_parser,
    build_visual_composer,
    main,
    run_pipeline,
)
from hawedit.transcripts import AsrProvenance, RawTranscript, UnalignedSpeech, Word
from hawedit.visual_index import MAX_FRAMES_PER_WINDOW

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

# Two complete Kurdish sentences whose timings sit inside the 4.16 s fixture, matching the two
# utterances Stage 0's VAD actually finds in it.
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
    )


def a_verdict(clip_in_ms: int, clip_out_ms: int) -> JudgeVerdict:
    """What §3 Stage 4 would have returned. A human can supply one today; Gemini will later."""
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


# --- the honest report --------------------------------------------------------------------


@needs_ffmpeg
def test_a_run_without_a_transcript_is_incomplete_and_says_which_stage_stopped_it(
    tmp_path: Path,
) -> None:
    """No ASR runs here, so Stage 1 cannot produce a transcript and everything after it stops.

    The alternative — rendering nothing and exiting 0 — is the failure this whole project is
    written against: a green run that means "did nothing".
    """
    run = run_pipeline(FIXTURE, tmp_path / "work")
    assert not run.complete
    assert run.ingest is not None, "Stage 0 needs nothing that is blocked and must have run"
    assert isinstance(run.transcript, StageSkipped)
    assert run.transcript.blocked_by == ("Stage 1 producer not enabled",)
    assert "omniASR" in run.transcript.reason
    assert run.clip is None


@needs_ffmpeg
def test_the_report_names_every_stage_that_did_not_run(tmp_path: Path) -> None:
    run = run_pipeline(FIXTURE, tmp_path / "work")
    skipped = {name for name, _ in run.skipped()}
    assert {"transcript", "visual_index", "discovery", "editorial"} <= skipped, skipped
    for _, skip in run.skipped():
        assert skip.blocked_by, f"{skip} names no blocker"


@needs_ffmpeg
def test_a_skipped_stage_is_never_reported_as_an_empty_result(tmp_path: Path) -> None:
    """ "Did not run" and "ran and found nothing" must not serialize to the same thing."""
    run = run_pipeline(FIXTURE, tmp_path / "work")
    payload = run.to_dict()
    assert payload["transcript"]["skipped"] is True
    assert payload["transcript"]["blocked_by"]


def test_an_empty_run_object_cannot_claim_completion() -> None:
    """Absence of explicit skip markers is not evidence that any stage actually ran."""
    run = PipelineRun(media_id="m", source="m.mp4", work_dir="work")
    assert not run.complete
    assert run.to_dict()["complete"] is False


# --- the end-to-end path that does run ----------------------------------------------------


@pytest.fixture(scope="module")
def full_run(tmp_path_factory: pytest.TempPathFactory) -> PipelineRun:
    """Six §3 stages against the real fixture, in one call. Rendered once."""
    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")
    work = tmp_path_factory.mktemp("pipeline")
    return run_pipeline(
        FIXTURE,
        work,
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 4_100),
    )


@needs_ffmpeg
def test_the_full_run_reaches_a_rendered_clip(full_run: PipelineRun) -> None:
    assert full_run.clip is not None
    assert not isinstance(full_run.render, StageSkipped), full_run.render
    assert full_run.render is not None
    assert Path(full_run.render.path).exists()


@needs_ffmpeg
def test_stage_0_ran_on_the_real_media(full_run: PipelineRun) -> None:
    assert not isinstance(full_run.ingest, StageSkipped)
    assert full_run.ingest is not None
    assert full_run.ingest.shot_cuts_ms == (1_400, 2_800)
    assert len(full_run.ingest.speech) == 2


@needs_ffmpeg
def test_stage_2s_window_plan_was_built_from_this_runs_own_shot_cuts(
    full_run: PipelineRun,
) -> None:
    """§3 Stage 2's visual half, on real media, without the weights it is blocked on.

    Stage 0 found cuts at 1400 ms and 2800 ms on this video. The window plan must be *those*
    scenes — the join, not a fixture — and it must cover the media, because a gap is footage
    no visual query could ever retrieve.
    """
    from hawedit.visual_index import assert_window_coverage

    assert not isinstance(full_run.ingest, StageSkipped)
    assert full_run.ingest is not None
    windows = full_run.visual_windows
    assert [w.span for w in windows] == [
        (0, 1_400),
        (1_400, 2_800),
        (2_800, full_run.ingest.duration_ms),
    ]
    assert_window_coverage(windows, media_id="fixture", duration_ms=full_run.ingest.duration_ms)
    # The embedder is still missing, and the run must keep saying so rather than let a real
    # window plan stand in for a visual index it does not have.
    assert isinstance(full_run.visual_index, StageSkipped)


@needs_ffmpeg
def test_the_pipeline_can_use_the_declared_visual_rate_for_short_scenes(tmp_path: Path) -> None:
    run = run_pipeline(FIXTURE, tmp_path / "work", visual_fps=2.0)
    assert run.visual_windows
    assert {window.fps for window in run.visual_windows} == {2.0}
    assert all(window.frame_count >= 3 for window in run.visual_windows)


@needs_ffmpeg
def test_the_normalized_transcript_is_what_the_index_read(full_run: PipelineRun) -> None:
    """Kurdish invariant #3, at the one place the whole pipeline could have got it wrong."""
    assert not isinstance(full_run.index, StageSkipped)
    assert full_run.index is not None
    hits = full_run.index.search("هەولێر")
    assert hits, "the index cannot retrieve a word from its own transcript"


@needs_ffmpeg
def test_the_raw_transcript_is_written_once_and_never_rewritten(full_run: PipelineRun) -> None:
    """Kurdish invariant #1, exercised by the runner rather than only by the store's tests."""
    from hawedit.transcripts import RawTranscriptImmutable, TranscriptStore

    store = TranscriptStore(Path(full_run.work_dir) / "transcripts")
    assert store.raw_path("fixture").exists()
    store.verify_raw_integrity("fixture")
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(a_transcript())


@needs_ffmpeg
def test_a_reused_work_dir_refuses_a_different_supplied_transcript(tmp_path: Path) -> None:
    """Write-once must not become "silently use yesterday's different transcript"."""
    from hawedit.transcripts import RawTranscriptImmutable

    work = tmp_path / "work"
    first = a_transcript("reuse")
    run_pipeline(FIXTURE, work, media_id="reuse", transcript=first)
    changed_words = (replace(first.words[0], w="جیاواز"), *first.words[1:])
    changed = replace(
        first,
        text_ckb=" ".join(word.w for word in changed_words),
        words=changed_words,
    )
    with pytest.raises(RawTranscriptImmutable, match="different canonical transcript"):
        run_pipeline(FIXTURE, work, media_id="reuse", transcript=changed)


@needs_ffmpeg
def test_the_boundary_was_fused_against_stage_0s_real_shot_cuts(full_run: PipelineRun) -> None:
    """§3 Stage 5 takes shot cuts as one of five soft signals — from the same run, not a fixture.

    This is the join the whole runner exists to make: Stage 0 detected 1400 ms and 2800 ms on
    this video, and Stage 5 saw those numbers rather than a hand-written list.
    """
    assert full_run.clip is not None
    boundary = full_run.clip.boundary
    assert boundary.final_in_ms <= boundary.anchor_in_ms
    assert boundary.final_out_ms >= boundary.anchor_out_ms


@needs_ffmpeg
def test_the_rendered_clip_is_vertical_and_the_length_of_the_fused_boundary(
    full_run: PipelineRun,
) -> None:
    assert not isinstance(full_run.render, StageSkipped)
    assert full_run.render is not None
    assert full_run.clip is not None
    assert (full_run.render.width, full_run.render.height) == (1080, 1920)
    assert full_run.render.duration_ms == full_run.clip.out_ms - full_run.clip.in_ms


@needs_ffmpeg
def test_the_run_report_serializes_to_json(full_run: PipelineRun) -> None:
    """The run is data (§1). A report you cannot store is a report you cannot compare."""
    payload = json.loads(json.dumps(full_run.to_dict(), ensure_ascii=False))
    assert payload["media_id"] == "fixture"
    assert payload["index"]["document_count"] == 1
    assert payload["boundary"]["sentence_complete"] is True
    assert payload["clip"]["boundary"]["sentence_complete"] is True
    assert payload["render"]["reframe"] == "static_centre"


@needs_ffmpeg
def test_the_full_run_is_still_not_complete(full_run: PipelineRun) -> None:
    """It rendered a clip. It is still not the system §3 describes, and it says so.

    A run that produced output and called itself complete would be the most expensive kind of
    wrong: nothing about the artifact reveals that no model discovered it, no judge scored it,
    and no diarization informed the crop.
    """
    assert not full_run.complete
    assert {name for name, _ in full_run.skipped()} >= {"discovery", "visual_index"}
    assert "editorial" not in {name for name, _ in full_run.skipped()}


# --- the refusals -------------------------------------------------------------------------


@needs_ffmpeg
def test_a_selection_with_no_complete_sentence_produces_no_clip(tmp_path: Path) -> None:
    """Kurdish invariant #2 reaching all the way out to the runner.

    `anchors_for` returns None when nothing in the selection closed, and §5's contract is
    reject, never render. The runner must stop, not pick an approximate boundary.
    """
    fragment = RawTranscript(
        media_id="frag",
        text_ckb="ڕۆژنامەوانی",
        words=(Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=900, conf=0.9),),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    run = run_pipeline(
        FIXTURE, tmp_path / "work", media_id="frag", transcript=fragment, select_sentences=(0,)
    )
    assert run.clip is None
    assert isinstance(run.boundary, StageSkipped)
    assert "sentence" in run.boundary.reason.lower()


@needs_ffmpeg
def test_a_clip_that_has_not_cleared_qc_is_not_rendered(tmp_path: Path) -> None:
    """§2 puts a human QC gate before output, always — including when a runner is driving."""
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="qc",
        transcript=a_transcript("qc"),
        select_sentences=(0, 1),
        qc=Qc(auto_pass=False, flags=("low_confidence",), human_reviewed=False),
        verdict=a_verdict(100, 4_100),
    )
    assert run.clip is not None, "the clip exists; it is the render that must refuse"
    assert isinstance(run.render, StageSkipped)
    assert "QC" in run.render.reason


@needs_ffmpeg
def test_a_transcript_for_different_media_is_refused(tmp_path: Path) -> None:
    """A transcript of another episode would produce a clip whose captions are fiction."""
    with pytest.raises(ValueError, match="media_id"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            transcript=a_transcript("some-other-episode"),
            media_id="fixture",
            select_sentences=(0, 1),
        )


@needs_ffmpeg
def test_rendering_refuses_a_partial_or_punctuation_changed_alignment(tmp_path: Path) -> None:
    transcript = RawTranscript(
        media_id="partial",
        text_ckb="یەکەم ئاماژەنەکراوە دووەم.",
        words=(
            Word(w="یەکەم", start_ms=100, end_ms=800, conf=0.9),
            Word(w="دووەم.", start_ms=800, end_ms=1_700, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    with pytest.raises(ValueError, match="token-for-token"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="partial",
            transcript=transcript,
            select_sentences=(0,),
        )


@needs_ffmpeg
def test_clip_transcript_preserves_canonical_raw_whitespace(tmp_path: Path) -> None:
    transcript = a_transcript("spacing")
    transcript = replace(transcript, text_ckb=transcript.text_ckb.replace(" ", "  "))
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="spacing",
        transcript=transcript,
        select_sentences=(0, 1),
        verdict=a_verdict(100, 4_100),
    )
    assert run.clip is not None
    assert "  " in run.clip.transcript.raw_ckb
    assert run.clip.transcript.raw_ckb == transcript.text_ckb


@needs_ffmpeg
def test_selecting_a_sentence_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(IndexError, match="sentence"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="oob",
            transcript=a_transcript("oob"),
            select_sentences=(0, 99),
        )


@needs_ffmpeg
def test_an_out_of_order_contiguous_selection_is_processed_in_time_order(tmp_path: Path) -> None:
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="reverse",
        transcript=a_transcript("reverse"),
        select_sentences=(1, 0),
        verdict=a_verdict(100, 4_100),
    )
    assert run.clip is not None
    assert [word.start_ms for word in run.clip.transcript.words] == [100, 800, 2_000, 2_400]
    assert run.clip.clip_id == "reverse-s0-1"


@needs_ffmpeg
def test_soft_boundary_expansion_cannot_swallow_uncaptioned_speech(tmp_path: Path) -> None:
    transcript = RawTranscript(
        media_id="tail",
        text_ckb="یەکەم. دووەم.",
        words=(
            Word(w="یەکەم.", start_ms=100, end_ms=1_700, conf=0.9),
            Word(w="دووەم.", start_ms=1_800, end_ms=2_400, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="tail",
        transcript=transcript,
        select_sentences=(0,),
    )
    assert run.clip is None
    assert isinstance(run.boundary, StageSkipped)
    assert run.boundary.blocked_by == ("uncaptioned speech",)


def test_a_missing_source_file_is_named(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="absent.mp4"):
        run_pipeline(tmp_path / "absent.mp4", tmp_path / "work")


# --- the command-line surface --------------------------------------------------------------


@needs_ffmpeg
def test_the_cli_reports_and_exits_nonzero_when_the_run_is_incomplete(tmp_path: Path) -> None:
    """A partial pipeline must not exit 0 — that is what a shell script would check."""
    from hawedit.pipeline import main

    code = main([str(FIXTURE), "--work-dir", str(tmp_path / "work")])
    assert code != 0


@needs_ffmpeg
def test_missing_gemini_key_is_a_json_stage_skip_not_a_pre_run_cli_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hawedit.pipeline import main

    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(a_transcript("kurdish-speech-3cuts").to_json(), encoding="utf-8")
    monkeypatch.setattr("hawedit.gemini.read_credential", lambda _name=None: None)

    code = main(
        [
            str(FIXTURE),
            "--work-dir",
            str(tmp_path / "work"),
            "--transcript",
            str(transcript_path),
            "--gemini",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert code == 1
    assert captured.err == ""
    assert report["discovery"]["skipped"] is True
    assert "no Gemini API key" in report["discovery"]["reason"]


def test_the_cli_reports_a_missing_source_without_a_traceback(tmp_path: Path) -> None:
    from hawedit.pipeline import main

    assert main([str(tmp_path / "absent.mp4"), "--work-dir", str(tmp_path / "work")]) == 2


def test_the_cli_reports_malformed_transcript_json_without_a_traceback(tmp_path: Path) -> None:
    from hawedit.pipeline import main

    source = tmp_path / "source.mp4"
    source.touch()
    transcript = tmp_path / "transcript.json"
    transcript.write_text("{}", encoding="utf-8")
    assert main([str(source), "--transcript", str(transcript)]) == 2


@pytest.mark.parametrize(
    "flags",
    [
        ("--sentences", "0"),
        ("--qc-pass",),
        ("--confidential",),
    ],
)
def test_the_cli_refuses_flags_whose_prerequisites_are_absent(
    tmp_path: Path, flags: tuple[str, ...]
) -> None:
    from hawedit.pipeline import main

    source = tmp_path / "source.mp4"
    source.touch()
    assert main([str(source), *flags]) == 2


def test_the_cli_can_load_the_documented_stage_4_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.pipeline import PipelineRun, main

    source = tmp_path / "source.mp4"
    source.touch()
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(a_transcript("source").to_json(), encoding="utf-8")
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(
        json.dumps(a_verdict(0, 4_300).to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    captured: dict[str, object] = {}

    def fake_run(source_arg: Path, work_arg: Path, **kwargs: object) -> PipelineRun:
        captured.update(kwargs)
        return PipelineRun(media_id="source", source=str(source_arg), work_dir=str(work_arg))

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", fake_run)
    assert (
        main(
            [
                str(source),
                "--work-dir",
                str(tmp_path / "work"),
                "--transcript",
                str(transcript_path),
                "--verdict",
                str(verdict_path),
                "--sentences",
                "0,1",
                "--qc-pass",
            ]
        )
        == 1
    )
    assert isinstance(captured["verdict"], JudgeVerdict)
    assert captured["qc"] == Qc(auto_pass=False, flags=(), human_reviewed=True)


# --- §3 Stages 3 and 4, wired in ------------------------------------------------------------


@needs_ffmpeg
def test_supplying_path_a_makes_the_runner_discover_instead_of_skip(tmp_path: Path) -> None:
    """The seam closing: `discovery.py` had no producers, and now one plugs in.

    Path B stays absent because its model needs a GPU, so the union runs one-sided — which §3
    says is correct rather than degraded. Candidates from *either* path proceed, and a
    verbal-only moment is precisely the case the dual path exists to protect.
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    def path_a(norm: object) -> list[Candidate]:
        return [
            Candidate("v1", "disc", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9),
            Candidate("v2", "disc", 2_000, 4_100, DiscoveryPath.VERBAL, rank=2, score=0.5),
        ]

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="disc",
        transcript=a_transcript("disc"),
        discover=path_a,
    )
    assert len(run.candidates) == 2
    assert {c.discovery_path for c in run.candidates} == {DiscoveryPath.VERBAL}
    assert "discovery" not in {name for name, _ in run.skipped()}


@needs_ffmpeg
def test_supplying_both_paths_makes_the_union_two_sided_on_this_video(tmp_path: Path) -> None:
    """§3 Stage 3 with both producers, over the scene windows Stage 2 planned on this media.

    Path B reads the windows Stage 0's own cuts produced — 0..1400, 1400..2800, 2800..4162 —
    not a fixture list, so this is the join rather than two modules that happen to typecheck.
    The verbal candidate at 0..1700 overlaps the first visual window, and the merge concludes
    BOTH about that moment while every other candidate survives on its own path: "union, never
    intersect".
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.visual_pipeline import VisualDiscoveryResult

    class Composer:
        def discover(
            self,
            source: Path,
            windows: Sequence[Any],
            query: str,
            work_dir: Path,
            *,
            media_id: str,
            ffmpeg: Path | None = None,
        ) -> VisualDiscoveryResult:
            assert [window.span for window in windows] == [
                (0, 1_400),
                (1_400, 2_800),
                (2_800, 4_162),
            ]
            return VisualDiscoveryResult(
                media_id,
                query,
                3,
                3,
                (),
                (
                    Candidate("scene-0", media_id, 0, 1_400, DiscoveryPath.VISUAL, 1, 0.9),
                    Candidate("scene-2", media_id, 2_800, 4_162, DiscoveryPath.VISUAL, 2, 0.7),
                ),
            )

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="dual",
        transcript=a_transcript("dual"),
        discover=lambda _norm: [
            Candidate("v1", "dual", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
        ],
        visual_composer=Composer(),  # type: ignore[arg-type]
    )
    assert [w.span for w in run.visual_windows] == [(0, 1_400), (1_400, 2_800), (2_800, 4_162)]
    paths = {c.discovery_path for c in run.candidates}
    assert DiscoveryPath.BOTH in paths, paths
    assert DiscoveryPath.VISUAL in paths, paths
    # Nothing is dropped: one verbal candidate plus two bounded visual survivors, and the
    # overlap merges into one rather than disappearing.
    assert sum(len(c.sources) for c in run.candidates) == 3


@needs_ffmpeg
def test_visual_composer_refusal_is_reported_as_a_skipped_stage(tmp_path: Path) -> None:
    from hawedit.visual_pipeline import VisualPipelineError

    class Composer:
        def discover(self, *args: object, **kwargs: object) -> None:
            raise VisualPipelineError("media is too short for Stage 2's survivor slice")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="short",
        transcript=a_transcript("short"),
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert isinstance(run.visual_index, StageSkipped)
    assert "too short" in run.visual_index.reason
    assert run.candidates == ()


@needs_ffmpeg
def test_visual_composer_plans_to_the_measured_videochat_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit import pipeline as pipeline_module
    from hawedit.visual_index import SceneWindow
    from hawedit.visual_index import plan_scene_windows as real_plan
    from hawedit.visual_pipeline import VisualPipelineError

    selected: list[int] = []

    def recording_plan(
        media_id: str,
        duration_ms: int,
        shot_cuts_ms: Sequence[int],
        fps: float,
        *,
        max_frames: int,
    ) -> tuple[SceneWindow, ...]:
        selected.append(max_frames)
        return real_plan(
            media_id,
            duration_ms,
            shot_cuts_ms,
            fps,
            max_frames=max_frames,
        )

    class Composer:
        def discover(self, *args: object, **kwargs: object) -> None:
            raise VisualPipelineError("stop after observing the plan")

    monkeypatch.setattr(pipeline_module, "plan_scene_windows", recording_plan)
    run_pipeline(
        FIXTURE,
        tmp_path / "capacity",
        media_id="capacity",
        transcript=a_transcript("capacity"),
        visual_composer=Composer(),  # type: ignore[arg-type]
        visual_max_frames=8,
    )
    assert selected == [8], "the 64-frame general ceiling still reached VideoChat3"


@needs_ffmpeg
def test_visual_composer_failure_reason_is_single_line_and_bounded(tmp_path: Path) -> None:
    from hawedit.visual_pipeline import VisualPipelineError

    class Composer:
        def discover(self, *args: object, **kwargs: object) -> None:
            raise VisualPipelineError("visual backend\x00\n" + ("v" * 1_000_000))

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="bounded-visual-error",
        transcript=a_transcript("bounded-visual-error"),
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert isinstance(run.visual_index, StageSkipped)
    assert len(run.visual_index.reason) == 1_024
    assert run.visual_index.reason.endswith("…")
    assert not any(character in run.visual_index.reason for character in ("\n", "\t", "\x00"))


@needs_ffmpeg
def test_visual_backend_failure_preserves_path_a_candidates(tmp_path: Path) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.visual_pipeline import VisualPipelineError

    class Composer:
        def discover(self, *args: object, **kwargs: object) -> None:
            failure = RuntimeError("CUDA out of memory")
            raise VisualPipelineError("Qwen backend failed: CUDA out of memory") from failure

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="oom-fallback",
        transcript=a_transcript("oom-fallback"),
        discover=lambda _norm: [
            Candidate(
                "verbal-survivor",
                "oom-fallback",
                0,
                1_400,
                DiscoveryPath.VERBAL,
                rank=1,
                score=0.8,
            )
        ],
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert isinstance(run.visual_index, StageSkipped)
    assert [candidate.discovery_path for candidate in run.candidates] == [DiscoveryPath.VERBAL]


@needs_ffmpeg
def test_unranked_path_b_injection_is_refused(tmp_path: Path) -> None:
    """A bare reader could promote every scene and bypass the keep-5–10 contract."""

    class Reader:
        def read_scenes(self, windows: Sequence[Any]) -> tuple[object, ...]:
            return ()

    with pytest.raises(ValueError, match="Qwen retrieval/reranking"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="unsafe",
            transcript=a_transcript("unsafe"),
            read_scenes=Reader(),  # type: ignore[arg-type]
        )


@needs_ffmpeg
def test_a_discovery_pass_that_finds_nothing_is_reported_not_hidden(tmp_path: Path) -> None:
    """ "Found nothing" is a real answer about this media and §8.2 records it."""
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="empty",
        transcript=a_transcript("empty"),
        discover=lambda _norm: [],
    )
    assert run.candidates == ()
    skipped = dict(run.skipped())
    assert "discovery" in skipped
    assert "no candidates" in skipped["discovery"].blocked_by


@needs_ffmpeg
def test_supplying_a_judge_scores_the_top_candidate(tmp_path: Path) -> None:
    """Stage 4 stops being a stand-in: the runner asks the judge itself."""
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    seen: list[JudgeRequest] = []

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            seen.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            Candidate("v1", "judged", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
        ],
        judge=Judge(),
    )
    assert len(seen) == 1, "the judge must be asked exactly once for the top candidate"
    assert seen[0].carried_verbal_score == 0.9, (
        "§3: Stage 4 adds visual context to survivors rather than re-deriving verbal "
        "judgment — the score Path A produced has to arrive with the request"
    )
    assert seen[0].text_ckb, "the judge was sent no text to read"
    assert "editorial" not in {name for name, _ in run.skipped()}


@needs_ffmpeg
def test_the_judge_gets_rank_one_not_the_earliest_candidate(tmp_path: Path) -> None:
    """Merge order is chronological; Stage 4 survivor order is not."""
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    seen: list[JudgeRequest] = []

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            seen.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="ranked",
        transcript=a_transcript("ranked"),
        discover=lambda _n: [
            Candidate("best", "ranked", 2_000, 4_100, DiscoveryPath.VERBAL, 1, 0.99),
            Candidate("early", "ranked", 0, 1_700, DiscoveryPath.VERBAL, 2, 0.10),
        ],
        judge=Judge(),
    )
    assert seen[0].candidate_id == "best"
    assert seen[0].text_ckb == "لە هەولێر."


@needs_ffmpeg
def test_partial_candidate_overlap_cannot_lend_evidence_to_a_larger_manual_clip(
    tmp_path: Path,
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    with pytest.raises(ValueError, match="not contained"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="partial-candidate",
            transcript=a_transcript("partial-candidate"),
            select_sentences=(0, 1),
            discover=lambda _n: [
                Candidate(
                    "tiny",
                    "partial-candidate",
                    100,
                    200,
                    DiscoveryPath.VERBAL,
                    rank=1,
                    score=0.99,
                )
            ],
        )


def test_vad_onset_is_selected_for_the_anchor_not_the_episode_start() -> None:
    from hawedit.ingest import IngestResult, SpeechSegment
    from hawedit.pipeline import _vad_onset_for_anchor

    ingested = IngestResult(
        media_id="m",
        source="m.mp4",
        audio_path="audio.wav",
        proxy_path="proxy.mp4",
        duration_ms=200_000,
        shot_cuts_ms=(),
        speech=(SpeechSegment(1_000, 5_000), SpeechSegment(99_500, 106_000)),
    )
    assert _vad_onset_for_anchor(ingested, 100_000, 105_000) == 99_500


@needs_ffmpeg
def test_the_run_writes_section_2s_whole_delivery_set(full_run: PipelineRun) -> None:
    """§2's diagram ends with `MP4 · SRT/ASS · editing JSON · EDL`. All four, on disk.

    Two of them did not exist until M3.6, so a run could produce an MP4 and an ASS and be two
    deliverables short of what §2 says this system delivers, with nothing reporting it.
    """
    from hawedit.delivery import parse_srt_times
    from hawedit.pipeline import Delivery

    assert isinstance(full_run.delivery, Delivery), full_run.delivery
    srt = Path(full_run.delivery.srt_path)
    edl = Path(full_run.delivery.edl_path)
    editing_json = Path(full_run.delivery.editing_json_path)
    assert srt.exists() and edl.exists() and editing_json.exists()

    assert full_run.clip is not None
    duration = full_run.clip.out_ms - full_run.clip.in_ms
    cues = parse_srt_times(srt.read_text(encoding="utf-8"))
    assert cues, "the SRT has no cues"
    # The sidecar is on the clip's timeline, like the ASS burned into the picture.
    assert all(start >= 0 and end <= duration for start, end in cues), cues

    body = edl.read_text(encoding="utf-8")
    assert "FCM: NON-DROP FRAME" in body
    # The EDL's record timeline starts at zero; its source timecodes do not have to.
    assert "00:00:00:00" in body
    assert json.loads(editing_json.read_text(encoding="utf-8"))["clip_id"] == full_run.clip.clip_id


@needs_ffmpeg
def test_distinct_selections_do_not_overwrite_each_others_deliveries(tmp_path: Path) -> None:
    work = tmp_path / "work"
    first = run_pipeline(
        FIXTURE,
        work,
        media_id="variants",
        transcript=a_transcript("variants"),
        select_sentences=(0,),
        qc=Qc(auto_pass=False, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )
    assert first.render is not None and not isinstance(first.render, StageSkipped)
    first_path = Path(first.render.path)
    first_bytes = first_path.read_bytes()

    second = run_pipeline(
        FIXTURE,
        work,
        media_id="variants",
        transcript=a_transcript("variants"),
        select_sentences=(0, 1),
        qc=Qc(auto_pass=False, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 4_100),
    )
    assert second.render is not None and not isinstance(second.render, StageSkipped)
    assert Path(second.render.path) != first_path
    assert first_path.read_bytes() == first_bytes

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_pipeline(
            FIXTURE,
            work,
            media_id="variants",
            transcript=a_transcript("variants"),
            select_sentences=(0,),
            qc=Qc(auto_pass=False, flags=(), human_reviewed=True),
            verdict=a_verdict(100, 1_700),
        )


# --- composed model stages -----------------------------------------------------------------


@needs_ffmpeg
def test_runner_invokes_canonical_asr_when_no_transcript_is_supplied(tmp_path: Path) -> None:
    from hawedit.ingest import IngestResult

    seen: list[tuple[str, Path, tuple[tuple[int, int], ...]]] = []

    class CanonicalAsr:
        def transcribe(
            self,
            media_id: str,
            audio_path: Path,
            speech_segments: Sequence[Any],
            work_dir: Path,
            ffmpeg: Path | None = None,
        ) -> RawTranscript:
            segments = tuple(speech_segments)
            seen.append(
                (
                    media_id,
                    audio_path,
                    tuple((segment.start_ms, segment.end_ms) for segment in segments),
                )
            )
            return a_transcript(media_id)

    run = run_pipeline(FIXTURE, tmp_path / "work", media_id="asr", asr=CanonicalAsr())
    assert seen and seen[0][0] == "asr" and seen[0][1].exists() and seen[0][2]
    assert isinstance(run.ingest, IngestResult)
    assert max(end_ms for _, end_ms in seen[0][2]) == run.ingest.duration_ms
    assert not isinstance(run.transcript, StageSkipped)


@needs_ffmpeg
def test_canonical_asr_runtime_failure_is_a_json_capable_stage_skip(tmp_path: Path) -> None:
    class BrokenAsr:
        def transcribe(self, *args: Any, **kwargs: Any) -> RawTranscript:
            raise RuntimeError("checkpoint could not load")

    run = run_pipeline(FIXTURE, tmp_path / "work", media_id="asr-failed", asr=BrokenAsr())

    assert isinstance(run.transcript, StageSkipped)
    assert "RuntimeError: checkpoint could not load" in run.transcript.reason
    assert run.clip is None
    assert json.loads(json.dumps(run.to_dict()))["transcript"]["skipped"] is True


@needs_ffmpeg
def test_automatic_selection_uses_complete_sentences_inside_the_best_survivor(
    tmp_path: Path,
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="automatic",
        transcript=a_transcript("automatic"),
        discover=lambda _n: [
            Candidate("best", "automatic", 0, 1_700, DiscoveryPath.VERBAL, 1, 0.99)
        ],
        judge=Judge(),
        auto_select=True,
    )
    assert run.clip is not None
    assert run.clip.clip_id == "automatic-s0-0"
    assert tuple(word.w for word in run.clip.transcript.words) == tuple(
        word.w for word in WORDS[:2]
    )


@needs_ffmpeg
def test_automatic_selection_with_no_complete_sentence_never_extracts_frames_or_calls_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    calls = {"frames": 0, "judge": 0}

    def extract_frames(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        calls["frames"] += 1
        return ()

    class Judge:
        model_id = "gemini-2.5-pro"
        requires_keyframes = True

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            calls["judge"] += 1
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    monkeypatch.setattr("hawedit.pipeline.extract_judge_frames", extract_frames)
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="automatic-gap",
        transcript=a_transcript("automatic-gap"),
        discover=lambda _n: [
            Candidate(
                "gap",
                "automatic-gap",
                1_750,
                1_950,
                DiscoveryPath.VERBAL,
                1,
                0.99,
            )
        ],
        judge=Judge(),
        auto_select=True,
    )

    assert calls == {"frames": 0, "judge": 0}
    assert run.clip is None
    assert isinstance(run.editorial, StageSkipped)
    assert "no complete contiguous sentence" in run.editorial.reason


@needs_ffmpeg
def test_multimodal_judge_receives_real_source_keyframes_from_runner(tmp_path: Path) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    seen: list[JudgeRequest] = []

    class Judge:
        model_id = "gemini-2.5-pro"
        requires_keyframes = True

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            seen.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="pixels",
        transcript=a_transcript("pixels"),
        discover=lambda _n: [Candidate("best", "pixels", 0, 1_700, DiscoveryPath.VERBAL, 1, 0.99)],
        judge=Judge(),
    )
    assert len(seen) == 1
    assert 1 <= len(seen[0].keyframes) <= 20
    assert all(frame.data.startswith(b"\xff\xd8") for frame in seen[0].keyframes)


@needs_ffmpeg
def test_keyframe_operational_failure_is_an_editorial_skip_before_judging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest
    from hawedit.keyframes import KeyframeError

    judge_calls = 0

    def broken_frames(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        raise KeyframeError("ffmpeg decoder refused the slice")

    class Judge:
        model_id = "gemini-2.5-pro"
        requires_keyframes = True

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            nonlocal judge_calls
            judge_calls += 1
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    monkeypatch.setattr("hawedit.pipeline.extract_judge_frames", broken_frames)
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="bad-frames",
        transcript=a_transcript("bad-frames"),
        discover=lambda _n: [
            Candidate("best", "bad-frames", 0, 1_700, DiscoveryPath.VERBAL, 1, 0.99)
        ],
        judge=Judge(),
    )

    assert judge_calls == 0
    assert isinstance(run.editorial, StageSkipped)
    assert "KeyframeError: ffmpeg decoder refused the slice" in run.editorial.reason


def test_operational_failure_sanitizes_and_bounds_notes_without_changing_plain_reason() -> None:
    from hawedit.pipeline import _operational_failure

    plain = _operational_failure("editorial", "Stage 4", RuntimeError("plain failure"))
    assert plain.reason == "Stage 4 failed with RuntimeError: plain failure"

    noted = RuntimeError("body failure")
    noted.add_note(" first\n\tprivacy warning\x00 ")
    noted.add_note("x" * 2_000)
    failure = _operational_failure("editorial", "Stage 4", noted)
    note_summary = failure.reason.split("; exception notes: ", 1)[1]

    assert note_summary.startswith("first privacy warning | ")
    assert len(note_summary) <= 512
    assert note_summary.endswith("…")
    assert not any(character in note_summary for character in ("\n", "\t", "\x00"))


def test_operational_failure_sanitizes_and_hard_caps_base_message_in_json() -> None:
    from hawedit.pipeline import _operational_failure

    provider_secret = "AIza" + ("S" * 64)
    error = RuntimeError("private-prefix\x00\n" + ("x" * 1_000_000) + provider_secret)
    error.add_note("bounded note")

    failure = _operational_failure("editorial", "Stage 4", error)
    report = json.loads(json.dumps(failure.to_dict()))
    reason = report["reason"]
    detail = reason.split("RuntimeError: ", 1)[1].split("; exception notes: ", 1)[0]

    assert detail.startswith("private-prefix ")
    assert len(detail) == 1_024
    assert detail.endswith("…")
    assert provider_secret not in reason
    assert reason.endswith("; exception notes: bounded note")
    assert not any(character in reason for character in ("\n", "\t", "\x00"))


@needs_ffmpeg
def test_atomic_bundle_failure_reasons_are_single_line_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.artifact_bundle import ArtifactBundle, BundleError

    def refuse_bundle(cls: type[ArtifactBundle], /, *args: object, **kwargs: object) -> None:
        raise BundleError("bundle creation\x00\n" + ("b" * 1_000_000))

    monkeypatch.setattr(ArtifactBundle, "create", classmethod(refuse_bundle))
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="bounded-bundle-error",
        transcript=a_transcript("bounded-bundle-error"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )

    assert isinstance(run.render, StageSkipped)
    assert isinstance(run.delivery, StageSkipped)
    for failure in (run.render, run.delivery):
        assert len(failure.reason) == 1_024
        assert failure.reason.endswith("…")
        assert not any(character in failure.reason for character in ("\n", "\t", "\x00"))


@needs_ffmpeg
def test_keyframe_cleanup_privacy_note_survives_into_json_stage_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest
    from hawedit.keyframes import KeyframeError

    error = KeyframeError("ffmpeg produced no usable keyframe")
    error.add_note(
        "private Stage 4 keyframe cleanup failed for C:/private\nframes: directory locked"
    )
    judge_calls = 0

    def broken_frames(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        raise error

    class Judge:
        model_id = "gemini-2.5-pro"
        requires_keyframes = True

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            nonlocal judge_calls
            judge_calls += 1
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    monkeypatch.setattr("hawedit.pipeline.extract_judge_frames", broken_frames)
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="cleanup-note",
        transcript=a_transcript("cleanup-note"),
        discover=lambda _n: [
            Candidate("best", "cleanup-note", 0, 1_700, DiscoveryPath.VERBAL, 1, 0.99)
        ],
        judge=Judge(),
    )
    report = json.loads(json.dumps(run.to_dict()))
    reason = report["editorial"]["reason"]

    assert judge_calls == 0
    assert "KeyframeError: ffmpeg produced no usable keyframe" in reason
    assert (
        "private Stage 4 keyframe cleanup failed for C:/private frames: directory locked" in reason
    )
    assert "\n" not in reason


@needs_ffmpeg
def test_unsafe_candidate_id_is_rejected_before_stage4_touches_its_work_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    frame_calls = 0

    def extract_frames(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        nonlocal frame_calls
        frame_calls += 1
        return ()

    class Judge:
        model_id = "gemini-2.5-pro"
        requires_keyframes = True

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    monkeypatch.setattr("hawedit.pipeline.extract_judge_frames", extract_frames)
    work = tmp_path / "work"
    with pytest.raises(ValueError, match=r"candidate_id .*safe Stage 4 work component"):
        run_pipeline(
            FIXTURE,
            work,
            media_id="unsafe-candidate",
            transcript=a_transcript("unsafe-candidate"),
            discover=lambda _n: [
                Candidate(
                    "../../outside",
                    "unsafe-candidate",
                    0,
                    1_700,
                    DiscoveryPath.VERBAL,
                    1,
                    0.99,
                )
            ],
            judge=Judge(),
        )

    assert frame_calls == 0
    assert not (tmp_path / "outside").exists()


def test_colon_delimited_candidate_id_has_a_portable_single_work_component() -> None:
    from hawedit.pipeline import _candidate_work_component

    assert _candidate_work_component("episode:s0:w1") == "episode_s0_w1"


@pytest.mark.parametrize("failure_kind", ["gemini", "unusable", "not-routable", "too-large"])
@needs_ffmpeg
def test_known_judge_operational_failures_are_editorial_skips(
    tmp_path: Path, failure_kind: str
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.gemini import GeminiUnavailable, JudgeUnusable
    from hawedit.judge import JudgeRequest, NotRoutable, RequestTooLarge

    failure = {
        "gemini": GeminiUnavailable("cloud refused"),
        "unusable": JudgeUnusable("malformed model output"),
        "not-routable": NotRoutable("shadow model"),
        "too-large": RequestTooLarge("token ceiling"),
    }[failure_kind]

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            raise failure

    run = run_pipeline(
        FIXTURE,
        tmp_path / f"work-{failure_kind}",
        media_id=f"judge-{failure_kind}",
        transcript=a_transcript(f"judge-{failure_kind}"),
        discover=lambda _n: [
            Candidate(
                "best",
                f"judge-{failure_kind}",
                0,
                1_700,
                DiscoveryPath.VERBAL,
                1,
                0.99,
            )
        ],
        judge=Judge(),
    )

    assert isinstance(run.editorial, StageSkipped)
    assert type(failure).__name__ in run.editorial.reason
    assert run.clip is None


@needs_ffmpeg
def test_composed_visual_path_uses_measured_fps_and_best_verbal_slice_as_query(
    tmp_path: Path,
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.visual_pipeline import VisualDiscoveryResult

    observed: dict[str, object] = {}

    class Composer:
        def discover(
            self,
            source: Path,
            windows: Sequence[Any],
            query: str,
            work_dir: Path,
            *,
            media_id: str,
            ffmpeg: Path | None = None,
        ) -> VisualDiscoveryResult:
            observed.update(query=query, fps=windows[0].fps, media_id=media_id)
            return VisualDiscoveryResult(
                media_id,
                query,
                len(windows),
                len(windows),
                (),
                (Candidate("scene", media_id, 2_000, 4_100, DiscoveryPath.VISUAL, 1, 0.8),),
            )

    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="composed",
        transcript=a_transcript("composed"),
        discover=lambda _n: [
            Candidate("best", "composed", 2_000, 4_100, DiscoveryPath.VERBAL, 1, 0.9)
        ],
        visual_composer=Composer(),  # type: ignore[arg-type]
    )
    assert observed == {"query": "لە هەولێر.", "fps": 2.0, "media_id": "composed"}


@needs_ffmpeg
def test_path_a_operational_failure_stays_visible_while_independent_visual_path_runs(
    tmp_path: Path,
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.gemini import GeminiUnavailable
    from hawedit.visual_pipeline import VisualDiscoveryResult

    class Composer:
        def discover(
            self,
            source: Path,
            windows: Sequence[Any],
            query: str,
            work_dir: Path,
            *,
            media_id: str,
            ffmpeg: Path | None = None,
        ) -> VisualDiscoveryResult:
            candidate = Candidate(
                "visual",
                media_id,
                0,
                1_700,
                DiscoveryPath.VISUAL,
                1,
                0.9,
            )
            return VisualDiscoveryResult(media_id, query, len(windows), 1, (), (candidate,))

    def broken_path_a(_transcript: Any) -> Sequence[Candidate]:
        raise GeminiUnavailable("temporary cloud refusal")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="one-path",
        transcript=a_transcript("one-path"),
        discover=broken_path_a,
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert isinstance(run.discovery, StageSkipped)
    assert "GeminiUnavailable: temporary cloud refusal" in run.discovery.reason
    assert tuple(candidate.candidate_id for candidate in run.candidates) == ("visual",)
    assert not isinstance(run.visual_index, StageSkipped)


@needs_ffmpeg
def test_programmer_exception_from_discovery_is_not_normalized(tmp_path: Path) -> None:
    def broken_discovery(_transcript: Any) -> Sequence[Any]:
        raise AssertionError("producer invariant broke")

    with pytest.raises(AssertionError, match="producer invariant broke"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="programmer-error",
            transcript=a_transcript("programmer-error"),
            discover=broken_discovery,
        )


@needs_ffmpeg
def test_timelens_grounding_is_composed_into_boundary_fusion(tmp_path: Path) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.timelens import VisualEvidenceInterval
    from hawedit.visual_index import SceneWindow

    seen: list[SceneWindow] = []
    events: list[str] = []

    class Grounder:
        def ground_all(
            self, windows: Sequence[SceneWindow], query: str
        ) -> tuple[VisualEvidenceInterval, ...]:
            events.append("ground")
            seen.extend(windows)
            assert query
            return (VisualEvidenceInterval("grounded", 1_500, 1_950, "visible reaction"),)

        def close(self) -> None:
            events.append("close")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="grounded",
        transcript=a_transcript("grounded"),
        select_sentences=(0,),
        discover=lambda _n: [Candidate("wide", "grounded", 0, 2_800, DiscoveryPath.VERBAL, 1, 0.9)],
        temporal_grounder=Grounder(),
    )
    assert seen and all(window.in_ms < 2_800 and window.out_ms > 0 for window in seen)
    assert events == ["ground", "close"], "GPU 1 must be released before boundary/render work"
    assert run.clip is not None
    assert run.clip.boundary.final_out_ms == 1_950
    assert run.clip.boundary.out_extended_by == "timelens_interval_end"


@pytest.mark.parametrize("failure_kind", ["grounding", "weights", "frames"])
@needs_ffmpeg
def test_known_timelens_failures_skip_boundary_and_never_render(
    tmp_path: Path, failure_kind: str
) -> None:
    from hawedit.qwen_visual import EmbedderUnavailable
    from hawedit.video_grounding import GroundingError
    from hawedit.video_input import VideoInputError

    failure = {
        "grounding": GroundingError("model response was not spans"),
        "weights": EmbedderUnavailable("checkpoint absent"),
        "frames": VideoInputError("window extraction failed"),
    }[failure_kind]

    class Grounder:
        def ground_all(self, windows: Sequence[Any], query: str) -> tuple[Any, ...]:
            raise failure

    run = run_pipeline(
        FIXTURE,
        tmp_path / f"work-{failure_kind}",
        media_id=f"timelens-{failure_kind}",
        transcript=a_transcript(f"timelens-{failure_kind}"),
        select_sentences=(0,),
        verdict=replace(
            a_verdict(100, 1_700),
            candidate_id=f"timelens-{failure_kind}-0",
        ),
        temporal_grounder=Grounder(),
    )

    assert isinstance(run.boundary, StageSkipped)
    assert type(failure).__name__ in run.boundary.reason
    assert isinstance(run.render, StageSkipped)
    assert run.clip is None


@needs_ffmpeg
def test_timelens_cleanup_failure_after_success_becomes_a_boundary_refusal(tmp_path: Path) -> None:
    from hawedit.timelens import VisualEvidenceInterval

    class Grounder:
        def ground_all(self, windows: Sequence[Any], query: str) -> tuple[Any, ...]:
            return (VisualEvidenceInterval("ok", 100, 1_700, "visible"),)

        def close(self) -> None:
            raise RuntimeError("CUDA allocator would not release")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "cleanup-after-success",
        media_id="cleanup-after-success",
        transcript=a_transcript("cleanup-after-success"),
        select_sentences=(0,),
        temporal_grounder=Grounder(),
    )
    assert isinstance(run.boundary, StageSkipped)
    assert "TimeLens cleanup failed after inference" in run.boundary.reason
    assert run.clip is None


@needs_ffmpeg
def test_timelens_cleanup_does_not_mask_the_primary_grounding_failure(tmp_path: Path) -> None:
    from hawedit.video_grounding import GroundingError

    class Grounder:
        def ground_all(self, windows: Sequence[Any], query: str) -> tuple[Any, ...]:
            raise GroundingError("primary model refusal")

        def close(self) -> None:
            raise RuntimeError("cleanup also failed")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "cleanup-after-failure",
        media_id="cleanup-after-failure",
        transcript=a_transcript("cleanup-after-failure"),
        select_sentences=(0,),
        temporal_grounder=Grounder(),
    )
    assert isinstance(run.boundary, StageSkipped)
    assert "primary model refusal" in run.boundary.reason
    assert "TimeLens cleanup failed" in run.boundary.reason
    assert run.clip is None


@needs_ffmpeg
def test_subject_tracking_marks_output_for_dynamic_reframing(tmp_path: Path) -> None:
    from hawedit.reframe import FocusPoint

    class Tracker:
        def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]:
            assert source == FIXTURE and out_ms > in_ms
            return (FocusPoint(in_ms, 120), FocusPoint(out_ms - 1, 520))

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="tracked",
        transcript=a_transcript("tracked"),
        select_sentences=(0,),
        verdict=replace(a_verdict(100, 1_700), candidate_id="tracked-0"),
        subject_tracker=Tracker(),
    )
    assert run.clip is not None and run.clip.output is not None
    assert run.clip.output.crop_target == "face_tracked"


@needs_ffmpeg
def test_requested_tracker_runtime_failure_skips_render_without_static_fallback(
    tmp_path: Path,
) -> None:
    class BrokenTracker:
        def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[Any, ...]:
            raise RuntimeError("OpenCV could not decode a frame")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="tracking-failed",
        transcript=a_transcript("tracking-failed"),
        select_sentences=(0,),
        verdict=replace(a_verdict(100, 1_700), candidate_id="tracking-failed-0"),
        subject_tracker=BrokenTracker(),
    )

    assert run.clip is None
    assert isinstance(run.render, StageSkipped)
    assert "RuntimeError: OpenCV could not decode a frame" in run.render.reason
    assert "requested subject tracking" in run.render.reason


# =========================================================================================
# §3 Stage 5's fifth out-point signal
#
# `fuse_boundary` has always had a `natural_silence` branch. This runner computed the VAD
# silences (`_pauses_between`), spent them on §4.2's sentence segmentation, and never handed
# Stage 5 its own — so the branch was unreachable from the runner and the fused out point was
# three of §3's five signals. D-070.
#
# Both directions are asserted on the fused artifact, and the pair is the point: the same
# wiring bug is also consistent with reading "natural silence" as *the next speech onset*,
# which is the plausible wrong answer. On this fixture that would put the out point at 1954 ms
# — across the whole 164 ms pause, butting against the next utterance — so the control below
# fails for it while the positive test passes either way.
# =========================================================================================


def _transcript_ending_speech_early(media_id: str) -> RawTranscript:
    """The same fixture transcript with sentence 0's last word ending 200 ms sooner.

    Stage 0's real VAD puts speech at 0..1790 ms and 1954..4180 ms on this media. With the
    stock timings the last word of sentence 0 ends at 1700, so §3's 200 ms tail reaches 1900
    and beats the 1790 ms silence — which is why the stock case is the control, not the proof.
    Ending the word at 1500 is the ordinary situation this signal exists for: the speaker's
    audible tail runs past the last aligned word.
    """
    words = (WORDS[0], replace(WORDS[1], end_ms=1_500), WORDS[2], WORDS[3])
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )


@needs_ffmpeg
def test_the_fused_out_point_ends_on_stage_0s_real_natural_silence(tmp_path: Path) -> None:
    """The out point lands where this run's VAD says speech stopped, not 200 ms after a word."""
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="silence",
        transcript=_transcript_ending_speech_early("silence"),
        select_sentences=(0,),
    )
    assert run.clip is not None, run.boundary
    # 1790 ms is Stage 0's own measurement on this file, not a constant in this test.
    assert run.clip.boundary.final_out_ms == 1_790
    assert run.clip.boundary.out_extended_by == "natural_silence"
    # The invariant Stage 5 exists to protect, on the artifact.
    assert run.clip.boundary.final_out_ms >= run.clip.boundary.anchor_out_ms


@needs_ffmpeg
def test_natural_silence_does_not_extend_past_where_speech_stopped(tmp_path: Path) -> None:
    """The control. With the stock timings §3's tail is later, so the tail must win.

    This fails if `natural_silence` is read as the next speech onset (1954 ms here): that
    reaches across the entire pause to the following utterance, which is the opposite of a
    natural stop and would silently lengthen every clip in the middle of an episode.
    """
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="tailwins",
        transcript=a_transcript("tailwins"),
        select_sentences=(0,),
    )
    assert run.clip is not None, run.boundary
    assert run.clip.boundary.final_out_ms == 1_900
    assert run.clip.boundary.out_extended_by == "tail"


def test_there_is_no_natural_silence_to_extend_to_inside_a_pause() -> None:
    """An anchor already sitting in a silence has nothing to extend to, so the signal is None.

    `None`, never the pause's own edge: a number here would be indistinguishable from a
    measurement, and §3 counts which signal moved the boundary.
    """
    from typing import cast

    from hawedit.ingest import SpeechSegment
    from hawedit.pipeline import _natural_silence_for_anchor

    class Ingested:
        speech = (SpeechSegment(0, 1_790), SpeechSegment(1_954, 4_180))

    ingested = cast(Any, Ingested())
    assert _natural_silence_for_anchor(ingested, 1_700) == 1_790
    assert _natural_silence_for_anchor(ingested, 1_850) is None  # inside the 164 ms pause
    assert _natural_silence_for_anchor(ingested, 4_180) is None  # past all speech
    # Exactly on the edge: speech already stopped there, so there is nothing to extend to.
    assert _natural_silence_for_anchor(ingested, 1_790) is None


# =========================================================================================
# The overwrite refusal used to fire after the money was spent
#
# `_assert_no_existing_artifacts` lived beside the render step, ~180 lines after the billed
# Stage 4 `generateContent` and after Stage 2/3's model calls. A re-run into a used work
# directory paid Gemini, loaded both Qwen checkpoints and VideoChat3, and *then* refused with
# nothing to show for it. The condition depended only on the work dir, the media id and the
# sentence selection — all knowable before any of that. D-071.
# =========================================================================================


def _existing_artifact(work_dir: Path, media_id: str, sentence: int) -> Path:
    """Plant one of the five files a completed run writes, exactly as the run names it."""
    from hawedit.pipeline import _clip_id, _delivery_artifact_paths

    work_dir.mkdir(parents=True, exist_ok=True)
    planted = _delivery_artifact_paths(work_dir, _clip_id(media_id, (sentence,)))[0]
    planted.parent.mkdir(parents=True)
    planted.write_text("a previous run left this here", encoding="utf-8")
    return planted


def test_an_overwriting_run_refuses_before_the_billed_judge_call(tmp_path: Path) -> None:
    """The artifact of this fix is a request that never happened."""
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    work = tmp_path / "work"
    planted = _existing_artifact(work, "billed", 0)

    calls: list[JudgeRequest] = []

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            calls.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    with pytest.raises(FileExistsError) as raised:
        run_pipeline(
            FIXTURE,
            work,
            media_id="billed",
            transcript=a_transcript("billed"),
            select_sentences=(0,),
            discover=lambda _n: [
                Candidate("v1", "billed", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
            ],
            judge=Judge(),
        )

    assert str(planted.parent) in str(raised.value)
    # The whole point. Not "it refused" — it refused without spending anything.
    assert calls == [], f"the billed judge ran {len(calls)} time(s) before the refusal"


def test_an_overwriting_auto_selected_run_also_refuses_before_the_judge(tmp_path: Path) -> None:
    """`--auto-select` picks its sentences after Stage 3, so it needs its own guard point.

    Without the second call site this run reaches the judge: the first guard sees an empty
    selection, returns, and nothing re-checks once auto-selection has named sentence 0.
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    work = tmp_path / "work"
    _existing_artifact(work, "autobilled", 0)

    calls: list[JudgeRequest] = []

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            calls.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    with pytest.raises(FileExistsError):
        run_pipeline(
            FIXTURE,
            work,
            media_id="autobilled",
            transcript=a_transcript("autobilled"),
            discover=lambda _n: [
                Candidate("v1", "autobilled", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
            ],
            auto_select=True,
            judge=Judge(),
        )

    assert calls == [], f"the billed judge ran {len(calls)} time(s) before the refusal"


def test_a_clean_work_directory_still_reaches_the_judge(tmp_path: Path) -> None:
    """The control. A guard that refused every run would pass both tests above.

    Same call, nothing planted: the judge must be reached exactly once, so the tests above
    are measuring the collision and not a pipeline that stopped working.
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.judge import JudgeRequest

    calls: list[JudgeRequest] = []

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            calls.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="billed",
        transcript=a_transcript("billed"),
        select_sentences=(0,),
        discover=lambda _n: [
            Candidate("v1", "billed", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
        ],
        judge=Judge(),
    )
    assert len(calls) == 1, f"expected one billed call, got {len(calls)}"
    assert run.clip is not None


def test_the_guard_checks_the_paths_the_run_actually_writes(tmp_path: Path) -> None:
    """The guard and the writer must derive names from one place, or the guard can miss.

    Asserted against the rendered artifact rather than against the helper: whatever the run
    puts on disk has to be a file the guard would have refused on a second run.
    """
    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")
    from hawedit.pipeline import _clip_id, _delivery_artifact_paths

    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="paths",
        transcript=a_transcript("paths"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )
    assert run.render is not None and not isinstance(run.render, StageSkipped), run.render
    guarded = set(_delivery_artifact_paths(work, _clip_id("paths", (0,))))
    assert Path(run.render.path) in guarded, (
        f"the run wrote {run.render.path}, which the overwrite guard does not check"
    )
    assert Path(run.render.path).parent == next(iter(guarded)).parent
    assert set(Path(run.render.path).parent.iterdir()) == guarded
    assert not tuple(work.glob(".paths-s0-0.*.staging"))


# =========================================================================================
# §2's delivery set is all-or-none
#
# The runner once wrote JSON and SRT before discovering that its EDL builder could not represent
# an NTSC source. Building all three first closed that partial-set window. NTSC drop-frame is now
# supported, but the ordering remains load-bearing for unsupported fractional rates. D-072.
#
# The fixture is 25 fps, which is EDL-safe — that is what makes the control below possible.
# =========================================================================================

_SIDECARS = (".json", ".srt", ".edl")


def _fractional_rate_copy(source: Path, dest: Path, rate: str) -> Path:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-r",
            rate,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(dest),
        ],
        check=True,
    )
    return dest


def _ntsc_copy(source: Path, dest: Path) -> Path:
    """A real 29.97 fps transcode of the fixture. `frame_rate` reads 30000/1001 from it."""
    return _fractional_rate_copy(source, dest, "30000/1001")


def _sidecars_on_disk(work: Path) -> list[str]:
    return sorted(
        p.name for p in work.rglob("*") if p.suffix in _SIDECARS and p.parent.name == p.stem
    )


@needs_ffmpeg
def test_an_ntsc_source_writes_a_complete_drop_frame_delivery_set(tmp_path: Path) -> None:
    ntsc = _ntsc_copy(FIXTURE, tmp_path / "ntsc.mp4")
    from hawedit.render import frame_rate

    assert frame_rate(ntsc) != int(frame_rate(ntsc)), "the transcode must be a non-integer rate"

    work = tmp_path / "work"
    run = run_pipeline(
        ntsc,
        work,
        media_id="ntsc",
        transcript=a_transcript("ntsc"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )
    assert run.delivery is not None and not isinstance(run.delivery, StageSkipped), run.delivery
    assert _sidecars_on_disk(work) == ["ntsc-s0-0.edl", "ntsc-s0-0.json", "ntsc-s0-0.srt"]
    edl = Path(run.delivery.edl_path).read_text(encoding="utf-8")
    assert "FCM: DROP FRAME" in edl
    assert ";" in next(line for line in edl.splitlines() if line.startswith("001"))


@needs_ffmpeg
def test_an_edl_safe_source_still_writes_the_whole_delivery_set(tmp_path: Path) -> None:
    """The control. Cleaning up unconditionally, or never building the set, passes the test
    above and fails this one — the fixture is 25 fps and must deliver all three sidecars."""
    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="safe",
        transcript=a_transcript("safe"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )
    assert not isinstance(run.delivery, StageSkipped), run.delivery
    assert _sidecars_on_disk(work) == ["safe-s0-0.edl", "safe-s0-0.json", "safe-s0-0.srt"]


@needs_ffmpeg
def test_a_write_failing_partway_through_the_sidecars_leaves_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Building first fixes the refusal case; this covers the disk filling up mid-sequence.

    The JSON is written, the SRT write raises, and the JSON must not survive it.
    """
    from hawedit.artifact_bundle import ArtifactBundle

    real_write_text = ArtifactBundle.write_text

    def failing_write_text(self: ArtifactBundle, suffix: str, payload: str) -> Path:
        if suffix == "srt":
            raise OSError("no space left on device")
        return real_write_text(self, suffix, payload)

    monkeypatch.setattr(ArtifactBundle, "write_text", failing_write_text)

    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="nospace",
        transcript=a_transcript("nospace"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )
    assert isinstance(run.render, StageSkipped)
    assert "not published" in run.render.reason
    assert isinstance(run.delivery, StageSkipped)
    assert "no space left" in run.delivery.reason
    assert _sidecars_on_disk(work) == [], f"stranded {_sidecars_on_disk(work)}"
    assert not (work / "nospace-s0-0").exists()
    assert not tuple(work.glob(".nospace-s0-0.*.staging"))


@needs_ffmpeg
def test_an_ass_staging_failure_is_reported_and_leaves_no_private_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.artifact_bundle import ArtifactBundle, BundleError

    def fail_ass(self: ArtifactBundle, suffix: str, payload: str) -> Path:
        raise BundleError(f"could not stage {suffix}: permission denied")

    monkeypatch.setattr(ArtifactBundle, "write_text", fail_ass)
    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="noass",
        transcript=a_transcript("noass"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )

    assert isinstance(run.render, StageSkipped)
    assert "permission denied" in run.render.reason
    assert not (work / "noass-s0-0").exists()
    assert not tuple(work.glob(".noass-s0-0.*.staging"))


@needs_ffmpeg
def test_an_unsupported_fractional_edl_never_writes_a_sidecar_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stronger than "no sidecars survive": none is ever created.

    The cleanup loop alone makes the *final* disk state correct, so a mutation audit found
    that reverting the build-before-write ordering changed nothing observable. It does change
    something that matters: written-then-deleted leaves a window in which the files exist, and
    a crash inside it — power loss, SIGKILL — strands exactly the partial set this fixes. The
    only way to see the difference is to watch the writes rather than the leftovers.
    """
    from hawedit.artifact_bundle import ArtifactBundle

    fractional = _fractional_rate_copy(FIXTURE, tmp_path / "fractional.mp4", "24000/1001")
    real_write_text = ArtifactBundle.write_text
    attempted: list[str] = []

    def recording_write_text(self: ArtifactBundle, suffix: str, payload: str) -> Path:
        attempted.append(suffix)
        return real_write_text(self, suffix, payload)

    monkeypatch.setattr(ArtifactBundle, "write_text", recording_write_text)

    work = tmp_path / "work"
    run = run_pipeline(
        fractional,
        work,
        media_id="fractional",
        transcript=a_transcript("fractional"),
        select_sentences=(0,),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 1_700),
    )
    assert isinstance(run.delivery, StageSkipped)
    assert "fractional frame rate" in run.delivery.reason
    assert attempted == ["ass"], f"wrote {attempted[1:]} before discovering the EDL refusal"
    assert not (work / "fractional-s0-0").exists()
    assert not tuple(work.glob(".fractional-s0-0.*.staging"))


# --- D-137: §6 assigns the video phase across both GPUs, and the code used one ---------------


def test_the_cli_defaults_put_each_visual_model_where_section_6_puts_it() -> None:
    """§6, VIDEO PHASE: `GPU 0 → VideoChat3-4B` and `GPU 1 → Embedding / Reranker / TimeLens2`.

    All three used to take `--visual-device`, so on hawapc01 they landed together on GPU 0 while
    GPU 1 held 1.3 GiB — and the real 38-minute run died with *"CUDA out of memory. Tried to
    allocate 21.83 GiB. GPU 0 has a total capacity of 23.99 GiB of which 3.59 GiB is free. Of the
    allocated memory 18.30 GiB is allocated by PyTorch."* Asserted on the parsed defaults, because
    a comment claiming §6 is not §6 being followed. D-137.
    """
    parser = build_parser()
    args = parser.parse_args(["source.mp4"])
    assert args.visual_device == "cuda:0", "§6 reserves GPU 0 for the Path B reader"
    assert args.index_device == "cuda:1", "§6 puts Stage 2 embedding and reranking on GPU 1"
    assert args.timelens_device == "cuda:1", "§6 puts TimeLens2 on GPU 1"
    assert args.index_device != args.visual_device, (
        "indexing and the reader on one GPU is the packing that OOM'd on real media"
    )


def test_a_cuda_device_this_machine_does_not_have_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two-GPU defaults must not become a cryptic torch error on a one-GPU box.

    Without this, `--index-device cuda:1` on a single-GPU machine dies inside torch with a device
    ordinal message that names neither the stage nor the remedy.
    """
    monkeypatch.setattr("hawedit.pipeline.visible_cuda_devices", lambda: 1)
    with pytest.raises(SystemExit) as caught:
        assert_devices_available({"Stage 2 indexing": "cuda:1", "the Path B reader": "cuda:0"})
    message = str(caught.value)
    assert "1 CUDA device(s)" in message
    assert "Stage 2 indexing on cuda:1" in message
    assert "the Path B reader" not in message, "cuda:0 exists on a one-GPU machine"
    assert "--index-device cuda:0" in message, "a refusal that names no remedy is a dead end"


def test_the_devices_this_machine_does_have_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control. A check that refused every CUDA device would satisfy the test above and stop
    the machine §6 was written for from running at all.
    """
    monkeypatch.setattr("hawedit.pipeline.visible_cuda_devices", lambda: 2)
    assert_devices_available(
        {
            "the Path B reader": "cuda:0",
            "Stage 2 indexing": "cuda:1",
            "TimeLens2": "cuda:1",
        }
    )  # must not raise


def test_a_non_cuda_device_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """`cpu`, or `cuda` with no ordinal, is not a device index to bounds-check."""
    monkeypatch.setattr("hawedit.pipeline.visible_cuda_devices", lambda: 0)
    assert_devices_available({"Stage 2 indexing": "cpu", "TimeLens2": "cuda"})


def test_the_composer_wires_each_model_to_the_device_section_6_assigns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The wiring, not the flag. This is the test D-137 needed and did not have at first.

    The first version asserted the parsed defaults, and the audit showed why that measures nothing:
    reverting either Qwen model to `--visual-device` left the suite green, because a default nothing
    reads is not an assignment. Same shape as D-094's substring — the request echoed back rather
    than the thing that happens.
    """
    seen: dict[str, str] = {}

    class FakeEmbedder:
        def __init__(self, directory: Path, device: str = "") -> None:
            seen["embedder"] = device

    class FakeReranker:
        def __init__(self, directory: Path, read: object, device: str = "") -> None:
            seen["reranker"] = device

    class FakeReader:
        def __init__(self, directory: Path, read: object, score: object, device: str = "") -> None:
            seen["reader"] = device

    monkeypatch.setattr("hawedit.qwen_visual.QwenVisualEmbedder", FakeEmbedder)
    monkeypatch.setattr("hawedit.qwen_visual.QwenVisualReranker", FakeReranker)
    monkeypatch.setattr("hawedit.video_reader.VideoChat3Reader", FakeReader)
    monkeypatch.setattr("hawedit.models.ModelStore.path_for", lambda self, entry: tmp_path)

    args = build_parser().parse_args(["source.mp4", "--visual"])
    composer = build_visual_composer(args)

    def never_called(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("the factories are built, not run, in this test")

    # both are factories: §3 Stage 2 builds them per run, so the device only lands when called
    composer.reranker_factory(never_called)
    composer.reader_factory(never_called, never_called)

    assert seen["embedder"] == "cuda:1", "§6 puts Stage 2 embedding on GPU 1"
    assert seen["reranker"] == "cuda:1", "§6 puts Stage 2 reranking on GPU 1"
    assert seen["reader"] == "cuda:0", "§6 reserves GPU 0 for the Path B reader"
    assert seen["embedder"] != seen["reader"], (
        "indexing and the reader on one GPU is the packing that OOM'd on real media"
    )


# --- D-143: the frame ceiling has to survive the trip from the CLI to the plan ----------------


@needs_ffmpeg
def test_the_frame_ceiling_reaches_the_planned_windows(tmp_path: Path) -> None:
    """Asserted on the windows the run reports, not on the argument it was handed.

    The D-143 audit found the planner tested and the *wiring* untested: replacing
    `max_frames=visual_max_frames` with `max_frames=MAX_FRAMES_PER_WINDOW` left the suite green.
    That is D-137's survivor one iteration earlier, in a new place — so this asserts the artifact.

    At 2 fps the fixture's 1400 ms scenes plan 3 frames each, which a ceiling of 2 splits. At 1 fps
    they plan exactly 2 and no legal ceiling bites, which is how the first version of this test came
    to assert a difference that could not exist.
    """
    wide = run_pipeline(FIXTURE, tmp_path / "wide", visual_fps=2.0)
    narrow = run_pipeline(FIXTURE, tmp_path / "narrow", visual_fps=2.0, visual_max_frames=2)

    assert max(window.frame_count for window in wide.visual_windows) == 3
    assert max(window.frame_count for window in narrow.visual_windows) <= 2
    assert len(narrow.visual_windows) > len(wide.visual_windows), (
        "a lower ceiling must produce more windows, or it did not reach the planner"
    )


@needs_ffmpeg
def test_the_cli_hands_the_ceiling_to_the_run(tmp_path: Path) -> None:
    """The other half of the trip. Deleting the keyword at the call site left the suite
    green too.
    """
    captured: dict[str, object] = {}
    real = run_pipeline

    def spy(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("hawedit.pipeline.run_pipeline", spy)
        main([str(FIXTURE), "--work-dir", str(tmp_path / "work"), "--visual-max-frames", "2"])

    assert captured.get("visual_max_frames") == 2, (
        f"the CLI value never reached run_pipeline: {sorted(captured)}"
    )


@needs_ffmpeg
def test_the_default_run_still_plans_at_section_3s_ceiling(tmp_path: Path) -> None:
    """The control. Defaulting the pipeline to one machine's limit would satisfy both tests above
    and quietly replace §3's published setting for every machine.
    """
    run = run_pipeline(FIXTURE, tmp_path / "work", visual_fps=2.0)

    assert max(window.frame_count for window in run.visual_windows) == 3, (
        "the fixture's scenes plan 3 frames at 2 fps; a default ceiling below §3's would cut this"
    )
    assert build_parser().parse_args(["x.mp4"]).visual_max_frames == MAX_FRAMES_PER_WINDOW


# --- D-145: the report was silent about speech the transcript does not contain ----------------


@needs_ffmpeg
def test_the_report_says_which_speech_has_no_transcription(tmp_path: Path) -> None:
    """D-103 put the gaps in `transcript.raw.json`; the report shows the *normalized* transcript,
    which by design has no such field, so a run that dropped speech said nothing about it.

    Measured on the real 38-minute run: 2 of 547 regions, **664 ms** of Kurdish with no
    transcription, and the emitted report mentioned neither `unaligned` nor
    `segment_confidence`. This module's own §1 is "fail visible, not silent". D-145.
    """
    with_gaps = RawTranscript(
        media_id="fixture",
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        unaligned=(
            UnalignedSpeech(
                start_ms=226_754,
                end_ms=227_070,
                reason="AlignmentInfeasible: 15 frames cannot emit 15 tokens",
            ),
            UnalignedSpeech(
                start_ms=1_985_346,
                end_ms=1_985_694,
                reason="AlignmentInfeasible: 17 frames cannot emit 16 tokens",
            ),
        ),
    )
    run = run_pipeline(FIXTURE, tmp_path / "work", media_id="fixture", transcript=with_gaps)

    payload = run.to_dict()
    assert payload["speech_without_transcription_ms"] == 664, (
        "the report has to total the speech it does not contain, or 664 ms of Kurdish vanishes "
        "into a run that looks finished"
    )
    assert [gap["duration_ms"] for gap in payload["transcript_gaps"]] == [316, 348]
    assert [gap["start_ms"] for gap in payload["transcript_gaps"]] == [226_754, 1_985_346]
    assert "AlignmentInfeasible" in payload["transcript_gaps"][0]["reason"], (
        "a gap with no reason is indistinguishable from silence that was never there"
    )


@needs_ffmpeg
def test_a_run_with_nothing_missing_reports_zero_rather_than_omitting_the_key(
    tmp_path: Path,
) -> None:
    """The control. A report that only mentions gaps when there are some makes their absence
    unreadable — the operator cannot tell "nothing was dropped" from "this build does not check".

    It is also what would let the test above pass while the field stayed empty on every real run.
    """
    run = run_pipeline(FIXTURE, tmp_path / "work", media_id="fixture", transcript=a_transcript())

    payload = run.to_dict()
    assert payload["transcript_gaps"] == []
    assert payload["speech_without_transcription_ms"] == 0
    assert run.transcript_gaps == ()


# --- D-146: a stage that ran reported nothing about itself -------------------------------------


def _seven_candidates() -> tuple[MergedCandidate, ...]:
    """The shape the real 38-minute run produced: seven survivors, all from Path B."""
    return tuple(
        MergedCandidate(
            candidate_id=f"c{index}",
            media_id="zar38final",
            in_ms=index * 1_000,
            out_ms=index * 1_000 + 900,
            discovery_path=DiscoveryPath.VISUAL,
            sources=(f"c{index}",),
            verbal_rank=None,
            visual_rank=index,
            verbal_score=None,
            visual_score=0.5,
            sv6d=None,
        )
        for index in range(7)
    )


def test_a_discovery_that_ran_says_so_in_its_own_field() -> None:
    """`discovery` holds only a `StageSkipped` or `None`, and `None` was how success was written.

    Measured on the real 38-minute run: `discovery: null` in the emitted report alongside **7**
    merged candidates, with "discovery" absent from `skipped` as well. A reader checking that field
    could not tell "Stage 3 produced seven candidates" from "Stage 3 was never attempted" without
    cross-referencing another key. This module's §1 is fail visible, not silent. D-146.
    """
    run = PipelineRun(
        media_id="zar38final", source="x", work_dir="w", candidates=_seven_candidates()
    )
    reported = run.to_dict()["discovery"]

    assert reported is not None, "a stage that ran must not report null"
    assert reported["skipped"] is False
    assert reported["candidates"] == 7
    assert reported["by_path"] == {"visual": 7}, (
        "§8.2 partitions on discovery_path, so the split is what a reader needs — not a bare 'ran'"
    )


def test_a_stage_nobody_attempted_still_reads_as_unknown() -> None:
    """The control. Emitting a positive record unconditionally would satisfy the test above and
    claim Stage 3 ran on every run that never reached it — the same falsehood in the other
    direction.
    """
    run = PipelineRun(media_id="m", source="x", work_dir="w")
    assert run.to_dict()["discovery"] is None
    assert run.to_dict()["editorial"] is None


def test_a_named_skip_still_wins_over_the_positive_record() -> None:
    """The other control: an explicit refusal must never be overwritten by an inferred success."""
    skip = StageSkipped(
        stage="discovery", reason="no Stage 3 producer was enabled", blocked_by=("x",)
    )
    run = PipelineRun(
        media_id="m",
        source="x",
        work_dir="w",
        discovery=skip,
        candidates=_seven_candidates(),
    )
    reported = run.to_dict()["discovery"]
    assert reported["skipped"] is True
    assert reported["blocked_by"] == ["x"]


# --- D-153: §5's rejection set had a type, validation, tests and no producer -------------------


def _a_stub_judge() -> Any:
    """Stage 4 without Gemini. `BLOCKED.md` #3 is the real judge; this only lets Stage 4 run."""

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: Any) -> JudgeVerdict:
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    return Judge()


@needs_ffmpeg
def test_every_candidate_a_decision_ruled_out_is_recorded_with_its_reason_and_path(
    tmp_path: Path,
) -> None:
    """§5: "Rejection is a first-class outcome … that set is your only measure of recall."

    `RejectedCandidate` carried that requirement — with validation, `to_dict`/`from_dict` and its
    own tests — and **nothing in `src/` ever constructed one**. Measured on the real 38-minute
    run, Stage 3 produced 7 candidates, 1 was chosen and the other 6 left no trace at all.
    """
    from hawedit.discovery import Candidate

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="rejects",
        transcript=a_transcript("rejects"),
        discover=lambda _n: [
            Candidate("best", "rejects", 2_000, 4_100, DiscoveryPath.VERBAL, 1, 0.99),
            Candidate("early", "rejects", 0, 1_700, DiscoveryPath.VERBAL, 2, 0.10),
            Candidate("silent", "rejects", 1_700, 1_950, DiscoveryPath.VERBAL, 3, 0.80),
        ],
        judge=_a_stub_judge(),
    )

    assert len(run.candidates) == 3
    assert len(run.rejected) == 2, run.rejected
    assert {r.reject_reason for r in run.rejected}, "a rejection with no reason measures nothing"
    # The chosen survivor is never in the set it survived.
    chosen = (2_000, 4_100)
    assert all((r.in_ms, r.out_ms) != chosen for r in run.rejected), run.rejected
    # The path that found it, because §8.2 measures Recall@20 per discovery path.
    assert {(r.in_ms, r.discovery_path) for r in run.rejected} == {
        (0, DiscoveryPath.VERBAL),
        (1_700, DiscoveryPath.VERBAL),
    }
    assert run.to_dict()["rejected_by_path"] == {"verbal": 2}


@needs_ffmpeg
def test_the_reason_recorded_is_the_reason_the_code_acted_on(tmp_path: Path) -> None:
    """A generic reason on every rejection would satisfy the test above and measure nothing.

    The fixture's two sentences run 100..1700 and 2000..4100 ms, so a candidate at 1700..1950
    contains neither — it was ruled out by eligibility, not by rank, and the record has to say
    which. `_complete_sentences_within` is shared with the selector so the two cannot drift.
    """
    from hawedit.discovery import Candidate

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="reasons",
        transcript=a_transcript("reasons"),
        discover=lambda _n: [
            Candidate("best", "reasons", 2_000, 4_100, DiscoveryPath.VERBAL, 1, 0.99),
            Candidate("early", "reasons", 0, 1_700, DiscoveryPath.VERBAL, 2, 0.10),
            Candidate("silent", "reasons", 1_700, 1_950, DiscoveryPath.VERBAL, 3, 0.80),
        ],
        judge=_a_stub_judge(),
    )

    reasons = {r.in_ms: r.reject_reason for r in run.rejected}
    assert "no complete sentence" in reasons[1_700], reasons
    assert "out-ranked" in reasons[0], reasons
    assert reasons[0] != reasons[1_700], "one reason for every rejection is not a reason"


@needs_ffmpeg
def test_a_run_that_chose_nothing_rejects_nothing(tmp_path: Path) -> None:
    """The control. Recording every candidate but one as rejected passes the tests above and is
    false whenever no decision was ever made — it would put candidates in §8.2's rejection
    column that nothing ruled out."""
    from hawedit.discovery import Candidate

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="undecided",
        transcript=a_transcript("undecided"),
        discover=lambda _n: [
            Candidate("a", "undecided", 0, 1_700, DiscoveryPath.VERBAL, 1, 0.9),
            Candidate("b", "undecided", 2_000, 4_100, DiscoveryPath.VERBAL, 2, 0.8),
        ],
    )
    assert len(run.candidates) == 2, "Stage 3 still ran"
    assert run.rejected == (), "no judge, no selection — nothing chose, so nothing was rejected"


def test_the_rejection_split_names_every_path_that_found_a_candidate() -> None:
    """A path missing from the split cannot be told apart from a path that was never run, and
    "if Path B never surfaces a winner Path A missed, collapse it" is decided on this table."""
    from hawedit.clip import RejectedCandidate

    run = PipelineRun(
        media_id="zar38final",
        source="x",
        work_dir="w",
        candidates=_seven_candidates(),
        rejected=(
            RejectedCandidate(
                media_id="zar38final",
                in_ms=0,
                out_ms=900,
                discovery_path=DiscoveryPath.VISUAL,
                reject_reason="out-ranked by survivor c3",
            ),
        ),
    )
    payload = run.to_dict()
    assert payload["rejected_by_path"] == {"visual": 1}
    assert payload["rejected"][0]["reject_reason"] == "out-ranked by survivor c3"

    quiet = PipelineRun(media_id="m", source="x", work_dir="w", candidates=_seven_candidates())
    assert quiet.to_dict()["rejected"] == []
    assert quiet.to_dict()["rejected_by_path"] == {"visual": 0}, (
        "an absent path reads as a path that never ran; zero is the readable answer (D-110)"
    )
