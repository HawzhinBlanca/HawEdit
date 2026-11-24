"""Tests for HawEdit V9 episode arc discovery, client delivery pack & HTML gallery (D-389/D-390)."""

from __future__ import annotations

import json
import struct
import subprocess
import wave
import zipfile
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import DiscoveryPath
from hawedit.delivery import parse_srt_times
from hawedit.discovery import Candidate
from hawedit.sentences import Sentence
from hawedit.transcripts import Word
from hawedit.v8.compiler import (
    DefaultV8SubtitleRenderer,
    LockedCropWindow,
    ReelQualityError,
    SubtitleArtifact,
    V8CompileConfig,
    V8CompileResult,
    VideoGrillReport,
)
from hawedit.v8.delivery_pack import (
    DeliveryPackError,
    extract_v8_cover_png,
    verify_client_pack_complete,
    write_client_delivery_pack,
    write_client_review_html,
)
from hawedit.v8.episode import (
    V8EpisodeConfig,
    V8EpisodeError,
    compile_v8_episode,
    discover_viral_arcs_offline,
)
from hawedit.v8.schema import CameraMove, DirectorScript, VisualInterrupt


def _write_pcm_wav(
    wav_path: Path,
    duration_s: float,
    *,
    sample_rate: int = 8_000,
    high_energy_windows_s: tuple[tuple[float, float, float], ...] = (),
) -> Path:
    """Write a deterministic 16-bit mono PCM WAV with configurable high-energy speech windows."""
    n_samples = int(round(duration_s * sample_rate))
    t = np.arange(n_samples, dtype=np.float32) / float(sample_rate)
    amp = np.full(n_samples, 0.06, dtype=np.float32)
    for start_s, end_s, boost in high_energy_windows_s:
        mask = (t >= start_s) & (t <= end_s)
        burst = 1.0 + 0.65 * np.sin(2.0 * np.pi * 3.5 * (t[mask] - start_s))
        amp[mask] = np.minimum(0.92, boost * burst)
    pcm = np.clip(np.round(amp * 32767.0 * np.sin(2.0 * np.pi * 220.0 * t)), -32767, 32767).astype(
        "<i2"
    )
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return wav_path


def _make_sentence(
    text: str,
    start_ms: int,
    duration_ms: int,
    *,
    complete: bool = True,
) -> Sentence:
    tokens = text.split()
    step = max(80, duration_ms // max(1, len(tokens)))
    words: list[Word] = []
    cur = start_ms
    for idx, tok in enumerate(tokens):
        w_end = (
            start_ms + duration_ms
            if idx == len(tokens) - 1
            else min(start_ms + duration_ms - 10, cur + step - 20)
        )
        if w_end <= cur:
            w_end = cur + 40
        words.append(Word(w=tok, start_ms=cur, end_ms=w_end, conf=0.98))
        cur = w_end + 10
    return Sentence(words=tuple(words), complete=complete)


def _make_fake_png(dest: Path) -> Path:
    # Minimal valid 1x1 PNG bytes for fast unit tests without FFmpeg.
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
        b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png_bytes)
    return dest


def _make_compile_result(
    out_dir: Path,
    *,
    clip_id: str = "ep29-r01-s0-2",
    duration_ms: int = 36_000,
    grill_passed: bool | None = True,
    with_overlay: bool = True,
    hook_title_ckb: str = "ئایا ژیری دەستکرد کارەکانمان دەبات؟",
) -> V8CompileResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4_path = out_dir / f"{clip_id}.v8.mp4"
    mp4_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 4096)

    ass_path = out_dir / f"{clip_id}.v8.ass"
    ass_path.write_text("[Script Info]\nTitle: test\n", encoding="utf-8")

    overlay_path: Path | None = None
    if with_overlay:
        overlay_path = out_dir / f"{clip_id}.v8.overlay.mov"
        overlay_path.write_bytes(b"MOVDATA" * 8192)

    words = (
        Word("ئایا", 100, 480, 0.99),
        Word("ژیری", 520, 950, 0.99),
        Word("دەستکرد", 1000, 1600, 0.99),
        Word("کارەکانمان", 1650, 2400, 0.99),
        Word("دەبات؟", 2450, 3100, 0.99),
        Word("لە", 4100, 4400, 0.98),
        Word("ڕاستیدا", 4450, 5200, 0.98),
        Word("ئەنجامەکەی", 5250, 6100, 0.98),
        Word("سەرسوڕهێنەرە.", 6150, 7200, 0.98),
    )
    script = DirectorScript(
        clip_id=clip_id,
        hook_title_ckb=hook_title_ckb,
        camera_moves=(
            CameraMove(
                start_ms=5_000,
                end_ms=9_000,
                kind="punch_cut",
                scale_start=1.12,
                scale_end=1.12,
                reason="emphasis punch",
            ),
        ),
        visual_interrupts=(
            VisualInterrupt(
                start_ms=4_000,
                end_ms=6_500,
                text_ckb="ئەنجامی چاوەڕواننەکراو",
                position="top",
            ),
        ),
    )
    script_path = out_dir / f"{clip_id}.director.json"
    script_path.write_text(script.to_json(indent=2) + "\n", encoding="utf-8")

    grill_report: VideoGrillReport | None = None
    if grill_passed is not None:
        grill_report = VideoGrillReport(
            mp4_path=mp4_path,
            duration_ms=duration_ms,
            fps=25.0,
            frame_count=int(duration_ms * 25 / 1000),
            cut_times_s=(5.0, 18.2),
            double_cuts=() if grill_passed else ((5.0, 5.12),),
            trailing_cuts=(),
            long_silences=(),
            audio_flat_factor=0.0,
            passed=grill_passed,
            defects=() if grill_passed else ("double_cuts: 1 flash",),
        )
        grill_path = out_dir / f"{clip_id}.grill.json"
        grill_path.write_text(json.dumps(grill_report.to_dict(), indent=2) + "\n", encoding="utf-8")

    return V8CompileResult(
        clip_id=clip_id,
        output_mp4=mp4_path,
        script=script,
        script_path=script_path,
        repaired_words=words,
        camera_filter="null",
        camera_jump_cuts_ms=(5_000,),
        subtitles=SubtitleArtifact(
            engine="skia" if with_overlay else "libass",
            ass_path=ass_path,
            overlay_path=overlay_path,
            chunk_count=5,
        ),
        locked_crops=(
            LockedCropWindow(
                start_ms=0,
                end_ms=duration_ms,
                focus_x_px=960,
                face_center_y_px=420,
                face_height_px=260,
                active_track_id=1,
            ),
        ),
        critique=None,
        critique_revisions=0,
        director_backend="offline",
        sub_engine="skia" if with_overlay else "libass",
        grill_report=grill_report,
    )


