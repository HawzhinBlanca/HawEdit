"""Integration tests for V7 Masterpiece Engine pipeline wiring (D-377..D-381)."""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

import pytest

from hawedit.assembly import AssemblySpan
from hawedit.boundary import Boundary
from hawedit.caption_polish import LocalLlmJsonClient
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath
from hawedit.pipeline import (
    _prepare_viral_story_assembly,
    _resolve_polish_client,
    _tighten_clip_word_onsets,
    build_parser,
)
from hawedit.reframe import FocusPoint
from hawedit.render import measure_audio_loudness
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word


def _write_pcm_wav(path: Path, segments: list[tuple[int, float]], *, rate: int = 16_000) -> None:
    samples = array.array("h")
    phase = 0.0
    step = 2.0 * math.pi * 240.0 / rate
    for dur_ms, amp in segments:
        count = int(rate * dur_ms / 1000)
        for _ in range(count):
            val = int(max(-32767, min(32767, round(amp * 28000.0 * math.sin(phase)))))
            samples.append(val)
            phase += step
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())


def _boundary(in_ms: int, out_ms: int) -> Boundary:
    return Boundary(
        anchor_in_ms=in_ms,
        anchor_out_ms=out_ms,
        final_in_ms=in_ms,
        final_out_ms=out_ms,
        in_extended_by=None,
        out_extended_by=None,
        sentence_complete=True,
    )


def test_v7_cli_flags_default_false_and_parse_opt_in() -> None:
    parser = build_parser()
    defaults = parser.parse_args(["episode.mp4"])
    assert defaults.condense is False
    assert defaults.cold_open is False

    enabled = parser.parse_args(["episode.mp4", "--condense", "--cold-open"])
    assert enabled.condense is True
    assert enabled.cold_open is True


def test_v7_resolve_polish_client_uses_local_llm_env_when_no_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAWEDIT_LOCAL_LLM_URL", raising=False)
    assert _resolve_polish_client(None) is None

    monkeypatch.setenv("HAWEDIT_LOCAL_LLM_URL", "http://127.0.0.1:1234/v1")
    client = _resolve_polish_client(None)
    assert isinstance(client, LocalLlmJsonClient)
    assert client.base_url == "http://127.0.0.1:1234/v1"


