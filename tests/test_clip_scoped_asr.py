"""Clip-scoped final ASR contracts (`specs/b2-clip-scoped-final-asr`)."""

from __future__ import annotations

import array
import hashlib
import math
import struct
import wave
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hawedit.asr import (
    OmniAsrProducer,
    SegmentTranscript,
    _contextual_speech_regions,
    select_contextual_regions_for_spans,
)
from hawedit.captions import find_ffmpeg
from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.ingest import IngestResult, SpeechSegment
from hawedit.judge import JudgeRequest, JudgeVerdict
from hawedit.pipeline import StageSkipped, _build_and_run, build_parser, run_pipeline
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    RawTranscriptImmutable,
    Word,
)
from test_pipeline import _test_qc, a_verdict


def _segs(*intervals: tuple[int, int]) -> tuple[SimpleNamespace, ...]:
    return tuple(SimpleNamespace(start_ms=start, end_ms=end) for start, end in intervals)


def test_padded_clip_region_planner_preserves_episode_context_bounds() -> None:
    # Full episode speech regions coalesce via _contextual_speech_regions into:
    #   (0, 6_500), (8_000, 14_000), (16_000, 22_000), (35_000, 40_000)
    speech = _segs(
        (0, 3_000),
        (3_500, 6_500),
        (8_000, 14_000),
        (16_000, 22_000),
        (35_000, 40_000),
    )
    selected = select_contextual_regions_for_spans(
        speech, ((17_500, 20_000),), duration_ms=50_000, pad_ms=4_000
    )
    # Padded window is 13_500..24_000 -> overlaps (8_000, 14_000) and (16_000, 22_000)
    # Bounds must stay exact episode context-region bounds without splitting at 13_500.
    assert [(r.start_ms, r.end_ms) for r in selected] == [(8_000, 14_000), (16_000, 22_000)]


def test_padded_clip_region_planner_rejects_padding_outside_3_to_5_seconds() -> None:
    speech = _segs((1_000, 5_000))
    for bad_pad in (0, 2_999, 5_001, True):
        with pytest.raises(ValueError, match="pad"):
            select_contextual_regions_for_spans(
                speech, ((2_000, 4_000),), duration_ms=10_000, pad_ms=bad_pad
            )
    with pytest.raises(ValueError, match="span"):
        select_contextual_regions_for_spans(speech, (), duration_ms=10_000, pad_ms=4_000)


def test_context_region_subset_is_idempotent_under_context_grouping() -> None:
    # Craft regions spanning the 18s split cliff so intermediate windows get dropped
    speech = _segs(
        (0, 10_000),
        (10_500, 19_000),  # cannot merge with (0, 10_000) since 19s > 18s
        (19_500, 27_000),  # merges with (10_500, 19_000) -> (10_500, 27_000)
        (28_500, 34_000),
        (45_000, 52_000),
    )
    episode_grouped = _contextual_speech_regions(speech)
    subset = select_contextual_regions_for_spans(
        speech,
        ((1_000, 2_000), (20_000, 24_000)),
        duration_ms=60_000,
        pad_ms=4_000,
    )
    assert [(r.start_ms, r.end_ms) for r in _contextual_speech_regions(subset)] == [
        (r.start_ms, r.end_ms) for r in subset
    ]
    # And subset elements are exact members of episode_grouped
    assert all(
        any((r.start_ms, r.end_ms) == (g.start_ms, g.end_ms) for g in episode_grouped)
        for r in subset
    )


