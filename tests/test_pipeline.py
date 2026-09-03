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

import builtins
import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from hawedit.asr import CanonicalTranscriptProducer
from hawedit.captions import find_ffmpeg
from hawedit.clip import (
    MAX_CANDIDATE_SPAN_MS,
    MIN_CANDIDATE_SPAN_MS,
    DiscoveryPath,
    Qc,
    QcRecord,
)
from hawedit.diarization import Segment
from hawedit.discovery import Candidate, MergedCandidate
from hawedit.escalation import DEFAULT_DISAGREEMENT_CER
from hawedit.ingest import DiarizationUnavailable, IngestError
from hawedit.judge import MAX_PERSISTED_VERDICT_BYTES, JudgeRequest, JudgeVerdict
from hawedit.pipeline import (
    DEFAULT_JUDGE_TOP_N,
    MAX_INTERNAL_SILENCE_MS,
    PipelineRun,
    StageSkipped,
    _automatic_sentence_selection,
    _build_and_run,
    _grown_sentence_run,
    _judgeable_plans,
    _nothing_fits_a_candidate,
    _print_report,
    _rejected_candidates,
    _run_span_ms,
    _sentence_run_for_candidate,
    assert_devices_available,
    build_parser,
    build_visual_composer,
    dead_air_flags,
    main,
    run_pipeline,
)
from hawedit.render import Reframe
from hawedit.sentences import Sentence
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    UnalignedSpeech,
    Word,
)
from hawedit.visual_index import MAX_FRAMES_PER_WINDOW

ROOT = Path(__file__).resolve().parents[1]


FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

FIXTURE_RENDER_S0_1_SHA256 = "f4c4ba3c8bb540762eaa182cecb319e52267c8ce4e1b7743647efb3de11492e0"
FIXTURE_RENDER_S0_SHA256 = "373fe39d308e042f56014ec0544d34259689e62b9681148b591bd0da12df9e11"
NTSC30_RENDER_SHA256 = "5864ac268634d8845d5cb383741da6258694c1d032708d70c39ee6a9445222f5"
NTSC60_RENDER_SHA256 = "a66829ceb0b199c7bcfe1b431a28b1559015d926cf4c8e2ab6a463e954ffbdca"
SPEAKER_TRACKED_RENDER_SHA256 = "6ceba45fade2c32e7b546e4f4c94f760fdc2827e315a075061cc6b4d97e50ae1"
SPEAKER_AMBIGUOUS_RENDER_SHA256 = "6ceba45fade2c32e7b546e4f4c94f760fdc2827e315a075061cc6b4d97e50ae1"


def _test_qc(
    auto_pass: bool = True,
    flags: tuple[str, ...] = (),
    reviewed_sha256: str = FIXTURE_RENDER_S0_1_SHA256,
) -> Qc:
    return Qc(
        auto_pass=auto_pass,
        flags=flags,
        human_reviewed=True,
        reviewed_by="Hawa",
        reviewed_at="2026-09-02T19:00:00Z",
        reviewed_sha256=reviewed_sha256,
    )


needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

# Two complete Kurdish sentences whose timings sit inside the 4.16 s fixture, matching the two
# utterances Stage 0's VAD actually finds in it.


WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def a_transcript(
    media_id: str = "fixture", *, media_sha256: str | None = FIXTURE_SHA256
) -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=media_sha256,
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


class _MeasuredDiarizer:
    def diarize(self, audio: Path) -> tuple[Segment, ...]:
        assert audio.name == "audio.wav"
        return (
            Segment(0, 1_950, "SPEAKER_00"),
            Segment(1_950, 4_162, "SPEAKER_01"),
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
    assert {"diarization", "transcript", "visual_index", "discovery", "editorial"} <= skipped
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


@needs_ffmpeg
def test_an_enabled_diarizer_records_a_measured_success(tmp_path: Path) -> None:
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="diarized",
        transcript=a_transcript("diarized"),
        diarizer=_MeasuredDiarizer(),
    )
    assert not isinstance(run.ingest, StageSkipped)
    assert run.ingest is not None
    assert run.ingest.diarization == (
        Segment(0, 1_950, "SPEAKER_00"),
        Segment(1_950, 4_162, "SPEAKER_01"),
    )
    assert run.diarization is None
    assert run.to_dict()["diarization"] == {
        "skipped": False,
        "stage": "diarization",
        "turns": 2,
        "speakers": 2,
    }


@needs_ffmpeg
def test_diarizer_operational_failure_retains_base_ingest_and_continues(tmp_path: Path) -> None:
    class FailingDiarizer:
        def diarize(self, audio: Path) -> tuple[Segment, ...]:
            raise DiarizationUnavailable("gated model is unavailable")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="diarizer-failed",
        transcript=a_transcript("diarizer-failed"),
        diarizer=FailingDiarizer(),
    )
    assert not isinstance(run.ingest, StageSkipped)
    assert run.ingest is not None and run.ingest.diarization is None
    assert isinstance(run.diarization, StageSkipped)
    assert "gated model is unavailable" in run.diarization.reason
    assert run.sentences, "independent transcript segmentation must still run"
    assert run.to_dict()["diarization"]["skipped"] is True


@needs_ffmpeg
def test_stage_5_fuses_the_speaker_turn_containing_the_selected_anchor(tmp_path: Path) -> None:
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="speaker-boundary",
        transcript=a_transcript("speaker-boundary"),
        diarizer=_MeasuredDiarizer(),
        select_sentences=(0,),
    )
    assert run.clip is not None
    assert run.clip.boundary.final_out_ms == 1_950
    assert run.clip.boundary.out_extended_by == "speaker_turn_end"


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
        qc=_test_qc(True),
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
    # This asserted `== 1` until D-134, which is the defect written down as an expectation: a
    # one-document index carries a single idf value and returns the whole media as its only
    # window. The count is now the sentence count, and it must be more than one or §2's text half
    # cannot order anything.
    assert payload["index"]["document_count"] == len(full_run.sentences)
    assert payload["index"]["document_count"] > 1
    # §3 Stage 1's routing decision is in the artifact, always — an empty `segments` list means
    # nothing needs the validator, which must be distinguishable from the rule never running
    # (D-135; the policy had no caller in `src/` at all before it).
    escalation = payload["escalation"]
    assert escalation["escalated"] == len(escalation["segments"])
    assert escalation["disagreement_threshold_cer"] == DEFAULT_DISAGREEMENT_CER
    # Which trigger fired has to be readable: measured on the real 38-minute run, 176 of the 312
    # escalations came from disagreement alone, and that half rests on an unconditioned CTC decode
    # (BLOCKED #19). A bare total would read as §3's intended routing.
    by_trigger = escalation["by_trigger"]
    assert set(by_trigger) == {"quartile_only", "disagreement_only", "both"}
    assert sum(by_trigger.values()) == escalation["escalated"]
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
        media_sha256=FIXTURE_SHA256,
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
def test_a_legacy_unbound_supplied_transcript_is_refused_before_downstream_work(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="has no source-media SHA-256"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            transcript=a_transcript(media_sha256=None),
            media_id="fixture",
        )


@needs_ffmpeg
def test_same_media_id_cannot_bind_a_transcript_to_different_video_bytes(tmp_path: Path) -> None:
    other = tmp_path / "other" / FIXTURE.name
    other.parent.mkdir()
    shutil.copyfile(FIXTURE, other)
    with other.open("ab") as stream:
        stream.write(b"different-source-bytes")

    assert other.stem == FIXTURE.stem
    assert hashlib.sha256(other.read_bytes()).hexdigest() != FIXTURE_SHA256
    with pytest.raises(ValueError, match="was created for source media"):
        run_pipeline(
            other,
            tmp_path / "work",
            transcript=a_transcript(FIXTURE.stem),
            media_id=FIXTURE.stem,
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
        media_sha256=FIXTURE_SHA256,
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
        media_sha256=FIXTURE_SHA256,
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


@needs_ffmpeg
def test_boundary_extension_absorbs_fully_enclosed_sentence(tmp_path: Path) -> None:
    """Task T4.8 / AC-1: complete sentence fully inside extended boundary is absorbed."""
    transcript = RawTranscript(
        media_id="absorbed",
        text_ckb="یەکەم. بەڵێ.",
        words=(
            Word(w="یەکەم.", start_ms=100, end_ms=1_400, conf=0.9),
            Word(w="بەڵێ.", start_ms=1_450, end_ms=1_550, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )
    # 200 ms tail after 1400 ms reaches 1600 ms, fully enclosing "بەڵێ." (1450..1550 ms)
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="absorbed",
        transcript=transcript,
        select_sentences=(0,),
    )
    # The boundary should not be skipped; "بەڵێ." should be absorbed into clip words
    assert not isinstance(run.boundary, StageSkipped)
    if run.clip is not None:
        words = [w.w for w in run.clip.transcript.words]
        assert "بەڵێ." in words
        assert "یەکەم." in words


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


def test_the_cli_reports_malformed_transcript_json_without_a_traceback(tmp_path: Path) -> None:
    from hawedit.pipeline import main

    source = tmp_path / "source.mp4"
    source.touch()
    transcript = tmp_path / "transcript.json"
    transcript.write_text("{}", encoding="utf-8")
    assert main([str(source), "--transcript", str(transcript)]) == 2


def test_the_cli_refuses_non_finite_stage1_evidence_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hawedit.pipeline import main

    source = tmp_path / "source.mp4"
    source.touch()
    transcript = tmp_path / "transcript.json"
    document = json.loads(a_transcript("source", media_sha256=None).to_json())
    document["segment_confidence"] = [{"start_ms": 0, "end_ms": 1, "mean_logprob": float("nan")}]
    transcript.write_text(json.dumps(document), encoding="utf-8")

    assert main([str(source), "--transcript", str(transcript)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "non-standard JSON numeric constant" in captured.err
    assert "Traceback" not in captured.err


# `main`'s except tuple has ten members. Measured by deleting each and running this file plus
# tests/test_cli.py: FileNotFoundError, KeyError and ValueError were held; FileExistsError,
# RuntimeError and TypeError were not.
#
# The other four — CredentialError, GeminiUnavailable, IngestError, RawTranscriptImmutable — all
# subclass RuntimeError, which is itself in the tuple, so deleting them cannot change behaviour
# and no test can hold them. They are listed for the reader, not for the interpreter. Removing
# RuntimeError is the one that bites: every refusal `reframe.py` raises for a missing OpenCV, an
# unloadable detector or an unopenable source is a bare RuntimeError, and would reach the
# operator as a traceback with exit 1 — which `main`'s own contract reserves for an incomplete
# run, not a refused one.


@pytest.mark.parametrize(
    "raised",
    [FileExistsError, FileNotFoundError, KeyError, RuntimeError, TypeError, ValueError],
)
def test_the_cli_maps_every_expected_failure_to_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    raised: type[Exception],
) -> None:
    """A refusal has to arrive as `✗ <message>` on stderr with exit 2.

    Exit 1 means "the run was incomplete" — a shell script driving this distinguishes the two,
    and an uncaught exception exits 1 with a traceback, so a failure that escapes the tuple is
    reported as the wrong kind of outcome as well as the wrong shape.

    The raised message is asserted in stderr on purpose: without it this test would pass on any
    earlier refusal that also exits 2, and prove nothing about the tuple.
    """
    from hawedit import pipeline as module

    def boom(*args: object, **kwargs: object) -> PipelineRun:
        raise raised("the run refused for a reason the tuple must carry")

    monkeypatch.setattr(module, "run_pipeline", boom)
    source = tmp_path / "source.mp4"
    source.touch()

    assert module.main([str(source), "--work-dir", str(tmp_path / "work")]) == 2
    captured = capsys.readouterr()
    assert "the run refused for a reason the tuple must carry" in captured.err
    assert captured.err.startswith("✗")


# `test_the_cli_refuses_flags_whose_prerequisites_are_absent` stood here and asserted
# `main([source, *flags]) == 2` for three flag combinations. Exit 2 is the code for *every*
# exception `_run_from_args` catches, so it passed whether the refusal fired or not: measured,
# with `--sentences requires --transcript or --omni-asr` deleted outright, the same call still
# returned 2 — because `source.mp4` was an empty `touch()`ed file and ffmpeg said *"moov atom not
# found"*. It was asserting that an empty MP4 breaks Stage 0. Replaced below by a table that
# asserts *which* refusal fired, covering those three and ten more. D-149.


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
                "--qc-record",
                json.dumps(
                    {
                        "reviewer": "Hawa",
                        "reviewed_at": "2026-09-02T19:00:00Z",
                        "mp4_sha256": "0" * 64,
                        "seconds_watched": 57.0,
                        "verdict": "pass",
                    }
                ),
            ]
        )
        == 1
    )
    assert isinstance(captured["verdict"], JudgeVerdict)
    assert captured["qc"] == Qc(
        auto_pass=False,
        flags=(),
        human_reviewed=True,
        reviewed_by="Hawa",
        reviewed_at="2026-09-02T19:00:00Z",
        reviewed_sha256="0" * 64,
    )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (', "hook_score": 0.1', "duplicate JSON key"),
        (', "unexpected": true', "invalid fields"),
        (', "future_score": NaN', "non-standard JSON numeric constant"),
    ],
)
def test_cli_refuses_ambiguous_persisted_verdict_json_without_a_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: str,
    message: str,
) -> None:
    source = tmp_path / "source.mp4"
    source.touch()
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(a_transcript("source").to_json(), encoding="utf-8")
    verdict = json.dumps(a_verdict(0, 4_300).to_dict(), ensure_ascii=False)
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(verdict[:-1] + extra + "}", encoding="utf-8")

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
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_cli_bounds_persisted_verdict_before_parsing_or_media_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.mp4"
    source.touch()
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(a_transcript("source").to_json(), encoding="utf-8")
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_bytes(b"{" + b" " * MAX_PERSISTED_VERDICT_BYTES + b"}")

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
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "exceeds 1048576 bytes" in captured.err
    assert "Traceback" not in captured.err
    assert "ffmpeg" not in captured.err
    assert captured.out == ""


def test_cli_refuses_non_utf8_persisted_verdict_without_media_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.mp4"
    source.touch()
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(a_transcript("source").to_json(), encoding="utf-8")
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_bytes(b"\xff\xfe")

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
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "not valid UTF-8" in captured.err
    assert "Traceback" not in captured.err
    assert "ffmpeg" not in captured.err
    assert captured.out == ""


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
        # An explicit query, because without one Stage 2 now refuses before the composer is
        # reached (D-117) and this test is about the composer's own refusal.
        visual_query="ڕۆژنامەوانی",
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert isinstance(run.visual_index, StageSkipped)
    assert "too short" in run.visual_index.reason
    assert run.candidates == ()


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
        source_sha256="a" * 64,
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
    assert json.loads(editing_json.read_text(encoding="utf-8"))["media_sha256"] == FIXTURE_SHA256


@needs_ffmpeg
def test_distinct_selections_do_not_overwrite_each_others_deliveries(tmp_path: Path) -> None:
    work = tmp_path / "work"
    first = run_pipeline(
        FIXTURE,
        work,
        media_id="variants",
        transcript=a_transcript("variants"),
        select_sentences=(0,),
        qc=_test_qc(False, reviewed_sha256=FIXTURE_RENDER_S0_SHA256),
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
        qc=_test_qc(False, reviewed_sha256=FIXTURE_RENDER_S0_1_SHA256),
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
            qc=_test_qc(False, reviewed_sha256=FIXTURE_RENDER_S0_SHA256),
            verdict=a_verdict(100, 1_700),
        )


# --- composed model stages -----------------------------------------------------------------


@needs_ffmpeg
def test_runner_invokes_canonical_asr_when_no_transcript_is_supplied(tmp_path: Path) -> None:
    seen: list[tuple[str, Path, int]] = []

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
            seen.append((media_id, audio_path, len(segments)))
            return a_transcript(media_id)

    run = run_pipeline(FIXTURE, tmp_path / "work", media_id="asr", asr=CanonicalAsr())
    assert seen and seen[0][0] == "asr" and seen[0][1].exists() and seen[0][2] > 0
    assert not isinstance(run.transcript, StageSkipped)


@needs_ffmpeg
def test_automatic_selection_uses_complete_sentences_inside_the_best_survivor(
    tmp_path: Path,
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

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
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every candidate
        # in it on length alone. Naming the floor says "this source is a toy" at the call site.
        min_clip_ms=4_000,
    )
    assert run.clip is not None
    # `s0-1`, not `s0-0`: the candidate is 1.7 s and D-254's minimum is 30 s, so T3 grows the
    # seed outward on complete sentence boundaries. This fixture holds two sentences and the
    # grown run takes both — it still cannot reach 30 s, and growth returns what it reached.
    # The property under test is unchanged: the selection is complete sentences, whole.
    assert run.clip.clip_id == "automatic-s0-1"
    assert tuple(word.w for word in run.clip.transcript.words) == tuple(word.w for word in WORDS)


@needs_ffmpeg
def test_multimodal_judge_receives_real_source_keyframes_from_runner(tmp_path: Path) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

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
def test_visual_retrieval_refuses_source_changed_after_stage_zero(tmp_path: Path) -> None:
    from hawedit.discovery import Candidate
    from hawedit.visual_pipeline import VisualDiscoveryResult

    source = tmp_path / "visual-drift.mp4"
    source.write_bytes(FIXTURE.read_bytes())
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    class MutatingComposer:
        def discover(
            self,
            source_path: Path,
            windows: Sequence[Any],
            query: str,
            work_dir: Path,
            *,
            media_id: str,
            ffmpeg: Path | None = None,
        ) -> VisualDiscoveryResult:
            with source_path.open("ab") as stream:
                stream.write(b"changed-during-visual-retrieval")
            return VisualDiscoveryResult(
                media_id,
                query,
                len(windows),
                len(windows),
                (),
                (Candidate("scene", media_id, 0, 1_700, DiscoveryPath.VISUAL, 1, 0.8),),
            )

    with pytest.raises(ValueError, match="Path B visual retrieval completion"):
        run_pipeline(
            source,
            tmp_path / "work",
            media_id="visual-drift",
            transcript=a_transcript("visual-drift", media_sha256=source_sha256),
            visual_composer=MutatingComposer(),  # type: ignore[arg-type]
            visual_query="ڕۆژنامەوانی",
        )