def test_v7_tighten_clip_word_onsets_exposes_hidden_silence_and_guards_outer_bounds(
    tmp_path: Path,
) -> None:
    wav_path = tmp_path / "audio.wav"
    # 0..1000ms: voiced word 0; 1000..1700ms: hidden silence; 1700..2200ms: voiced word 1
    _write_pcm_wav(wav_path, [(1000, 0.7), (700, 0.0005), (500, 0.7)])
    w0 = Word(w="ئێستا", start_ms=100, end_ms=1000, conf=0.95)
    w1 = Word(w="نازانی", start_ms=1000, end_ms=2200, conf=0.95)
    sent = Sentence(words=(w0, w1), complete=True)
    clip = Clip(
        clip_id="c-1",
        media_id="m-1",
        media_sha256="a" * 64,
        in_ms=0,
        out_ms=2300,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=_boundary(0, 2300),
        transcript=ClipTranscript(
            raw_ckb="ئێستا نازانی",
            norm_ckb="ئێستا نازانی",
            en_aux=None,
            words=(w0, w1),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
    )
    vad_selected, vad_clip, vad_words = _tighten_clip_word_onsets(
        (sent,),
        clip,
        wav_path,
        max_outer_in_pad_ms=200,
        max_outer_out_pad_ms=200,
    )
    assert len(vad_words) == 2
    assert vad_words[0].start_ms == 100
    assert vad_words[1].start_ms >= 1650
    assert vad_selected[0].words == vad_words
    assert vad_clip.transcript.words == vad_words


def test_v7_prepare_viral_story_assembly_condenses_and_remaps_tracks() -> None:
    def _make_sent(start_ms: int, dur_ms: int, words_text: list[str]) -> Sentence:
        n = len(words_text)
        step = dur_ms // n
        ws = tuple(
            Word(
                w=tok,
                start_ms=start_ms + i * step,
                end_ms=start_ms + i * step + step - 40,
                conf=0.95,
            )
            for i, tok in enumerate(words_text)
        )
        return Sentence(words=ws, complete=True)

    s0 = _make_sent(100_100, 14_000, ["بەڕای", "من", "یەکەم", "پیشە", "وەرگێڕانە."])
    s1 = _make_sent(115_000, 42_000, ["لە", "ئێستادا", "زۆر", "شتی", "تر", "هەیە."])
    s2 = _make_sent(158_000, 10_000, ["بۆ", "نموونە", "چات", "باش", "کار", "دەکات."])
    s3_words: list[Word] = []
    # Include a 900 ms interior pause inside s3 to exercise sub-span silence splitting too.
    cursor = 169_000
    for idx, tok in enumerate(
        [
            "ژیریی",
            "دەستکرد",
            "کوردییەکەیان",
            "زۆر",
            "زۆر",
            "جوان",
            "تێدەگات",
            "لە",
            "هەموو",
            "قسەکان",
            "بە",
            "شێوەیەکی",
            "تەواو",
            "و",
            "ڕوون.",
        ]
    ):
        if idx == 6:
            cursor += 900
        s3_words.append(Word(w=tok, start_ms=cursor, end_ms=cursor + 420, conf=0.95))
        cursor += 480
    s3 = Sentence(words=tuple(s3_words), complete=True)
    selected = (s0, s1, s2, s3)
    all_words = tuple(w for s in selected for w in s.words)
    clip = Clip(
        clip_id="story-1",
        media_id="m-1",
        media_sha256="b" * 64,
        in_ms=100_000,
        out_ms=s3.end_ms + 100,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=_boundary(100_000, s3.end_ms + 100),
        transcript=ClipTranscript(
            raw_ckb=" ".join(s.text for s in selected),
            norm_ckb=" ".join(s.text for s in selected),
            en_aux=None,
            words=all_words,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
    )
    focus_pts = (
        FocusPoint(at_ms=100_000, center_x=960),
        FocusPoint(at_ms=171_000, center_x=1120),
    )
    per_shot_boxes = ((100_000, s3.end_ms + 100, 420, 260),)
    prepared = _prepare_viral_story_assembly(
        selected=selected,
        clip=clip,
        all_shot_cuts_ms=(160_000,),
        focus_points=focus_pts,
        per_shot_boxes=per_shot_boxes,
        raw_excited_intervals_ms=((169_500, 172_500),),
        payoff_at_ms=170_500,
        condense=True,
        cold_open=True,
        silence_threshold_ms=480,
        silence_target_gap_ms=160,
        excise_fillers=False,
        filler_tokens=None,
    )
    assert prepared is not None
    assert prepared.total_output_ms < 48_000
    assert prepared.final_spans[0].role == "cold_open"
    assert len(prepared.final_spans) >= 4
    assert prepared.remapped_focus_points[0].at_ms == 0
    # Verify hard 1 ms hold-and-step camera switch at cold-open -> body splice (zero wall pan)
    cold_open_end = prepared.final_spans[0].duration_ms
    assert any(
        p.at_ms == cold_open_end - 1 and p.center_x == 1120 for p in prepared.remapped_focus_points
    )
    assert any(
        p.at_ms == cold_open_end and p.center_x == 960 for p in prepared.remapped_focus_points
    )
    assert prepared.remapped_per_shot_boxes
    assert prepared.remapped_payoff_ms is not None
    assert prepared.jump_cuts_rel_ms


def test_v7_measure_audio_loudness_supports_assembly_spans(tmp_path: Path) -> None:
    wav_path = tmp_path / "source.wav"
    _write_pcm_wav(wav_path, [(1500, 0.4), (1000, 0.01), (1500, 0.4)], rate=48_000)
    s_a = Sentence(words=(Word(w="سڵاو.", start_ms=2600, end_ms=3800, conf=0.95),), complete=True)
    s_b = Sentence(words=(Word(w="باشە.", start_ms=200, end_ms=1300, conf=0.95),), complete=True)
    spans = (
        AssemblySpan(
            span_index=0, source_in_ms=2500, source_out_ms=3900, duration_ms=1400, sentences=(s_a,)
        ),
        AssemblySpan(
            span_index=1, source_in_ms=100, source_out_ms=1400, duration_ms=1300, sentences=(s_b,)
        ),
    )
    stats = measure_audio_loudness(
        source=wav_path,
        in_ms=0,
        duration_ms=2700,
        speech_chain=True,
        assembly_spans=spans,
    )
    assert math.isfinite(stats.input_i)
    assert math.isfinite(stats.input_tp)