def _build_synthetic_episode_sentences() -> tuple[Sentence, ...]:
    """Build 3 clearly separated Kurdish stories across a 240-second episode."""
    sentences: list[Sentence] = []
    # Arc A (10s..52s = 42s): Strong question + concrete numbers + payoff, high acoustic energy
    sentences.append(
        _make_sentence(
            "ئایا دەزانیت ٩٠ لەسەدا لە کۆمپانیاکان چۆن ژیری دەستکرد بەکاردێنن؟",
            10_000,
            13_000,
            complete=True,
        )
    )
    sentences.append(
        _make_sentence(
            "لە ڕاستیدا هەزاران کارمەند تێچووی کارەکانیان بە نیوە کەم کردووەتەوە.",
            23_800,
            14_000,
            complete=True,
        )
    )
    sentences.append(
        _make_sentence(
            "کەواتە ئەنجامەکەی ئەوەیە کە هەر کەسێک خێرا فێربێت پێش دەکەوێت.",
            38_500,
            13_500,
            complete=True,
        )
    )

    # Weak filler region (60s..95s): unresolved pronoun openers, flat quiet energy
    sentences.append(
        _make_sentence("ئەوە هەر وایە و شتێکی ئاساییە لەو کاتەدا.", 60_000, 17_000, complete=True)
    )
    sentences.append(
        _make_sentence("بۆیە ئەویش هەر بەو شێوەیە بەردەوام بوو.", 77_600, 17_400, complete=True)
    )

    # Arc B (105s..148s = 43s): Contrast hook + concrete numbers + payoff, high energy
    sentences.append(
        _make_sentence(
            "بەڵام لە ڕاستیدا خەڵک وا دەزانێت ئەم کارە مەحاڵە بەڵام هەڵەیە.",
            105_000,
            14_000,
            complete=True,
        )
    )
    sentences.append(
        _make_sentence(
            "سەیرە کە لە ماوەی ٣ ساڵدا ٥٠٠ گەنجی کورد توانییان داهاتی باش دروست بکەن.",
            119_800,
            14_000,
            complete=True,
        )
    )
    sentences.append(
        _make_sentence(
            "ڕاستییەکەی دەرکەوت کە تەنها بە پلانی دروست دەکرێت سەرکەوتوو بیت.",
            134_500,
            13_500,
            complete=True,
        )
    )

    # Incomplete trailing fragment in the middle (must never be an arc boundary)
    sentences.append(
        _make_sentence("ئەگەر بێت و باسی ئەوە بکەین چونکە", 155_000, 12_000, complete=False)
    )

    # Arc C (185s..226s = 41s): Question + contrast + payoff, high energy
    sentences.append(
        _make_sentence(
            "بۆچی گرنگترین نهێنی سەرکەوتنی چێشتلێنان تەنها ئاگری هێواشە؟",
            185_000,
            13_000,
            complete=True,
        )
    )
    sentences.append(
        _make_sentence(
            "خەڵک پەلە دەکات بەڵام کاتێک ٢٠ خولەک زیاتر چاوەڕێ دەکەیت تامەکەی دەگۆڕێت.",
            198_800,
            13_500,
            complete=True,
        )
    )
    sentences.append(
        _make_sentence(
            "لە ئەنجامدا هەموو میوانەکان دەپرسن چۆن ئەم خواردنەت دروست کردووە.",
            213_000,
            13_000,
            complete=True,
        )
    )
    return tuple(sentences)


# ---------------------------------------------------------------------------
# 1. Offline Viral Arc Discovery Tests
# ---------------------------------------------------------------------------


