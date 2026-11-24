"""Regression tests for Cinema Intelligence v4 (ADRs D-365 to D-368)."""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from hawedit.audio_signals import analyze_word_energy_peaks
from hawedit.caption_polish import deduplicate_micro_stutters
from hawedit.captions import (
    DEFAULT_CAPTION_FONT,
    KURDISH_NON_TERMINAL_WORDS,
    POPUP_MAX_CHARS,
    VIRAL_FONT_SIZE,
    VIRAL_THEME,
    CaptionStyle,
    _rebalance_kurdish_chunks,
    build_ass,
)
from hawedit.gemini import _https
from hawedit.pipeline import _excited_caption_intervals_ms
from hawedit.render import audio_filter
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _w(text: str, start_ms: int, end_ms: int, conf: float = 0.95) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=conf)


def _write_modulated_wav(path: Path, word_amplitudes: list[tuple[int, int, float]]) -> None:
    """Create a 16 kHz mono 16-bit PCM WAV with controlled per-word RMS amplitudes."""
    sr = 16_000
    total_ms = max((e for _, e, _ in word_amplitudes), default=1_000) + 200
    n_samples = int(sr * total_ms / 1000)
    buf = [0.02] * n_samples
    for s_ms, e_ms, amp in word_amplitudes:
        s_i = max(0, int(sr * s_ms / 1000))
        e_i = min(n_samples, int(sr * e_ms / 1000))
        for i in range(s_i, e_i):
            buf[i] = amp * math.sin(2.0 * math.pi * 280.0 * i / sr)
    pcm = array.array("h", (max(-32767, min(32767, int(v * 32767.0))) for v in buf))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def test_word_energy_peaks_select_only_vocal_bursts_and_payoff(tmp_path: Path) -> None:
    """D-365: Word-level acoustic peaks never saturate 100% and spotlight true bursts + payoff."""
    words: list[Word] = []
    amps: list[tuple[int, int, float]] = []
    # 20 words across 10 seconds: words 6..8 are a loud vocal burst, word 17 is the payoff.
    for idx in range(20):
        s_ms = idx * 500
        e_ms = s_ms + 420
        amp = 0.85 if idx in (6, 7, 8) else 0.12
        words.append(_w(f"وشە{idx}", s_ms, e_ms))
        amps.append((s_ms, e_ms, amp))

    wav_path = tmp_path / "clip.wav"
    _write_modulated_wav(wav_path, amps)

    peaks = analyze_word_energy_peaks(wav_path, words, payoff_at_ms=8_700)
    assert len(peaks) == 2
    # First interval covers the genuine vocal burst around words 6..8 (3000..4420 ms).
    assert peaks[0][0] <= 3_000 and peaks[0][1] >= 4_420
    # Second interval spotlights the payoff around 8700 ms without turning the whole clip lime.
    assert peaks[1][0] <= 8_500 and peaks[1][1] >= 8_920
    # Strictly non-saturating: calm words 0..3 and 11..13 are NOT inside any excited peak.
    for calm_idx in (0, 1, 2, 11, 12, 13):
        mid = (words[calm_idx].start_ms + words[calm_idx].end_ms) / 2.0
        assert not any(s <= mid <= e for s, e in peaks)

    # Wired cleanly through _excited_caption_intervals_ms on >= 12-word clips.
    sent = Sentence(words=tuple(words), complete=True)
    intervals = _excited_caption_intervals_ms(
        (sent,),
        None,
        clip_in_ms=0,
        clip_out_ms=10_000,
        selected_sentences=(sent,),
        audio_path=wav_path,
        payoff_at_ms=8_700,
    )
    assert intervals == peaks


