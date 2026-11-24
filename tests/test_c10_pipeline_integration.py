"""Integration tests for Lane D (D-359): pipeline wiring and broadcast quality scorecard.

Covers:
- AC-D1: End-to-end wiring of Stage 3 acoustic signals, explicit `--encoder`, intra-shot
  active-speaker switches, non-face `BLURRED_FILL`, and clip-only Sorani caption polish
- AC-D2: Deterministic `BroadcastScorecard` in `ClipMeasurement` / `.measured.json`
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from hawedit.audio_signals import SentenceAudioMetrics
from hawedit.captions import find_ffmpeg
from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeRequest, JudgeVerdict
from hawedit.measure import (
    AudioMeasurement,
    BroadcastScorecard,
    CaptionMeasurement,
    ClipMeasurement,
    FaceTrackMeasurement,
    FileSummary,
    VideoMeasurement,
    evaluate_broadcast_scorecard,
    measure_clip,
)
from hawedit.pipeline import (
    StageSkipped,
    _build_and_run,
    build_parser,
    run_pipeline,
)
from hawedit.reframe import FocusPoint
from hawedit.render import Encoder, Reframe
from hawedit.sentences import Sentence
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    TranscriptStore,
    Word,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"


def _make_measurement(
    *,
    cuts_ms: list[int] | None = None,
    integrated_lufs: float = -14.0,
    true_peak_db: float = -1.0,
    audio_channels: int = 2,
    audio_codec: str = "aac",
    caption_events: int = 4,
    median_contrast_ratio: float | None = 15.2,
    samples_count: int = 20,
    face_detected_frames_count: int = 20,
    face_detected_share: float = 1.0,
    speaking_samples_count: int = 16,
    speaking_face_frames_count: int = 16,
    speaking_face_share: float = 1.0,
    scorecard: BroadcastScorecard | None = None,
) -> ClipMeasurement:
    return ClipMeasurement(
        schema=1,
        file=FileSummary(path="/tmp/reel.mp4", sha256="a" * 64, size_bytes=12_345),
        video=VideoMeasurement(
            width=1080,
            height=1920,
            fps=25.0,
            fps_ratio="25/1",
            duration_ms=10_000,
            frames_count=250,
            bitrate_kbps=6_000.0,
            codec="h264",
            pix_fmt="yuv420p",
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
        ),
        audio=AudioMeasurement(
            codec=audio_codec,
            sample_rate=48_000 if audio_channels > 0 else 0,
            channels=audio_channels,
            duration_ms=10_000,
            integrated_lufs=integrated_lufs,
            true_peak_db=true_peak_db,
            lra_lu=3.0,
            silences=[],
            total_silence_ms=0,
            silence_share=0.0,
        ),
        scenes={"cuts_ms": list(cuts_ms) if cuts_ms is not None else []},
        faces=FaceTrackMeasurement(
            sample_interval_ms=200,
            samples_count=samples_count,
            face_detected_frames_count=face_detected_frames_count,
            face_detected_share=face_detected_share,
            median_face_height_share=0.25 if face_detected_frames_count > 0 else None,
            median_y_center_share=0.35 if face_detected_frames_count > 0 else None,
            first_frame_face_share=0.25 if face_detected_frames_count > 0 else 0.0,
            speaking_samples_count=speaking_samples_count,
            speaking_face_frames_count=speaking_face_frames_count,
            speaking_face_share=speaking_face_share,
        ),
        captions=CaptionMeasurement(
            events_count=caption_events,
            ink_energy_detected_share=1.0 if caption_events > 0 else 0.0,
            median_contrast_ratio=median_contrast_ratio,
        ),
        vmaf=None,
        tool_metadata={"ffmpeg_version": "ffmpeg version 8.1.1"},
        broadcast_scorecard=scorecard,
    )


class _StructuredStubJudge:
    """Test double satisfying both EditorialJudge and StructuredJsonClient."""

    model_id = KURDISH_EDITORIAL_JUDGE

    def __init__(self, polish_replacements: list[dict[str, object]]) -> None:
        self._polish_replacements = polish_replacements
        self.polish_calls: list[list[dict[str, Any]]] = []

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        mid = (request.clip_in_ms + request.clip_out_ms) // 2
        return JudgeVerdict(
            candidate_id=request.candidate_id,
            hook_score=0.90,
            self_contained=True,
            payoff_at_ms=mid,
            meaning_fidelity=0.96,
            misleading_edit_risk=0.04,
            cultural_landing=0.92,
            narrative_role="payoff",
            title_ckb="تایتڵی کوردی",
            description_ckb="وەسفی تەواوی کوردی بۆ تاقیکردنەوە.",
            hashtags_ckb=("#کوردی",),
            judge=self.model_id,
            clip_in_ms=request.clip_in_ms,
            clip_out_ms=request.clip_out_ms,
        )

    def count_parts(self, parts: list[dict[str, Any]]) -> int:
        return len(json.dumps(parts))

    def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
        self.polish_calls.append(parts)
        return json.dumps({"replacements": self._polish_replacements}, ensure_ascii=False)


def _stutter_transcript(media_id: str) -> RawTranscript:
    words = (
        Word(w="تۆپ", start_ms=100, end_ms=160, conf=0.72),
        Word(w="تۆپ", start_ms=170, end_ms=230, conf=0.80),
        Word(w="تۆپ", start_ms=240, end_ms=300, conf=0.88),
        Word(w="ڕۆژنامەوانی", start_ms=350, end_ms=900, conf=0.95),
        Word(w="کوردی.", start_ms=920, end_ms=1_500, conf=0.95),
        Word(w="لە", start_ms=2_000, end_ms=2_500, conf=0.94),
        Word(w="هەولێر.", start_ms=2_520, end_ms=4_000, conf=0.94),
    )
    return RawTranscript(
        media_id=media_id,
        text_ckb="تۆپ تۆپ تۆپ ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    )


def test_pipeline_wires_audio_signals_encoder_and_caption_polish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-D1 / T7: Pipeline wires acoustic signals, encoder, blurred_fill, switches & polish."""
    # 1. Verify CLI defaults preserve existing behavior & new flags forward cleanly.
    captured_cli: dict[str, object] = {}

    def spy_run_pipeline(*args: object, **kwargs: object) -> object:
        captured_cli["kwargs"] = kwargs
        raise RuntimeError("stop-after-capture")

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", spy_run_pipeline)

    default_args = build_parser().parse_args([str(FIXTURE), "--work-dir", str(tmp_path / "cli0")])
    assert default_args.encoder == "libx264"
    assert default_args.non_face_layout == "fail"
    assert default_args.polish_captions is False
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        _build_and_run(default_args)
    kw_default = captured_cli["kwargs"]
    assert isinstance(kw_default, dict)
    assert kw_default["encoder"] == "libx264"
    assert kw_default["non_face_layout"] == "fail"
    assert kw_default["polish_captions"] is False

    custom_args = build_parser().parse_args(
        [
            str(FIXTURE),
            "--work-dir",
            str(tmp_path / "cli1"),
            "--encoder",
            "auto",
            "--non-face-layout",
            "blurred_fill",
            "--polish-captions",
        ]
    )
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        _build_and_run(custom_args)
    kw_custom = captured_cli["kwargs"]
    assert isinstance(kw_custom, dict)
    assert kw_custom["encoder"] == "auto"
    assert kw_custom["non_face_layout"] == "blurred_fill"
    assert kw_custom["polish_captions"] is True

    monkeypatch.undo()

    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.is_file():
        pytest.skip("needs ffmpeg")

    # 2. End-to-end run with acoustic discovery, --encoder auto, non-face BLURRED_FILL, and
    #    clip-only Sorani caption polish (never mutating raw.json or clip.transcript).
    seen_audio_metrics: list[tuple[SentenceAudioMetrics, ...]] = []
    seen_topic_audio_metrics: list[tuple[SentenceAudioMetrics, ...] | None] = []
    seen_encoder_choices: list[tuple[Encoder | str, Encoder]] = []

    def spy_discover(
        norm: NormalizedTranscript,
        *,
        sentences: Sequence[Sentence] | None = None,
        audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    ) -> list[Candidate]:
        assert sentences is not None and len(sentences) >= 2
        assert audio_metrics is not None and len(audio_metrics) == len(sentences)
        seen_audio_metrics.append(tuple(audio_metrics))
        return [
            Candidate("v1", norm.media_id, 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.95)
        ]

    from hawedit.topic_segmenter import discover_topics as real_discover_topics

    def spy_discover_topics(
        norm: NormalizedTranscript,
        *,
        sentences: Sequence[Sentence] | None = None,
        audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
        **kwargs: Any,
    ) -> tuple[Candidate, ...]:
        seen_topic_audio_metrics.append(tuple(audio_metrics) if audio_metrics is not None else None)
        return real_discover_topics(
            norm,
            sentences=sentences,
            audio_metrics=audio_metrics,
            **kwargs,
        )

    def spy_resolve_encoder(choice: str | Encoder, binary: Path | None = None) -> Encoder:
        # Force X264 so render runs identically on CPU-only and GPU hosts while proving wiring.
        seen_encoder_choices.append((choice, Encoder.X264))
        return Encoder.X264

    class _ZeroFaceTracker:
        last_intra_shot_switches_ms: tuple[int, ...] = ()

        def track(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            shot_cuts_ms: Sequence[int] = (),
        ) -> tuple[FocusPoint, ...]:
            return ()

    monkeypatch.setattr("hawedit.pipeline.discover_topics", spy_discover_topics)
    monkeypatch.setattr("hawedit.pipeline.resolve_encoder", spy_resolve_encoder)

    # After stutter deduplication of `تۆپ تۆپ تۆپ`, flat words are:
    # 0: "تۆپ", 1: "ڕۆژنامەوانی", 2: "کوردی." -> replace index 0 with "تۆپێک" (within 25% diff)
    judge = _StructuredStubJudge(polish_replacements=[{"index": 0, "w": "تۆپێک"}])
    transcript = _stutter_transcript("c10wire")
    work = tmp_path / "work_blurred"

    run = run_pipeline(
        FIXTURE,
        work,
        media_id="c10wire",
        transcript=transcript,
        discover=spy_discover,
        topic_candidates=True,
        judge=judge,
        select_sentences=(0,),
        subject_tracker=_ZeroFaceTracker(),
        excise_fillers=False,
        encoder="auto",
        non_face_layout="blurred_fill",
        polish_captions=True,
        ffmpeg=ffmpeg,
    )

    assert len(seen_audio_metrics) == 1
    assert seen_topic_audio_metrics and seen_topic_audio_metrics[0] is not None
    assert len(seen_topic_audio_metrics[0]) == len(run.sentences)
    assert seen_encoder_choices == [("auto", Encoder.X264)]
    assert judge.polish_calls, "caption polish client must be invoked on chosen clip"

    assert run.render is not None and not isinstance(run.render, StageSkipped), run.render
    assert run.render.reframe is Reframe.BLURRED_FILL
    assert run.render.encoder is Encoder.X264
    assert run.clip is not None and run.clip.output is not None
    assert run.clip.output.crop_target == "blurred_fill"

    # Caption display layer has deduplicated stutter + polished spelling, while raw.json and
    # clip.transcript remain strictly unmutated (Kurdish invariant #1).
    review_dir = work / "review" / run.clip.clip_id
    ass_text = (review_dir / f"{run.clip.clip_id}.ass").read_text(encoding="utf-8")
    assert "تۆپێک" in ass_text
    assert "تۆپ تۆپ" not in ass_text
    assert run.clip.transcript.raw_ckb == "تۆپ تۆپ تۆپ ڕۆژنامەوانی کوردی."
    raw_disk = json.loads(
        TranscriptStore(work / "transcripts").raw_path("c10wire").read_text(encoding="utf-8")
    )
    assert raw_disk["text_ckb"] == transcript.text_ckb

    # Measured sidecar includes broadcast_scorecard.
    measured_doc = json.loads(
        (review_dir / f"{run.clip.clip_id}.measured.json").read_text(encoding="utf-8")
    )
    assert "broadcast_scorecard" in measured_doc
    sc = BroadcastScorecard.from_dict(measured_doc["broadcast_scorecard"])
    assert sc.zero_double_cuts is True
    assert sc.face_framing_ok is True

    # 3. Verify explicit NVENC request fails-stop when unavailable (zero silent fallback).
    monkeypatch.undo()
    monkeypatch.setattr("hawedit.render.encoder_available", lambda _enc, _bin: False)
    work_nvenc = tmp_path / "work_nvenc_fail"
    nvenc_run = run_pipeline(
        FIXTURE,
        work_nvenc,
        media_id="c10nvenc",
        transcript=_stutter_transcript("c10nvenc"),
        discover=lambda _n: [
            Candidate("v1", "c10nvenc", 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.95)
        ],
        judge=_StructuredStubJudge(polish_replacements=[]),
        select_sentences=(0,),
        excise_fillers=False,
        encoder="h264_nvenc",
        ffmpeg=ffmpeg,
    )
    assert isinstance(nvenc_run.render, StageSkipped)
    assert "h264_nvenc" in nvenc_run.render.reason

    # 4. Verify default non_face_layout="fail" preserves strict fail-stop in production profile.
    monkeypatch.undo()
    work_fail_face = tmp_path / "work_fail_face"
    fail_face_run = run_pipeline(
        FIXTURE,
        work_fail_face,
        media_id="c10facefail",
        transcript=_stutter_transcript("c10facefail"),
        discover=lambda _n: [
            Candidate("v1", "c10facefail", 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.95)
        ],
        judge=_StructuredStubJudge(polish_replacements=[]),
        select_sentences=(0,),
        subject_tracker=_ZeroFaceTracker(),
        excise_fillers=False,
        profile="production",
        ffmpeg=ffmpeg,
    )
    assert isinstance(fail_face_run.render, StageSkipped)
    assert "zero faces detected" in fail_face_run.render.reason

    # 5. Verify intra-shot active-speaker switch timestamps merge into _steady_camera shot_cuts_ms.
    seen_steady_cuts: list[tuple[int, ...]] = []
    from hawedit.pipeline import _steady_camera as real_steady_camera

    def spy_steady_camera(
        points: tuple[FocusPoint, ...],
        source: Path,
        binary: Path | None,
        source_dimensions: tuple[int, int] | None = None,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[FocusPoint, ...]:
        seen_steady_cuts.append(tuple(shot_cuts_ms))
        return real_steady_camera(
            points,
            source,
            binary,
            source_dimensions=source_dimensions,
            shot_cuts_ms=shot_cuts_ms,
        )

    class _IntraSwitchTracker:
        last_intra_shot_switches_ms: tuple[int, ...] = (850,)

        def track(
            self,
            source: Path,
            in_ms: int,
            out_ms: int,
            shot_cuts_ms: Sequence[int] = (),
        ) -> tuple[FocusPoint, ...]:
            return (
                FocusPoint(at_ms=in_ms, center_x=180, center_y=150, face_height=90),
                FocusPoint(at_ms=849, center_x=180, center_y=150, face_height=90),
                FocusPoint(at_ms=850, center_x=460, center_y=150, face_height=90),
                FocusPoint(at_ms=max(out_ms - 10, 860), center_x=460, center_y=150, face_height=90),
            )

    monkeypatch.setattr("hawedit.pipeline._steady_camera", spy_steady_camera)
    work_switch = tmp_path / "work_switch"
    run_pipeline(
        FIXTURE,
        work_switch,
        media_id="c10switch",
        transcript=_stutter_transcript("c10switch"),
        discover=lambda _n: [
            Candidate("v1", "c10switch", 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.95)
        ],
        judge=_StructuredStubJudge(polish_replacements=[]),
        select_sentences=(0,),
        subject_tracker=_IntraSwitchTracker(),
        excise_fillers=False,
        ffmpeg=ffmpeg,
    )
    assert seen_steady_cuts and 850 in seen_steady_cuts[0]


def test_broadcast_scorecard_flags_double_cuts_and_passes_clean_reel() -> None:
    """AC-D2 / T7: BroadcastScorecard detects double cuts & passes clean broadcast reels."""
    # 1. Clean talking-head broadcast reel passes all checks.
    clean = _make_measurement(
        cuts_ms=[3_200, 6_800],
        integrated_lufs=-14.1,
        true_peak_db=-1.0,
        caption_events=6,
        median_contrast_ratio=14.8,
        samples_count=50,
        face_detected_frames_count=48,
        face_detected_share=0.96,
        speaking_samples_count=40,
        speaking_face_frames_count=39,
        speaking_face_share=0.975,
    )
    clean_card = evaluate_broadcast_scorecard(clean)
    assert clean_card.double_cuts_count == 0
    assert clean_card.zero_double_cuts is True
    assert clean_card.loudness_ok is True
    assert clean_card.contrast_ok is True
    assert clean_card.face_framing_ok is True
    assert clean_card.all_passed is True
    assert BroadcastScorecard.from_dict(clean_card.to_dict()) == clean_card

    # 2. Adjacent cuts <= 80 ms are flagged as double cuts; 81 ms is clean.
    double_cut_meas = _make_measurement(cuts_ms=[1_000, 1_040, 4_500, 4_580, 7_000, 7_081])
    dc_card = evaluate_broadcast_scorecard(double_cut_meas)
    assert dc_card.double_cuts_count == 2
    assert dc_card.zero_double_cuts is False
    assert dc_card.all_passed is False

    # 3. Loudness bounds: [-16.0, -12.5] LUFS and true_peak <= -0.5 dBTP; missing audio fails.
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(integrated_lufs=-16.0, true_peak_db=-0.5)
        ).loudness_ok
        is True
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(integrated_lufs=-12.5, true_peak_db=-0.5)
        ).loudness_ok
        is True
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(integrated_lufs=-16.1, true_peak_db=-1.0)
        ).loudness_ok
        is False
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(integrated_lufs=-12.4, true_peak_db=-1.0)
        ).loudness_ok
        is False
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(integrated_lufs=-14.0, true_peak_db=-0.4)
        ).loudness_ok
        is False
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(audio_channels=0, audio_codec="none")
        ).loudness_ok
        is False
    )

    # 4. Caption contrast: >= 12.0 when captions present, True when no captions.
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(caption_events=0, median_contrast_ratio=None)
        ).contrast_ok
        is True
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(caption_events=3, median_contrast_ratio=12.0)
        ).contrast_ok
        is True
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(caption_events=3, median_contrast_ratio=11.9)
        ).contrast_ok
        is False
    )
    assert (
        evaluate_broadcast_scorecard(
            _make_measurement(caption_events=3, median_contrast_ratio=None)
        ).contrast_ok
        is False
    )

    # 5. Face framing: >= 0.90 when faces present; True for non-face cooking/B-roll clips.
    non_face = _make_measurement(
        samples_count=30,
        face_detected_frames_count=0,
        face_detected_share=0.0,
        speaking_samples_count=0,
        speaking_face_frames_count=0,
        speaking_face_share=1.0,
    )
    assert evaluate_broadcast_scorecard(non_face).all_passed is True

    poor_framing = _make_measurement(
        samples_count=30,
        face_detected_frames_count=15,
        face_detected_share=0.50,
        speaking_samples_count=20,
        speaking_face_frames_count=12,
        speaking_face_share=0.60,
    )
    assert evaluate_broadcast_scorecard(poor_framing).face_framing_ok is False
    assert evaluate_broadcast_scorecard(poor_framing).all_passed is False

    poor_no_speaking_breakdown = _make_measurement(
        samples_count=30,
        face_detected_frames_count=15,
        face_detected_share=0.50,
        speaking_samples_count=0,
        speaking_face_frames_count=0,
        speaking_face_share=1.0,
    )
    assert evaluate_broadcast_scorecard(poor_no_speaking_breakdown).face_framing_ok is False

    # 6. ClipMeasurement serialization roundtrip (both with and without broadcast_scorecard).
    assert "broadcast_scorecard" not in clean.to_dict()
    with_card = _make_measurement(scorecard=clean_card)
    payload = with_card.to_dict()
    assert payload["broadcast_scorecard"] == clean_card.to_dict()
    restored = ClipMeasurement.from_dict(payload)
    assert restored.broadcast_scorecard == clean_card

    # 7. Real measure_clip() automatically computes and serializes broadcast_scorecard.
    ffmpeg = find_ffmpeg()
    if ffmpeg is not None and ffmpeg.is_file() and FIXTURE.is_file():
        real_meas = measure_clip(FIXTURE, ffmpeg=ffmpeg)
        assert real_meas.broadcast_scorecard is not None
        assert real_meas.broadcast_scorecard == evaluate_broadcast_scorecard(real_meas)
        parsed = json.loads(real_meas.to_json())
        assert parsed["broadcast_scorecard"] == real_meas.broadcast_scorecard.to_dict()


