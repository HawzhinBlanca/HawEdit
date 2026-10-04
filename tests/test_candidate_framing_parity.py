"""Camera contract tests on decoded media, not speaker-identity accuracy evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.diarization import Segment
from hawedit.discovery import Candidate
from hawedit.judge import JudgeRequest, JudgeVerdict
from hawedit.pipeline import PipelineRun, StageSkipped, run_pipeline
from hawedit.reframe import FocusPoint, SpeakerFocusPoint
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/kurdish-speech-3cuts.mp4"
_TEXT = (
    "\u0695\u06c6\u0698\u0646\u0627\u0645\u06d5\u0648\u0627\u0646\u06cc "
    "\u06a9\u0648\u0631\u062f\u06cc. \u0644\u06d5 "
    "\u0647\u06d5\u0648\u0644\u06ce\u0631."
)


def _a_transcript() -> RawTranscript:
    tokens = _TEXT.split()
    words = tuple(
        Word(token, start, end, confidence)
        for token, start, end, confidence in zip(
            tokens,
            (100, 800, 2_000, 2_400),
            (800, 1_500, 2_400, 4_100),
            (0.95, 0.94, 0.93, 0.92),
            strict=True,
        )
    )
    return RawTranscript(
        media_id="fixture",
        text_ckb=_TEXT,
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    )


class _Judge:
    model_id = "gemini-2.5-pro"

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        return JudgeVerdict(
            candidate_id=request.candidate_id,
            clip_in_ms=request.clip_in_ms,
            clip_out_ms=request.clip_out_ms,
            hook_score=0.95,
            self_contained=True,
            payoff_at_ms=(request.clip_in_ms + request.clip_out_ms) // 2,
            meaning_fidelity=0.9,
            misleading_edit_risk=0.05,
            cultural_landing=0.8,
            narrative_role="payoff",
            title_ckb=_TEXT.split()[0],
            description_ckb=_TEXT,
            hashtags_ckb=(),
            judge=self.model_id,
            payoff_strength=0.8,
            ends_on_a_beat=True,
            reason_ckb=_TEXT,
            title_variants_ckb=(_TEXT.split()[0], _TEXT, _TEXT.split()[1]),
        )


class _Diarizer:
    def __init__(self, turns: tuple[Segment, ...]) -> None:
        self.turns = turns

    def diarize(self, audio: Path) -> tuple[Segment, ...]:
        assert audio.is_file()
        return self.turns


class _Tracker:
    def __init__(self, outcome: str = "valid") -> None:
        self.outcome = outcome
        self.calls: list[tuple[int, int, tuple[Segment, ...]]] = []

    def track_speakers(
        self, source: Path, in_ms: int, out_ms: int, turns: Sequence[Segment]
    ) -> tuple[SpeakerFocusPoint, ...]:
        assert source == FIXTURE
        self.calls.append((in_ms, out_ms, tuple(turns)))
        if self.outcome == "runtime":
            raise RuntimeError("association backend unavailable")
        if self.outcome == "type-error":
            raise TypeError("association internal type error")
        if self.outcome == "empty":
            return ()
        if self.outcome == "invalid":
            return (SpeakerFocusPoint(in_ms + 100, 150, "WRONG_SPEAKER"),)
        if self.outcome == "three":
            return (
                SpeakerFocusPoint(100, 120, "SPEAKER_00"),
                SpeakerFocusPoint(700, 320, "SPEAKER_01"),
                SpeakerFocusPoint(1_300, 520, "SPEAKER_02"),
            )
        if self.outcome == "split":
            return (
                SpeakerFocusPoint(in_ms + 100, 150, "SPEAKER_00"),
                SpeakerFocusPoint(1_000, 490, "SPEAKER_01"),
            )
        return (SpeakerFocusPoint(in_ms + 100, 150, "SPEAKER_00"),)


class _ForbiddenFaceTracker:
    def __init__(self) -> None:
        self.calls = 0

    def track(
        self, source: Path, in_ms: int, out_ms: int, shot_cuts_ms: Sequence[int] = ()
    ) -> tuple[FocusPoint, ...]:
        self.calls += 1
        raise AssertionError("requested association or chosen split cannot become face tracking")


_SINGLE_TURN = (Segment(0, 1_950, "SPEAKER_00"),)
_TWO_TURNS = (Segment(0, 900, "SPEAKER_00"), Segment(900, 1_950, "SPEAKER_01"))


def _run(
    work: Path,
    route: str,
    tracker: _Tracker | None,
    *,
    turns: tuple[Segment, ...] | None = _SINGLE_TURN,
    split: str = "never",
    face: _ForbiddenFaceTracker | None = None,
) -> PipelineRun:
    candidate = Candidate("c1", "fixture", 100, 1_500, DiscoveryPath.VERBAL, 1, 0.95)
    return run_pipeline(
        FIXTURE,
        work,
        media_id="fixture",
        transcript=_a_transcript(),
        diarizer=_Diarizer(turns) if turns is not None else None,
        discover=lambda _: (candidate,),
        judge=_Judge(),
        auto_select=True,
        min_clip_ms=1_000,
        max_clips=1 if route == "episode" else None,
        speaker_tracker=tracker,
        subject_tracker=face,
        two_person_split=split,
        excise_fillers=False,
        profile="production",
    )


def _refusal(run: PipelineRun, route: str) -> str:
    assert run.render is None or isinstance(run.render, StageSkipped)
    assert run.clip is None
    if route == "episode":
        assert run.episode_manifest is not None
        assert run.episode_manifest.clips_count == 0
        assert len(run.episode_manifest.items) == 1
        item = run.episode_manifest.items[0]
        assert item.status == "failed"
        assert item.delivery_dir is None
        assert item.error is not None
        return item.error
    assert isinstance(run.render, StageSkipped)
    return run.render.reason


@pytest.mark.parametrize("route", ["single", "episode"])
@pytest.mark.parametrize("turns", [None, (Segment(2_800, 4_162, "SPEAKER_01"),)])
def test_requested_speaker_tracking_refuses_missing_turns_in_both_routes(
    tmp_path: Path, route: str, turns: tuple[Segment, ...] | None
) -> None:
    tracker = _Tracker()
    run = _run(tmp_path / "work", route, tracker, turns=turns)
    assert "measured diarization" in _refusal(run, route)
    assert tracker.calls == []
    assert not list((tmp_path / "work").glob("review/*/*.mp4"))


@pytest.mark.parametrize("route", ["single", "episode"])
def test_explicit_split_requires_speaker_evidence_without_provider(
    tmp_path: Path, route: str
) -> None:
    work = tmp_path / "work"
    run = _run(work, route, None, split="always")
    assert "speaker" in _refusal(run, route)
    assert not list(work.glob("review/*/*.mp4"))


@pytest.mark.parametrize("route", ["single", "episode"])
@pytest.mark.parametrize("outcome", ["runtime", "invalid", "empty", "type-error"])
def test_production_association_failure_never_substitutes_a_crop(
    tmp_path: Path, route: str, outcome: str
) -> None:
    tracker = _Tracker(outcome)
    face = _ForbiddenFaceTracker()
    work = tmp_path / "work"
    run = _run(work, route, tracker, face=face)
    reason = _refusal(run, route)
    assert "speaker" in reason or "association" in reason
    assert len(tracker.calls) == 1
    assert face.calls == 0
    assert not list(work.glob("review/*/*.mp4"))


@pytest.mark.parametrize("route", ["single", "episode"])
def test_episode_candidate_retains_validated_speaker_camera_evidence(
    tmp_path: Path, route: str
) -> None:
    tracker = _Tracker()
    work = tmp_path / "work"
    run = _run(work, route, tracker)
    assert run.clip is not None and run.clip.output is not None
    assert run.clip.output.crop_target == "speaker_face"
    assert len(tracker.calls) == 1
    assert tracker.calls[0] == (run.clip.in_ms, run.clip.out_ms, _SINGLE_TURN)
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    assert (run.render.width, run.render.height) == (1080, 1920)
    paths = list(work.glob("review/*/*.edit_plan.json"))
    assert len(paths) == 1
    plan = json.loads(paths[0].read_text(encoding="utf-8"))
    assert plan["config"]["reframe_mode"] == "speaker_tracked"
    assert plan["speaker_turns"] == [[0, 1_950, "SPEAKER_00"]]


@pytest.mark.parametrize("route", ["single", "episode"])
@pytest.mark.parametrize("split", ["always", "never"])
def test_episode_split_policy_is_executed_and_recorded_without_override(
    tmp_path: Path, route: str, split: str
) -> None:
    work = tmp_path / "work"
    run = _run(work, route, _Tracker("split"), turns=_TWO_TURNS, split=split)
    assert run.clip is not None and run.clip.output is not None
    expected = "two_person_split" if split == "always" else "speaker_face"
    assert run.clip.output.crop_target == expected
    paths = list(work.glob("review/*/*.edit_plan.json"))
    assert len(paths) == 1
    plan = json.loads(paths[0].read_text(encoding="utf-8"))
    assert plan["config"]["two_person_split"] == split
    assert plan["speaker_turns"] == [[0, 900, "SPEAKER_00"], [900, 1_950, "SPEAKER_01"]]


@pytest.mark.parametrize("route", ["single", "episode"])
def test_selected_split_cannot_be_overwritten_by_subject_tracker(
    tmp_path: Path, route: str
) -> None:
    face = _ForbiddenFaceTracker()
    run = _run(
        tmp_path / "work", route, _Tracker("split"), turns=_TWO_TURNS, split="always", face=face
    )
    assert run.clip is not None and run.clip.output is not None
    assert run.clip.output.crop_target == "two_person_split"
    assert face.calls == 0


def test_episode_tracking_refusal_preserves_honest_item_state(tmp_path: Path) -> None:
    work = tmp_path / "work"
    run = _run(work, "episode", _Tracker(), split="always")
    assert "only 1 distinct speaker" in _refusal(run, "episode")
    assert not list(work.glob("review/*/*.mp4"))
    assert not run.complete


@pytest.mark.parametrize("route", ["single", "episode"])
@pytest.mark.parametrize("split", ["always", "auto"])
def test_two_person_layout_never_drops_a_third_tracked_speaker(
    tmp_path: Path, route: str, split: str
) -> None:
    turns = (
        Segment(0, 600, "SPEAKER_00"),
        Segment(600, 1_200, "SPEAKER_01"),
        Segment(1_200, 1_950, "SPEAKER_02"),
    )
    work = tmp_path / "work"
    run = _run(work, route, _Tracker("three"), turns=turns, split=split)
    if split == "always":
        assert "exactly two" in _refusal(run, route)
        assert not list(work.glob("review/*/*.mp4"))
    else:
        assert run.clip is not None and run.clip.output is not None
        assert run.clip.output.crop_target == "speaker_face"
        paths = list(work.glob("review/*/*.edit_plan.json"))
        assert len(paths) == 1
        plan = json.loads(paths[0].read_text(encoding="utf-8"))
        assert plan["speaker_turns"] == [[t.start_ms, t.end_ms, t.speaker] for t in turns]


@pytest.mark.parametrize("route", ["single", "episode"])
def test_camera_parity_preserves_source_raw_and_private_review_contract(
    tmp_path: Path, route: str
) -> None:
    before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    work = tmp_path / "work"
    raw = _a_transcript()
    run = _run(work, route, _Tracker())
    assert run.clip is not None
    assert not run.complete
    assert run.clip.qc is None
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == before
    stored = json.loads(
        (work / "transcripts/fixture.transcript.raw.json").read_text(encoding="utf-8")
    )
    assert stored["text_ckb"] == raw.text_ckb
    assert stored["words"] == [asdict(word) for word in raw.words]
    plans = list(work.glob("review/*/*.edit_plan.json"))
    assert len(plans) == 1
    plan = json.loads(plans[0].read_text(encoding="utf-8"))
    assert plan["media_sha256"] == before
    assert list(work.glob("review/*/*.mp4"))
    assert not (work / run.clip.clip_id).exists()
    assert not list(work.glob("*.mp4"))
    assert len(run.billed_calls) == 1
    call = run.billed_calls[0]
    assert (call.candidate_id, call.stage, call.tokens, call.cost_usd_estimate) == (
        "c1",
        "editorial",
        0,
        0.0,
    )
