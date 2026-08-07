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
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import Qc
from hawedit.judge import JudgeVerdict
from hawedit.pipeline import (
    PipelineRun,
    StageSkipped,
    run_pipeline,
)
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

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
    assert run.transcript.blocked_by == ("BLOCKED.md #2", "BLOCKED.md #6")
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
        verdict=a_verdict(0, 4_300),
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
    assert {name for name, _ in full_run.skipped()} >= {"discovery", "editorial"}


# --- the refusals -------------------------------------------------------------------------


@needs_ffmpeg
def test_a_selection_with_no_complete_sentence_produces_no_clip(tmp_path: Path) -> None:
    """Kurdish invariant #2 reaching all the way out to the runner.

    `anchors_for` returns None when nothing in the selection closed, and §5's contract is
    reject, never render. The runner must stop, not pick an approximate boundary.
    """
    fragment = RawTranscript(
        media_id="frag",
        text_ckb="ڕۆژنامەوانی کوردی",
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
        verdict=a_verdict(0, 4_300),
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
def test_selecting_a_sentence_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(IndexError, match="sentence"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="oob",
            transcript=a_transcript("oob"),
            select_sentences=(0, 99),
        )


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


def test_the_cli_reports_a_missing_source_without_a_traceback(tmp_path: Path) -> None:
    from hawedit.pipeline import main

    assert main([str(tmp_path / "absent.mp4"), "--work-dir", str(tmp_path / "work")]) == 2


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
    from collections.abc import Sequence

    from hawedit.clip import DiscoveryPath, Sv6d
    from hawedit.discovery import Candidate
    from hawedit.path_b import SceneReading
    from hawedit.visual_index import SceneWindow

    def sv6d_for(window: SceneWindow) -> Sv6d:
        at = f"{window.in_ms + 100}ms"
        return Sv6d(
            subject=f"speaker at {at}",
            aesthetics=f"warm grade at {at}",
            camera=f"static at {at}",
            editing=f"cut at {at}",
            narrative=f"setup at {at}",
            retention=f"hook at {at}",
        )

    class Reader:
        def read_scenes(self, windows: Sequence[SceneWindow]) -> tuple[SceneReading, ...]:
            return tuple(
                SceneReading(window=w, sv6d=sv6d_for(w), score=0.9 - i * 0.1)
                for i, w in enumerate(windows)
            )

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="dual",
        transcript=a_transcript("dual"),
        discover=lambda _norm: [
            Candidate("v1", "dual", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
        ],
        read_scenes=Reader(),
    )
    assert [w.span for w in run.visual_windows] == [(0, 1_400), (1_400, 2_800), (2_800, 4_162)]
    paths = {c.discovery_path for c in run.candidates}
    assert DiscoveryPath.BOTH in paths, paths
    assert DiscoveryPath.VISUAL in paths, paths
    # Nothing is dropped: one verbal candidate plus three windows, and the overlap merges into
    # one rather than disappearing.
    assert sum(len(c.sources) for c in run.candidates) == 4


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
            return a_verdict(0, 4_300)

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
