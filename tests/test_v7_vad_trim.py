"""Unit and synthetic-WAV tests for D-377 Audio-VAD sub-word silence tightening."""

from __future__ import annotations

import array
import itertools
import math
import struct
import wave
from pathlib import Path

import pytest

from hawedit import silence as silence_mod
from hawedit.content_type import ContentType
from hawedit.edit_plan import (
    CURRENT_PLAN_VERSION,
    EditorialBrief,
    EffectiveConfiguration,
    SourceTimeMapping,
    VisualEditPlan,
    validate_edl,
)
from hawedit.sentences import Sentence
from hawedit.silence import (
    KURDISH_FILLER_TOKENS,
    plan_silence_tightening,
    tighten_ctc_word_onsets,
)
from hawedit.transcripts import Word


def _write_pcm_wav(
    path: Path,
    segments: list[tuple[int, float]],
    *,
    sample_rate: int = 16_000,
    nchannels: int = 1,
    sampwidth: int = 2,
    freq_hz: float = 440.0,
) -> Path:
    """Write a synthetic PCM WAV composed of (duration_ms, level_dbfs) sine/silence segments.

    A segment with ``level_dbfs <= -120.0`` writes exact zeros.
    """
    frames_bytes = bytearray()
    full_scale = {1: 127.0, 2: 32767.0, 3: 8388607.0, 4: 2147483647.0}[sampwidth]
    phase_idx = 0

    for dur_ms, level_dbfs in segments:
        n_frames = (dur_ms * sample_rate) // 1000
        # Sine wave RMS is amplitude / sqrt(2), so scale peak amplitude by sqrt(2).
        amp = (
            0.0
            if level_dbfs <= -120.0
            else min(1.0, (10.0 ** (level_dbfs / 20.0)) * math.sqrt(2.0))
        )
        omega = 2.0 * math.pi * freq_hz / sample_rate

        if sampwidth == 2:
            buf_i16 = array.array("h")
            for _ in range(n_frames):
                val = int(round(amp * full_scale * math.sin(omega * phase_idx)))
                val = max(-32768, min(32767, val))
                for _ch in range(nchannels):
                    buf_i16.append(val)
                phase_idx += 1
            frames_bytes.extend(buf_i16.tobytes())
        elif sampwidth == 1:
            buf_u8 = array.array("B")
            for _ in range(n_frames):
                val = 128 + int(round(amp * full_scale * math.sin(omega * phase_idx)))
                val = max(0, min(255, val))
                for _ch in range(nchannels):
                    buf_u8.append(val)
                phase_idx += 1
            frames_bytes.extend(buf_u8.tobytes())
        elif sampwidth == 3:
            for _ in range(n_frames):
                val = int(round(amp * full_scale * math.sin(omega * phase_idx)))
                val = max(-8388608, min(8388607, val))
                sample_b = val.to_bytes(3, "little", signed=True)
                for _ch in range(nchannels):
                    frames_bytes.extend(sample_b)
                phase_idx += 1
        elif sampwidth == 4:
            buf_i32 = array.array("i")
            for _ in range(n_frames):
                val = int(round(amp * full_scale * math.sin(omega * phase_idx)))
                val = max(-2147483648, min(2147483647, val))
                for _ch in range(nchannels):
                    buf_i32.append(val)
                phase_idx += 1
            frames_bytes.extend(buf_i32.tobytes())
        else:
            raise ValueError(f"unsupported sampwidth: {sampwidth}")

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames_bytes))
    return path


def _word(w: str, start_ms: int, end_ms: int, conf: float = 0.9) -> Word:
    return Word(w=w, start_ms=start_ms, end_ms=end_ms, conf=conf)


def test_tighten_ctc_word_onsets_is_exported_in_all() -> None:
    assert "tighten_ctc_word_onsets" in silence_mod.__all__