def test_silence_trim_frames_before_concat_and_reconciles_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silence trimming frames [0:v] before setpts/concat and reconciles effective duration."""
    import subprocess

    from hawedit.boundary import BoundaryInputs, fuse_boundary
    from hawedit.captions import build_ass
    from hawedit.clip import Clip, ClipTranscript, Editorial, Output, Provenance
    from hawedit.episode import EpisodeClipSummary, EpisodeManifest, reconcile_episode_manifest
    from hawedit.pipeline import FONTS_DIR
    from hawedit.render import Encoder, render_clip
    from hawedit.silence import SilencePlan, silence_trim_filter
    from hawedit.transcripts import AsrProvenance, Word

    # 1. Intermediate pad video_in splits cleanly across retained intervals.
    filt = silence_trim_filter(((0, 800), (1300, 2500)), video_in="[v_framed]")
    assert filt.startswith("[v_framed]split=2[v_in_0][v_in_1];")
    assert "[v_in_0]trim=start=0.000:end=0.800,setpts=PTS-STARTPTS[v0];" in filt
    assert "[v_in_1]trim=start=1.300:end=2.500,setpts=PTS-STARTPTS[v1];" in filt

    # 2. render_clip applies video_filter BEFORE silence_trim_filter (zero PTS-shift cut lag).
    ffmpeg = find_ffmpeg()
    if ffmpeg is not None and ffmpeg.is_file() and FIXTURE.is_file():
        captured_cmd: list[str] = []
        real_run = subprocess.run

        def spy_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(cmd, list) and "-filter_complex" in cmd:
                captured_cmd.extend(str(c) for c in cmd)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr("hawedit.render.subprocess.run", spy_run)
        words = (
            Word(w="یەک", start_ms=0, end_ms=700, conf=0.95),
            Word(w="دوو", start_ms=1_500, end_ms=2_200, conf=0.95),
        )
        boundary = fuse_boundary(
            BoundaryInputs(anchor_in_ms=500, anchor_out_ms=2_500, sentence_complete=True)
        )
        clip_dur = boundary.final_out_ms - boundary.final_in_ms
        clip = Clip(
            clip_id="sil-frame-first",
            media_id="fx",
            media_sha256="a" * 64,
            in_ms=boundary.final_in_ms,
            out_ms=boundary.final_out_ms,
            discovery_path=DiscoveryPath.VERBAL,
            boundary=boundary,
            transcript=ClipTranscript(
                raw_ckb="یەک دوو",
                norm_ckb="یەک دوو",
                en_aux=None,
                words=words,
                asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
            ),
            editorial=Editorial(
                hook_score=0.8,
                self_contained=True,
                meaning_fidelity=0.9,
                misleading_edit_risk=0.05,
                cultural_landing=0.7,
                narrative_role="payoff",
                judge=KURDISH_EDITORIAL_JUDGE,
            ),
            output=Output(
                title_ckb="تاقیکردنەوە",
                description_ckb="تاقیکردنەوە",
                crop_target="9:16",
                caption_style="word_highlight",
                durations=(30,),
            ),
            provenance=Provenance.current(),
        )
        plan = SilencePlan(
            clip_in_ms=clip.in_ms,
            clip_out_ms=clip.out_ms,
            threshold_ms=400,
            target_gap_ms=100,
            retained_intervals_ms=((0, 800), (1_300, clip_dur)),
            removed_intervals_ms=((800, 1_300),),
            total_removed_ms=500,
        )
        ass_path = tmp_path / "c.ass"
        ass_path.write_text(build_ass((Sentence(words=words, complete=True),)), encoding="utf-8")
        out_mp4 = tmp_path / "out.mp4"
        res = render_clip(
            clip,
            FIXTURE,
            ass_path,
            FONTS_DIR,
            out_mp4,
            source_width=640,
            source_height=360,
            encoder=Encoder.X264,
            silence_plan=plan,
            for_review=True,
            ffmpeg=ffmpeg,
        )
        assert res.requested_duration_ms == clip_dur - 500
        assert "-filter_complex" in captured_cmd
        fc = captured_cmd[captured_cmd.index("-filter_complex") + 1]
        assert fc.startswith("[0:v]crop="), fc[:120]
        assert "[v_framed];[v_framed]split=2[v_in_0][v_in_1];" in fc
        assert "[v_cfr]ass=" in fc

    # 3. Reconciler succeeds when EpisodeClipSummary records effective silence-tightened duration.
    clip_dir = tmp_path / "review" / "c1"
    clip_dir.mkdir(parents=True)
    for ext in ("mp4", "ass", "srt", "edl", "json", "cover.png"):
        (clip_dir / f"c1.{ext}").write_bytes(b"ok")
    (clip_dir / "c1.measured.json").write_text(
        json.dumps({"video": {"duration_ms": 86_400}}),
        encoding="utf-8",
    )
    summary = EpisodeClipSummary(
        clip_id="c1",
        in_ms=535_850,
        out_ms=624_486,
        duration_ms=86_400,
        hook_score=0.9,
        hook_type="insight",
        title_ckb="تاقیکردنەوە",
        delivery_dir="review/c1",
    )
    manifest = EpisodeManifest(
        episode_id="ep-sil",
        media_id="fx",
        media_sha256="a" * 64,
        clips_count=1,
        total_duration_ms=86_400,
        clips=(summary,),
    )
    reconcile_episode_manifest(manifest, tmp_path)


def test_asr_cuda_oom_on_long_segment_splits_cleanly_and_preserves_fail_stop(
    tmp_path: Path,
) -> None:
    """Oversized (>20 s) segment hitting CUDA OOM splits into two contiguous halves."""
    import wave

    from hawedit.asr import (
        AsrProductionFailure,
        SegmentTranscript,
        _PreparedSpeechSegment,
        transcribe_prepared_segments,
    )
    from hawedit.transcripts import Word

    wav_path = tmp_path / "long_music_speech.wav"
    duration_ms = 36_000
    n_frames = 16_000 * 36
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(b"\x10\x01" * n_frames)

    seg = _PreparedSpeechSegment(path=wav_path, start_ms=0, end_ms=duration_ms)

    class _OomOnLongBackend:
        def __init__(self, *, always_fail: bool = False) -> None:
            self.always_fail = always_fail
            self.seen_durations: list[float] = []

        def transcribe_segment(self, path: Path, duration_s: float) -> SegmentTranscript:
            self.seen_durations.append(duration_s)
            if self.always_fail or duration_s > 25.0:
                raise RuntimeError("CUDA out of memory. Tried to allocate 238.00 MiB.")
            return SegmentTranscript(
                text_raw="سڵاو",
                ctc_text="سڵاو",
                words=(Word(w="سڵاو", start_ms=0, end_ms=500, conf=0.95),),
                mean_logprob=-0.2,
            )

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> SegmentTranscript:
            return self.transcribe_segment(audio_path, duration_s)

    backend = _OomOnLongBackend()
    results, failures = transcribe_prepared_segments(backend, (seg,))
    assert not failures
    assert len(results) == 2
    assert results[0][0].start_ms == 0 and results[0][0].end_ms == 18_000
    assert results[1][0].start_ms == 18_000 and results[1][0].end_ms == 36_000

    with pytest.raises(AsrProductionFailure):
        transcribe_prepared_segments(
            _OomOnLongBackend(always_fail=True), (seg,), stop_on_failure=True
        )