@needs_ffmpeg
def test_render_refuses_and_discards_if_source_changes_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.render import render_clip as real_render_clip

    source = tmp_path / "render-drift.mp4"
    source.write_bytes(FIXTURE.read_bytes())
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    def mutate_after_render(*args: Any, **kwargs: Any) -> Any:
        rendered = real_render_clip(*args, **kwargs)
        with source.open("ab") as stream:
            stream.write(b"changed-after-render")
        return rendered

    monkeypatch.setattr("hawedit.pipeline.render_clip", mutate_after_render)
    work = tmp_path / "work"
    run = run_pipeline(
        source,
        work,
        media_id="render-drift",
        transcript=a_transcript("render-drift", media_sha256=source_sha256),
        select_sentences=(0,),
        qc=_test_qc(True),
        verdict=replace(a_verdict(100, 1_700), candidate_id="render-drift-0"),
    )

    assert isinstance(run.render, StageSkipped)
    assert "source media changed" in run.render.reason
    assert not (work / "render-drift-s0-0").exists()
    assert not tuple(work.glob(".render-drift-s0-0.*.staging"))


@needs_ffmpeg
def test_timelens_grounding_is_composed_into_boundary_fusion(tmp_path: Path) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
    from hawedit.timelens import VisualEvidenceInterval
    from hawedit.visual_index import SceneWindow

    seen: list[SceneWindow] = []

    class Grounder:
        def ground_all(
            self, windows: Sequence[SceneWindow], query: str
        ) -> tuple[VisualEvidenceInterval, ...]:
            seen.extend(windows)
            assert query
            return (VisualEvidenceInterval("grounded", 1_500, 1_950, "visible reaction"),)

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
    assert run.clip is not None
    assert run.clip.boundary.final_out_ms == 1_950
    assert run.clip.boundary.out_extended_by == "timelens_interval_end"


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
def test_speaker_tracking_receives_only_overlapping_turns_and_labels_the_artifact(
    tmp_path: Path,
) -> None:
    from hawedit.reframe import FocusPoint, SpeakerFocusPoint
    from hawedit.render import Reframe

    class SpeakerTracker:
        def track_speakers(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            turns: Sequence[Segment],
        ) -> tuple[SpeakerFocusPoint, ...]:
            assert source == FIXTURE
            assert (in_ms, out_ms) == (0, 1_950)
            assert turns == (Segment(0, 1_950, "SPEAKER_00"),)
            return (
                SpeakerFocusPoint(100, 120, "SPEAKER_00"),
                SpeakerFocusPoint(1_700, 520, "SPEAKER_00"),
            )

    class FaceFallback:
        def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]:
            pytest.fail("validated speaker evidence must win before the face-only fallback")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="speaker-tracked",
        transcript=a_transcript("speaker-tracked"),
        diarizer=_MeasuredDiarizer(),
        select_sentences=(0,),
        verdict=replace(a_verdict(100, 1_700), candidate_id="speaker-tracked-0"),
        qc=_test_qc(True, reviewed_sha256=SPEAKER_TRACKED_RENDER_SHA256),
        speaker_tracker=SpeakerTracker(),
        subject_tracker=FaceFallback(),
    )
    assert run.clip is not None and run.clip.output is not None
    assert run.clip.output.crop_target == "speaker_face"
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    assert run.render.reframe is Reframe.SPEAKER_TRACKED


@needs_ffmpeg
def test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance(
    tmp_path: Path,
) -> None:
    from hawedit.reframe import FocusPoint, SpeakerFocusPoint
    from hawedit.render import Reframe

    class AmbiguousSpeakerTracker:
        def track_speakers(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            turns: Sequence[Segment],
        ) -> tuple[SpeakerFocusPoint, ...]:
            return ()

    class FaceFallback:
        def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]:
            return (FocusPoint(in_ms, 120), FocusPoint(out_ms - 1, 520))

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="speaker-ambiguous",
        transcript=a_transcript("speaker-ambiguous"),
        diarizer=_MeasuredDiarizer(),
        select_sentences=(0,),
        verdict=replace(a_verdict(100, 1_700), candidate_id="speaker-ambiguous-0"),
        qc=_test_qc(True, reviewed_sha256=SPEAKER_AMBIGUOUS_RENDER_SHA256),
        speaker_tracker=AmbiguousSpeakerTracker(),
        subject_tracker=FaceFallback(),
    )
    assert run.clip is not None and run.clip.output is not None
    assert run.clip.output.crop_target == "face_tracked"
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    assert run.render.reframe is Reframe.FACE_TRACKED


def test_requested_speaker_tracking_refuses_missing_diarization_without_calling_provider(
    tmp_path: Path,
) -> None:
    from hawedit.reframe import SpeakerFocusPoint

    class MustNotRun:
        def track_speakers(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            turns: Sequence[Segment],
        ) -> tuple[SpeakerFocusPoint, ...]:
            pytest.fail("speaker association cannot run without measured diarization")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="speaker-no-diarization",
        transcript=a_transcript("speaker-no-diarization"),
        select_sentences=(0,),
        verdict=replace(a_verdict(100, 1_700), candidate_id="speaker-no-diarization-0"),
        speaker_tracker=MustNotRun(),
    )
    assert isinstance(run.render, StageSkipped)
    assert "measured diarization" in run.render.reason
    assert run.clip is None


def test_requested_speaker_tracking_refuses_when_no_measured_turn_overlaps_the_clip(
    tmp_path: Path,
) -> None:
    from hawedit.reframe import SpeakerFocusPoint

    class NonOverlappingDiarizer:
        def diarize(self, audio: Path) -> tuple[Segment, ...]:
            assert audio.name == "audio.wav"
            return (Segment(2_800, 4_162, "SPEAKER_01"),)

    class MustNotRun:
        def track_speakers(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            turns: Sequence[Segment],
        ) -> tuple[SpeakerFocusPoint, ...]:
            pytest.fail("speaker association cannot run without an overlapping measured turn")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="speaker-no-overlap",
        transcript=a_transcript("speaker-no-overlap"),
        diarizer=NonOverlappingDiarizer(),
        select_sentences=(0,),
        verdict=replace(a_verdict(100, 1_700), candidate_id="speaker-no-overlap-0"),
        speaker_tracker=MustNotRun(),
    )
    assert isinstance(run.render, StageSkipped)
    assert "no measured diarization turn" in run.render.reason
    assert "overlapping the final clip" in run.render.reason
    assert run.clip is None


def test_invalid_or_failed_speaker_association_is_not_silently_treated_as_ambiguity(
    tmp_path: Path,
) -> None:
    from hawedit.reframe import FocusPoint, SpeakerFocusPoint

    class FaceFallback:
        def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]:
            pytest.fail("invalid or failed association is not an ambiguous empty result")

    class WrongSpeaker:
        def track_speakers(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            turns: Sequence[Segment],
        ) -> tuple[SpeakerFocusPoint, ...]:
            return (SpeakerFocusPoint(100, 320, "SPEAKER_01"),)

    class Broken:
        def track_speakers(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            turns: Sequence[Segment],
        ) -> tuple[SpeakerFocusPoint, ...]:
            raise RuntimeError("association backend unavailable")

    for media_id, tracker, detail in (
        ("speaker-invalid", WrongSpeaker(), "active speaker is 'SPEAKER_00'"),
        ("speaker-failed", Broken(), "association backend unavailable"),
    ):
        run = run_pipeline(
            FIXTURE,
            tmp_path / media_id,
            media_id=media_id,
            transcript=a_transcript(media_id),
            diarizer=_MeasuredDiarizer(),
            select_sentences=(0,),
            verdict=replace(a_verdict(100, 1_700), candidate_id=f"{media_id}-0"),
            speaker_tracker=tracker,
            subject_tracker=FaceFallback(),
        )
        assert isinstance(run.render, StageSkipped)
        assert detail in run.render.reason
        assert run.clip is None


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
        media_sha256=FIXTURE_SHA256,
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


def _existing_artifact(work_dir: Path, media_id: str, sentences: tuple[int, ...]) -> Path:
    """Plant a *finished* delivery, exactly as a completed run leaves it.

    Written through `ArtifactBundle`, the production writer, so the plant cannot drift from what
    a real run produces. It used to plant one file, and the guard used to refuse on one file -
    which read an abandoned attempt as a delivery and wedged the work directory of any run that
    was interrupted (D-146). What is refused is a delivery that *finished*, so that is what this
    plants.

    Ported from the flat writer across the readiness merge. The bundle makes the distinction
    structural rather than careful: staging is private and the set becomes visible only on
    publish, so an unfinished plant is not merely discouraged, it is unrepresentable.
    """
    from hawedit.artifact_bundle import ArtifactBundle
    from hawedit.pipeline import _clip_id

    work_dir.mkdir(parents=True, exist_ok=True)
    clip_id = _clip_id(media_id, sentences)
    bundle = ArtifactBundle.create(work_dir, clip_id)
    for suffix in ArtifactBundle.suffixes():
        bundle.write_text(suffix, "a previous run left this here")
    bundle.publish()
    return bundle.final_dir


def test_an_overwriting_run_refuses_before_the_billed_judge_call(tmp_path: Path) -> None:
    """The artifact of this fix is a request that never happened."""
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    work = tmp_path / "work"
    planted = _existing_artifact(work, "billed", (0,))

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

    assert str(planted) in str(raised.value)
    # The whole point. Not "it refused" — it refused without spending anything.
    assert calls == [], f"the billed judge ran {len(calls)} time(s) before the refusal"


def test_an_overwriting_auto_selected_run_also_refuses_before_the_judge(tmp_path: Path) -> None:
    """`--auto-select` picks its sentences after Stage 3, so it needs its own guard point.

    Without the second call site this run reaches the judge: the first guard sees an empty
    selection, returns, and nothing re-checks once auto-selection has named sentence 0.
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    work = tmp_path / "work"
    # Sentences 0 *and* 1: `--auto-select` grows a 1.7 s seed outward (T3), so the selection it
    # names is the whole fixture rather than sentence 0 alone. Planting the collision on the
    # selection the run actually makes is what keeps this a test of the guard.
    _existing_artifact(work, "autobilled", (0, 1))

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
            # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every candidate
            # in it on length alone. Naming the floor says "this source is a toy" at the call site.
            min_clip_ms=4_000,
        )

    assert calls == [], f"the billed judge ran {len(calls)} time(s) before the refusal"


def test_a_clean_work_directory_still_reaches_the_judge(tmp_path: Path) -> None:
    """The control. A guard that refused every run would pass both tests above.

    Same call, nothing planted: the judge must be reached exactly once, so the tests above
    are measuring the collision and not a pipeline that stopped working.
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

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
        qc=_test_qc(True, reviewed_sha256=FIXTURE_RENDER_S0_SHA256),
        verdict=a_verdict(100, 1_700),
    )
    assert run.render is not None and not isinstance(run.render, StageSkipped), run.render
    guarded = set(_delivery_artifact_paths(work, _clip_id("paths", (0,))))
    assert Path(run.render.path) in guarded, (
        f"the run wrote {run.render.path}, which the overwrite guard does not check"
    )


# =========================================================================================
# §2's delivery set is all-or-none
#
# The runner wrote the editing JSON, then the SRT, then *built* the EDL — and the EDL is the
# one that legitimately refuses. An NTSC 29.97 fps source needs SMPTE drop-frame timecode,
# which `build_edl` will not fake, so on ordinary broadcast footage the run left a playable
# captioned MP4, an ASS, a JSON and an SRT on disk with no EDL, reported the stage skipped,
# and anyone reading the work directory for deliverables had four fifths of a set that looked
# whole. Nothing in the sequence needed a file to exist before the next step. D-072.
#
# The fixture is 25 fps, which is EDL-safe — that is what makes the control below possible.
# =========================================================================================


_SIDECARS = (".json", ".srt", ".edl")


def _ntsc_copy(source: Path, dest: Path, rate: str = "30000/1001") -> Path:
    """A real NTSC transcode. `frame_rate` must read the requested exact fractional rate."""
    return _fractional_rate_copy(source, dest, rate)


def _sidecars_on_disk(work: Path, clip_id: str) -> list[str]:
    """The exact sidecars in one atomically published delivery bundle."""
    bundle = work / clip_id
    if not bundle.is_dir():
        return []
    return sorted(path.name for path in bundle.iterdir() if path.suffix in _SIDECARS)


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
        qc=_test_qc(True, reviewed_sha256=FIXTURE_RENDER_S0_SHA256),
        verdict=a_verdict(100, 1_700),
    )
    assert not isinstance(run.delivery, StageSkipped), run.delivery
    assert _sidecars_on_disk(work, "safe-s0-0") == [
        "safe-s0-0.edl",
        "safe-s0-0.json",
        "safe-s0-0.measured.json",
        "safe-s0-0.srt",
    ]


@needs_ffmpeg
def test_a_write_failing_partway_through_the_sidecars_leaves_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Building first fixes the refusal case; this covers the disk filling up mid-sequence.

    The JSON is written, the SRT write raises, and the JSON must not survive it.
    """
    from hawedit.artifact_bundle import ArtifactBundle, BundleError

    real_write_text = ArtifactBundle.write_text

    def failing_write_text(self: ArtifactBundle, suffix: str, payload: str) -> Path:
        if suffix == "srt":
            raise BundleError("no space left on device")
        return real_write_text(self, suffix, payload)

    monkeypatch.setattr(ArtifactBundle, "write_text", failing_write_text)

    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="nospace",
        transcript=a_transcript("nospace"),
        select_sentences=(0,),
        qc=_test_qc(True),
        verdict=a_verdict(100, 1_700),
    )
    assert isinstance(run.delivery, StageSkipped)
    assert "no space left" in run.delivery.reason
    assert _sidecars_on_disk(work, "nospace-s0-0") == []


@needs_ffmpeg
def test_reconciliation_failure_skips_delivery_and_discards_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clip failing Level C reconciliation is refused before publish:
    delivery is marked StageSkipped, the private staging directory is discarded,
    and no public bundle appears in the work directory. ADR D-263 / T1.2.
    """
    import hawedit.pipeline as pipeline_mod
    from hawedit.delivery import DeliveryRefused

    def refusing_reconcile(*args: object, **kwargs: object) -> None:
        raise DeliveryRefused(
            "geometry_mismatch",
            expected="1080x1920 vertical",
            measured="720x1280",
        )

    monkeypatch.setattr(pipeline_mod, "reconcile_delivery", refusing_reconcile)

    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="reconcile_refused",
        transcript=a_transcript("reconcile_refused"),
        select_sentences=(0,),
        qc=_test_qc(True),
        verdict=a_verdict(100, 1_700),
    )
    assert isinstance(run.delivery, StageSkipped)
    assert "geometry_mismatch" in run.delivery.reason
    assert _sidecars_on_disk(work, "reconcile_refused-s0-0") == []


def test_the_cli_defaults_put_each_visual_model_where_section_6_puts_it() -> None:
    """§6, VIDEO PHASE: `GPU 0 → VideoChat3-4B` and `GPU 1 → Embedding / Reranker / TimeLens2`.

    All three used to take `--visual-device`, so on hawapc01 they landed together on GPU 0 while
    GPU 1 held 1.3 GiB — and the real 38-minute run died with *"CUDA out of memory. Tried to
    allocate 21.83 GiB. GPU 0 has a total capacity of 23.99 GiB of which 3.59 GiB is free. Of the
    allocated memory 18.30 GiB is allocated by PyTorch."* Asserted on the parsed defaults, because
    a comment claiming §6 is not §6 being followed. D-105.
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
    """The wiring, not the flag. This is the test D-105 needed and did not have at first.

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


# --- D-108: the frame ceiling has to survive the trip from the CLI to the plan ----------------