def test_tighten_ctc_word_onsets_exposes_clean_leading_silence_like_bajei(tmp_path: Path) -> None:
    """Mirrors Cooking s7-7 'بەجێی': 700 ms leading silence hidden inside a 960 ms word."""
    wav = _write_pcm_wav(
        tmp_path / "bajei.wav",
        [
            (400, -16.0),  # 0..400: prev word
            (700, -120.0),  # 400..1100: hidden leading silence
            (260, -16.0),  # 1100..1360: voiced 'بەجێی'
            (400, -16.0),  # 1360..1760: next word
        ],
    )
    words = (
        _word("لە", 0, 400, conf=0.8),
        _word("بەجێی", 400, 1360, conf=0.4),
        _word("هێشت", 1360, 1760, conf=0.9),
    )

    plan_before = plan_silence_tightening(words, 0, 1760, threshold_ms=480, target_gap_ms=160)
    assert plan_before.total_removed_ms == 0

    tightened = tighten_ctc_word_onsets(words, wav)
    assert len(tightened) == 3
    assert tightened[0] == words[0]
    assert tightened[1].w == "بەجێی"
    assert tightened[1].conf == pytest.approx(0.4)
    # Onset at 1100 ms minus 25 ms pad -> 1075 ms; end_ms preserved at 1360 ms.
    assert tightened[1].start_ms == 1075
    assert tightened[1].end_ms == 1360
    assert tightened[2] == words[2]

    plan_after = plan_silence_tightening(tightened, 0, 1760, threshold_ms=480, target_gap_ms=160)
    # Exposed gap is 1075 - 400 = 675 ms; keeping 160 ms removes 515 ms.
    assert plan_after.total_removed_ms == 515
    assert plan_after.removed_intervals_ms == ((480, 995),)


def test_tighten_ctc_word_onsets_skips_brief_weak_previous_word_bleed_like_nazani(
    tmp_path: Path,
) -> None:
    """Mirrors AI s86-87 'نازانی': 40 ms weak release bleed -> 860 ms silence -> 420 ms speech."""
    wav = _write_pcm_wav(
        tmp_path / "nazani.wav",
        [
            (200, -19.0),  # 0..200: previous word 'دەر'
            (40, -33.0),  # 200..240: 40 ms weak decay bleed (> 6 dB below -19 dBFS peak)
            (860, -120.0),  # 240..1100: 860 ms dead silence
            (420, -19.0),  # 1100..1520: 420 ms voiced 'نازانی'
            (200, -25.0),  # 1520..1720: next word 'تۆ'
        ],
    )
    words = (
        _word("دەر", 0, 200),
        _word("نازانی", 200, 1520),
        _word("تۆ", 1520, 1720),
    )

    plan_before = plan_silence_tightening(words, 0, 1720, threshold_ms=480, target_gap_ms=160)
    assert plan_before.total_removed_ms == 0

    tightened = tighten_ctc_word_onsets(words, wav)
    assert tightened[1].start_ms == 1075  # 1100 ms onset - 25 ms pad
    assert tightened[1].end_ms == 1520

    plan_after = plan_silence_tightening(tightened, 0, 1720, threshold_ms=480, target_gap_ms=160)
    # Gap [200..1075] = 875 ms -> cut [280..995] (715 ms); [200..280] retains the 40 ms tail.
    assert plan_after.total_removed_ms == 715
    assert plan_after.removed_intervals_ms == ((280, 995),)


def test_tighten_ctc_word_onsets_preserves_loud_or_long_initial_syllable(tmp_path: Path) -> None:
    """Real initial syllables (loud OR > 60 ms) before an internal pause are never skipped."""
    wav_loud = _write_pcm_wav(
        tmp_path / "loud_init.wav",
        [
            (40, -18.0),  # Loud initial burst matching word peak (NOT weak bleed)
            (300, -120.0),  # Internal pause
            (560, -18.0),  # Rest of word
        ],
    )
    w_loud = (_word("تاقی", 0, 900),)
    assert tighten_ctc_word_onsets(w_loud, wav_loud) == w_loud

    wav_long_weak = _write_pcm_wav(
        tmp_path / "long_weak_init.wav",
        [
            (120, -32.0),  # 120 ms weak syllable (> 60 ms max bleed)
            (400, -120.0),  # Internal pause
            (480, -18.0),  # Main vowel
        ],
    )
    w_long = (_word("ئەوە", 0, 1000),)
    assert tighten_ctc_word_onsets(w_long, wav_long_weak) == w_long


def test_tighten_ctc_word_onsets_trims_trailing_silence_and_respects_flag(tmp_path: Path) -> None:
    """Trailing unvoiced tail >= 250 ms is retracted with 35 ms breath pad when enabled."""
    wav = _write_pcm_wav(
        tmp_path / "trailing.wav",
        [
            (400, -18.0),  # 0..400: voiced speech
            (500, -120.0),  # 400..900: 500 ms trailing silence
        ],
    )
    words = (_word("ئەڕوات", 0, 900),)

    trimmed = tighten_ctc_word_onsets(words, wav, trim_trailing=True)
    assert trimmed[0].start_ms == 0
    assert trimmed[0].end_ms == 435  # 400 ms offset + 35 ms breath pad

    disabled = tighten_ctc_word_onsets(words, wav, trim_trailing=False)
    assert disabled == words

    wav_short_tail = _write_pcm_wav(
        tmp_path / "short_tail.wav",
        [
            (400, -18.0),
            (200, -120.0),  # < 250 ms threshold -> untouched
        ],
    )
    w_short = (_word("کورت", 0, 600),)
    assert tighten_ctc_word_onsets(w_short, wav_short_tail) == w_short