def test_discover_viral_arcs_offline_finds_three_separated_complete_arcs(tmp_path: Path) -> None:
    sentences = _build_synthetic_episode_sentences()
    wav_path = _write_pcm_wav(
        tmp_path / "stage0.wav",
        duration_s=240.0,
        high_energy_windows_s=(
            (10.0, 52.0, 0.72),
            (105.0, 148.0, 0.76),
            (185.0, 226.0, 0.74),
        ),
    )

    arcs = discover_viral_arcs_offline(
        sentences,
        wav_path,
        max_clips=3,
        min_duration_ms=28_000,
        max_duration_ms=68_000,
        min_separation_ms=30_000,
    )

    assert len(arcs) == 3
    spans: list[tuple[int, int]] = []
    for sent_indices, score, reason in arcs:
        assert sent_indices == tuple(range(sent_indices[0], sent_indices[-1] + 1))
        s_first = sentences[sent_indices[0]]
        s_last = sentences[sent_indices[-1]]
        assert s_first.complete is True
        assert s_last.complete is True
        dur_ms = s_last.end_ms - s_first.start_ms
        assert 28_000 <= dur_ms <= 68_000
        assert score > 0.5
        assert "acoustic=" in reason
        spans.append((s_first.start_ms, s_last.end_ms))

    # Strict >= 30 s separation between every pair of selected arcs.
    spans.sort()
    for (_s1, e1), (s2, _e2) in pairwise(spans):
        assert s2 - e1 >= 30_000

    # Determinism check: second call produces identical output.
    arcs_again = discover_viral_arcs_offline(sentences, wav_path, max_clips=3)
    assert arcs == arcs_again


def test_discover_viral_arcs_offline_penalizes_unresolved_pronoun_openers(tmp_path: Path) -> None:
    # Identical acoustic profile across two 35s spans: one has a strong Kurdish question hook,
    # the other begins with unresolved pronoun "ئەوە" and continuation "بۆیە".
    weak = (
        _make_sentence("ئەوە شتێک بوو کە دوێنێ باسمان کرد لەو کۆبوونەوەیە.", 5_000, 17_000),
        _make_sentence("بۆیە ئەمەش هەر وەک پێشوو دەمێنێتەوە بێ گۆڕانکاری.", 22_500, 17_500),
    )
    strong = (
        _make_sentence("ئایا دەزانیت نهێنی سەرکەوتنی ١٠٠ کۆمپانیا چییە؟", 90_000, 17_000),
        _make_sentence("لە ئەنجامدا دەرکەوت کە تەنها ڕێکخستن هەموو شتێک دەگۆڕێت.", 107_500, 17_500),
    )
    sentences = weak + strong
    wav_path = _write_pcm_wav(
        tmp_path / "even.wav",
        duration_s=135.0,
        high_energy_windows_s=((5.0, 40.0, 0.50), (90.0, 125.0, 0.50)),
    )

    arcs = discover_viral_arcs_offline(sentences, wav_path, max_clips=2)
    assert len(arcs) == 2
    best_indices, best_score, best_reason = arcs[0]
    second_indices, second_score, second_reason = arcs[1]
    assert best_indices == (2, 3)
    assert second_indices == (0, 1)
    assert best_score > second_score + 0.25
    assert "question-hook" in best_reason
    assert "unresolved-opener" in second_reason


def test_discover_viral_arcs_offline_fail_stop_validation(tmp_path: Path) -> None:
    sentences = _build_synthetic_episode_sentences()
    wav_path = _write_pcm_wav(tmp_path / "ok.wav", duration_s=10.0)

    with pytest.raises(V8EpisodeError, match="empty sentences"):
        discover_viral_arcs_offline((), wav_path)

    with pytest.raises(V8EpisodeError, match="missing or empty"):
        discover_viral_arcs_offline(sentences, tmp_path / "nonexistent.wav")

    with pytest.raises(V8EpisodeError, match="No complete-sentence viral arcs"):
        discover_viral_arcs_offline(
            sentences[:1],
            wav_path,
            min_duration_ms=50_000,
            max_duration_ms=60_000,
        )


# ---------------------------------------------------------------------------
# 2. Client Delivery Pack, Overlay Cleanup & Verification Tests
# ---------------------------------------------------------------------------