@needs_ffmpeg
def test_the_frame_ceiling_reaches_the_planned_windows(tmp_path: Path) -> None:
    """Asserted on the windows the run reports, not on the argument it was handed.

    The D-108 audit found the planner tested and the *wiring* untested: replacing
    `max_frames=visual_max_frames` with `max_frames=MAX_FRAMES_PER_WINDOW` left the suite green.
    That is D-105's survivor one iteration earlier, in a new place — so this asserts the artifact.

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


# --- D-110: the report was silent about speech the transcript does not contain ----------------


@needs_ffmpeg
def test_the_report_says_which_speech_has_no_transcription(tmp_path: Path) -> None:
    """D-103 put the gaps in `transcript.raw.json`; the report shows the *normalized* transcript,
    which by design has no such field, so a run that dropped speech said nothing about it.

    Measured on the real 38-minute run: 2 of 547 regions, **664 ms** of Kurdish with no
    transcription, and the emitted report mentioned neither `unaligned` nor
    `segment_confidence`. This module's own §1 is "fail visible, not silent". D-110.
    """
    with_gaps = RawTranscript(
        media_id="fixture",
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
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


# --- D-111: a stage that ran reported nothing about itself -------------------------------------


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
    cross-referencing another key. This module's §1 is fail visible, not silent. D-111.
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


# --- D-116: §5's rejection set had a type, validation, tests and no producer -------------------


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
    overlaps neither — it was ruled out by eligibility, not by rank, and the record has to say
    which. The predicate is `_grown_sentence_run`, the one the selector acts on, so the reason
    in the artifact cannot drift from the decision that produced it (AC-7). It moved here when
    T3 made growth the thing eligibility is decided by; before that it was
    `_complete_sentences_within`, which is still shared but no longer what rules a candidate out.
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
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every candidate
        # in it on length alone. Naming the floor says "this source is a toy" at the call site.
        min_clip_ms=4_000,
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


# --- D-117: the retrieval query was the corpus ------------------------------------------------


@needs_ffmpeg
def test_stage_2_refuses_rather_than_retrieving_against_the_whole_transcript(
    tmp_path: Path,
) -> None:
    """The fallback query was `normalized.text_ckb` — the entire episode.

    Measured on hawapc01 with the real 38-minute media: embedding its 35,185-character
    transcript asks for **40.89 GiB** on a 23.99 GiB card and the run dies mid-Stage-2. Where it
    does fit, ranking every window against the whole episode orders nothing in particular. §3
    Stage 2 retrieves against a query; without one there is nothing to retrieve against.
    """
    asked: list[str] = []

    class Composer:
        def discover(self, *args: object, **kwargs: object) -> None:
            asked.append("called")
            raise AssertionError("the composer must not be reached without a query")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="noquery",
        transcript=a_transcript("noquery"),
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert asked == [], "no GPU work may start before the query is known to exist"
    assert isinstance(run.visual_index, StageSkipped)
    assert run.visual_index.blocked_by == ("a retrieval query",)
    assert "--visual-query" in run.visual_index.reason
    assert run.candidates == ()
    # The skip is named in the report, not merely absent from it.
    assert "visual_index" in {name for name, _ in run.skipped()}


@needs_ffmpeg
def test_an_explicit_query_still_reaches_the_composer(tmp_path: Path) -> None:
    """The control. Refusing whenever Path A found nothing would satisfy the test above and
    disable `--visual --visual-query` entirely, which is the one invocation that works today."""
    from hawedit.visual_index import SceneWindow
    from hawedit.visual_pipeline import VisualDiscoveryResult

    seen: list[str] = []

    class Composer:
        def discover(
            self,
            source: Path,
            windows: Sequence[SceneWindow],
            query: str,
            work_dir: Path,
            *,
            media_id: str,
            ffmpeg: Path | None = None,
        ) -> VisualDiscoveryResult:
            seen.append(query)
            return VisualDiscoveryResult(media_id, query, len(windows), len(windows), (), ())

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="explicit",
        transcript=a_transcript("explicit"),
        visual_query="هەولێر",
        visual_composer=Composer(),  # type: ignore[arg-type]
    )
    assert seen == ["هەولێر"], seen
    assert not isinstance(run.visual_index, StageSkipped), run.visual_index


@needs_ffmpeg
def test_a_verbal_anchor_still_supplies_the_query_it_always_did(tmp_path: Path) -> None:
    """The second control: the anchored query must be the candidate's slice, not the episode.

    A refusal that also dropped this path would pass the first test and delete the behaviour
    D-066 composed. The slice is short by construction — one candidate's transcript — which is
    why it never met the ceiling the whole transcript does.
    """
    from hawedit.discovery import Candidate
    from hawedit.visual_index import SceneWindow
    from hawedit.visual_pipeline import VisualDiscoveryResult

    seen: list[str] = []

    class Composer:
        def discover(
            self,
            source: Path,
            windows: Sequence[SceneWindow],
            query: str,
            work_dir: Path,
            *,
            media_id: str,
            ffmpeg: Path | None = None,
        ) -> VisualDiscoveryResult:
            seen.append(query)
            return VisualDiscoveryResult(media_id, query, len(windows), len(windows), (), ())

    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="anchored",
        transcript=a_transcript("anchored"),
        discover=lambda _n: [
            Candidate("best", "anchored", 2_000, 4_100, DiscoveryPath.VERBAL, 1, 0.9)
        ],
        visual_composer=Composer(),  # type: ignore[arg-type]
    )
    assert seen == ["لە هەولێر."], seen
    assert a_transcript("anchored").text_ckb not in seen, (
        "the whole transcript must never be the query again"
    )


# --- D-126: a text-only judge must not be charged for frames -----------------------------------


@needs_ffmpeg
def test_a_judge_that_does_not_want_keyframes_is_sent_none(tmp_path: Path) -> None:
    """The other half of `requires_keyframes`, which nothing held.

    M2.9's cell says the extraction is wired behind the judge's own flag "so a text-only judge is
    not charged for frames". Only the positive direction was tested, so making the gate
    unconditional — extracting and attaching frames for every judge — left the suite green. A
    text-only model billed for twenty inline images is the quiet half of the same defect.
    """
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    seen: list[JudgeRequest] = []

    class TextOnlyJudge:
        model_id = "gemini-2.5-pro"
        # No `requires_keyframes` at all — the attribute is read with a `False` default, and a
        # judge that never heard of it is the case that default exists for.

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            seen.append(request)
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="textonly",
        transcript=a_transcript("textonly"),
        discover=lambda _n: [
            Candidate("best", "textonly", 0, 1_700, DiscoveryPath.VERBAL, 1, 0.99)
        ],
        judge=TextOnlyJudge(),
    )
    assert len(seen) == 1
    assert seen[0].keyframes == (), (
        "a judge that did not ask for keyframes was sent them anyway — inline image bytes are "
        "billed, and §3 Stage 4's cost model counts them"
    )
    assert seen[0].text_ckb, "the text half of the request must still be there"


# --- what adversarial pass #16 found revertible (D-129) ---------------------------------


@pytest.fixture(scope="module")
def whole_run(tmp_path_factory: pytest.TempPathFactory) -> PipelineRun:
    """A run where **every** §3 stage produced something — the first in this suite.

    `complete` is what the CLI's exit code derives from (`return 0 if run.complete else 1`), and
    three of its eleven conjuncts were revertible: `not self.skipped()`,
    `bool(self.visual_windows)` and `bool(self.candidates)` could each become `True` with the
    whole suite green. Measured, the reason is that **nothing ever reached the True branch** —
    even `full_run` is incomplete, missing `candidates` and carrying `visual_index` and
    `discovery` skips, so no test could tell a conjunct from a no-op.

    Built through the real `run_pipeline` rather than by fabricating dataclasses, so it cannot
    drift from the product it describes.
    """
    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")
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
            return VisualDiscoveryResult(media_id, query, len(windows), len(windows), (), ())

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    return run_pipeline(
        FIXTURE,
        tmp_path_factory.mktemp("whole"),
        media_id="whole",
        transcript=a_transcript("whole"),
        diarizer=_MeasuredDiarizer(),
        select_sentences=(0, 1),
        qc=_test_qc(True),
        discover=lambda _n: [Candidate("best", "whole", 100, 4_100, DiscoveryPath.VERBAL, 1, 0.9)],
        visual_composer=Composer(),  # type: ignore[arg-type]
        judge=Judge(),
        visual_query="گرنگ",
    )


@needs_ffmpeg
def test_a_run_where_every_stage_produced_something_is_complete(whole_run: PipelineRun) -> None:
    """The control every test below rests on. Without a run that *is* complete, removing a
    requirement proves nothing — which is exactly why three conjuncts were revertible."""
    assert whole_run.skipped() == ()
    assert whole_run.complete is True


@needs_ffmpeg
def test_a_run_with_a_skipped_stage_is_never_complete(whole_run: PipelineRun) -> None:
    """`not self.skipped()` was revertible. The exit code follows `complete`, so a run that
    named a blocker and still exited 0 is the silent success this module's §1 forbids."""
    named = replace(
        whole_run,
        editorial=StageSkipped(
            stage="editorial", reason="no judge was supplied", blocked_by=("a judge",)
        ),
    )
    assert named.complete is False


@needs_ffmpeg
def test_a_run_with_no_visual_windows_is_never_complete(whole_run: PipelineRun) -> None:
    """Stage 2's visual half is arithmetic over Stage 0's cuts and runs on any real media, so an
    empty plan means the stage did not run — not that the media had nothing in it."""
    assert replace(whole_run, visual_windows=()).complete is False


@needs_ffmpeg
def test_a_run_with_no_candidates_is_never_complete(whole_run: PipelineRun) -> None:
    """§3 Stage 3 is the most important structural decision in the system; a run that produced
    no candidate did not perform it, whatever the other stages managed."""
    assert replace(whole_run, candidates=()).complete is False


# The three tests above cover three of `complete`'s eleven conjuncts. Measured by replacing each
# conjunct with `True` in a shadow copy of `src/hawedit` and running this file: those three are
# held, and the remaining eight — ingest, transcript, index, boundary, clip, editorial, render,
# delivery — could each be deleted with the suite green.
#
# The reason they were reachable at all is `whole_run`: before it existed nothing reached the
# True branch, so no conjunct could be told from a no-op. The control was the hard part; these
# are the rest of the sweep it made possible.
#
# Method note worth keeping: a first attempt put the shadow package one level too shallow, so
# `pipeline.py:111`'s `parents[2] / "assets" / "fonts"` missed and every ffmpeg test died on
# FontCoverageError. A mutation result read off a baseline like that means nothing — the shadow
# has to mirror `src/` with the assets beside it.


@needs_ffmpeg
@pytest.mark.parametrize(
    ("missing", "strip"),
    [
        ("ingest", lambda run: replace(run, ingest=None)),
        ("transcript", lambda run: replace(run, transcript=None)),
        ("index", lambda run: replace(run, index=None)),
        ("boundary", lambda run: replace(run, boundary=None)),
        ("clip", lambda run: replace(run, clip=None)),
        ("render", lambda run: replace(run, render=None)),
        ("delivery", lambda run: replace(run, delivery=None)),
    ],
)
def test_a_run_missing_any_material_evidence_is_never_complete(
    whole_run: PipelineRun, missing: str, strip: Callable[[PipelineRun], PipelineRun]
) -> None:
    """`complete` is the CLI's exit code (`return 0 if run.complete else 1`) and the `"complete"`
    key of the `--json` document.

    Its docstring gives the rule these seven conjuncts enforce: `None` means "this stage
    succeeded and has no separate result object" for several seams, and is also every field's
    construction default — so "nothing was skipped" alone lets an empty `PipelineRun` claim
    success. Each conjunct demands the material evidence a finished run necessarily leaves
    behind, and each was deletable without reddening anything.
    """
    assert strip(whole_run).complete is False, f"a run with no {missing} claimed completeness"


@needs_ffmpeg
def test_a_run_without_measured_diarization_is_never_complete(whole_run: PipelineRun) -> None:
    assert not isinstance(whole_run.ingest, StageSkipped)
    assert whole_run.ingest is not None
    without_turns = replace(whole_run.ingest, diarization=None)
    assert replace(whole_run, ingest=without_turns).complete is False


@needs_ffmpeg
def test_a_clip_with_no_editorial_block_is_never_complete(whole_run: PipelineRun) -> None:
    """The eighth conjunct, and the one that is not a field of the run.

    §3 Stage 5 produces a boundary before Stage 4 has judged anything, so `Clip.editorial` is
    optional by design — a clip can exist without it. `complete` is where that optionality has
    to end: a run whose clip carries no editorial block never had a verdict, and reporting exit
    0 for it would be the silent success §1 of this module forbids.
    """
    assert whole_run.clip is not None
    assert replace(whole_run, clip=replace(whole_run.clip, editorial=None)).complete is False