def test_tighten_ctc_word_onsets_respects_min_word_ms_and_min_leading_silence_ms(
    tmp_path: Path,
) -> None:
    wav = _write_pcm_wav(
        tmp_path / "thresholds.wav",
        [
            (300, -120.0),  # 0..300 silence
            (240, -18.0),  # 300..540 speech (total 540 ms < 550 ms min_word_ms)
            (160, -120.0),  # 540..700 silence (160 ms < 180 ms min_leading_silence_ms)
            (440, -18.0),  # 700..1140 speech (total 600 ms >= 550 ms)
        ],
    )
    words = (
        _word("کورت", 0, 540),
        _word("درێژ", 540, 1140),
    )
    assert tighten_ctc_word_onsets(words, wav) == words


def test_tighten_ctc_word_onsets_never_shrinks_below_120ms(tmp_path: Path) -> None:
    """Words whose remaining voiced span is < 120 ms are left untouched."""
    wav = _write_pcm_wav(
        tmp_path / "short_voiced.wav",
        [
            (600, -120.0),  # 0..600 silence
            (100, -18.0),  # 600..700 only 100 ms voiced (< 120 ms)
            (560, -120.0),  # 700..1260 silence
            (140, -18.0),  # 1260..1400 140 ms voiced (>= 120 ms)
        ],
    )
    words = (
        _word("کەم", 0, 700),
        _word("تەواو", 700, 1400),
    )
    tightened = tighten_ctc_word_onsets(words, wav)
    assert tightened[0] == words[0]  # Protected: < 120 ms voiced core
    assert tightened[1].start_ms == 1235  # 1260 - 25 = 1235
    assert tightened[1].end_ms == 1400
    assert tightened[1].end_ms - tightened[1].start_ms >= 120


def test_tighten_ctc_word_onsets_preserves_quiet_below_floor_words(tmp_path: Path) -> None:
    wav = _write_pcm_wav(tmp_path / "quiet.wav", [(800, -50.0)])
    words = (_word("چرپە", 0, 800),)
    assert tighten_ctc_word_onsets(words, wav, floor_db=-38.0) == words


def test_tighten_ctc_word_onsets_uses_relative_drop_db_above_floor(tmp_path: Path) -> None:
    """When peak_db - drop_db > floor_db, relative threshold trims room-hum leading pause."""
    wav = _write_pcm_wav(
        tmp_path / "hum.wav",
        [
            (400, -32.0),  # Above -38 dBFS floor, but 26 dB below -6 dBFS peak (> 22 dB drop)
            (400, -6.0),  # Loud speech peak (-6 dBFS -> threshold = -28 dBFS)
        ],
    )
    words = (_word("دەنگ", 0, 800),)
    tightened = tighten_ctc_word_onsets(words, wav, drop_db=22.0, floor_db=-38.0)
    assert tightened[0].start_ms == 375
    assert tightened[0].end_ms == 800


def test_tighten_ctc_word_onsets_preserves_monotonic_order(tmp_path: Path) -> None:
    wav = _write_pcm_wav(
        tmp_path / "multi.wav",
        [
            (250, -18.0),  # w0 voiced
            (350, -120.0),  # w0 trailing silence (0..600)
            (300, -120.0),  # w1 leading silence
            (300, -18.0),  # w1 voiced (600..1200)
            (200, -18.0),  # w2 short word (1200..1400)
            (260, -120.0),  # w3 leading silence
            (260, -18.0),  # w3 voiced
            (280, -120.0),  # w3 trailing silence (1400..2200)
        ],
    )
    words = (
        _word("یەک", 0, 600),
        _word("دوو", 600, 1200),
        _word("سێ", 1200, 1400),
        _word("چوار", 1400, 2200),
    )
    tightened = tighten_ctc_word_onsets(words, wav)
    assert len(tightened) == len(words)
    for orig, new in zip(words, tightened, strict=True):
        assert orig.start_ms <= new.start_ms < new.end_ms <= orig.end_ms
        if new != orig:
            assert new.end_ms - new.start_ms >= 120
    for prev_w, curr_w in itertools.pairwise(tightened):
        assert prev_w.end_ms <= curr_w.start_ms
    # w0 speech occupies frames 0..12 (0..260 ms -> +35 ms pad = 295 ms);
    # w1 trimmed start (900-25=875) -> combined 580 ms gap.
    assert tightened[0].end_ms == 295
    assert tightened[1].start_ms == 875
    assert tightened[2] == words[2]
    assert tightened[3].start_ms == 1635  # 1660 - 25
    assert tightened[3].end_ms == 1955  # 1920 + 35