def test_write_client_delivery_pack_and_overlay_cleanup(tmp_path: Path) -> None:
    source_mp4 = tmp_path / "episode.mp4"
    source_mp4.write_bytes(b"SRC")
    out_dir = tmp_path / "out"
    res = _make_compile_result(out_dir, grill_passed=True, with_overlay=True)
    overlay_path = res.subtitles.overlay_path
    assert overlay_path is not None and overlay_path.is_file()
    expected_overlay_size = overlay_path.stat().st_size

    pack = write_client_delivery_pack(
        res,
        source_mp4=source_mp4,
        clip_in_ms=120_000,
        clip_out_ms=156_000,
        fps=25.0,
        media_id="ep29",
        keep_overlay=False,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )

    # All deliverables exist, non-empty, valid
    verify_client_pack_complete(pack)
    assert pack.social_zip_path is not None
    with zipfile.ZipFile(pack.social_zip_path) as archive:
        assert set(archive.namelist()) == {"reel.mp4", "captions.ckb.srt", "cover.png", "post.txt"}
        assert archive.read("reel.mp4") == res.output_mp4.read_bytes()
        assert archive.read("captions.ckb.srt") == pack.srt_path.read_bytes()
        assert pack.hook_title_ckb in archive.read("post.txt").decode("utf-8")
    assert pack.srt_path.name == f"{res.clip_id}.v8.srt"
    assert pack.edl_path.name == f"{res.clip_id}.v8.edl"
    assert pack.otio_path.name == f"{res.clip_id}.v8.otio"
    assert pack.cover_png_path.name == f"{res.clip_id}.v8.cover.png"

    # SRT parses cleanly and contains Kurdish repaired words
    srt_text = pack.srt_path.read_text(encoding="utf-8")
    cues = parse_srt_times(srt_text)
    assert len(cues) >= 2
    assert "ژیری" in srt_text and "سەرسوڕهێنەرە." in srt_text

    # EDL has CMX 3600 source timecodes starting at 00:02:00:00 (120s @ 25fps)
    edl_text = pack.edl_path.read_text(encoding="utf-8")
    assert "00:02:00:00" in edl_text
    assert "00:00:00:00" in edl_text

    # OTIO is schema-valid Timeline.1 with V8 editorial markers
    otio_doc = json.loads(pack.otio_path.read_text(encoding="utf-8"))
    assert otio_doc["OTIO_SCHEMA"] == "Timeline.1"
    v_clip = otio_doc["tracks"]["children"][0]["children"][0]
    marker_types = {m["metadata"]["type"] for m in v_clip["markers"]}
    assert {"hook", "camera_move", "visual_interrupt", "speaker_turn"} <= marker_types

    # Temporary .v8.overlay.mov was cleaned up and bytes reclaimed recorded!
    assert pack.overlay_cleaned is True
    assert pack.overlay_bytes_reclaimed == expected_overlay_size
    assert not overlay_path.exists()
    assert pack.face_share == 1.0
    assert pack.grill_passed is True


def test_overlay_preserved_when_keep_overlay_or_grill_not_passed(tmp_path: Path) -> None:
    source_mp4 = tmp_path / "episode.mp4"
    source_mp4.write_bytes(b"SRC")

    # Case 1: keep_overlay=True keeps .mov even when grill passed
    res_keep = _make_compile_result(tmp_path / "keep", clip_id="c-keep", grill_passed=True)
    pack_keep = write_client_delivery_pack(
        res_keep,
        source_mp4=source_mp4,
        clip_in_ms=10_000,
        clip_out_ms=46_000,
        keep_overlay=True,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )
    assert pack_keep.overlay_cleaned is False
    assert pack_keep.overlay_bytes_reclaimed == 0
    assert res_keep.subtitles.overlay_path is not None
    assert res_keep.subtitles.overlay_path.is_file()

    # Case 2: grill_passed=False keeps .mov for forensic debugging
    res_fail = _make_compile_result(tmp_path / "fail", clip_id="c-fail", grill_passed=False)
    pack_fail = write_client_delivery_pack(
        res_fail,
        source_mp4=source_mp4,
        clip_in_ms=10_000,
        clip_out_ms=46_000,
        keep_overlay=False,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )
    assert pack_fail.overlay_cleaned is False
    assert res_fail.subtitles.overlay_path is not None
    assert res_fail.subtitles.overlay_path.is_file()

    # Case 3: grill_report=None keeps .mov (never delete without verified grill pass)
    res_none = _make_compile_result(tmp_path / "none", clip_id="c-none", grill_passed=None)
    pack_none = write_client_delivery_pack(
        res_none,
        source_mp4=source_mp4,
        clip_in_ms=10_000,
        clip_out_ms=46_000,
        keep_overlay=False,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )
    assert pack_none.overlay_cleaned is False
    assert res_none.subtitles.overlay_path is not None
    assert res_none.subtitles.overlay_path.is_file()


def test_verify_client_pack_complete_fails_loudly_on_missing_or_empty_artifact(
    tmp_path: Path,
) -> None:
    source_mp4 = tmp_path / "episode.mp4"
    source_mp4.write_bytes(b"SRC")
    res = _make_compile_result(tmp_path / "out", grill_passed=True)
    pack = write_client_delivery_pack(
        res,
        source_mp4=source_mp4,
        clip_in_ms=0,
        clip_out_ms=36_000,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )

    # Delete OTIO -> must fail loudly
    pack.otio_path.unlink()
    with pytest.raises(DeliveryPackError, match="otio_path missing"):
        verify_client_pack_complete(pack)

    # Restore empty OTIO -> must fail loudly
    pack.otio_path.write_text("", encoding="utf-8")
    with pytest.raises(DeliveryPackError, match="otio_path is empty"):
        verify_client_pack_complete(pack)

    # Corrupt OTIO JSON -> must fail loudly
    pack.otio_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(DeliveryPackError, match="otio_path invalid JSON"):
        verify_client_pack_complete(pack)