@needs_ffmpeg
def test_stage_5_fuses_against_the_cuts_stage_0_found_on_this_video(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Asserted on the input, and the reason is measured rather than assumed.

    §3 Stage 5 takes the **latest** of its out-point signals, and on the only media in this
    checkout natural silence is the end of the VAD speech region — **4162 ms**, the whole file.
    Measured through the real runner with an anchor 300 ms before the 2800 ms cut:
    `out_extended_by='natural_silence'`, `final_out=4162`. So no anchor makes the shot cut decide
    the result here, and replacing the cuts with `(9000, 9500)` — cuts from nowhere on this video
    — left the whole suite green.

    The two sides of this assertion come from different places, so it is not the request echoed
    back: one is what Stage 0 measured off the file, the other is what Stage 5 was handed.
    """
    from hawedit.boundary import BoundaryInputs, fuse_boundary

    seen: list[BoundaryInputs] = []
    real = fuse_boundary

    def recording(inputs: BoundaryInputs) -> object:
        seen.append(inputs)
        return real(inputs)

    monkeypatch.setattr("hawedit.pipeline.fuse_boundary", recording)
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="cuts",
        transcript=a_transcript("cuts"),
        select_sentences=(0, 1),
    )
    assert seen, "Stage 5 never ran"
    assert not isinstance(run.ingest, StageSkipped) and run.ingest is not None
    assert run.ingest.shot_cuts_ms == (1_400, 2_800), run.ingest.shot_cuts_ms
    assert seen[-1].shot_cuts_ms == run.ingest.shot_cuts_ms, (
        f"Stage 5 was fused against {seen[-1].shot_cuts_ms} while Stage 0 found "
        f"{run.ingest.shot_cuts_ms} on this video"
    )


def test_stage_1_is_not_re_run_when_its_output_is_already_in_the_work_directory(
    tmp_path: Path,
) -> None:
    """§3 Stage 1 is the expensive stage — **1,547 s** for 545 segments on hawapc01's two 3090 Ti
    — and `run_pipeline` called `asr.transcribe` before it consulted `TranscriptStore` at all.

    Measured with a counting producer before D-136: two runs over one work directory produced
    **2** calls, and a second pass differing by one character hit `RawTranscriptImmutable`
    *after* the full spend — D-071's shape, where a billed Gemini call preceded an overwrite
    refusal.
    """
    calls: list[str] = []

    def producer(transcript: RawTranscript) -> CanonicalTranscriptProducer:
        class Counting:
            def transcribe(
                self,
                media_id: str,
                audio_path: Path,
                speech_segments: object,
                work_dir: Path,
                ffmpeg: Path | None = None,
            ) -> RawTranscript:
                calls.append(media_id)
                return replace(transcript, media_id=media_id)

        return Counting()

    work = tmp_path / "work"
    supplied = a_transcript("probe")
    run_pipeline(FIXTURE, work_dir=work, media_id="probe", asr=producer(supplied))
    assert len(calls) == 1

    run_pipeline(FIXTURE, work_dir=work, media_id="probe", asr=producer(supplied))
    assert len(calls) == 1, f"Stage 1 ran again with a complete transcript on disk: {calls}"

    # The control: a *different* producer must re-transcribe, because a transcript made by one
    # producer cannot be read as another's output. Without this, the assertion above is also
    # satisfied by a cache that never checks anything.
    class OtherProducer:
        def transcribe(
            self,
            media_id: str,
            audio_path: Path,
            speech_segments: object,
            work_dir: Path,
            ffmpeg: Path | None = None,
        ) -> RawTranscript:
            calls.append("other")
            return replace(supplied, media_id=media_id)

    run_pipeline(FIXTURE, work_dir=work, media_id="probe", asr=OtherProducer())
    assert calls[-1] == "other", "a different producer reused the first producer's transcript"


def test_an_adapted_stage_1_does_not_reuse_the_stock_run_s_transcript(tmp_path: Path) -> None:
    """The defect D-181 exists for, at the level it actually bites.

    Reuse is keyed on the producer, and every OmniASR producer is the same class — so a run with
    a LoRA adapter and a run without one were **one key**. The stock transcript would be handed
    back after 0 s and the report would name the adapter: 545 segments of words the champion
    never read, presented as the champion's. This is D-136's own rule ("a transcript stored by a
    stub must not be reused by a real run") on the axis that did not exist when it was written.
    """
    calls: list[str | None] = []

    class Adaptable:
        """One class, two sets of weights — exactly the shape the class-name key could not see."""

        def __init__(self, adapter: str | None) -> None:
            self.model_identity = adapter

        def transcribe(
            self,
            media_id: str,
            audio_path: Path,
            speech_segments: object,
            work_dir: Path,
            ffmpeg: Path | None = None,
        ) -> RawTranscript:
            calls.append(self.model_identity)
            return replace(a_transcript(media_id), media_id=media_id)

    mixed = tmp_path / "mixed"
    run_pipeline(FIXTURE, work_dir=mixed, media_id="probe", asr=Adaptable(None))
    assert calls == [None]

    run_pipeline(FIXTURE, work_dir=mixed, media_id="probe", asr=Adaptable("lora:abc123"))

    assert calls == [None, "lora:abc123"], (
        "the adapted run reused the stock transcript; its words would ship as the adapter's"
    )

    # The control, in its own work directory because invariant #1 gives one media_id exactly one
    # canonical transcript: reuse must still fire for the *same* weights, or this key re-runs
    # Stage 1 on every invocation and the 1,547 s D-136 saved is spent again each time.
    same = tmp_path / "same"
    calls.clear()
    run_pipeline(FIXTURE, work_dir=same, media_id="probe", asr=Adaptable("lora:abc123"))
    run_pipeline(FIXTURE, work_dir=same, media_id="probe", asr=Adaptable("lora:abc123"))
    assert calls == ["lora:abc123"], "the same adapter re-transcribed instead of reusing"


def test_a_supplied_transcript_never_licenses_a_reuse(tmp_path: Path) -> None:
    """`--transcript` hands in a file that was not made from this audio by any producer here, so
    it must leave no provenance sidecar — otherwise the next `--omni-asr` run would reuse it and
    the report would claim canonical ASR for words that came from elsewhere.
    """
    work = tmp_path / "work"
    run_pipeline(FIXTURE, work_dir=work, media_id="probe", transcript=a_transcript("probe"))
    assert not (work / "transcripts" / "probe.transcript.raw.provenance.json").exists()


def test_the_composer_is_built_with_the_pinned_embedding_revision() -> None:
    """The wiring, which D-140's audit found unheld: dropping `embedding_revision` from
    `build_visual_composer` left every test green, and the embedding cache then never matched —
    a silent return to re-embedding 641 windows on every run.

    Asserted on the source, the shape D-105, D-133 and D-135 all needed: the claim is *what the
    runner passes*, and every other test builds its own composer.
    """
    source = (ROOT / "src" / "hawedit" / "pipeline.py").read_text(encoding="utf-8")
    body = source[source.index("def build_visual_composer(") :]
    following = body.find("\ndef ")
    body = body if following == -1 else body[:following]
    assert "embedding_revision=_embedding_revision(model_store)" in body, (
        "the runner no longer gives the composer the pinned checkpoint revision, so its "
        "embedding cache can never match and Stage 2 re-embeds every window"
    )


# --- D-146: an interrupted delivery must be recoverable, and a finished one untouchable ------
#
# D-072 built all three sidecars before writing any, and its `except` unlinks them, so a write
# that *fails* leaves none. A Ctrl-C is a `KeyboardInterrupt` — a `BaseException` the clause
# never sees — and a SIGKILL runs no clause at all. Measured on a real run interrupted at the
# second of the three writes: `.ass`, `.mp4` and `.json` on disk, and the retry into the same
# directory raised `FileExistsError`. One keystroke wedged the work directory for good.
# =========================================================================================


def _abandoned_attempt(work: Path, media_id: str, sentence: int = 0) -> tuple[str, ...]:
    """What a run killed partway through the sidecars leaves: artifacts, and no record."""
    from hawedit.pipeline import _clip_id, _delivery_artifact_paths

    work.mkdir(parents=True, exist_ok=True)
    clip_id = _clip_id(media_id, (sentence,))
    ass_path, render_path, _srt, _edl, editing_json_path, _measured = _delivery_artifact_paths(
        work, clip_id
    )
    for path in (ass_path, render_path, editing_json_path):
        path.write_text("from the attempt that was interrupted", encoding="utf-8")
    return tuple(p.name for p in (ass_path, render_path, editing_json_path))


def _cli_exit(argv: list[str], tmp_path: Path) -> tuple[int, str]:
    """Run `main` and return its exit code with whatever it wrote to stderr."""
    import contextlib
    import io

    from hawedit.pipeline import main

    captured = io.StringIO()
    with contextlib.redirect_stderr(captured), contextlib.redirect_stdout(io.StringIO()):
        code = main([str(FIXTURE), "--work-dir", str(tmp_path / "work"), *argv])
    return code, captured.getvalue()


def test_auto_select_refuses_visual_without_a_query(tmp_path: Path) -> None:
    """The artifact of this fix is a Stage 0 that never runs."""
    code, stderr = _cli_exit(["--transcript", "x.json", "--visual", "--auto-select"], tmp_path)
    assert code == 2, stderr
    assert "--visual-query" in stderr, stderr
    assert not (tmp_path / "work").exists(), "the refusal came after the work directory was made"


def test_auto_select_accepts_visual_with_a_query(tmp_path: Path) -> None:
    """First control: the query is what makes `--visual` a producer, so it must be accepted.

    Stops at the missing transcript file, which is *after* the producer test — so this measures
    that the producer test passed rather than that some other refusal fired.
    """
    code, stderr = _cli_exit(
        ["--transcript", "x.json", "--visual", "--visual-query", "ڕۆژنامەوان", "--auto-select"],
        tmp_path,
    )
    assert code == 2, stderr
    assert "--visual-query" not in stderr, f"the producer test still refused: {stderr}"
    assert "x.json" in stderr, stderr


def test_auto_select_accepts_path_a_alone(tmp_path: Path) -> None:
    """Second control: Path A anchors its own query, so `--gemini` needs no `--visual-query`.

    Reaches the missing Gemini key — a refusal from `GeminiJudge`, past the producer test.
    """
    code, stderr = _cli_exit(["--transcript", "x.json", "--gemini", "--auto-select"], tmp_path)
    assert code == 2, stderr
    assert "--visual-query" not in stderr, f"the producer test refused Path A: {stderr}"


def test_auto_select_still_refuses_when_no_path_is_enabled(tmp_path: Path) -> None:
    """Third control: the original rule has not been weakened into always passing."""
    code, stderr = _cli_exit(["--transcript", "x.json", "--auto-select"], tmp_path)
    assert code == 2, stderr
    assert "Stage 3 producer" in stderr, stderr


def test_the_no_producer_skip_names_the_query_the_visual_path_needs(tmp_path: Path) -> None:
    """The runtime message told the reader `--visual` was enough, and since D-117 it is not.

    A reader who follows it gets a run that pays for Stage 0 and selects nothing.
    """
    from hawedit.pipeline import _STAGE_3_DISCOVERY

    assert "--visual-query" in _STAGE_3_DISCOVERY.reason, _STAGE_3_DISCOVERY.reason


def test_a_query_without_the_visual_path_is_refused_before_the_producer_test(
    tmp_path: Path,
) -> None:
    """Why the producer test may say `--visual and --visual-query` rather than just the query.

    Found by mutating the producer test: dropping the `--visual` conjunct left the suite green,
    because this earlier refusal makes the state unreachable — measured, `--visual-query q
    --auto-select` exits 2 with `--visual-query requires --visual`. That refusal had no test of
    its own, so the ordering the producer test leans on was held by nothing.
    """
    code, stderr = _cli_exit(
        ["--transcript", "x.json", "--visual-query", "ڕۆژنامەوان", "--auto-select"], tmp_path
    )
    assert code == 2, stderr
    assert "--visual-query requires --visual" in stderr, stderr


# --- D-149: the CLI's refusal surface, held as a set rather than one flag at a time -----------
#
# `_run_from_args` opens with fourteen refusals for flag combinations that cannot work. D-147
# found one of them *wrong* — `--auto-select` accepted `--visual`, which since D-117 cannot
# produce — and found it had no test. Measured across the whole gate suite, turning each
# refusal off one at a time: 12 of the 14 were unheld. `evidence/twelve-refusals-nothing-held.md`.
# =========================================================================================


def _argv_refusals() -> tuple[str, ...]:
    """Every combination `_build_and_run` refuses, read out of its own source.

    Taken from the AST rather than listed here, so a fifteenth refusal is covered the day it is
    added instead of the day someone remembers to add a case. Every `ValueError` this function
    raises *directly* is an argv refusal — nothing later in it raises that type — which is what
    makes the set well defined rather than a hopeful filter.

    Reads `_build_and_run`, not `_run_from_args`: D-A2 moved every validation this test walks
    into a function `durable.py` can also call, leaving `_run_from_args` a thin catch-and-print
    wrapper with no `raise` of its own. This test caught the move — it named the function it
    scans, and asserted against messages, not call sites, so a real extraction was exactly the
    diff that trips it. Fixed by pointing at the new home rather than widening what the walk
    accepts, so a *third* function quietly gaining a `raise ValueError` still fails it.
    """
    import ast

    source = (ROOT / "src" / "hawedit" / "pipeline.py").read_text(encoding="utf-8")
    function = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "_build_and_run"
    )
    messages: list[str] = []
    for node in ast.walk(function):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        if getattr(node.exc.func, "id", None) != "ValueError" or not node.exc.args:
            continue
        argument = node.exc.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            messages.append(argument.value)
        elif isinstance(argument, ast.JoinedStr):
            messages.append(
                "".join(
                    part.value
                    for part in argument.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
            )
    return tuple(messages)


# One argv per refusal, each reaching *that* one: the block is ordered and the first match wins,
# so every case here also asserts the ordering it depends on.


_REFUSAL_CASES: tuple[tuple[str, list[str], str], ...] = (
    (
        # The judging loop exists only on the automatic path. Accepting the flag beside
        # `--sentences` would silently do nothing while the operator believed N were scored.
        "judge-top-n where it cannot act",
        ["--judge-top-n", "5"],
        "--judge-top-n requires --auto-select",
    ),
    (
        "judging fewer than one candidate",
        ["--judge-top-n", "0", "--auto-select"],
        "--judge-top-n must be at least 1",
    ),
    (
        "a clip minimum that cannot hold a clip",
        ["--min-clip-seconds", "0"],
        "--min-clip-seconds must be greater than 0",
    ),
    (
        "two Stage 1 sources",
        ["--transcript", "x.json", "--omni-asr"],
        "--transcript and --omni-asr are mutually exclusive Stage 1 sources",
    ),
    (
        "an OmniASR runtime flag without the runtime",
        ["--wsl-distro", "Ubuntu"],
        "--omni-asr-runtime, --wsl-distro and --omni-asr-adapter require --omni-asr",
    ),
    (
        "an OmniASR adapter without the runtime",
        ["--omni-asr-adapter", "champion"],
        "--omni-asr-runtime, --wsl-distro and --omni-asr-adapter require --omni-asr",
    ),
    (
        "both cloud routes",
        ["--transcript", "x.json", "--gemini", "--vertex-project", "p"],
        "--gemini and --vertex-project are mutually exclusive cloud routes",
    ),
    (
        "two Stage 4 sources",
        ["--transcript", "x.json", "--sentences", "0", "--gemini", "--verdict", "v.json"],
        "cloud judging and --verdict are mutually exclusive Stage 4 sources",
    ),
    (
        "cloud discovery with nothing to discover in",
        ["--gemini"],
        "cloud discovery requires --transcript or --omni-asr",
    ),
    (
        "a selection with no transcript to select from",
        ["--sentences", "0"],
        "--sentences requires --transcript or --omni-asr",
    ),
    (
        "a verdict with no selection to attach it to",
        ["--transcript", "x.json", "--verdict", "v.json"],
        "--verdict requires a Stage 1 source and --sentences",
    ),
    (
        "Path B with no transcript",
        ["--visual"],
        "--visual requires --transcript or --omni-asr",
    ),
    (
        "a retrieval query with no retrieval",
        ["--transcript", "x.json", "--visual-query", "ڕۆژنامەوان"],
        "--visual-query requires --visual",
    ),
    (
        "a blank retrieval query",
        ["--transcript", "x.json", "--visual", "--visual-query", "   "],
        "--visual-query must contain non-whitespace Sorani retrieval text",
    ),
    (
        "Path B with neither Path A nor an explicit query",
        ["--transcript", "x.json", "--visual"],
        "--visual without Path A requires --visual-query",
    ),
    (
        "passing QC on nothing",
        ["--transcript", "x.json", "--qc-record", "rec.json"],
        "--qc-record requires --sentences or --auto-select",
    ),
    (
        "auto-select with no producer that can produce",
        ["--transcript", "x.json", "--auto-select"],
        "--auto-select needs a Stage 3 producer that can actually produce",
    ),
    (
        "Stage 5 with nothing selected",
        ["--transcript", "x.json", "--timelens"],
        "--timelens requires --sentences or --auto-select",
    ),
    (
        # D-258 inverted the flag. argparse would answer "unrecognized arguments", which reads
        # as a typo rather than as a decision, so the refusal names its replacement.
        "an invocation still passing the flag that was inverted",
        ["--face-reframe"],
        "--face-reframe is now the default and the flag is gone",
    ),
    (
        "two decoders asked for at once",
        ["--omni-asr", "--stock-decoder", "--omni-asr-adapter", "x"],
        "ask for different decoders",
    ),
    (
        "the base decoder without a Stage 1 run to draft with it",
        ["--transcript", "x.json", "--stock-decoder"],
        "--stock-decoder applies only to a Stage 1 run",
    ),
    (
        "claiming ZDR governance with nothing being sent anywhere",
        ["--transcript", "x.json", "--sentences", "0", "--zero-data-retention"],
        "governance flags apply only with a Gemini or Vertex route",
    ),
)

# Refused for a reason that a *different* refusal always reaches first, so no argv can trigger it
# and no test can hold it. Named here with the guard that pre-empts it rather than deleted: the
# unreachability is a property of the block's order, and this is where that gets checked.


_PRE_EMPTED_REFUSALS: tuple[tuple[str, str], ...] = (
    (
        "--auto-select requires --transcript or --omni-asr",
        # `--auto-select` needs a producer that can produce, and both producers need a Stage 1
        # source of their own: `--gemini`/`--vertex-project` hit "cloud discovery requires
        # --transcript or --omni-asr", and `--visual --visual-query` hits "--visual requires
        # --transcript or --omni-asr". So a run reaching here always has one.
        "--visual requires --transcript or --omni-asr",
    ),
)


@pytest.mark.parametrize(
    ("label", "argv", "expected"),
    [(label, argv, expected) for label, argv, expected in _REFUSAL_CASES],
    ids=[label for label, _argv, _expected in _REFUSAL_CASES],
)
def test_the_cli_refuses_a_combination_that_cannot_work(
    label: str, argv: list[str], expected: str, tmp_path: Path
) -> None:
    code, stderr = _cli_exit(argv, tmp_path)
    assert code == 2, f"{label}: exit {code}, stderr {stderr!r}"
    assert expected in stderr, f"{label}: {stderr!r}"
    # The refusal is about argv, so it must land before any work: no work directory, no Stage 0.
    assert not (tmp_path / "work").exists(), f"{label}: the run had already started"


def test_every_refusal_in_the_source_has_a_case(tmp_path: Path) -> None:
    """Bidirectional, so the set stays a description of the block rather than a snapshot.

    A refusal with no case fails here; a case naming a message the source no longer raises fails
    too. Either way it is a line in a diff instead of a guard nothing exercises — which is what
    twelve of these fourteen were before D-149.
    """
    refusals = _argv_refusals()
    covered = {expected for _label, _argv, expected in _REFUSAL_CASES}
    pre_empted = {message for message, _by in _PRE_EMPTED_REFUSALS}

    unmatched = [
        message
        for message in refusals
        if message not in pre_empted and not any(fragment in message for fragment in covered)
    ]
    assert not unmatched, f"argv refusals with no case: {unmatched}"

    orphaned = [
        fragment for fragment in covered if not any(fragment in message for message in refusals)
    ]
    assert not orphaned, f"cases naming a refusal the source no longer raises: {orphaned}"

    missing = [message for message in pre_empted if message not in refusals]
    assert not missing, f"pre-empted refusals that no longer exist: {missing}"

    # The two lists are alternatives, not overlapping labels: "unreachable" is an escape from
    # needing a case, so a refusal that has one cannot also claim it. Found by mutation —
    # adding a reachable refusal to `_PRE_EMPTED_REFUSALS` left the suite green, because
    # `unmatched` above simply skips anything listed there. That is how a live guard would get
    # excused from coverage by one line, which is the whole failure this file exists to stop.
    both = sorted(
        message for message in pre_empted if any(fragment in message for fragment in covered)
    )
    assert not both, (
        f"refusals claimed unreachable that also have a case: {both}. A refusal an argv can "
        f"trigger is not pre-empted — remove it from _PRE_EMPTED_REFUSALS."
    )


@pytest.mark.parametrize(
    ("refusal", "pre_empted_by"),
    _PRE_EMPTED_REFUSALS,
    ids=[refusal.split()[0] for refusal, _by in _PRE_EMPTED_REFUSALS],
)
def test_a_pre_empted_refusal_really_is_unreachable(
    refusal: str, pre_empted_by: str, tmp_path: Path
) -> None:
    """`--auto-select requires --transcript or --omni-asr` cannot fire, and this says why.

    Both producers need a Stage 1 source of their own, so every argv that would reach it is
    refused earlier. Asserted rather than deleted: the unreachability is a property of the
    block's *order*, and if that order changes this test is where it shows.
    """
    code, stderr = _cli_exit(
        ["--visual", "--visual-query", "ڕۆژنامەوان", "--auto-select"], tmp_path
    )
    assert code == 2, stderr
    assert pre_empted_by in stderr, stderr
    assert refusal not in stderr, f"{refusal!r} fired after all: {stderr!r}"


def test_a_complete_argv_reaches_the_run(tmp_path: Path) -> None:
    """The control. Every test above passes for a `_run_from_args` that refuses *everything*.

    This argv breaks none of the fourteen rules, so it must get past them — and it does, far
    enough to fail on the transcript file it names, which is read after the last refusal.
    """
    code, stderr = _cli_exit(
        ["--transcript", "no-such.json", "--sentences", "0", "--qc-record", "rec.json"], tmp_path
    )
    assert code == 2, stderr
    assert "no-such.json" in stderr, stderr
    for message in _argv_refusals():
        assert message not in stderr, f"a refusal fired on a legal argv: {message}"


# --- D-166: the delivery block's handler enumerates types, and one was missing ---------------


def _delivery_handler_types() -> tuple[str, ...]:
    """The exception names in the delivery block's `except` clause, read from the source.

    Parsed rather than imported because the claim is about *that* handler: a tuple written
    somewhere else, however correct, would not be the one protecting the five writes.
    """
    import ast

    source = (Path(__file__).resolve().parents[1] / "src" / "hawedit" / "pipeline.py").read_text(
        encoding="utf-8"
    )
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Try):
            continue
        calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
        builds_edl = any(getattr(call.func, "id", None) == "build_edl" for call in calls)
        publishes_bundle = any(
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "publish"
            and getattr(call.func.value, "id", None) == "bundle"
            for call in calls
        )
        if not builds_edl or not publishes_bundle:
            continue
        handlers = [h.type for h in node.handlers if h.type is not None]
        assert len(handlers) == 1, f"the delivery block has {len(handlers)} except clauses"
        caught = handlers[0]
        assert isinstance(caught, ast.Tuple), "the delivery handler no longer catches a tuple"
        return tuple(element.id for element in caught.elts if isinstance(element, ast.Name))
    raise AssertionError("could not find the delivery block in pipeline.py")


def test_the_delivery_handler_catches_everything_its_builders_refuse_with() -> None:
    """D-165 added `UndeliverableOrder`, a `ValueError` and **not** a `DeliveryError` — siblings,
    not parent and child — so it escaped this handler the moment it was introduced.

    Demonstrated against the real tuple: the exception propagates out of a stage written to
    refuse gracefully, skipping the cleanup that keeps the delivery set all-or-none and the
    `StageSkipped` that names the gap. It was reachable only through call order — `build_ass`
    runs first on the same sentences and its handler catches `ValueError` — and an ordering
    guarantee is not an exception contract.

    Every type the three builders raise for bad input must appear here, so the next one added
    fails this test rather than escaping in production.
    """
    from hawedit.delivery import DeliveryError
    from hawedit.sentences import UndeliverableOrder

    caught = _delivery_handler_types()

    for refusal in (DeliveryError, UndeliverableOrder):
        assert refusal.__name__ in caught, (
            f"{refusal.__name__} is raised by the delivery builders and is not in the handler "
            f"{caught}; it would propagate instead of leaving a named gap"
        )

    # Why both must be listed, asserted rather than asserted-about: they are siblings under
    # ValueError, so neither catches the other.
    #
    # Recorded, not pinned: this is documentation, not a control. Its audit mutation SURVIVED,
    # correctly — deleting it measures nothing, because the state it would catch (one of them
    # subclassing the other) cannot be built. `sentences.py` cannot import `DeliveryError`
    # without a cycle, `delivery.py` importing `sentences`. D-166 says so rather than counting
    # it as a guard.
    assert not issubclass(UndeliverableOrder, DeliveryError)
    assert not issubclass(DeliveryError, UndeliverableOrder)


# --- D-171: the report's stage list was hand-written beside the dataclass it describes -------


def _pipeline_source() -> str:
    from pathlib import Path as _Path

    return (_Path(__file__).resolve().parents[1] / "src" / "hawedit" / "pipeline.py").read_text(
        encoding="utf-8"
    )


def _stage_names_the_pipeline_can_produce() -> set[str]:
    """Every stage name a `StageSkipped` in `pipeline.py` is actually constructed with.

    Two producers: the constructor called directly, and `_not_reached(stage, dependency)`.
    Read out of the source, so a stage added later is covered without anyone extending a list
    here — which is the failure this pair of tests exists for.
    """
    import re

    source = _pipeline_source()
    direct = set(re.findall(r'stage="([a-z_0-9]+)"', source))
    helper = set(re.findall(r'_not_reached\(\s*"([a-z_0-9]+)"', source))
    # Non-vacuity, and not a magic number: both producers must have been found. A regex that
    # matched neither would make everything below assert nothing at all.
    assert direct, "no direct StageSkipped(stage=...) found; the scan is broken, not the code"
    assert helper, "no _not_reached(...) found; the scan is broken, not the code"
    return direct | helper


def test_every_stage_the_pipeline_can_skip_is_a_field_the_report_reads() -> None:
    """A skipped stage that `PipelineRun` has no field for can never reach a reader.

    `skipped()` reads the dataclass, so "is there a field with this name" is exactly the
    question that decides whether a `StageSkipped` the code builds is reportable.
    """
    from dataclasses import fields as dataclass_fields

    from hawedit.pipeline import PipelineRun

    known = {field.name for field in dataclass_fields(PipelineRun)}
    orphaned = sorted(_stage_names_the_pipeline_can_produce() - known)
    assert not orphaned, (
        f"pipeline.py builds StageSkipped for {orphaned}, and PipelineRun has no field of that "
        f"name — the stage would be skipped with nothing in the report saying so"
    )


def test_a_skipped_stage_in_any_field_is_named_in_the_report() -> None:
    """The guard the hand-written list did not give.

    Measured before this: deleting `("delivery", self.delivery)` from that list left the whole
    suite green, and a run with the delivery stage skipped reported *"INCOMPLETE — 1 stage(s)
    did not run"* instead of two, with `blocked_by=('§2 delivery set',)` reaching no one.
    `complete` stayed False throughout, so this was never an exit-code defect — it was §1's
    *fail visible, not silent*, failing silently.

    Exhaustive over the dataclass rather than over a list of stage names, so the property is
    "any field holding a skip is reported" and a field added later needs no edit here.
    """
    from dataclasses import fields as dataclass_fields

    from hawedit.pipeline import PipelineRun, StageSkipped

    # Derived twice over, because neither derivation is complete on its own: most stage fields
    # declare `StageSkipped` in their annotation, but `boundary` is annotated `object | None`
    # and would be missed — and it is one of the stages `_not_reached` builds.
    declared = {
        field.name for field in dataclass_fields(PipelineRun) if "StageSkipped" in str(field.type)
    }
    assert declared, "no field declares StageSkipped; the annotation scan is broken"
    stage_fields = declared | _stage_names_the_pipeline_can_produce()

    base = PipelineRun(media_id="m", source="s.mp4", work_dir="w")
    checked = 0
    for field in dataclass_fields(PipelineRun):
        if field.name not in stage_fields:
            continue
        skip = StageSkipped(stage=field.name, reason="measured", blocked_by=("a dependency",))
        # `Any` because the override is genuinely dynamic — the point of the test is that the
        # set of stage fields is not written out here.
        overrides: dict[str, Any] = {field.name: skip}
        run = replace(base, **overrides)
        reported = dict(run.skipped())
        assert field.name in reported, (
            f"{field.name} holds a StageSkipped and `skipped()` does not name it, so the run "
            f"report would be short by one and would not say which stage"
        )
        assert reported[field.name].blocked_by == ("a dependency",), (
            f"{field.name} is named but its blocker is not carried, which is the half a reader "
            f"acts on"
        )
        assert not run.complete, f"a run with {field.name} skipped called itself complete"
        checked += 1
    assert checked == len(stage_fields & {f.name for f in dataclass_fields(PipelineRun)}), (
        f"only {checked} of {sorted(stage_fields)} were exercised"
    )
    assert checked >= len(declared), f"fewer fields exercised ({checked}) than declare a skip"


def test_the_report_counts_every_skipped_stage_it_names() -> None:
    """The control for the count, which is the number a reader actually sees.

    The defect showed as a *count* — "1 stage(s)" for two skipped stages — so a test that only
    checked membership would have passed on it for the stages it did name.
    """
    from hawedit.pipeline import PipelineRun, StageSkipped

    def skip(stage: str) -> StageSkipped:
        return StageSkipped(stage=stage, reason="measured", blocked_by=("a dependency",))

    run = PipelineRun(
        media_id="m",
        source="s.mp4",
        work_dir="w",
        render=skip("render"),
        delivery=skip("delivery"),
        discovery=skip("discovery"),
    )
    assert len(run.skipped()) == 3, f"three stages were skipped, the report has {run.skipped()}"
    assert {name for name, _ in run.skipped()} == {"render", "delivery", "discovery"}


# --- D-177: a persisted verdict must identify the footage it is applied to ------------------


def test_a_supplied_verdict_for_another_span_is_refused(tmp_path: Path) -> None:
    """`--verdict` is the only Stage 4 route available while BLOCKED #3 stands, so it is the
    path a real run takes today — and deleting this check left the whole suite green.

    `JudgeVerdict.__post_init__` cannot catch it: it requires
    `clip_in_ms <= payoff_at_ms <= clip_out_ms`, which a verdict for a *different* clip
    satisfies perfectly. The verdict is internally valid and externally wrong.

    Measured on the block that ships: a verdict scored for 900000..904000 ms carries
    `payoff_at_ms: 902000` into §5's editorial block for a clip running 100..4100 ms — §5's
    payoff marker pointing 898 seconds past the end of the clip — along with every score
    (`hook_score`, `meaning_fidelity`, `misleading_edit_risk`, `cultural_landing`) reached on
    footage this clip does not contain. D-177.
    """

    def run_with(verdict_in: int, verdict_out: int) -> None:
        run_pipeline(
            FIXTURE,
            tmp_path / f"work-{verdict_in}-{verdict_out}",
            media_id="fixture",
            transcript=a_transcript(),
            select_sentences=(0, 1),
            verdict=a_verdict(verdict_in, verdict_out),
        )

    # Both ends, separately. A first version of this test moved both at once, and the audit
    # showed that comparing **only the in-point** then passed — so a verdict scored for the
    # right start and the wrong end would have been accepted, which is the one an operator is
    # actually likely to produce by editing a span by hand.
    with pytest.raises(ValueError, match="identify the same footage"):
        run_with(900_000, 904_000)
    with pytest.raises(ValueError, match="identify the same footage"):
        run_with(100, 5_000)  # right in-point, wrong out-point
    with pytest.raises(ValueError, match="identify the same footage"):
        run_with(200, 4_100)  # wrong in-point, right out-point


def test_a_supplied_verdict_for_this_span_is_accepted(tmp_path: Path) -> None:
    """The control. Without it the test above passes for a pipeline that refuses **every**
    supplied verdict, which would make `--verdict` — today's only Stage 4 route — unusable
    while looking guarded.
    """
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        verdict=a_verdict(100, 4_100),
    )
    assert run.clip is not None
    assert run.clip.editorial is not None, "a matching verdict produced no editorial block"
    assert run.clip.editorial.payoff_at_ms == 2_100


# --- D-178: the adapter-side twin of D-177, which had never once refused ---------------------


def _run_with_judge_returning(
    tmp_path: Path, make_verdict: Callable[..., JudgeVerdict]
) -> PipelineRun:
    """Drive Stage 4 with an adapter whose verdict is whatever `make_verdict` builds."""
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            return make_verdict(request)

    return run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            Candidate("v1", "judged", 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
        ],
        judge=Judge(),
    )


@needs_ffmpeg
def test_a_judge_returning_another_candidates_verdict_is_refused(tmp_path: Path) -> None:
    """`_assert_verdict_matches_request` runs on every judged run and had **never fired**.

    Measured by tracing the whole suite: its call site and both of its comparisons execute,
    and neither of its two `raise` statements ever does. It is the only thing standing between
    an adapter's answer and §5's editorial block, and D-177 measured what a verdict for other
    footage carries there — `payoff_at_ms` outside the clip, every editorial score reached on
    footage the clip does not contain. D-178.
    """
    with pytest.raises(ValueError, match="belongs to different footage"):
        _run_with_judge_returning(
            tmp_path,
            lambda request: replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id="a-different-candidate",
            ),
        )


@needs_ffmpeg
def test_a_judge_returning_another_span_is_refused(tmp_path: Path) -> None:
    """The second refusal, which the same trace showed had never fired either.

    Separate from the one above because they catch different lies: an adapter that answers the
    right candidate over the wrong seconds passes the identifier check completely.
    """
    with pytest.raises(ValueError, match="judge returned span"):
        _run_with_judge_returning(
            tmp_path,
            lambda request: replace(
                a_verdict(request.clip_in_ms + 5_000, request.clip_out_ms + 5_000),
                candidate_id=request.candidate_id,
            ),
        )


@needs_ffmpeg
def test_a_judge_answering_the_request_it_was_given_is_accepted(tmp_path: Path) -> None:
    """The control. Without it both tests above pass for a pipeline that refuses **every**
    adapter verdict, which would make Stage 4 unusable while looking guarded.
    """
    run = _run_with_judge_returning(
        tmp_path,
        lambda request: replace(
            a_verdict(request.clip_in_ms, request.clip_out_ms),
            candidate_id=request.candidate_id,
        ),
    )
    assert "editorial" not in {name for name, _ in run.skipped()}, (
        "a judge answering its own request was refused"
    )


# --- D-183: the printed report was silent about the stage that does the discovering ---------


def _printed(run: PipelineRun, capsys: pytest.CaptureFixture[str]) -> str:
    from hawedit.pipeline import _print_report

    _print_report(run)
    return capsys.readouterr().out


def _discovered_run(tmp_path: Path, media_id: str = "reported") -> PipelineRun:
    """A run whose Stage 3 actually ran, over BOTH paths — `discover` is the verbal path only,
    so a visual composer is what puts a second `discovery_path` in the split."""
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
            return VisualDiscoveryResult(
                media_id,
                query,
                3,
                3,
                (),
                (Candidate("scene-2", media_id, 2_800, 4_162, DiscoveryPath.VISUAL, 1, 0.7),),
            )

    return run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id=media_id,
        transcript=a_transcript(media_id),
        discover=lambda _n: [
            Candidate("v1", media_id, 0, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9)
        ],
        visual_composer=Composer(),  # type: ignore[arg-type]
        visual_query="two people talking",
    )


@needs_ffmpeg
def test_the_printed_report_says_what_stage_3_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-111's finding one representation over.

    That entry fixed `report["discovery"]` reading `null` whether Stage 3 produced candidates or
    was never attempted — "a stage reporting nothing about itself is the silent case" — and fixed
    it only in the JSON. Measured on the real 38-minute run with `--visual`: the JSON carried
    `discovery: {skipped: false, candidates: 7}` and the printed report, which is what the
    documented invocation produces, went straight from Stage 2's survivors to §4.2's sentences.
    """
    run = _discovered_run(tmp_path)
    assert run.candidates, "this fixture must actually discover something"

    printed = _printed(run, capsys)

    assert "stage 3" in printed, "the stage that produces the pipeline's output is unreported"
    assert f"{len(run.candidates)} candidate(s)" in printed
    # §5: rejection is first-class and "your only measure of recall" — reported even at zero,
    # because the set was computed and a line that appears only when non-empty cannot be told
    # from one that never ran.
    assert f"{len(run.rejected)} rejected" in printed


@needs_ffmpeg
def test_the_printed_report_splits_candidates_by_discovery_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§8.2 measures Recall@20 *per discovery path*, and "if Path B never surfaces a winner Path
    A missed, collapse it" is decided on that split — a bare total cannot support it."""
    run = _discovered_run(tmp_path, "split")
    printed = _printed(run, capsys)

    counts: dict[str, int] = {}
    for candidate in run.candidates:
        key = candidate.discovery_path.value
        counts[key] = counts.get(key, 0) + 1
    assert len(counts) == 2, "a one-path fixture cannot show whether the split is real"

    # The count, not just the path name. Asserting the bare name passed for the WRONG answer:
    # the *rejection* split prints the same names, so deleting the candidate split entirely
    # left `visual` in the output and this test green. Caught by the mutation audit, which is
    # what it is for.
    for path, count in counts.items():
        assert f"{path} {count}" in printed, (
            f"the printed report does not credit {count} candidate(s) to {path}"
        )


@needs_ffmpeg
def test_the_printed_report_reads_the_same_source_as_the_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control that matters: two reports of one run must not be able to disagree. Both read
    `_discovery_ran`, so a count recomputed in the printer would fail here."""
    run = _discovered_run(tmp_path, "agree")
    printed = _printed(run, capsys)
    machine = run.to_dict()["discovery"]

    assert machine["skipped"] is False
    assert f"{machine['candidates']} candidate(s)" in printed


def test_a_skipped_stage_3_still_prints_exactly_its_skip_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control on the whole change: a run with no Stage 3 producer must print what it
    printed before — one SKIPPED line and no `stage 3` line invented from an empty tuple."""
    run = run_pipeline(FIXTURE, tmp_path / "work", media_id="fixture", transcript=a_transcript())
    assert not run.candidates

    printed = _printed(run, capsys)

    assert "stage 3" not in printed, "a stage that never ran must not report a result"
    assert "SKIPPED discovery" in printed


# --- D-185: --auto-select chose nothing and would not say why -------------------------------


def _auto_select_run(
    tmp_path: Path, window_ms: int, media_id: str, start_ms: int = 0
) -> PipelineRun:
    """A run whose only candidate is `window_ms` long, auto-selecting against real sentences."""
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

    return run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id=media_id,
        transcript=a_transcript(media_id),
        discover=lambda _n: [
            Candidate(
                "v1",
                media_id,
                start_ms,
                start_ms + window_ms,
                DiscoveryPath.VERBAL,
                rank=1,
                score=0.9,
            )
        ],
        auto_select=True,
        # A 4.1 s fixture against D-254's 30 s floor would refuse on length before this test
        # could measure anything about window width.
        min_clip_ms=4_000,
    )


@needs_ffmpeg
def test_auto_select_choosing_nothing_says_why_in_the_numbers(tmp_path: Path) -> None:
    """§5 selects complete sentences a candidate can anchor, and a candidate that anchors none
    used to leave the operator reading "complete selected sentences was not available" — the
    symptom rather than the cause.

    Measured on the real 38-minute file: 7 candidates of 3.48–3.96 s against 184 complete
    sentences with a median of 6.72 s, 0 wholly inside any of them.

    **T3 narrowed when this fires, and the fixture moved with it.** A window shorter than a
    sentence is no longer enough on its own: growth seeds from the sentences a candidate
    *overlaps*, so a 120 ms window sitting inside a sentence now grows into it. What still
    produces nothing is a window that overlaps no complete sentence at all — this one sits in
    the 1,700–2,000 ms silence between them. The reason text below is unchanged, and so is the
    thing it must not go back to saying.
    """
    run = _auto_select_run(tmp_path, window_ms=120, media_id="tootight", start_ms=1_750)
    assert run.clip is None, "this fixture must fail to select, or it measures nothing"

    boundary = dict(run.skipped())["boundary"]

    assert "no complete sentence fits a candidate window" in boundary.blocked_by
    assert "--auto-select examined 1 candidate(s)" in boundary.reason
    # The span values, not just the count: a reason that says "1 candidate" without saying how
    # long it was states the symptom again.
    assert "0.12–0.12s" in boundary.reason, boundary.reason
    lengths = sorted(s.end_ms - s.start_ms for s in run.sentences if s.complete)
    median = lengths[len(lengths) // 2] / 1000
    assert f"median {median:.2f}s" in boundary.reason, (
        "the sentence lengths are the other half of the cause, and the median is the number "
        "that says whether a wider window would help"
    )
    assert "BLOCKED.md #17" in boundary.reason


@needs_ffmpeg
def test_a_candidate_wide_enough_still_selects_and_reports_no_such_reason(
    tmp_path: Path,
) -> None:
    """The control. A window that does contain a complete sentence must select normally and
    must NOT carry the explanation — a reason attached unconditionally explains nothing."""
    run = _auto_select_run(tmp_path, window_ms=4_162, media_id="widecand")

    boundary = dict(run.skipped()).get("boundary")
    reason = boundary.reason if boundary is not None else ""
    assert "no complete sentence fits a candidate window" not in (
        boundary.blocked_by if boundary is not None else ()
    ), f"a window wide enough to hold a sentence still reported nothing fits: {reason}"


@needs_ffmpeg
def test_a_run_without_auto_select_keeps_the_plain_dependency_reason(tmp_path: Path) -> None:
    """The second control: this explanation belongs to --auto-select. A run that simply
    selected no sentences must still say what it said before."""
    run = run_pipeline(
        FIXTURE, tmp_path / "work", media_id="plain", transcript=a_transcript("plain")
    )

    boundary = dict(run.skipped())["boundary"]

    assert "complete selected sentences was not available" in boundary.reason
    assert "--auto-select" not in boundary.reason


def test_an_operational_ingest_failure_is_a_complete_structured_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 0 used to escape before ``PipelineRun`` existed, contradicting this module's API.

    The downstream skips matter as much as the ingest record: a consumer must not need to infer
    that an absent transcript/index/render all share the same root blocker.
    """

    def fail_ingest(*_args: object, **_kwargs: object) -> None:
        raise IngestError("ffmpeg could not open the media")

    monkeypatch.setattr("hawedit.pipeline.ingest", fail_ingest)
    run = run_pipeline(FIXTURE, tmp_path / "work")

    assert not run.complete
    assert [name for name, _ in run.skipped()] == [
        "ingest",
        "diarization",
        "transcript",
        "index",
        "visual_index",
        "discovery",
        "editorial",
        "boundary",
        "render",
        "delivery",
    ]
    assert isinstance(run.ingest, StageSkipped)
    assert "ffmpeg could not open the media" in run.ingest.reason
    assert run.ingest.blocked_by == ("Stage 0 ingest",)
    for name, skip in run.skipped()[1:]:
        assert skip.blocked_by == ("Stage 0 ingest",), name


def test_an_ingest_os_error_is_normalized_but_programmer_errors_still_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def os_failure(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("media read denied")

    monkeypatch.setattr("hawedit.pipeline.ingest", os_failure)
    run = run_pipeline(FIXTURE, tmp_path / "os-work")
    assert isinstance(run.ingest, StageSkipped)
    assert "PermissionError" in run.ingest.reason

    def control(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("programmer control")

    monkeypatch.setattr("hawedit.pipeline.ingest", control)
    with pytest.raises(AssertionError, match="programmer control"):
        run_pipeline(FIXTURE, tmp_path / "control-work")


# --- the command-line surface --------------------------------------------------------------


def test_cli_json_reports_an_operational_stage_0_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hawedit.pipeline import main

    def fail_ingest(*_args: object, **_kwargs: object) -> None:
        raise IngestError("ffprobe launch was denied")

    monkeypatch.setattr("hawedit.pipeline.ingest", fail_ingest)
    code = main([str(FIXTURE), "--work-dir", str(tmp_path / "work"), "--json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert code == 1
    assert captured.err == ""
    assert report["ingest"]["skipped"] is True
    assert report["ingest"]["blocked_by"] == ["Stage 0 ingest"]
    assert report["delivery"]["blocked_by"] == ["Stage 0 ingest"]


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
        visual_query="گرنگ",
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
        visual_query="گرنگ",
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
def test_path_b_refuses_the_whole_transcript_when_path_a_has_no_candidate(
    tmp_path: Path,
) -> None:
    from hawedit.gemini import GeminiUnavailable

    calls = 0

    class Composer:
        def discover(self, *args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            raise AssertionError("the GPU must not be touched without a bounded query")

    def broken_path_a(_transcript: Any) -> Sequence[Candidate]:
        raise GeminiUnavailable("temporary cloud refusal")

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="no-query-authority",
        transcript=a_transcript("no-query-authority"),
        discover=broken_path_a,
        visual_composer=Composer(),  # type: ignore[arg-type]
    )

    assert calls == 0
    assert isinstance(run.discovery, StageSkipped)
    assert isinstance(run.visual_index, StageSkipped)
    assert "refusing the whole episode transcript" in run.visual_index.reason
    assert run.visual_index.blocked_by == ("a retrieval query",)
    assert run.visual_query_source is None
    assert run.to_dict()["visual_query_source"] is None
    assert run.candidates == ()


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
def test_automatic_selection_with_no_complete_sentence_never_extracts_frames_or_calls_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate

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
def test_keyframe_operational_failure_is_an_editorial_skip_before_judging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.clip import DiscoveryPath
    from hawedit.discovery import Candidate
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
        qc=_test_qc(True),
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
    from hawedit.judge import NotRoutable, RequestTooLarge

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
        visual_query="گرنگ",
    )

    assert isinstance(run.discovery, StageSkipped)
    assert "GeminiUnavailable: temporary cloud refusal" in run.discovery.reason
    assert tuple(candidate.candidate_id for candidate in run.candidates) == ("visual",)
    assert not isinstance(run.visual_index, StageSkipped)
    assert run.visual_query_source == "explicit"


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


@needs_ffmpeg
@pytest.mark.parametrize(
    ("rate", "media_id"),
    [("30000/1001", "ntsc30"), ("60000/1001", "ntsc60")],
)
def test_an_ntsc_source_writes_a_complete_drop_frame_delivery_set(
    tmp_path: Path, rate: str, media_id: str
) -> None:
    ntsc = _ntsc_copy(FIXTURE, tmp_path / f"{media_id}.mp4", rate)
    from hawedit.render import frame_rate

    assert frame_rate(ntsc) != int(frame_rate(ntsc)), "the transcode must be a non-integer rate"

    work = tmp_path / "work"
    run = run_pipeline(
        ntsc,
        work,
        media_id=media_id,
        transcript=a_transcript(
            media_id, media_sha256=hashlib.sha256(ntsc.read_bytes()).hexdigest()
        ),
        select_sentences=(0,),
        qc=_test_qc(
            True,
            reviewed_sha256=NTSC30_RENDER_SHA256 if "30" in media_id else NTSC60_RENDER_SHA256,
        ),
        verdict=a_verdict(100, 1_700),
    )
    assert run.delivery is not None and not isinstance(run.delivery, StageSkipped), run.delivery
    assert _sidecars_on_disk(work, f"{media_id}-s0-0") == [
        f"{media_id}-s0-0.edl",
        f"{media_id}-s0-0.json",
        f"{media_id}-s0-0.measured.json",
        f"{media_id}-s0-0.srt",
    ]
    edl = Path(run.delivery.edl_path).read_text(encoding="utf-8")
    assert "FCM: DROP FRAME" in edl
    assert ";" in next(line for line in edl.splitlines() if line.startswith("001"))


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
        qc=_test_qc(True),
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
        transcript=a_transcript(
            "fractional", media_sha256=hashlib.sha256(fractional.read_bytes()).hexdigest()
        ),
        select_sentences=(0,),
        qc=_test_qc(True),
        verdict=a_verdict(100, 1_700),
    )
    assert isinstance(run.delivery, StageSkipped)
    assert "fractional frame rate" in run.delivery.reason
    assert attempted == ["ass"], f"wrote {attempted[1:]} before discovering the EDL refusal"
    assert not (work / "fractional-s0-0").exists()
    assert not tuple(work.glob(".fractional-s0-0.*.staging"))


# --- D-137: §6 assigns the video phase across both GPUs, and the code used one ---------------


def _query_preflight_exit(argv: list[str], tmp_path: Path) -> tuple[int, str]:
    import contextlib
    import io

    captured = io.StringIO()
    with contextlib.redirect_stderr(captured), contextlib.redirect_stdout(io.StringIO()):
        code = main([str(FIXTURE), "--work-dir", str(tmp_path / "work"), *argv])
    return code, captured.getvalue()


_CLI_PREFLIGHT_CASES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "two Stage 1 sources",
        ("--transcript", "missing.json", "--omni-asr"),
        "mutually exclusive Stage 1",
    ),
    ("runtime without OmniASR", ("--omni-asr-runtime", "wsl"), "require --omni-asr"),
    ("distro without OmniASR", ("--wsl-distro", "Ubuntu"), "require --omni-asr"),
    (
        "two cloud routes",
        ("--gemini", "--vertex-project", "project"),
        "mutually exclusive cloud routes",
    ),
    (
        "live cloud and stored verdict",
        ("--gemini", "--verdict", "missing.json"),
        "mutually exclusive Stage 4 sources",
    ),
    (
        # The loop lives only on the automatic path; accepting the flag beside `--sentences`
        # would silently do nothing while the operator believed five candidates were scored.
        "judge-top-n without auto-select",
        ("--judge-top-n", "5"),
        "--judge-top-n requires --auto-select",
    ),
    (
        "judging fewer than one candidate",
        ("--judge-top-n", "0", "--auto-select"),
        "--judge-top-n must be at least 1",
    ),
    (
        "a clip minimum that cannot hold a clip",
        ("--min-clip-seconds", "0"),
        "--min-clip-seconds must be greater than 0",
    ),
    ("Gemini without Stage 1", ("--gemini",), "cloud discovery requires"),
    (
        "Vertex without Stage 1",
        ("--vertex-project", "project"),
        "cloud discovery requires",
    ),
    ("selection without Stage 1", ("--sentences", "0"), "--sentences requires"),
    ("verdict without Stage 1", ("--verdict", "missing.json"), "--verdict requires"),
    (
        "verdict without selection",
        ("--transcript", "missing.json", "--verdict", "missing-verdict.json"),
        "--verdict requires",
    ),
    (
        "visual without Stage 1",
        ("--visual", "--visual-query", "پرسیار"),
        "--visual requires",
    ),
    (
        "query without visual",
        ("--transcript", "missing.json", "--visual-query", "پرسیار"),
        "--visual-query requires --visual",
    ),
    (
        "blank visual query",
        ("--transcript", "missing.json", "--visual", "--visual-query", "   "),
        "non-whitespace Sorani retrieval text",
    ),
    (
        "visual without a query source",
        ("--transcript", "missing.json", "--visual"),
        "--visual without Path A",
    ),
    ("QC without selection", ("--qc-record", "rec.json"), "--qc-record requires"),
    (
        "auto-selection without discovery",
        ("--transcript", "missing.json", "--auto-select"),
        "Stage 3 producer that can actually produce",
    ),
    (
        "TimeLens without selection",
        ("--timelens",),
        "--timelens requires",
    ),
    (
        "an invocation still passing the flag that was inverted",
        ("--face-reframe",),
        "--face-reframe is now the default and the flag is gone",
    ),
    (
        "two decoders asked for at once",
        ("--omni-asr", "--stock-decoder", "--omni-asr-adapter", "x"),
        "ask for different decoders",
    ),
    (
        "the base decoder without a Stage 1 run to draft with it",
        ("--stock-decoder",),
        "--stock-decoder applies only to a Stage 1 run",
    ),
    (
        "confidential without cloud",
        ("--confidential",),
        "governance flags apply only",
    ),
    (
        "ZDR without cloud",
        ("--zero-data-retention",),
        "governance flags apply only",
    ),
    (
        "ZDR attribution without cloud",
        ("--zdr-confirmed-by", "Hawa"),
        "governance flags apply only",
    ),
)


@pytest.mark.parametrize(
    ("label", "flags", "expected"),
    _CLI_PREFLIGHT_CASES,
    ids=[label for label, _flags, _expected in _CLI_PREFLIGHT_CASES],
)
def test_every_reachable_cli_prerequisite_refuses_at_its_own_boundary(
    tmp_path: Path, label: str, flags: tuple[str, ...], expected: str
) -> None:
    """An exit-2 assertion alone passes when a later unrelated failure kills the run. D-181."""
    code, stderr = _query_preflight_exit(list(flags), tmp_path)

    assert code == 2, label
    assert expected in stderr, f"{label}: {stderr}"
    assert not (tmp_path / "work").exists(), label


def _preflight_value_error_messages() -> tuple[str, ...]:
    """Read the direct pre-input refusals so a future guard cannot arrive uncovered.

    Reads `_build_and_run`, not `_run_from_args`, for the same reason
    `_preflight_refusal_sources` above already does: D-A2 moved every validation this walks into
    a function `durable_workflow.py`'s DBOS step can also call, leaving `_run_from_args` a thin
    catch-and-print wrapper with no refusals of its own. Walking the old name found zero
    assignments and raised `min() arg is an empty sequence` — a vacuous pass waiting to happen
    had the `min()` had a default. D-A26.
    """
    import ast

    source = (ROOT / "src" / "hawedit" / "pipeline.py").read_text(encoding="utf-8")
    function = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "_build_and_run"
    )
    input_boundary = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "transcript" for target in node.targets
        )
    )
    messages: list[str] = []
    for node in ast.walk(function):
        if not (
            isinstance(node, ast.Raise)
            and node.lineno < input_boundary
            and isinstance(node.exc, ast.Call)
            and getattr(node.exc.func, "id", None) == "ValueError"
            and node.exc.args
        ):
            continue
        argument = node.exc.args[0]
        if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
            raise AssertionError(f"preflight refusal at line {node.lineno} has a dynamic message")
        messages.append(argument.value)
    pre_empted = {message for message, _by in _PRE_EMPTED_REFUSALS}
    return tuple(message for message in messages if message not in pre_empted)


def test_the_case_table_is_bound_bidirectionally_to_every_preflight_refusal() -> None:
    """A new guard needs a case; a removed guard cannot leave a decorative stale case."""
    messages = _preflight_value_error_messages()
    fragments = {expected for _label, _flags, expected in _CLI_PREFLIGHT_CASES}
    matches = {
        message: sorted(fragment for fragment in fragments if fragment in message)
        for message in messages
    }

    assert all(len(found) == 1 for found in matches.values()), (
        f"preflight refusals need exactly one case fragment: {matches}"
    )
    orphaned = sorted(
        fragment for fragment in fragments if not any(fragment in message for message in messages)
    )
    assert orphaned == [], f"cases naming no live preflight refusal: {orphaned}"


def test_a_legal_argv_gets_past_every_preflight_refusal(tmp_path: Path) -> None:
    """Control: an implementation that refused every invocation passes negative cases alone."""
    code, stderr = _query_preflight_exit(
        ["--transcript", "missing.json", "--sentences", "0", "--qc-record", "rec.json"], tmp_path
    )

    assert code == 2, stderr
    assert "missing.json" in stderr
    for message in _preflight_value_error_messages():
        assert message not in stderr, f"legal argv hit preflight refusal: {message}"


def test_auto_select_refuses_visual_without_a_query_before_stage_zero(tmp_path: Path) -> None:
    code, stderr = _query_preflight_exit(
        ["--transcript", "missing.json", "--visual", "--auto-select"], tmp_path
    )

    assert code == 2, stderr
    assert "--visual-query" in stderr
    assert not (tmp_path / "work").exists()


def test_auto_select_accepts_path_a_without_an_explicit_visual_query(tmp_path: Path) -> None:
    code, stderr = _query_preflight_exit(
        ["--transcript", "missing.json", "--gemini", "--auto-select"], tmp_path
    )

    assert code == 2, stderr
    assert "Stage 3 producer" not in stderr


def test_auto_select_still_refuses_when_no_discovery_path_is_enabled(tmp_path: Path) -> None:
    code, stderr = _query_preflight_exit(
        ["--transcript", "missing.json", "--auto-select"], tmp_path
    )

    assert code == 2, stderr
    assert "Stage 3 producer" in stderr
    assert not (tmp_path / "work").exists()


def test_visual_query_without_visual_is_refused_by_the_earlier_contract(tmp_path: Path) -> None:
    code, stderr = _query_preflight_exit(
        ["--transcript", "missing.json", "--visual-query", "query", "--auto-select"],
        tmp_path,
    )

    assert code == 2, stderr
    assert "--visual-query requires --visual" in stderr


def test_blank_visual_query_is_refused_before_stage_zero(tmp_path: Path) -> None:
    code, stderr = _query_preflight_exit(
        [
            "--transcript",
            "missing.json",
            "--visual",
            "--visual-query",
            "   ",
            "--auto-select",
        ],
        tmp_path,
    )

    assert code == 2, stderr
    assert "non-whitespace" in stderr
    assert not (tmp_path / "work").exists()


def test_no_producer_report_names_the_query_path_b_needs() -> None:
    from hawedit.pipeline import _STAGE_3_DISCOVERY

    assert "--visual-query" in _STAGE_3_DISCOVERY.reason


# --- D-146: a stage that ran reported nothing about itself -------------------------------------


def _spoken(start_ms: int, end_ms: int) -> Sentence:
    return Sentence(
        words=(Word(w="وشە.", start_ms=start_ms, end_ms=end_ms, conf=0.9),), complete=True
    )


def test_dead_air_is_measured_between_selected_sentences() -> None:
    """The real 38-minute source produced a 5,990 ms hole and nothing noticed.

    Every check in the pipeline was green and the rendered clip sat silent for six of its
    fifty-six seconds, because `qc.flags` was constructed empty on every run.
    """
    silent = (_spoken(0, 28_850), _spoken(34_840, 50_000))
    assert dead_air_flags(silent) == ("dead_air:28850-34840ms",)


def test_a_pause_short_enough_to_be_editing_is_not_a_finding() -> None:
    """A beat before a punchline is craft. The threshold is what separates it from a fault."""
    beat = (_spoken(0, 1_000), _spoken(1_000 + MAX_INTERNAL_SILENCE_MS, 4_000))
    assert dead_air_flags(beat) == ()

    fault = (_spoken(0, 1_000), _spoken(1_001 + MAX_INTERNAL_SILENCE_MS, 4_000))
    assert len(dead_air_flags(fault)) == 1


def test_every_hole_is_named_not_just_the_first() -> None:
    holes = (_spoken(0, 1_000), _spoken(5_000, 6_000), _spoken(9_000, 10_000))
    assert dead_air_flags(holes) == ("dead_air:1000-5000ms", "dead_air:6000-9000ms")


def test_dead_air_needs_two_sentences_to_have_a_gap_between_them() -> None:
    assert dead_air_flags(()) == ()
    assert dead_air_flags((_spoken(0, 60_000),)) == ()


def test_the_dead_air_limit_is_a_number_that_must_make_sense() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        dead_air_flags((_spoken(0, 1_000), _spoken(9_000, 10_000)), limit_ms=-1)


@needs_ffmpeg
def test_the_runner_refuses_a_stage_1_transcript_in_another_language(tmp_path: Path) -> None:
    """Measured: a real English interview produced a 78.6%-Latin `text_ckb` and every stage
    below accepted it. The runner must stop at Stage 1 and say why, before anything persists —
    Kurdish invariant #1 makes the canonical transcript write-once, so a wrong-language one
    committed to the store would have to be deleted by hand before the media could be re-run.
    """
    english = RawTranscript(
        media_id="fixture",
        text_ckb="The title is Media and Politics in Kurdistan",
        words=(
            Word(w="The", start_ms=100, end_ms=800, conf=0.9),
            Word(w="title.", start_ms=800, end_ms=1_700, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )
    run = run_pipeline(FIXTURE, tmp_path, media_id="fixture", transcript=english)

    assert isinstance(run.transcript, StageSkipped)
    assert "not Sorani Kurdish" in run.transcript.reason
    assert run.transcript.blocked_by == ("Sorani Kurdish source audio",)
    assert not run.complete
    # Nothing was written: the store must be untouched so a re-run with the right transcript
    # is not blocked by invariant #1.
    assert not (tmp_path / "transcripts" / "fixture.transcript.raw.json").exists()


# --- judge-top-n T1: the selector splits so the caller can own the loop --------------------


def _ranked(candidate_id: str, in_ms: int, out_ms: int, rank: int) -> MergedCandidate:
    return MergedCandidate(
        candidate_id=candidate_id,
        media_id="fixture",
        in_ms=in_ms,
        out_ms=out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        sources=(candidate_id,),
        verbal_rank=rank,
        visual_rank=None,
        verbal_score=0.5,
        visual_score=None,
        sv6d=None,
    )


_RUN_SENTENCES = (
    _spoken(1_000, 2_000),
    _spoken(2_000, 3_000),
    _spoken(5_000, 6_000),
    _spoken(10_000, 11_000),
)


def test_the_selector_returns_a_run_for_one_candidate() -> None:
    """The per-candidate half, extracted so the caller can ask it about every candidate.

    Judging only rank #1 is what produced two runs scoring hook 0.20 out of 26 and 18
    candidates. Asking more than one requires this to be answerable per candidate rather than
    once for the whole set.
    """
    best = _ranked("a", 4_000, 7_000, rank=0)
    second = _ranked("b", 500, 3_500, rank=1)

    assert _sentence_run_for_candidate(best, _RUN_SENTENCES) == (2,)
    # The longest contiguous complete run inside the span, not merely the first sentence.
    assert _sentence_run_for_candidate(second, _RUN_SENTENCES) == (0, 1)


def test_a_candidate_containing_no_whole_sentence_yields_no_run() -> None:
    """D-185 measured this as common rather than rare: 7 candidates spanning 3.48-3.96 s
    against sentences with a 6.72 s median, and zero wholly inside any candidate.

    It has to be answerable without spending a billed call to find out.
    """
    assert _sentence_run_for_candidate(_ranked("c", 1_200, 1_800, rank=0), _RUN_SENTENCES) == ()
    assert _sentence_run_for_candidate(_ranked("d", 3_100, 4_900, rank=0), _RUN_SENTENCES) == ()


def test_auto_selection_still_picks_what_it_picked_before() -> None:
    """T1 is a refactor. The whole-set behaviour must be byte-identical to the loop it replaced:
    candidates in `_candidate_priority` order, first one with an eligible run wins."""
    best = _ranked("a", 4_000, 7_000, rank=0)
    second = _ranked("b", 500, 3_500, rank=1)

    assert _automatic_sentence_selection((best, second), _RUN_SENTENCES) == (2,)
    assert _automatic_sentence_selection((second, best), _RUN_SENTENCES) == (2,)

    # A rank-0 candidate with nothing inside it is skipped, not allowed to end the search.
    barren = _ranked("e", 1_200, 1_800, rank=0)
    assert _automatic_sentence_selection((barren, second), _RUN_SENTENCES) == (0, 1)
    assert _automatic_sentence_selection((), _RUN_SENTENCES) == ()


# --- judge-top-n T2: more than one candidate reaches the judge -----------------------------


def _verbal(candidate_id: str, in_ms: int, out_ms: int, rank: int) -> Candidate:
    return Candidate(
        candidate_id, "judged", in_ms, out_ms, DiscoveryPath.VERBAL, rank=rank, score=0.9
    )


class _RecordingJudge:
    """A judge that records every request and answers each one on its own span."""

    model_id = "gemini-2.5-pro"

    def __init__(self) -> None:
        self.seen: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        self.seen.append(request)
        return replace(
            a_verdict(request.clip_in_ms, request.clip_out_ms),
            candidate_id=request.candidate_id,
        )


def test_more_than_one_candidate_can_be_judged(tmp_path: Path) -> None:
    """Stage 4 judged exactly one candidate and the run lived or died on that sample.

    Measured twice on real episodes: 26 candidates -> 1 judged -> hook 0.20, and 18 candidates
    -> 1 judged -> hook 0.20. Nothing established rank #1 was the best candidate, only that it
    ranked first by discovery score, which knows nothing about editorial quality.
    """
    judge = _RecordingJudge()
    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("v1", 0, 1_800, rank=1),
            _verbal("v2", 1_900, 4_200, rank=2),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=3,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    assert len(judge.seen) == 2, "both eligible candidates should have reached the judge"
    assert {request.candidate_id for request in judge.seen} == {"v1", "v2"}


def test_an_ineligible_candidate_costs_no_billed_call(tmp_path: Path) -> None:
    """A candidate with no complete sentence inside it cannot become a clip, and finding that
    out must not cost a Stage 4 request.

    D-185 measured this as the common case rather than the rare one: 7 candidates spanning
    3.48-3.96 s against sentences with a 6.72 s median, and zero wholly inside any candidate.
    At N=5 that would be five billed calls to learn nothing.
    """
    judge = _RecordingJudge()
    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("barren", 1_750, 1_880, rank=1),
            _verbal("real", 0, 1_800, rank=2),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=5,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    assert [request.candidate_id for request in judge.seen] == ["real"], (
        "the candidate containing no whole sentence must be skipped before the billed call"
    )


def test_every_verdict_is_persisted_even_when_render_is_refused(tmp_path: Path) -> None:
    """A refused render discarded a billed verdict.

    Measured on the real 75-minute run: `work/ep10/stage4/` held an empty keyframe directory
    and nothing else, so an 18-candidate episode kept no record of what Gemini actually said and
    a re-run would pay for the same answer again.
    """
    work = tmp_path / "work"
    judge = _RecordingJudge()
    run_pipeline(
        FIXTURE,
        work,
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("v1", 0, 1_800, rank=1),
            _verbal("v2", 1_900, 4_200, rank=2),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=3,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    persisted = sorted(path.name for path in (work / "stage4").rglob("verdict.json"))
    assert len(persisted) == len(judge.seen), (
        f"every billed verdict must survive the run: {len(judge.seen)} judged, "
        f"{len(persisted)} on disk"
    )
    stored = json.loads(next((work / "stage4").rglob("verdict.json")).read_text(encoding="utf-8"))
    assert stored["judge"] == "gemini-2.5-pro"


# --- judge-top-n T3: the best passing verdict ships ----------------------------------------


class _ScoringJudge:
    """Answers each candidate with the hook score its id is mapped to."""

    model_id = "gemini-2.5-pro"

    def __init__(self, hooks: dict[str, float]) -> None:
        self.hooks = hooks
        self.seen: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        self.seen.append(request)
        return replace(
            a_verdict(request.clip_in_ms, request.clip_out_ms),
            candidate_id=request.candidate_id,
            hook_score=self.hooks[request.candidate_id],
        )


def test_the_best_passing_candidate_wins_not_the_first(tmp_path: Path) -> None:
    """Discovery rank is what produced two runs scoring hook 0.20.

    `_candidate_priority` orders by discovery rank and knows nothing about editorial quality, so
    spending N billed calls and then shipping rank order would reach the same answer more
    expensively. The strongest verdict wins.
    """
    judge = _ScoringJudge({"v1": 0.78, "v2": 0.95})
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("v1", 0, 1_800, rank=1),
            _verbal("v2", 1_900, 4_200, rank=2),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=3,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    assert len(judge.seen) == 2, "both candidates should have been judged"
    assert run.clip is not None and run.clip.editorial is not None
    assert run.clip.editorial.hook_score == 0.95, "the strongest verdict must be the one that ships"
    # And the clip really is the second candidate's footage, not the first's with a borrowed
    # score. Asserted on the out-point: §5 fuses the in-point *outward* from the anchor toward
    # a VAD onset or shot cut, so a clip anchored at 1,900 ms legitimately starts earlier
    # (measured here: 1,834 ms). The out-point reaching sentence 1's end is what proves which
    # footage was chosen.
    assert run.clip.out_ms >= 4_100


def test_a_stronger_but_failing_candidate_does_not_win(tmp_path: Path) -> None:
    """Best *passing*, not best. A 0.99 hook with a misleading-edit risk over §8.2's ceiling is
    exactly the clip D-253 exists to refuse."""
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("v1", 0, 1_800, rank=1),
            _verbal("v2", 1_900, 4_200, rank=2),
        ],
        judge=_FailingHighScorer({"v1": 0.80, "v2": 0.99}, failing="v2"),
        auto_select=True,
        judge_top_n=3,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    assert run.clip is not None and run.clip.editorial is not None
    assert run.clip.editorial.hook_score == 0.80, (
        "the 0.99 candidate breached the misleading-edit ceiling and must not have been chosen"
    )


class _FailingHighScorer(_ScoringJudge):
    """Like `_ScoringJudge`, but one named candidate breaches §8.2's misleading-edit ceiling."""

    def __init__(self, hooks: dict[str, float], failing: str) -> None:
        super().__init__(hooks)
        self.failing = failing

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        verdict = super().judge(request)
        if request.candidate_id == self.failing:
            return replace(verdict, misleading_edit_risk=0.40)
        return verdict


def test_no_passing_candidate_refuses_and_names_every_score(tmp_path: Path) -> None:
    """Measured on two real episodes: every judged candidate scored hook 0.20.

    "No candidate passed" without the numbers costs the operator another billed run to learn
    what was close, and the run that produced them was billed already.
    """
    judge = _ScoringJudge({"v1": 0.20, "v2": 0.31})
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("v1", 0, 1_800, rank=1),
            _verbal("v2", 1_900, 4_200, rank=2),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=3,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    skipped = dict(run.skipped())
    assert "editorial" in skipped, "no shippable verdict must be a visible refusal"
    reason = skipped["editorial"].reason
    assert "0.20" in reason and "0.31" in reason, f"every score must be named: {reason}"
    assert "v1" in reason and "v2" in reason, f"every candidate must be named: {reason}"
    assert run.render is None or isinstance(run.render, StageSkipped)


# --- judge-top-n T4: the flag ---------------------------------------------------------------


def test_judge_top_n_defaults_and_is_bounded() -> None:
    """Hawa set the default at 5 on 2026-08-26: roughly $2-$3.50 a run at §3's Stage 4 rates.

    Left unset it resolves to that; the parser default is `None` so an explicit value can be
    told apart from an absent one, which is what lets the flag be refused when it cannot act.
    """
    assert build_parser().parse_args(["source.mp4"]).judge_top_n is None
    assert DEFAULT_JUDGE_TOP_N == 5

    parsed = build_parser().parse_args(["source.mp4", "--judge-top-n", "3"])
    assert parsed.judge_top_n == 3


def test_judging_fewer_than_one_candidate_is_refused() -> None:
    """Zero billed calls is not a cheaper run, it is a run that cannot produce a clip."""
    with pytest.raises(ValueError, match="at least 1"):
        _judgeable_plans((), (), 0, MIN_CANDIDATE_SPAN_MS)


def test_the_flag_is_refused_when_it_cannot_act(tmp_path: Path) -> None:
    """The loop only exists on the `--auto-select` path — `--sentences` is a decision the
    operator already made, and re-ranking it would judge footage they did not ask for.

    Accepting `--judge-top-n 5` there would silently do nothing, which §1 calls the expensive
    kind of wrong: the operator would believe five candidates were considered.
    """
    transcript = tmp_path / "transcript.json"
    transcript.write_text(a_transcript("fixture").to_json(), encoding="utf-8")
    code = main(
        [
            str(FIXTURE),
            "--work-dir",
            str(tmp_path / "work"),
            "--media-id",
            "fixture",
            "--transcript",
            str(transcript),
            "--judge-top-n",
            "5",
        ]
    )
    assert code == 2, "a flag that cannot act must be refused, not ignored"


def test_n_of_one_is_todays_behaviour(tmp_path: Path) -> None:
    """The escape hatch back to the original cost. One candidate judged, one billed call."""
    judge = _RecordingJudge()
    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="judged",
        transcript=a_transcript("judged"),
        discover=lambda _n: [
            _verbal("v1", 0, 1_800, rank=1),
            _verbal("v2", 1_900, 4_200, rank=2),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=1,
        # The fixture transcript is 4.1 s long, so D-254's 30 s floor refuses every
        # candidate in it on length alone. Naming the floor here says 'this source is
        # a toy' at the call site instead of leaving a reader to wonder.
        min_clip_ms=4_000,
    )
    assert len(judge.seen) == 1, "N=1 must cost exactly one billed call"


def test_the_escalation_line_quotes_a_reason_that_actually_escalated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The count and the reason have to describe the same segments.

    Measured on the real 20-minute episode: the report read "277/306 segment(s) (91%) escalated
    for human validation — confident (mean logprob -5.699) and the models agree". That reason
    belongs to `escalation[0]`, whose `escalate` is **False** — so an alarming count was printed
    beside a reassuring explanation of a segment that was never escalated. A reader would take
    it as "91% flagged, but the models agree, so it is fine".
    """
    from hawedit.escalation import EscalationDecision

    run = PipelineRun(
        media_id="m",
        source="s",
        work_dir="w",
        escalation=(
            EscalationDecision(segment_id="0-1", escalate=False, reason="confident and agreeing"),
            EscalationDecision(segment_id="1-2", escalate=True, reason="the models disagree"),
        ),
    )
    _print_report(run)
    line = next(text for text in capsys.readouterr().out.splitlines() if text.startswith("stage 1"))
    assert "1/2" in line
    assert "the models disagree" in line
    assert "confident and agreeing" not in line, (
        "the quoted reason must belong to a segment that was actually escalated"
    )


# --- candidate-span T1: the target range is a decision, not a derivation --------------------


def test_the_target_range_is_a_named_decision() -> None:
    """BLUEPRINT.md states no clip duration anywhere.

    Its only fixed duration is `max_speech_duration_s=38`, which governs ASR *input*. The
    20-55 s figure quoted around this project comes from `.claude/skills/pro-kurdish-reel`,
    an operator runbook, not from §3 — so this range is the owner's decision on the same
    footing as `MIN_HOOK_SCORE`, and changing it should read as a changed decision rather
    than a tweaked constant.
    """
    assert MIN_CANDIDATE_SPAN_MS == 30_000
    assert MAX_CANDIDATE_SPAN_MS == 90_000
    assert MIN_CANDIDATE_SPAN_MS < MAX_CANDIDATE_SPAN_MS

    blueprint = (ROOT / "BLUEPRINT.md").read_text(encoding="utf-8")
    assert "30-90" not in blueprint and "30–90" not in blueprint, (
        "if the frozen spec ever states a clip duration, this constant must cite it instead "
        "of standing as an owner decision"
    )


# --- candidate-span T2: the answer is counted, not assumed ----------------------------------


def _a_span(candidate_id: str, in_ms: int, out_ms: int, *, verbal: bool) -> MergedCandidate:
    return MergedCandidate(
        candidate_id=candidate_id,
        media_id="ep10",
        in_ms=in_ms,
        out_ms=out_ms,
        discovery_path=DiscoveryPath.VERBAL if verbal else DiscoveryPath.VISUAL,
        sources=(candidate_id,),
        verbal_rank=1 if verbal else None,
        visual_rank=None if verbal else 1,
        verbal_score=0.9 if verbal else None,
        visual_score=None if verbal else 0.5,
    )


def test_span_compliance_is_measured_not_assumed() -> None:
    """A prompt is a request. This repository has learned that twice already.

    `encoder_available` exists because a build listing an encoder is not one that can use it,
    and D-249 measured `-crf` being silently ignored by NVENC. A model told a duration is the
    same case: T2 puts the range in the prompt, and this counts what actually came back. The
    fixture deliberately ignores the instruction in both directions, so a report that assumed
    compliance would read 3 of 3 here.
    """
    run = PipelineRun(
        media_id="ep10",
        source="x",
        work_dir="w",
        candidates=(
            _a_span("in-range", 0, 45_000, verbal=True),
            _a_span("too-short", 60_000, 65_300, verbal=True),
            _a_span("too-long", 100_000, 220_000, verbal=True),
            _a_span("visual", 300_000, 345_000, verbal=False),
        ),
    )
    reported = run.to_dict()["discovery"]["in_target_span"]

    assert reported == {"asked": 3, "in_range": 1}, (
        "Path A returned three spans and one of them honoured the range; a report claiming "
        "otherwise would hide the thing D-254 exists to watch"
    )


def test_span_compliance_counts_only_what_path_a_answered() -> None:
    """The control. Counting the whole merged set would credit Path B for Path A's compliance,
    and a visual-only run would report a compliance figure for a prompt nobody sent.
    """
    visual_only = PipelineRun(
        media_id="ep10",
        source="x",
        work_dir="w",
        candidates=(_a_span("visual", 0, 45_000, verbal=False),),
    )
    assert visual_only.to_dict()["discovery"]["in_target_span"] == {"asked": 0, "in_range": 0}


# --- candidate-span T3: a seed grows into something that can carry a point -------------------


def _unfinished(start_ms: int, end_ms: int) -> Sentence:
    """A sentence §4.2 could not confirm finished. Kurdish invariant #2: never render one."""
    return Sentence(
        words=(Word(w="وشە", start_ms=start_ms, end_ms=end_ms, conf=0.9),), complete=False
    )


# Twenty complete five-second sentences, 0..100 s. Long enough that growth can actually reach
# the 30 s minimum, which the older fixtures in this file are deliberately too small to do.
_EPISODE_SENTENCES = tuple(_spoken(index * 5_000, (index + 1) * 5_000) for index in range(20))


def test_a_short_candidate_grows_to_the_target() -> None:
    """The 5.3-second span is the real one. It scored hook 0.90 and misleading-edit 0.85.

    Measured on the 75-minute episode with live gemini-2.5-pro: the strongest candidate in the
    set was five seconds long, and a five-second cut of a conversation is close to definitionally
    not self-contained. The seed is kept and the span around it is grown to D-254's minimum on
    complete sentence boundaries, alternating outward so the moment the judge liked does not end
    up at an edge of the clip.
    """
    seeded = _ranked("hot", 40_000, 45_300, rank=1)
    grown = _grown_sentence_run(seeded, _EPISODE_SENTENCES, MIN_CANDIDATE_SPAN_MS)

    assert _run_span_ms(grown, _EPISODE_SENTENCES) >= MIN_CANDIDATE_SPAN_MS, (
        "the grown span still cannot carry a whole argument, which is the entire mechanism"
    )
    assert grown == (5, 6, 7, 8, 9, 10), (
        "growth alternates outward from the seed; sentence 8 is the seed and stays away from "
        "both edges"
    )
    assert 8 in grown, "the moment the judge found must survive its own clip"
    # It stops *at* the minimum rather than running on to the maximum: every second of grown
    # video is billed at roughly 300 tokens.
    assert _run_span_ms(grown, _EPISODE_SENTENCES) == MIN_CANDIDATE_SPAN_MS


def test_growth_stops_at_complete_sentence_boundaries() -> None:
    """Kurdish invariant #2 outranks the target range.

    An incomplete sentence is one §4.2 could not confirm finished, and rendering one is the
    invariant this system refuses to break. So growth stops at that fence and returns a span
    short of the minimum — a real answer about the footage — rather than crossing it.
    """
    fenced = (
        _spoken(0, 5_000),
        _unfinished(5_000, 10_000),
        _spoken(10_000, 15_000),
        _spoken(15_000, 20_000),
        _spoken(20_000, 25_000),
        _unfinished(25_000, 30_000),
        _spoken(30_000, 35_000),
    )
    grown = _grown_sentence_run(
        _ranked("hot", 15_000, 20_000, rank=1), fenced, MIN_CANDIDATE_SPAN_MS
    )

    assert grown == (2, 3, 4), "growth crossed a sentence §4.2 could not confirm finished"
    assert all(fenced[index].complete for index in grown)
    assert _run_span_ms(grown, fenced) < MIN_CANDIDATE_SPAN_MS, (
        "this test is blind unless growth genuinely stopped short of the target"
    )


def test_a_candidate_already_in_range_is_left_alone() -> None:
    """A candidate the model got right is not something to improve.

    Also the over-long case, settled by the owner on 2026-08-27: a 90 s+ span is a real clip,
    and trimming it to hit a number would invent an edit nobody asked for. Both take the same
    branch — at or above the minimum, the ungrown answer stands.
    """
    in_range = _ranked("fine", 0, 45_000, rank=1)
    assert _grown_sentence_run(
        in_range, _EPISODE_SENTENCES, MIN_CANDIDATE_SPAN_MS
    ) == _sentence_run_for_candidate(in_range, _EPISODE_SENTENCES)

    over_long = _ranked("long", 0, 100_000, rank=1)
    assert _grown_sentence_run(
        over_long, _EPISODE_SENTENCES, MIN_CANDIDATE_SPAN_MS
    ) == _sentence_run_for_candidate(over_long, _EPISODE_SENTENCES)
    assert (
        _run_span_ms(
            _grown_sentence_run(over_long, _EPISODE_SENTENCES, MIN_CANDIDATE_SPAN_MS),
            _EPISODE_SENTENCES,
        )
        > MAX_CANDIDATE_SPAN_MS
    ), "the over-long span was cut to fit the maximum"


def test_a_candidate_smaller_than_every_sentence_still_seeds() -> None:
    """ep01's case, and the reason growth cannot depend on containment.

    Measured on the real 20-minute episode: 1 of 15 candidates was eligible, because its
    sentences run a 10.2 s median against candidates of about 5 s, so no complete sentence lay
    *wholly inside* almost any of them. Seeding from the sentences a candidate overlaps inverts
    that containment test instead of loosening `_complete_sentences_within`, which stays exactly
    as it is because `_rejected_candidates` shares it.
    """
    long_sentences = tuple(_spoken(index * 20_000, (index + 1) * 20_000) for index in range(6))
    inside_one = _ranked("tiny", 25_000, 30_300, rank=1)

    assert _sentence_run_for_candidate(inside_one, long_sentences) == (), (
        "the fixture no longer reproduces ep01; this test would prove nothing"
    )
    grown = _grown_sentence_run(inside_one, long_sentences, MIN_CANDIDATE_SPAN_MS)
    assert grown == (0, 1), "the overlapped sentence is the seed, and it grows from there"
    assert _run_span_ms(grown, long_sentences) >= MIN_CANDIDATE_SPAN_MS


# --- candidate-span T4: a fragment is refused before it is billed ---------------------------


def test_a_candidate_that_cannot_reach_the_minimum_is_refused() -> None:
    """Growth is an attempt, not a promise, and the attempt can fail.

    An episode can simply run out of complete sentences around a seed — at its edges, or across
    a stretch §4.2 could not confirm finished. What comes back is then a fragment, and §2's
    editorial gate has already been measured scoring one: hook 0.90 against misleading-edit 0.85
    on 5.3 seconds. That verdict costs a billed Stage 4 request to read, so the refusal belongs
    before the call rather than after it.
    """
    short_episode = (_spoken(0, 4_000), _spoken(4_000, 8_000))
    candidate = _ranked("doomed", 1_000, 2_000, rank=1)

    grown = _grown_sentence_run(candidate, short_episode, MIN_CANDIDATE_SPAN_MS)
    assert grown == (0, 1), "growth must take everything available before giving up"
    assert _run_span_ms(grown, short_episode) < MIN_CANDIDATE_SPAN_MS

    assert _judgeable_plans((candidate,), short_episode, 5, MIN_CANDIDATE_SPAN_MS) == (), (
        "a span the gate will refuse as a fragment must not reach a billed judge first"
    )
    # The control: the same candidate against a floor its episode can satisfy.
    assert _judgeable_plans((candidate,), short_episode, 5, 8_000) != ()


def test_the_reason_names_the_length_and_the_floor() -> None:
    """ "Ineligible" without the numbers costs the operator another run to learn what was close.

    Two different failures live here and they want different answers: an episode that ran out of
    complete sentences is not a retrieval window that landed in silence, and telling an operator
    the second when the first happened sends them to widen a window that was never the problem.
    """
    short_episode = (_spoken(0, 4_000), _spoken(4_000, 8_000))
    ran_out = _ranked("doomed", 1_000, 2_000, rank=1)
    silent = _ranked("silent", 8_500, 9_000, rank=2)

    skipped = _nothing_fits_a_candidate((ran_out,), short_episode, MIN_CANDIDATE_SPAN_MS)
    assert "8.00s" in skipped.reason, skipped.reason
    assert "30.00s minimum" in skipped.reason, skipped.reason
    assert skipped.blocked_by == ("a candidate that grows to the target minimum",)

    # The other cause keeps D-185's wording, because for that candidate it is still true.
    nothing = _nothing_fits_a_candidate((silent,), short_episode, MIN_CANDIDATE_SPAN_MS)
    assert nothing.blocked_by == ("no complete sentence fits a candidate window",)

    rejected = _rejected_candidates(
        (ran_out, silent),
        _ranked("won", 0, 8_000, rank=0),
        short_episode,
        None,
        MIN_CANDIDATE_SPAN_MS,
    )
    reasons = {record.in_ms: record.reject_reason for record in rejected}
    assert "grew to 8.00s" in reasons[1_000] and "30.00s minimum" in reasons[1_000], reasons
    assert "nothing to grow a clip around" in reasons[8_500], reasons


def test_the_cli_applies_the_target_minimum_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flag nothing reads is decoration. Measured at the seam, not asserted about the parser.

    `--min-clip-seconds` exists because a source genuinely shorter than the floor still deserves
    a clip; the point of the default is that an operator who never thinks about clip length gets
    the owner's number rather than no floor at all.
    """
    seen: dict[str, Any] = {}

    def recorder(*_args: Any, **kwargs: Any) -> PipelineRun:
        seen.update(kwargs)
        return PipelineRun(media_id="cli", source="s", work_dir="w")

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", recorder)
    transcript = tmp_path / "transcript.raw.json"
    transcript.write_text(a_transcript("cli").to_json(), encoding="utf-8")
    argv = [
        str(FIXTURE),
        "--transcript",
        str(transcript),
        "--work-dir",
        str(tmp_path / "work"),
    ]

    _build_and_run(build_parser().parse_args(argv))
    assert seen["min_clip_ms"] == MIN_CANDIDATE_SPAN_MS, "the CLI default is not D-254's floor"

    _build_and_run(build_parser().parse_args([*argv, "--min-clip-seconds", "7.5"]))
    assert seen["min_clip_ms"] == 7_500, "the operator's override never reached the pipeline"


# --- reframe-composition T1: tracking is what you get without asking ------------------------


def _tracker_for(argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    """Drive `_build_and_run` far enough to see which subject tracker it built."""
    seen: dict[str, Any] = {}

    def recorder(*_args: Any, **kwargs: Any) -> PipelineRun:
        seen.update(kwargs)
        return PipelineRun(media_id="cli", source="s", work_dir="w")

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", recorder)
    transcript = tmp_path / "transcript.raw.json"
    transcript.write_text(a_transcript("cli").to_json(), encoding="utf-8")
    _build_and_run(
        build_parser().parse_args(
            [
                str(FIXTURE),
                "--transcript",
                str(transcript),
                "--work-dir",
                str(tmp_path / "work"),
                "--sentences",
                "0",
                *argv,
            ]
        )
    )
    return seen.get("subject_tracker")


def test_face_tracking_is_the_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The old default rendered a wall.

    Measured 2026-08-27 on the real 20-minute episode: the same clip, same span, rendered twice.
    With the centred crop both speakers sat cut off at the edges of frame and the middle held an
    empty wall and table; with tracking it was a usable clip. A default that produces something
    nobody would post is not a default. D-258.
    """
    assert _tracker_for([], tmp_path, monkeypatch) is not None, (
        "an operator who asks for nothing must get the framing that works"
    )


def test_static_crop_opts_out_and_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old behaviour stays reachable, and the artifact still names which was used.

    `Reframe.STATIC_CENTRE` travels onto the clip contract, so two runs that differ in framing
    are distinguishable afterwards without anyone having to remember which was which.
    """
    assert _tracker_for(["--static-crop"], tmp_path, monkeypatch) is None
    assert Reframe.STATIC_CENTRE.value == "static_centre"


def test_the_replaced_flag_says_what_replaced_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inverting a flag breaks every saved invocation that used it.

    argparse would answer "unrecognized arguments: --face-reframe", which reads as a typo rather
    than as a decision. The refusal names its replacement instead.
    """
    transcript = tmp_path / "transcript.raw.json"
    transcript.write_text(a_transcript("cli").to_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="--static-crop for the old centred behaviour"):
        _build_and_run(
            build_parser().parse_args(
                [
                    str(FIXTURE),
                    "--transcript",
                    str(transcript),
                    "--work-dir",
                    str(tmp_path / "work"),
                    "--sentences",
                    "0",
                    "--face-reframe",
                ]
            )
        )


def test_a_missing_face_tracker_degrades_visibly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """OpenCV is an extra, and the default must not hard-fail on a missing optional dependency.

    §1 is fail visible, not silent: falling back without saying so would leave an operator
    comparing two runs that differ in framing for no stated reason.
    """
    real_import = builtins.__import__

    def refuse(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "hawedit.reframe":
            raise ImportError("No module named 'cv2'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    tracker = _tracker_for([], tmp_path, monkeypatch)

    assert tracker is None, "a missing tracker must not stop the run"
    noted = capsys.readouterr().err
    assert "face tracking is the default but OpenCV is not installed" in noted, noted
    assert "--static-crop" in noted, "the note must say how to ask for this deliberately"


def test_the_default_run_does_not_enable_diarization() -> None:
    """AC-2: The default pipeline run does not enable speaker diarization."""
    parsed = build_parser().parse_args(["source.mp4"])
    assert parsed.diarize is False
    assert parsed.diarize_device == "cpu"


def test_the_diarize_flag_reaches_run_pipeline_as_a_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1: Passing --diarize constructs a concrete PyannoteDiarizer and passes it."""
    from hawedit.pyannote_adapter import PyannoteDiarizer

    transcript = tmp_path / "transcript.raw.json"
    transcript.write_text(a_transcript("cli").to_json(), encoding="utf-8")

    captured_diarizer: Any = None

    def fake_run_pipeline(*args: Any, **kwargs: Any) -> Any:
        nonlocal captured_diarizer
        captured_diarizer = kwargs.get("diarizer")
        return None

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", fake_run_pipeline)

    _build_and_run(
        build_parser().parse_args(
            [
                str(FIXTURE),
                "--transcript",
                str(transcript),
                "--work-dir",
                str(tmp_path / "work"),
                "--sentences",
                "0",
                "--diarize",
                "--diarize-device",
                "cuda:0",
            ]
        )
    )

    assert isinstance(captured_diarizer, PyannoteDiarizer)
    assert captured_diarizer.device == "cuda:0"


def test_an_unavailable_diarizer_never_claims_speaker_tracking(tmp_path: Path) -> None:
    """pro-edit T7 / AC-9: When diarizer is unavailable, reframe stays face-tracked.

    The runner must never claim speaker tracking (speaker_face) without validated turns.
    """
    from hawedit.pipeline import Delivery
    from hawedit.pyannote_adapter import PyannoteDiarizer

    result = run_pipeline(
        FIXTURE,
        transcript=a_transcript(FIXTURE.stem),
        verdict=a_verdict(100, 1_700),
        qc=_test_qc(True, reviewed_sha256=FIXTURE_RENDER_S0_SHA256),
        work_dir=tmp_path / "work",
        select_sentences=(0,),
        diarizer=PyannoteDiarizer(),
    )

    assert result.render is not None
    assert isinstance(result.delivery, Delivery)
    contract = json.loads(Path(result.delivery.editing_json_path).read_text(encoding="utf-8"))
    assert contract["output"]["crop_target"] in {"face_tracked", "static_centre"}
    assert contract["output"]["crop_target"] != "speaker_face"
    assert result.clip is not None
    assert result.clip.output is not None
    assert result.clip.output.crop_target in {"face_tracked", "static_centre"}
    assert result.clip.output.crop_target != "speaker_face"


def test_cli_qc_record_validates_and_binds_to_clip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task T1.3 / Proof A: CLI parses --qc-record JSON file and binds to Qc."""
    source = tmp_path / "x.mp4"
    source.touch()
    transcript_path = tmp_path / "t.json"
    transcript_path.write_text(a_transcript().to_json(), encoding="utf-8")
    verdict_path = tmp_path / "v.json"
    verdict_path.write_text(
        json.dumps(a_verdict(0, 4_300).to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    record_path = tmp_path / "qc_record.json"
    record = QcRecord(
        reviewer="Hawa",
        reviewed_at="2026-09-02T19:00:00Z",
        mp4_sha256="0" * 64,
        seconds_watched=57.0,
        verdict="pass",
        notes="All speech verified",
    )
    record_path.write_text(record.to_json(), encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run(source_arg: Path, work_arg: Path, **kwargs: object) -> PipelineRun:
        captured.update(kwargs)
        return PipelineRun(media_id="source", source=str(source_arg), work_dir=str(work_arg))

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", fake_run)
    exit_code = main(
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
            "--qc-record",
            str(record_path),
        ]
    )
    assert exit_code == 1
    assert captured["qc"] == Qc(
        auto_pass=False,
        flags=(),
        human_reviewed=True,
        reviewed_by="Hawa",
        reviewed_at="2026-09-02T19:00:00Z",
        reviewed_sha256="0" * 64,
    )


def test_cli_refuses_removed_qc_pass_flag(tmp_path: Path) -> None:
    """Task T1.3: --qc-pass is retired; passing it exits with an argument error."""
    source = tmp_path / "x.mp4"
    source.touch()
    with pytest.raises(SystemExit) as exc_info:
        main([str(source), "--sentences", "0,1", "--qc-pass"])
    assert exc_info.value.code != 0


def test_cli_parses_profile_argument() -> None:
    """Task T1.9: CLI supports --profile default and --profile production."""
    parser = build_parser()
    args_default = parser.parse_args(["video.mp4"])
    assert args_default.profile == "default"

    args_prod = parser.parse_args(["video.mp4", "--profile", "production"])
    assert args_prod.profile == "production"

    with pytest.raises(SystemExit):
        parser.parse_args(["video.mp4", "--profile", "invalid_profile"])


@needs_ffmpeg
def test_the_production_profile_cannot_deliver_with_a_skipped_stage(
    tmp_path: Path,
) -> None:
    """Task T1.9: A run in production profile refuses delivery if any stage is StageSkipped."""
    work = tmp_path / "work"
    # Run pipeline with profile="production"
    # Stage 0 (diarizer) is omitted, so diarization is skipped.
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        qc=_test_qc(True),
        verdict=a_verdict(100, 4_100),
        profile="production",
    )
    assert isinstance(run.delivery, StageSkipped)
    assert "production_profile_skipped_stage" in run.delivery.reason
    # Delivery bundle must not be published
    assert not (work / "delivery" / "fixture-clip-0.mp4").exists()


@needs_ffmpeg
def test_the_contract_records_the_profile_used(tmp_path: Path) -> None:
    """Task T1.9: Clip provenance records the profile used for the run."""
    work = tmp_path / "work"
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        qc=_test_qc(True),
        verdict=a_verdict(100, 4_100),
        profile="production",
    )
    assert run.clip is not None
    assert run.clip.provenance is not None
    assert run.clip.provenance.profile == "production"