def test_kurdish_rebalance_eliminates_dangling_proclitics_and_orphans() -> None:
    """D-366: Kurdish prepositions never dangle at chunk end and 1-word orphans rebalance."""
    assert {"و", "بە", "لە", "ئەم", "ئەو", "ئەبێتە"}.issubset(KURDISH_NON_TERMINAL_WORDS)

    # Real ai-v3 pattern: `لاپتۆپەکە بکڕیت و` / `پەیوەندی کەی بە` / `ئەوە`
    chunks = (
        (_w("لاپتۆپەکە", 0, 400), _w("بکڕیت", 420, 800), _w("و", 820, 950)),
        (_w("پەیوەندی", 980, 1300), _w("کەی", 1320, 1600), _w("بە", 1620, 1750)),
        (_w("ئەوە", 1800, 2100),),
    )
    rebalanced = _rebalance_kurdish_chunks(chunks, max_words=3, max_width_px=None)
    # Chunk 0 no longer ends on dangling `و`; chunk 1 starts with `و` and carries `بە` forward.
    assert [w.w for w in rebalanced[0]] == ["لاپتۆپەکە", "بکڕیت"]
    assert rebalanced[1][0].w == "و"
    assert rebalanced[-1][-1].w == "ئەوە"
    # Zero 1-word orphans and zero dangling Kurdish proclitics anywhere.
    assert all(len(c) >= 2 for c in rebalanced)
    assert all(c[-1].w not in KURDISH_NON_TERMINAL_WORDS for c in rebalanced[:-1])

    # Real [3, 1] trailing long-word rebalance: `دنیا ڤیدیۆی تیا` + `ئەجووڵێن` -> [2, 2]
    long_orphan = (
        (_w("دنیا", 0, 300), _w("ڤیدیۆی", 320, 700), _w("تیا", 720, 900)),
        (_w("ئەجووڵێنەوە", 950, 1400),),
    )
    bal_tail = _rebalance_kurdish_chunks(long_orphan, max_words=3, max_width_px=None)
    assert [[w.w for w in c] for c in bal_tail] == [["دنیا", "ڤیدیۆی"], ["تیا", "ئەجووڵێنەوە"]]

    # End-to-end inside build_ass(..., merge_short_orphans=True) preserves all words in order.
    s = Sentence(
        words=(
            _w("لاپتۆپەکە", 0, 400),
            _w("بکڕیت", 420, 800),
            _w("و", 820, 950),
            _w("پەیوەندی", 980, 1300),
            _w("کەی", 1320, 1600),
            _w("بە", 1620, 1750),
            _w("ئەوە.", 1800, 2100),
        ),
        complete=True,
    )
    ass = build_ass(
        (s,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        merge_short_orphans=True,
        fonts_dir=FONTS_DIR,
    )
    k_lines = [line.split(",,", 1)[1] for line in ass.splitlines() if ",Kurdish," in line]
    assert not any(
        line.rstrip().endswith(" و") or line.rstrip().endswith(" بە") for line in k_lines
    )


def test_function_word_stutter_dedup_fixes_weku_weku_preserving_zor_zor() -> None:
    """D-366: Rapid spoken function-word stutters collapse while emphatic `زۆر زۆر` survives."""
    s = Sentence(
        words=(
            _w("وەکو", 0, 240),
            _w("وەکو", 280, 520),
            _w("ڕۆژنامەی", 560, 950),
            _w("زۆر", 1_000, 1_240),
            _w("زۆر", 1_280, 1_520),
            _w("جوان.", 1_560, 1_900),
        ),
        complete=True,
    )
    cleaned, removed = deduplicate_micro_stutters((s,))
    assert removed == 1
    assert [w.w for w in cleaned[0].words] == ["وەکو", "ڕۆژنامەی", "زۆر", "زۆر", "جوان."]
    assert cleaned[0].words[0].start_ms == 0 and cleaned[0].words[0].end_ms == 520


def test_gemini_https_timeout_defaults_to_300s_and_audio_filter_micro_fades() -> None:
    """D-367 / D-368: Gemini HTTP timeout >= 300 s and broadcast loop audio micro-fades work."""
    import inspect

    sig = inspect.signature(_https)
    assert sig.parameters["timeout_s"].default == 300.0

    # Legacy audio_filter() without boundary_fade_ms is byte-identical.
    plain = audio_filter(speech_chain=True)
    assert "afade=" not in plain

    # Broadcast loop micro-fades append cleanly after aresample=48000.
    faded = audio_filter(speech_chain=True, boundary_fade_ms=(15, 60), duration_ms=10_000)
    assert (
        "aresample=48000,afade=t=in:st=0:d=0.015:curve=qsin,afade=t=out:st=9.940:d=0.060:curve=qsin"
        in faded
    )