def test_tighten_ctc_word_onsets_empty_words_returns_empty(tmp_path: Path) -> None:
    wav = _write_pcm_wav(tmp_path / "valid.wav", [(200, -20.0)])
    assert tighten_ctc_word_onsets((), wav) == ()


@pytest.mark.parametrize(
    ("nchannels", "sampwidth"),
    [
        (2, 2),  # 16-bit stereo
        (1, 1),  # 8-bit unsigned mono
        (1, 3),  # 24-bit signed mono
        (1, 4),  # 32-bit signed mono
    ],
)
def test_tighten_ctc_word_onsets_supports_pcm_formats(
    tmp_path: Path, nchannels: int, sampwidth: int
) -> None:
    wav = _write_pcm_wav(
        tmp_path / f"pcm_{nchannels}ch_{sampwidth}b.wav",
        [(400, -120.0), (400, -14.0)],
        nchannels=nchannels,
        sampwidth=sampwidth,
    )
    words = (_word("فۆرمات", 0, 800),)
    tightened = tighten_ctc_word_onsets(words, wav)
    assert tightened[0].start_ms == 375
    assert tightened[0].end_ms == 800


def test_tighten_ctc_word_onsets_fails_loudly_on_missing_or_corrupt_wav(tmp_path: Path) -> None:
    words = (_word("تێست", 0, 800),)

    # Missing file -> FileNotFoundError (even for empty words: zero silent fallback)
    missing = tmp_path / "does_not_exist.wav"
    with pytest.raises(FileNotFoundError, match="audio WAV not found"):
        tighten_ctc_word_onsets(words, missing)
    with pytest.raises(FileNotFoundError, match="audio WAV not found"):
        tighten_ctc_word_onsets((), missing)

    # Directory path -> ValueError
    with pytest.raises(ValueError, match="not a regular file"):
        tighten_ctc_word_onsets(words, tmp_path)

    # Garbage bytes -> ValueError
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"NOT_A_RIFF_WAV_FILE_AT_ALL")
    with pytest.raises(ValueError, match="corrupt or unreadable WAV"):
        tighten_ctc_word_onsets(words, corrupt)

    # Empty 0-byte file -> ValueError
    zero_byte = tmp_path / "empty.wav"
    zero_byte.write_bytes(b"")
    with pytest.raises(ValueError, match="corrupt or unreadable WAV"):
        tighten_ctc_word_onsets(words, zero_byte)

    # Valid WAV header with zero frames -> ValueError
    zero_frames = tmp_path / "zero_frames.wav"
    with wave.open(str(zero_frames), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(b"")
    with pytest.raises(ValueError, match="zero frames"):
        tighten_ctc_word_onsets(words, zero_frames)

    # Truncated payload (header claims 1.0 s = 32000 bytes, truncated to 400 bytes) -> ValueError
    truncated = _write_pcm_wav(tmp_path / "truncated.wav", [(1000, -18.0)])
    raw_bytes = truncated.read_bytes()
    # Keep full 44-byte RIFF header + only 400 bytes of sample data
    assert raw_bytes[:4] == b"RIFF"
    header_data_size = struct.unpack("<I", raw_bytes[40:44])[0]
    assert header_data_size == 32_000
    truncated.write_bytes(raw_bytes[:444])
    with pytest.raises(ValueError, match="truncated WAV"):
        tighten_ctc_word_onsets(words, truncated)


def test_tighten_ctc_word_onsets_input_parameter_validation(tmp_path: Path) -> None:
    wav = _write_pcm_wav(tmp_path / "ok.wav", [(200, -20.0)])
    words = (_word("وشە", 0, 200),)

    with pytest.raises(ValueError, match="min_word_ms"):
        tighten_ctc_word_onsets(words, wav, min_word_ms=0)
    with pytest.raises(ValueError, match="min_leading_silence_ms"):
        tighten_ctc_word_onsets(words, wav, min_leading_silence_ms=0)
    with pytest.raises(ValueError, match="pad_before_onset_ms"):
        tighten_ctc_word_onsets(words, wav, pad_before_onset_ms=-1)
    with pytest.raises(ValueError, match="frame_ms"):
        tighten_ctc_word_onsets(words, wav, frame_ms=0)
    with pytest.raises(ValueError, match="drop_db"):
        tighten_ctc_word_onsets(words, wav, drop_db=0.0)
    with pytest.raises(ValueError, match="drop_db"):
        tighten_ctc_word_onsets(words, wav, drop_db=math.nan)
    with pytest.raises(ValueError, match="floor_db"):
        tighten_ctc_word_onsets(words, wav, floor_db=1.0)
    with pytest.raises(ValueError, match="min_trailing_silence_ms"):
        tighten_ctc_word_onsets(words, wav, min_trailing_silence_ms=0)
    with pytest.raises(ValueError, match="pad_after_offset_ms"):
        tighten_ctc_word_onsets(words, wav, pad_after_offset_ms=-1)


def test_tighten_ctc_word_onsets_end_to_end_passes_validate_edl(tmp_path: Path) -> None:
    """End-to-end: VAD onset tightening + plan_silence_tightening passes validate_edl cleanly."""
    # Construct a 20 s clip with Stage 5 padding (120 ms lead, 180 ms tail) and two hidden pauses:
    # 1) Clean 700 ms pre-word pause inside 'بەجێی'
    # 2) 40 ms weak release bleed + 860 ms pause inside 'نازانی'
    segments: list[tuple[int, float]] = [
        (120, -120.0),  # 0..120 outer lead pad
        (5_000, -18.0),  # 120..5120 initial speech
        (700, -120.0),  # 5120..5820 hidden silence inside 'بەجێی'
        (280, -16.0),  # 5820..6100 voiced 'بەجێی'
        (5_000, -18.0),  # 6100..11100 middle speech
        (40, -33.0),  # 11100..11140 weak bleed tail before 'نازانی'
        (860, -120.0),  # 11140..12000 hidden silence inside 'نازانی'
        (420, -19.0),  # 12000..12420 voiced 'نازانی'
        (7_400, -18.0),  # 12420..19820 closing speech
        (180, -120.0),  # 19820..20000 outer tail pad
    ]
    wav = _write_pcm_wav(tmp_path / "clip_20s.wav", segments)

    words = (
        _word("سەرەتا", 120, 5_120),
        _word("بەجێی", 5_120, 6_100),  # 980 ms hiding 700 ms silence
        _word("ناوەڕاست", 6_100, 11_100),
        _word("نازانی", 11_100, 12_420),  # 1320 ms hiding 40 ms bleed + 860 ms silence
        _word("کۆتایی", 12_420, 19_820),
    )

    plan_before = plan_silence_tightening(
        words,
        0,
        20_000,
        threshold_ms=480,
        target_gap_ms=160,
        filler_tokens=KURDISH_FILLER_TOKENS,
        preserve_emphatic_repeats=True,
    )
    assert plan_before.total_removed_ms == 0

    tight_words = tighten_ctc_word_onsets(words, wav)
    plan_after = plan_silence_tightening(
        tight_words,
        0,
        20_000,
        threshold_ms=480,
        target_gap_ms=160,
        filler_tokens=KURDISH_FILLER_TOKENS,
        preserve_emphatic_repeats=True,
    )
    # 515 ms removed before 'بەجێی' + 715 ms removed before 'نازانی' = 1230 ms total
    assert len(plan_after.removed_intervals_ms) == 2
    assert plan_after.total_removed_ms == 515 + 715

    tm = SourceTimeMapping(
        clip_in_ms=0,
        clip_out_ms=20_000,
        retained_intervals_ms=plan_after.retained_intervals_ms,
    )
    vep = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="v7-vad-e2e",
        media_id="synthetic-20s",
        media_sha256="a" * 64,
        brief=EditorialBrief(
            viewer_takeaway="VAD trim E2E",
            content_type=ContentType.PODCAST,
            target_duration_ms=(15_000, 60_000),
        ),
        config=EffectiveConfiguration.resolve(
            content_type=ContentType.PODCAST,
            silence_threshold_ms=480,
            silence_target_gap_ms=160,
        ),
        time_mapping=tm,
        sentences=(Sentence(words=tight_words, complete=True),),
        filler_cut_edges_ms=plan_after.filler_cut_edges_ms,
    )
    edl = validate_edl(
        vep,
        words=tight_words,
        media_duration_ms=20_000,
        min_duration_ms=15_000,
        max_duration_ms=60_000,
    )
    assert edl.is_valid is True
    assert edl.violations == ()
    assert edl.output_duration_ms == 20_000 - 1_230