def _write_multi_region_media(root: Path, ffmpeg: Path) -> tuple[Path, Path, IngestResult]:
    """Create a 16s MP4 + 16 kHz WAV with three spaced speech bursts for deterministic tests."""
    import subprocess

    wav_path = root / "multi.wav"
    total_samples = 16_000 * 16
    samples = [0] * total_samples
    # Put distinct pure sine tones (220 Hz, 440 Hz, 880 Hz) in 1..3s, 6..9s, and 12..14s
    for start_s, end_s, freq_hz in ((1, 3, 220), (6, 9, 440), (12, 14, 880)):
        for s in range(start_s * 16_000, end_s * 16_000):
            samples[s] = round(14_000 * math.sin(2.0 * math.pi * freq_hz * s / 16_000))
    with wave.open(str(wav_path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(struct.pack(f"<{total_samples}h", *samples))
    mp4_path = root / "multi.mp4"
    res = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x360:r=25:d=16",
            "-i",
            str(wav_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(mp4_path),
        ],
        capture_output=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    src_sha = hashlib.sha256(mp4_path.read_bytes()).hexdigest()
    ing = IngestResult(
        media_id="multi",
        source=str(mp4_path),
        source_sha256=src_sha,
        audio_path=str(wav_path),
        proxy_path=str(mp4_path),
        duration_ms=16_000,
        shot_cuts_ms=(),
        speech=tuple(
            SpeechSegment(start_ms=a, end_ms=b)
            for a, b in ((1_000, 3_000), (6_000, 9_000), (12_000, 14_000))
        ),
        diarization=None,
    )
    return mp4_path, wav_path, ing


def _patch_ingest(monkeypatch: pytest.MonkeyPatch, ing: IngestResult) -> None:
    monkeypatch.setattr("hawedit.ingest.detect_speech", lambda _wav: ing.speech)


class _RegionEchoBackend:
    """Deterministic backend keyed strictly on each segment WAV's tone frequency and duration."""

    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.durations_ms: list[int] = []

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        self.calls.append(audio_path)
        dur_ms = round(duration_s * 1000)
        self.durations_ms.append(dur_ms)
        with wave.open(str(audio_path), "rb") as stream:
            n_frames = min(stream.getnframes(), 3_200)
            pcm = array.array("h", stream.readframes(n_frames))
        crossings = sum(1 for a, b in pairwise(pcm) if a <= 0 < b)
        hz = (crossings * 16_000) / max(1, len(pcm))
        if hz < 330:
            w1, w2 = "بەشی", "یەکەم."
        elif hz < 660:
            w1, w2 = "بەشی", "دووەم."
        else:
            w1, w2 = "بەشی", "سێیەم."
        t1_end = max(100, dur_ms // 2 - 50)
        t2_start = dur_ms // 2
        t2_end = max(t2_start + 100, dur_ms - 50)
        return SegmentTranscript(
            text_raw=f"{w1} {w2}",
            ctc_text=f"{w1} {w2}",
            words=(
                Word(w1, 20, t1_end, 0.9),
                Word(w2, t2_start, t2_end, 0.92),
            ),
            mean_logprob=-0.25,
        )

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        return self.transcribe_segment(audio_path, duration_s)


def _noisy_draft_transcript(media_id: str, media_sha256: str) -> RawTranscript:
    words = (
        Word("دەقێکی", 1_050, 1_900, 0.7),
        Word("سەرەتایی.", 2_000, 2_900, 0.7),
        Word("ڕەشنووسی", 6_050, 7_400, 0.7),
        Word("دووەم.", 7_500, 8_900, 0.7),
        Word("بەشی", 12_050, 12_900, 0.7),
        Word("کۆتایی.", 13_000, 13_900, 0.7),
    )
    return RawTranscript(
        media_id=media_id,
        text_ckb="دەقێکی سەرەتایی.\nڕەشنووسی دووەم.\nبەشی کۆتایی.",
        words=words,
        asr=AsrProvenance("omniASR_LLM_7B_v2", aligner="ctc_viterbi", mean_logprob=-0.6),
        media_sha256=media_sha256,
    )


def test_clip_scoped_caption_text_and_word_timings_match_whole_episode_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    mp4, _wav, ing = _write_multi_region_media(tmp_path, ffmpeg)
    _patch_ingest(monkeypatch, ing)

    full_backend = _RegionEchoBackend()
    full_producer = OmniAsrProducer(
        full_backend, context_grouping=True, validate_hard_segments=False
    )
    # Whole-episode run selecting sentence 1 (middle speech burst 6_000..9_000)
    full_run = run_pipeline(
        mp4,
        tmp_path / "full_work",
        media_id="multi",
        asr=full_producer,
        select_sentences=(1,),
        verdict=a_verdict(6_020, 8_950),
        qc=_test_qc(False, reviewed_sha256=ing.source_sha256),
        ffmpeg=ffmpeg,
        min_clip_ms=1_000,
    )
    assert len(full_backend.calls) == 3
    assert full_run.render is not None and not isinstance(full_run.render, StageSkipped)
    assert full_run.clip is not None

    # Clip-scoped run: draft span 6_050..8_900 with pad_ms=3_000 -> 3_050..11_900
    # overlaps only the middle contextual region (6_000..9_000).
    clip_backend = _RegionEchoBackend()
    clip_producer = OmniAsrProducer(
        clip_backend, context_grouping=True, validate_hard_segments=False
    )
    draft = _noisy_draft_transcript("multi", ing.source_sha256)
    clip_run = run_pipeline(
        mp4,
        tmp_path / "clip_work",
        media_id="multi",
        transcript=draft,
        clip_asr=clip_producer,
        clip_asr_pad_ms=3_000,
        select_sentences=(1,),
        verdict=a_verdict(6_050, 8_900),
        qc=_test_qc(False, reviewed_sha256=ing.source_sha256),
        ffmpeg=ffmpeg,
        min_clip_ms=1_000,
    )
    # Only the middle region (6_000..9_000) ran through final ASR (1 call instead of 3!)
    assert len(clip_backend.calls) == 1
    assert clip_run.render is not None and not isinstance(clip_run.render, StageSkipped)
    assert clip_run.clip is not None
    assert clip_run.selected_sentences == full_run.selected_sentences
    assert clip_run.clip.in_ms == full_run.clip.in_ms
    assert clip_run.clip.out_ms == full_run.clip.out_ms
    assert clip_run.clip.transcript == full_run.clip.transcript
    # ASS and SRT caption files match identically
    assert (
        Path(clip_run.render.path).with_suffix(".srt").read_bytes()
        == Path(full_run.render.path).with_suffix(".srt").read_bytes()
    )
    assert clip_run.clip_scoped_asr_regions == 1
    assert clip_run.clip_scoped_asr_audio_ms == 3_000
    assert clip_run.clip_scoped_asr_wall_s is not None and clip_run.clip_scoped_asr_wall_s >= 0.0
    report_dict = clip_run.to_dict()
    assert report_dict["clip_scoped_asr_regions"] == 1
    assert report_dict["clip_scoped_asr_audio_ms"] == 3_000


def test_episode_delivery_batches_all_selected_clips_into_single_asr_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    mp4, _wav, ing = _write_multi_region_media(tmp_path, ffmpeg)
    _patch_ingest(monkeypatch, ing)

    draft = _noisy_draft_transcript("multi", ing.source_sha256)
    cands = (
        Candidate("c1", "multi", 1_050, 2_900, DiscoveryPath.VERBAL, rank=1),
        Candidate("c2", "multi", 12_050, 13_900, DiscoveryPath.VERBAL, rank=2),
    )

    class Judge:
        model_id = "gemini-2.5-pro"

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            return replace(
                a_verdict(request.clip_in_ms, request.clip_out_ms),
                candidate_id=request.candidate_id,
            )

    transcribe_calls = 0

    class CountingClipProducer(OmniAsrProducer):
        def transcribe(
            self,
            media_id: str,
            audio_path: Path,
            speech_segments: Any,
            work_dir: Path,
            ffmpeg: Path | None = None,
        ) -> RawTranscript:
            nonlocal transcribe_calls
            transcribe_calls += 1
            return super().transcribe(media_id, audio_path, speech_segments, work_dir, ffmpeg)

    backend = _RegionEchoBackend()
    producer = CountingClipProducer(backend, context_grouping=True, validate_hard_segments=False)
    run = run_pipeline(
        mp4,
        tmp_path / "ep_work",
        media_id="multi",
        transcript=draft,
        clip_asr=producer,
        clip_asr_pad_ms=3_000,
        discover=lambda _norm: cands,
        judge=Judge(),
        auto_select=True,
        judge_top_n=2,
        max_clips=2,
        min_separation_ms=1_000,
        ffmpeg=ffmpeg,
        min_clip_ms=1_000,
    )
    assert transcribe_calls == 1
    assert len(backend.calls) == 2  # Regions 0 and 2 only, batched into one call
    assert run.episode_manifest is not None
    assert run.episode_manifest.clips_count == 2
    assert run.clip_scoped_asr_regions == 2


def test_clip_scoped_store_never_overwrites_draft_raw_and_reuses_exact_region_subset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    mp4, _wav, ing = _write_multi_region_media(tmp_path, ffmpeg)
    _patch_ingest(monkeypatch, ing)

    draft = _noisy_draft_transcript("multi", ing.source_sha256)
    transcribe_calls = 0

    class CountingProducer(OmniAsrProducer):
        def transcribe(
            self,
            media_id: str,
            audio_path: Path,
            speech_segments: Any,
            work_dir: Path,
            ffmpeg: Path | None = None,
        ) -> RawTranscript:
            nonlocal transcribe_calls
            transcribe_calls += 1
            return super().transcribe(media_id, audio_path, speech_segments, work_dir, ffmpeg)

    backend = _RegionEchoBackend()
    producer = CountingProducer(backend, context_grouping=True, validate_hard_segments=False)
    wd = tmp_path / "cache_work"
    run_pipeline(
        mp4,
        wd,
        media_id="multi",
        transcript=draft,
        clip_asr=producer,
        clip_asr_pad_ms=3_000,
        select_sentences=(1,),
        verdict=a_verdict(6_050, 8_900),
        qc=_test_qc(False, reviewed_sha256=ing.source_sha256),
        ffmpeg=ffmpeg,
        min_clip_ms=1_000,
    )
    assert transcribe_calls == 1
    draft_raw_path = wd / "transcripts" / "multi.transcript.raw.json"
    clip_raw_path = wd / "clip_asr" / "transcripts" / "multi.transcript.raw.json"
    assert draft_raw_path.is_file() and clip_raw_path.is_file()
    assert "ڕەشنووسی" in draft_raw_path.read_text(encoding="utf-8")
    assert "بەشی دووەم." in clip_raw_path.read_text(encoding="utf-8")
    draft_bytes = draft_raw_path.read_bytes()

    # Exact rerun in same work_dir hits reusable_raw with 0 new ASR calls
    run_pipeline(
        mp4,
        wd,
        media_id="multi",
        transcript=draft,
        clip_asr=producer,
        clip_asr_pad_ms=3_000,
        select_sentences=(1,),
        verdict=a_verdict(6_050, 8_900),
        qc=_test_qc(False, reviewed_sha256=ing.source_sha256),
        ffmpeg=ffmpeg,
        min_clip_ms=1_000,
    )
    assert transcribe_calls == 1
    assert draft_raw_path.read_bytes() == draft_bytes

    # Changing chosen clip spans misses / refuses reuse rather than serving old span words
    with pytest.raises(RawTranscriptImmutable, match="admission"):
        run_pipeline(
            mp4,
            wd,
            media_id="multi",
            transcript=draft,
            clip_asr=producer,
            clip_asr_pad_ms=3_000,
            select_sentences=(0,),
            verdict=a_verdict(1_050, 2_900),
            qc=_test_qc(False, reviewed_sha256=ing.source_sha256),
            ffmpeg=ffmpeg,
            min_clip_ms=1_000,
        )


def test_clip_scoped_asr_failure_never_falls_back_to_draft_captions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    mp4, _wav, ing = _write_multi_region_media(tmp_path, ffmpeg)
    _patch_ingest(monkeypatch, ing)

    class FailingProducer:
        admission_policy = "failing-v1"

        def transcribe(self, *_args: object, **_kwargs: object) -> RawTranscript:
            raise RuntimeError("declared GPU failure in clip ASR")

    wd = tmp_path / "fail_work"
    run = run_pipeline(
        mp4,
        wd,
        media_id="multi",
        transcript=_noisy_draft_transcript("multi", ing.source_sha256),
        clip_asr=FailingProducer(),
        clip_asr_pad_ms=3_000,
        select_sentences=(1,),
        verdict=a_verdict(6_050, 8_900),
        qc=_test_qc(False, reviewed_sha256=ing.source_sha256),
        ffmpeg=ffmpeg,
        min_clip_ms=1_000,
    )
    assert run.clip is None
    assert isinstance(run.transcript, StageSkipped) or isinstance(run.render, StageSkipped)
    assert not list((wd / "clips").glob("*.mp4")) if (wd / "clips").exists() else True
    assert not list((wd / "review").glob("**/*.mp4")) if (wd / "review").exists() else True


def test_single_clip_two_pass_runs_draft_for_selection_and_final_asr_for_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    mp4, _wav, ing = _write_multi_region_media(tmp_path, ffmpeg)
    _patch_ingest(monkeypatch, ing)

    draft = _noisy_draft_transcript("multi", ing.source_sha256)
    draft_path = tmp_path / "draft.raw.json"
    draft_path.write_text(draft.to_json(), encoding="utf-8")

    backend = _RegionEchoBackend()
    producer = OmniAsrProducer(backend, context_grouping=True, validate_hard_segments=False)
    monkeypatch.setattr("hawedit.asr.create_omni_asr_producer", lambda *_a, **_kw: producer)

    args = build_parser().parse_args(
        [
            str(mp4),
            "--work-dir",
            str(tmp_path / "cli_work"),
            "--media-id",
            "multi",
            "--transcript",
            str(draft_path),
            "--omni-asr",
            "--stock-decoder",
            "--clip-scoped-asr",
            "--clip-asr-pad-ms",
            "3000",
            "--sentences",
            "1",
            "--min-clip-seconds",
            "1",
        ]
    )
    run = _build_and_run(args)
    assert len(backend.calls) == 1
    assert run.clip is not None
    assert "بەشی دووەم." in run.clip.transcript.raw_ckb
    assert "ڕەشنووسی" not in run.clip.transcript.raw_ckb


def test_cli_refuses_clip_scoped_asr_without_omni_asr_and_draft_source(tmp_path: Path) -> None:
    from test_pipeline import _cli_exit

    for bad_argv, expected in (
        (
            ["--clip-scoped-asr"],
            "--clip-scoped-asr requires both --omni-asr and a --transcript draft source",
        ),
        (
            ["--clip-scoped-asr", "--omni-asr"],
            "--clip-scoped-asr requires both --omni-asr and a --transcript draft source",
        ),
        (["--clip-asr-pad-ms", "4000"], "--clip-asr-pad-ms requires --clip-scoped-asr"),
        (
            [
                "--transcript",
                "draft.json",
                "--omni-asr",
                "--clip-scoped-asr",
                "--clip-asr-pad-ms",
                "2000",
            ],
            "--clip-asr-pad-ms must be between 3000 and 5000",
        ),
    ):
        code, stderr = _cli_exit(bad_argv, tmp_path)
        assert code == 2
        assert expected in stderr