def test_extract_v8_cover_png_real_ffmpeg_1080x1920(tmp_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "Bundled FFmpeg must be available"

    mp4_path = tmp_path / "sample.v8.mp4"
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x112233:s=1080x1920:r=25:d=1.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(mp4_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    assert proc.returncode == 0, proc.stderr

    cover_path = extract_v8_cover_png(
        mp4_path, tmp_path / "sample.v8.cover.png", at_seconds=0.6, ffmpeg=ffmpeg
    )
    raw = cover_path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (1080, 1920)


# ---------------------------------------------------------------------------
# 3. Client HTML Review Gallery Tests
# ---------------------------------------------------------------------------


def test_write_client_review_html_self_contained_rtl_badges_and_downloads(tmp_path: Path) -> None:
    source_mp4 = tmp_path / "ep29.mp4"
    source_mp4.write_bytes(b"SRC")
    out_dir = tmp_path / "review"

    res1 = _make_compile_result(
        out_dir,
        clip_id="ep29-r01-s0-2",
        grill_passed=True,
        hook_title_ckb="ئایا <AI> کارەکانمان دەبات؟",
    )
    res2 = _make_compile_result(
        out_dir,
        clip_id="ep29-r02-s5-7",
        grill_passed=False,
        hook_title_ckb="نهێنی گەورەی چێشتلێنان",
    )
    p1 = write_client_delivery_pack(
        res1,
        source_mp4=source_mp4,
        clip_in_ms=10_000,
        clip_out_ms=46_000,
        loudness_lufs=-14.0,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )
    p2 = write_client_delivery_pack(
        res2,
        source_mp4=source_mp4,
        clip_in_ms=105_000,
        clip_out_ms=141_000,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )

    html_path = write_client_review_html(
        [p1, p2],
        out_dir / "client-review.html",
        episode_title="Zar Podcast Ep 29",
        source_name="ep29.mp4",
        director_backend="offline",
        total_wall_s=42.5,
        style_preset="viral_gold",
    )
    content = html_path.read_text(encoding="utf-8")

    blind = (out_dir / "blind-review.html").read_text(encoding="utf-8")
    assert "blind-review.html" in content
    assert blind.count("<video ") == 2
    assert "GRILL PASSED" not in blind and p1.hook_title_ckb not in blind
    assert "meaning" in blind and "caption_accuracy" in blind
    # Zero external CDN links
    assert "http://" not in content
    assert "https://" not in content

    # RTL Kurdish hook titles + XSS escaping
    assert 'dir="rtl" lang="ckb"' in content
    assert "ئایا &lt;AI&gt; کارەکانمان دەبات؟" in content
    assert "نهێنی گەورەی چێشتلێنان" in content

    # Video player, cover thumbnail, green/red grill badges, telemetry stats
    assert "<video controls" in content
    assert "GRILL PASSED ✓" in content
    assert "GRILL FAILED" in content
    assert "-14.0 LUFS" in content
    assert "Double Cuts" in content
    assert "Silences" in content
    assert "Face Share" in content

    # All 7 download links present per clip
    for label in ("MP4", "SRT", "EDL", "OTIO", "Cover PNG", "Director JSON", "Grill JSON"):
        assert f">{label}</a>" in content

    with pytest.raises(DeliveryPackError, match="zero delivery packs"):
        write_client_review_html([], out_dir / "empty.html")


# ---------------------------------------------------------------------------
# 4. Full-Episode Multi-Reel Compiler Tests (`compile_v8_episode`)
# ---------------------------------------------------------------------------


def _write_transcript_json(path: Path, sentences: tuple[Sentence, ...]) -> Path:
    words_payload = [
        {"w": w.w, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
        for s in sentences
        for w in s.words
    ]
    path.write_text(json.dumps({"words": words_payload}, ensure_ascii=False), encoding="utf-8")
    return path


def test_compile_v8_episode_offline_batch_with_mocked_compiler(tmp_path: Path) -> None:
    sentences = _build_synthetic_episode_sentences()
    source_mp4 = tmp_path / "zar-ep29.mp4"
    source_mp4.write_bytes(b"SOURCE_VIDEO")
    transcript_json = _write_transcript_json(tmp_path / "ep29.transcript.raw.json", sentences)
    wav_path = _write_pcm_wav(
        tmp_path / "stage0.wav",
        duration_s=240.0,
        high_energy_windows_s=(
            (10.0, 52.0, 0.72),
            (105.0, 148.0, 0.76),
            (185.0, 226.0, 0.74),
        ),
    )

    compiled_calls: list[dict[str, Any]] = []

    def fake_compiler(**kwargs: Any) -> V8CompileResult:
        compiled_calls.append(kwargs)
        return _make_compile_result(
            kwargs["out_dir"],
            clip_id=kwargs["clip_id"],
            duration_ms=kwargs["clip_out_ms"] - kwargs["clip_in_ms"],
            grill_passed=True,
            with_overlay=True,
        )

    out_dir = tmp_path / "episode_out"
    result = compile_v8_episode(
        source_mp4,
        out_dir,
        transcript_path=transcript_json,
        audio_wav_path=wav_path,
        config=V8EpisodeConfig(
            director="offline",
            max_clips=3,
            style_preset="viral_gold",
            brand_accent_hex="#FFD700",
        ),
        clip_compiler=fake_compiler,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )

    assert len(compiled_calls) == 3
    assert len(result.clips) == 3
    assert result.all_grills_passed is True
    assert result.total_wall_s >= 0.0
    assert result.episode_json_path.is_file()
    assert result.review_html_path.is_file()

    # Every clip has a verified complete pack & cleaned overlay
    for idx, item in enumerate(result.clips, start=1):
        assert item.rank == idx
        assert item.grill_passed is True
        assert item.duration_s > 28.0
        assert item.delivery_pack.overlay_cleaned is True
        verify_client_pack_complete(item.delivery_pack)

    # episode.v8.json contains complete audit payload & config
    ep_doc = json.loads(result.episode_json_path.read_text(encoding="utf-8"))
    assert ep_doc["clip_count"] == 3
    assert ep_doc["all_grills_passed"] is True
    assert ep_doc["config"]["style_preset"] == "viral_gold"
    assert ep_doc["config"]["brand_accent_hex"] == "#FFD700"

    # client-review.html links all 3 clips
    html_text = result.review_html_path.read_text(encoding="utf-8")
    for item in result.clips:
        assert item.clip_id in html_text

    def reject_first(**kwargs: Any) -> V8CompileResult:
        if not compiled_calls:
            compiled_calls.append(kwargs)
            raise ReelQualityError("trailing cut")
        return fake_compiler(**kwargs)

    compiled_calls.clear()
    retried = compile_v8_episode(
        source_mp4,
        tmp_path / "reserves",
        transcript_path=transcript_json,
        audio_wav_path=wav_path,
        config=V8EpisodeConfig(max_clips=1),
        clip_compiler=reject_first,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )
    assert len(compiled_calls) == 2
    assert len(retried.clips) == 1
    assert retried.quarantined[0]["clip_id"] != retried.clips[0].clip_id
    assert retried.quarantined[0]["error"] == "trailing cut"


def test_compile_v8_episode_explicit_sentence_ranges_and_omni_asr_hook(tmp_path: Path) -> None:
    sentences = _build_synthetic_episode_sentences()
    source_mp4 = tmp_path / "zar-ep29.mp4"
    source_mp4.write_bytes(b"SOURCE_VIDEO")
    raw_words = tuple(w for s in sentences for w in s.words)

    def fake_asr(src: Path, work_dir: Path) -> tuple[tuple[Word, ...], Path]:
        assert src == source_mp4
        t_out = work_dir / "asr.transcript.raw.json"
        t_out.parent.mkdir(parents=True, exist_ok=True)
        _write_transcript_json(t_out, sentences)
        return raw_words, t_out

    def fake_compiler(**kwargs: Any) -> V8CompileResult:
        return _make_compile_result(
            kwargs["out_dir"],
            clip_id=kwargs["clip_id"],
            duration_ms=kwargs["clip_out_ms"] - kwargs["clip_in_ms"],
            grill_passed=True,
        )

    result = compile_v8_episode(
        source_mp4,
        tmp_path / "omni_out",
        use_omni_asr=True,
        sentence_ranges=((0, 1, 2), (9, 10, 11)),
        config=V8EpisodeConfig(director="local-omni", max_clips=2),
        clip_compiler=fake_compiler,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
        asr_runner=fake_asr,
    )

    assert len(result.clips) == 2
    assert result.clips[0].sentence_indices == (0, 1, 2)
    assert result.clips[1].sentence_indices == (9, 10, 11)
    assert result.transcript_path is not None and result.transcript_path.is_file()


def test_compile_v8_episode_gemini_discovery_and_strict_no_fallback(tmp_path: Path) -> None:
    sentences = _build_synthetic_episode_sentences()
    source_mp4 = tmp_path / "zar-ep29.mp4"
    source_mp4.write_bytes(b"SOURCE_VIDEO")
    transcript_json = _write_transcript_json(tmp_path / "ep29.transcript.raw.json", sentences)

    def fake_gemini(
        _norm: Any, *, sentences: tuple[Sentence, ...], audio_metrics: Any
    ) -> tuple[Candidate, ...]:
        _ = audio_metrics
        return (
            Candidate(
                candidate_id="ep29-verbal-1",
                media_id="zar-ep29",
                in_ms=sentences[5].start_ms,
                out_ms=sentences[7].end_ms,
                path=DiscoveryPath.VERBAL,
                rank=1,
                score=0.95,
            ),
        )

    def fake_compiler(**kwargs: Any) -> V8CompileResult:
        assert isinstance(kwargs["config"], V8CompileConfig)
        assert kwargs["config"].director_backend == "gemini"
        return _make_compile_result(
            kwargs["out_dir"],
            clip_id=kwargs["clip_id"],
            duration_ms=kwargs["clip_out_ms"] - kwargs["clip_in_ms"],
            grill_passed=True,
        )

    result = compile_v8_episode(
        source_mp4,
        tmp_path / "gemini_out",
        transcript_path=transcript_json,
        config=V8EpisodeConfig(director="gemini", max_clips=2),
        clip_compiler=fake_compiler,
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
        gemini_discoverer=fake_gemini,
    )
    assert len(result.clips) == 1
    assert result.clips[0].sentence_indices == (5, 6, 7)
    assert "gemini-path-a" in result.clips[0].discovery_reason

    # Strict fail-stop: Gemini discovery failure MUST NOT silently fall back to offline!
    def failing_gemini(*_args: Any, **_kwargs: Any) -> tuple[Candidate, ...]:
        raise RuntimeError("Gemini quota exhausted")

    with pytest.raises(V8EpisodeError, match="Gemini Path A arc discovery failed"):
        compile_v8_episode(
            source_mp4,
            tmp_path / "gemini_fail",
            transcript_path=transcript_json,
            config=V8EpisodeConfig(director="gemini", max_clips=2),
            clip_compiler=fake_compiler,
            cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
            gemini_discoverer=failing_gemini,
        )


def test_compile_v8_episode_strict_fail_stop_inputs_and_config(tmp_path: Path) -> None:
    source_mp4 = tmp_path / "ep.mp4"
    source_mp4.write_bytes(b"SRC")

    # Neither transcript_path nor use_omni_asr=True -> strict fail-stop
    with pytest.raises(V8EpisodeError, match="transcript_path or use_omni_asr=True"):
        compile_v8_episode(source_mp4, tmp_path / "out")

    # Missing source video -> strict fail-stop
    with pytest.raises(V8EpisodeError, match="Source video not found"):
        compile_v8_episode(tmp_path / "missing.mp4", tmp_path / "out", use_omni_asr=True)

    # Invalid brand_accent_hex -> strict fail-stop
    with pytest.raises(V8EpisodeError, match="brand_accent_hex"):
        V8EpisodeConfig(brand_accent_hex="gold")

    # Invalid max_clips -> strict fail-stop
    with pytest.raises(V8EpisodeError, match="max_clips"):
        V8EpisodeConfig(max_clips=0)


def test_delivery_pack_defaults_edl_and_otio_to_result_retained_intervals(tmp_path: Path) -> None:
    """Regression for ponytail-audit #3: condensed/trimmed spans propagate into EDL & OTIO."""
    from dataclasses import replace

    source_mp4 = tmp_path / "episode.mp4"
    source_mp4.write_bytes(b"SRC")
    base_res = _make_compile_result(tmp_path / "out", clip_id="ep-condensed", grill_passed=True)
    condensed_spans = ((100_000, 103_000), (60_000, 78_000), (92_000, 112_000))
    res = replace(base_res, retained_intervals_ms=condensed_spans)

    pack = write_client_delivery_pack(
        res,
        source_mp4=source_mp4,
        clip_in_ms=60_000,
        clip_out_ms=115_000,
        fps=25.0,
        media_id="ep",
        cover_extractor=lambda _mp4, dst, _t: _make_fake_png(dst),
    )
    edl_text = pack.edl_path.read_text(encoding="utf-8")
    assert "001 " in edl_text and "002 " in edl_text and "003 " in edl_text
    otio_doc = json.loads(pack.otio_path.read_text(encoding="utf-8"))
    video_clips = otio_doc["tracks"]["children"][0]["children"]
    assert len(video_clips) == 3
    assert video_clips[0]["source_range"]["start_time"]["value"] == 2500


def test_legacy_cover_fails_loudly_and_clip_probes_never_fake_7_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressions for ponytail-audit #7 and #16."""
    from hawedit.clip import _probe_ffmpeg_version, _probe_revisions_digest
    from hawedit.pipeline import _ensure_clip_cover_image
    from hawedit.render import RenderError

    missing_mp4 = tmp_path / "missing.mp4"
    with pytest.raises(RenderError, match="missing or empty"):
        _ensure_clip_cover_image(tmp_path, "clip-01", missing_mp4)
    assert not (tmp_path / "clip-01.cover.png").exists()

    def _raise_os_error(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("ffmpeg missing")

    monkeypatch.setattr("hawedit.clip.subprocess.run", _raise_os_error)
    assert _probe_ffmpeg_version() == "unknown"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hawedit.clip.Path.is_file",
        lambda self: self.name != "revisions.json",
    )
    assert _probe_revisions_digest() == "unknown"


def test_subsegment_long_utterances_splits_fast_unpunctuated_podcast_clauses() -> None:
    """Fast unpunctuated > 28 s utterances split at >= 220 ms breath pauses cleanly."""
    from hawedit.v8.episode import _subsegment_long_utterances

    words: list[Word] = []
    t = 0
    for i in range(60):
        # 20s mark (word 19 -> 20) has a 350ms breath pause; 40s mark (word 39 -> 40) has 380ms
        w = Word(w=f"وشەی{i}", start_ms=t, end_ms=t + 850, conf=0.95)
        words.append(w)
        if i == 19:
            t += 850 + 350
        elif i == 39:
            t += 850 + 380
        else:
            t += 850 + 100
    mega = Sentence(words=tuple(words), complete=True)
    parts = _subsegment_long_utterances((mega,))
    assert len(parts) == 3
    assert all((p.end_ms - p.start_ms) <= 28_000 for p in parts)
    assert sum(len(p.words) for p in parts) == 60


def test_tighten_internal_word_silences_handles_short_bleeding_tail_and_trough(
    tmp_path: Path,
) -> None:
    """80 ms decay tail + 700 ms dead-air trough + 260 ms spoken word advances start_ms."""
    from hawedit.v8.compiler import _tighten_internal_word_silences

    sr = 16_000
    t = np.arange(sr * 3, dtype=np.float32) / float(sr)
    amp = np.zeros_like(t)
    # Case 1 (0.02..1.50s): prev word 0.02..0.30s bleeds 80ms (0.30..0.38s), 700ms silence
    # (0.38..1.08s), then true spoken word "کە" at 1.08..1.34s.
    amp[(t >= 0.02) & (t <= 0.38)] = 0.35
    amp[(t >= 1.08) & (t <= 1.34)] = 0.45
    # Case 2 (1.60..2.80s): speech 1.60..1.85s, 600ms silence, next onset 2.45..2.90s.
    amp[(t >= 1.60) & (t <= 1.85)] = 0.40
    amp[(t >= 2.45) & (t <= 2.90)] = 0.40
    pcm = np.clip(np.round(amp * 32767.0 * np.sin(2.0 * np.pi * 220.0 * t)), -32767, 32767).astype(
        "<i2"
    )
    wav_path = tmp_path / "bleed.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    words = (
        Word(w="هەیە", start_ms=20, end_ms=300, conf=0.95),
        Word(w="کە", start_ms=300, end_ms=1_500, conf=0.90),
        Word(w="پاشان", start_ms=1_600, end_ms=2_600, conf=0.92),
        Word(w="دەستپێدەکات", start_ms=2_600, end_ms=2_900, conf=0.92),
    )
    out = _tighten_internal_word_silences(words, wav_path)
    # Case 1: prev keeps 80ms decay tail; "کە" advances to true onset; >=600ms gap exposed.
    assert out[0].end_ms >= 380
    assert out[1].start_ms >= 1_030
    assert out[1].end_ms == 1_500
    assert out[1].start_ms - out[0].end_ms >= 600
    # Case 2: "پاشان" retracts end_ms; next word snaps back to 2.45s onset; >=500ms gap exposed.
    assert out[2].end_ms <= 1_920
    assert out[3].start_ms <= 2_470
    assert out[3].start_ms - out[2].end_ms >= 500


def test_unpunctuated_reel_has_timed_phrase_sidecar(tmp_path: Path) -> None:
    words = tuple(Word("بە زمانی", i * 400, i * 400 + 380, 0.98) for i in range(30))
    result = replace(_make_compile_result(tmp_path), repaired_words=words)
    pack = write_client_delivery_pack(
        result,
        source_mp4=tmp_path / "source.mp4",
        clip_in_ms=0,
        clip_out_ms=36_000,
        cover_extractor=lambda _mp4, out, _ts: _make_fake_png(out),
    )
    content = pack.srt_path.read_text(encoding="utf-8")
    cues = parse_srt_times(content)
    assert len(cues) >= 20
    assert cues[0][0] == 0
    assert cues[-1][1] == words[-1].end_ms
    tokens = [
        w for cue in content.strip().split("\n\n") for w in " ".join(cue.splitlines()[2:]).split()
    ]
    assert tokens == " ".join(w.w for w in words).split()


def test_sidecar_rejects_cues_past_rendered_end(tmp_path: Path) -> None:
    result = _make_compile_result(tmp_path, duration_ms=6000)
    with pytest.raises(DeliveryPackError, match="past the end"):
        write_client_delivery_pack(
            result,
            source_mp4=tmp_path / "source.mp4",
            clip_in_ms=0,
            clip_out_ms=36_000,
            cover_extractor=lambda _mp4, out, _ts: _make_fake_png(out),
        )


def test_closeup_outro_keeps_call_to_action_in_post_text(tmp_path: Path) -> None:
    result = _make_compile_result(tmp_path)
    title = "بۆ ئەڵقەی زیاتر"
    renderer = DefaultV8SubtitleRenderer(end_card=(title, None, None))
    renderer.set_hook_y_top_px(1030.0)
    renderer.protect_outro_faces([LockedCropWindow(0, 8000, 960, 500, 430)], 1920, 1080, 8000, [])
    subs = renderer.render_subtitles(
        words=result.repaired_words,
        script=result.script,
        clip_duration_ms=8000,
        out_dir=tmp_path,
        engine="libass",
    )
    assert subs.ass_path is not None
    ass = subs.ass_path.read_text(encoding="utf-8")
    assert ",EndCard," not in ass
    assert any(
        line.endswith(",1030,0")
        for line in ass.splitlines()
        if line.startswith("Style: HookTitle,")
    )
    pack = write_client_delivery_pack(
        replace(result, subtitles=subs),
        source_mp4=tmp_path / "src.mp4",
        clip_in_ms=0,
        clip_out_ms=8000,
        post_cta=(title,),
        cover_extractor=lambda _mp4, out, _ts: _make_fake_png(out),
    )
    assert pack.social_zip_path is not None
    with zipfile.ZipFile(pack.social_zip_path) as archive:
        assert title in archive.read("post.txt").decode()
