"""Tests for human-grade-director-v2 Lane 1 (D-360): frame-accurate cuts, broadcast audio
mastering, two-pass loudness on non-deliverable renders, and content-aware push schedules.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
from itertools import pairwise
from pathlib import Path

import pytest

from hawedit.boundary import BoundaryInputs, fuse_boundary
from hawedit.captions import build_ass, find_ffmpeg
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Provenance, Qc
from hawedit.judge import KURDISH_EDITORIAL_JUDGE
from hawedit.render import (
    DELIVERY_LUFS,
    MAX_VERTICAL_ZOOM,
    SPEECH_CHAIN_FILTERS,
    _parse_loudnorm_stats,
    audio_filter,
    content_aware_push_schedule,
    crop_filter,
    measure_audio_loudness,
    render_clip,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
FONTS = ROOT / "assets" / "fonts"
SOURCE_WIDTH, SOURCE_HEIGHT = 640, 360

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")


def _review_clip() -> Clip:
    boundary = fuse_boundary(
        BoundaryInputs(anchor_in_ms=500, anchor_out_ms=2_500, sentence_complete=True)
    )
    text = "ڕۆژنامەوانی کوردی"
    return Clip(
        clip_id="hd-d360",
        media_id="kurdish-speech-3cuts",
        media_sha256=FIXTURE_SHA256,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb=text,
            norm_ckb=text,
            en_aux=None,
            words=(),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
        ),
        editorial=Editorial(
            hook_score=0.85,
            self_contained=True,
            meaning_fidelity=0.95,
            misleading_edit_risk=0.05,
            cultural_landing=0.8,
            narrative_role="payoff",
            judge=KURDISH_EDITORIAL_JUDGE,
        ),
        output=Output(
            title_ckb=text,
            description_ckb=text,
            crop_target="9:16",
            caption_style="word_highlight",
            durations=(30,),
        ),
        qc=Qc(
            auto_pass=True,
            flags=(),
            human_reviewed=True,
            reviewed_by="Hawa",
            reviewed_at="2026-11-21T00:00:00Z",
            reviewed_sha256="0" * 64,
        ),
        provenance=Provenance.current(),
    )


def _write_ass(tmp_path: Path) -> Path:
    sentence = Sentence(
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=800, conf=0.95),
            Word(w="کوردی", start_ms=800, end_ms=1_600, conf=0.95),
        ),
        complete=True,
    )
    path = tmp_path / "captions.ass"
    path.write_text(build_ass((sentence,)), encoding="utf-8")
    return path


# --- T1: Zero-double-cut per_shot_boxes alignment (D-360) ---------------------------------


def test_crop_filter_per_shot_boxes_snaps_two_ms_early_matching_focus_x() -> None:
    """AC-1 / T1: x, y_center_expr, and sendcmd w/h all switch -2 ms early on the same frame."""
    # Exact forensic repro from ai-c10/topic-14: in_ms=1_553_802, cut at +57_118 ms.
    clip_in_ms = 1_553_802
    cut_abs_ms = clip_in_ms + 57_118
    focus_points = (
        (clip_in_ms, 540),
        (cut_abs_ms, 540),
        (cut_abs_ms + 1, 1_360),
        (clip_in_ms + 70_000, 1_360),
    )
    shots = (
        (clip_in_ms, cut_abs_ms, 520, 320),
        (cut_abs_ms, clip_in_ms + 70_000, 360, 140),
    )

    chain = crop_filter(
        1920,
        1080,
        focus_points=focus_points,
        per_shot_boxes=shots,
        clip_in_ms=clip_in_ms,
    )

    # All four axes (x, y, w, h) must switch at 57.116 s (57.118 - 0.002), never 57.118 s.
    assert "57.116 crop w 522;57.116 crop h 932" in chain, chain
    assert "57.118 crop w" not in chain, chain
    assert "57.118 crop h" not in chain, chain
    # Both x (_interpolated) and y (y_center_expr) must carry lt(t\,57.116) and never 57.118.
    assert chain.count("lt(t\\,57.116)") == 2, chain
    assert "lt(t\\,57.118)" not in chain, chain

    # Regression guard: a tail punch-in inside [cut_ms - 2, cut_ms) from the outgoing shot
    # must never overwrite or trail the snapped shot-cut switch.
    shots_simple = (
        (0, 5_000, 520, 320),
        (5_000, 10_000, 360, 140),
    )
    tail_punch = ((0, 1.0), (4_998, 1.12), (4_999, 1.12), (5_000, 1.0), (10_000, 1.06))
    chain_with_tail = crop_filter(
        1920,
        1080,
        focus_x=960,
        per_shot_boxes=shots_simple,
        punch_ins=tail_punch,
        clip_in_ms=0,
    )
    assert "4.998 crop w 522;4.998 crop h 932" in chain_with_tail, chain_with_tail
    assert "4.999 crop w" not in chain_with_tail, chain_with_tail


# --- T2: Broadcast speech mastering & two_pass_loudness (D-360) ---------------------------


@needs_ffmpeg
def test_speech_chain_linear_loudnorm_tames_high_crest_audio(tmp_path: Path) -> None:
    """AC-2 / T2: SPEECH_CHAIN_FILTERS compressor + limiter keeps high-crest audio in linear
    loudnorm mode at -14.0 +- 0.5 LUFS and <= -1.0 dBTP, and render_clip honors two_pass_loudness.
    """
    assert "acompressor=threshold=-18dB:ratio=2.2:attack=10:release=120:makeup=3.5" in (
        SPEECH_CHAIN_FILTERS
    )
    assert "alimiter=limit=-5dB:attack=5:release=50:level=disabled" in SPEECH_CHAIN_FILTERS
    conditioned = audio_filter(speech_chain=True)
    assert conditioned.startswith(SPEECH_CHAIN_FILTERS)
    assert conditioned.index("alimiter=") < conditioned.index("loudnorm=")

    binary = find_ffmpeg()
    assert binary is not None

    # Build a 12 s high-crest-factor speech-like signal: modulated speech-band bed (realistic
    # LRA ~3-5 LU, ~-20 LUFS) mixed with sharp near-0 dBFS transient spikes every 1.5 s
    # (crest > 16 dB, breaking unconditioned linear loudnorm headroom).
    import array
    import wave

    high_crest = tmp_path / "high_crest.wav"
    sr = 48_000
    duration_s = 12
    n_samples = sr * duration_s
    pcm = array.array("h")
    two_pi = 2.0 * math.pi
    for i in range(n_samples):
        t = i / sr
        phrase_env = 0.05 + 0.09 * (0.5 + 0.5 * math.sin(two_pi * 0.22 * t))
        val = phrase_env * (0.7 * math.sin(two_pi * 240.0 * t) + 0.3 * math.sin(two_pi * 680.0 * t))
        if (t % 1.5) < 0.020:
            val += 0.90 * math.sin(two_pi * 1200.0 * t)
        sample = max(-32767, min(32767, int(val * 32767.0)))
        pcm.append(sample)
        pcm.append(sample)
    with wave.open(str(high_crest), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    # Confirm the raw unconditioned signal genuinely has high crest (> 13 dB linear headroom).
    raw_stats = measure_audio_loudness(
        high_crest, in_ms=0, duration_ms=12_000, binary=binary, speech_chain=False
    )
    assert raw_stats.input_tp - raw_stats.input_i > 13.0

    # Pass 1 with SPEECH_CHAIN_FILTERS tames peaks so Pass 2 stays linear on target.
    p1 = measure_audio_loudness(
        high_crest, in_ms=0, duration_ms=12_000, binary=binary, speech_chain=True
    )
    pass2_af = audio_filter(measured=p1, linear=True, speech_chain=True)
    pass2_out = tmp_path / "mastered.wav"
    proc = subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "info",
            "-nostats",
            "-i",
            str(high_crest),
            "-af",
            pass2_af,
            "-y",
            str(pass2_out),
        ],
        check=True,
        capture_output=True,
        timeout=30.0,
    )
    p2 = _parse_loudnorm_stats(proc.stderr.decode("utf-8", "replace"), default_norm_type="dynamic")
    assert p2.normalization_type == "linear", p2
    assert p2.output_i is not None
    assert abs(p2.output_i - DELIVERY_LUFS) <= 0.5, f"output_i={p2.output_i}"
    assert p2.output_tp is not None
    assert p2.output_tp <= -1.0 + 1e-3, f"output_tp={p2.output_tp}"

    # Verify render_clip(deliverable=False, two_pass_loudness=True) runs two-pass linear loudnorm
    # while default (deliverable=False, two_pass_loudness=False) preserves single-pass fast path.
    ass = _write_ass(tmp_path)
    res_two_pass = render_clip(
        _review_clip(),
        FIXTURE,
        ass,
        FONTS,
        tmp_path / "review_two_pass.mp4",
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        deliverable=False,
        speech_chain=True,
        two_pass_loudness=True,
    )
    assert res_two_pass.loudness_pass1 is not None
    assert res_two_pass.loudness_pass2 is not None
    assert res_two_pass.loudness_pass2.normalization_type == "linear"

    res_single_pass = render_clip(
        _review_clip(),
        FIXTURE,
        ass,
        FONTS,
        tmp_path / "review_single_pass.mp4",
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        deliverable=False,
    )
    assert res_single_pass.loudness_pass1 is None
    assert res_single_pass.loudness_pass2 is None


# --- T3: Content-aware emphasis push schedule (D-360) -------------------------------------


def test_content_aware_push_schedule_boosts_excited_and_payoff_spans() -> None:
    """AC-3 / T3: High-excitement & payoff spans push up to 1.12x; mid=1.06x; low<=1.03x."""
    spans = (
        (0, 3_000),  # calm low-energy -> 1.00x hold
        (3_000, 6_000),  # subtle low-energy -> 1.03x drift
        (6_000, 9_000),  # mid-energy -> 1.06x
        (9_000, 12_000),  # high-excitement -> >1.09x..1.12x
        (12_000, 15_000),  # quiet narrative payoff -> boosted to 1.12x
    )
    excitement = (0.10, 0.25, 0.50, 0.85, 0.20)
    schedule = content_aware_push_schedule(
        spans,
        excitement_by_span=excitement,
        payoff_at_ms=13_500,
        step_ms=80,
    )
    assert schedule

    def _span_max(start_ms: int, end_ms: int, *, include_end: bool = False) -> float:
        factors = [
            f
            for t, f in schedule
            if (start_ms <= t <= end_ms if include_end else start_ms <= t < end_ms)
        ]
        assert factors, f"no keyframes for span {(start_ms, end_ms)}"
        return max(factors)

    calm_max = _span_max(0, 3_000)
    subtle_max = _span_max(3_000, 6_000)
    mid_max = _span_max(6_000, 9_000)
    excited_max = _span_max(9_000, 12_000)
    payoff_max = _span_max(12_000, 15_000, include_end=True)

    assert calm_max == 1.0
    assert 1.0 < subtle_max <= 1.03
    assert 1.04 < mid_max <= 1.06
    assert mid_max < excited_max <= 1.12
    assert payoff_max == pytest.approx(1.12, abs=1e-3)
    assert payoff_max > excited_max

    # Every keyframe stays clamped in [1.0, MAX_VERTICAL_ZOOM], timestamps strictly increasing.
    assert all(1.0 <= f <= MAX_VERTICAL_ZOOM for _, f in schedule)
    assert all(t2 > t1 for (t1, _), (t2, _) in pairwise(schedule))

    # Each span opens at 1.0 (clean reset at shot boundary) and rises monotonically within span.
    for s_start, s_end in spans:
        span_pts = [(t, f) for t, f in schedule if s_start <= t < s_end]
        assert span_pts[0] == (s_start, 1.0)
        assert all(f2 >= f1 for (_, f1), (_, f2) in pairwise(span_pts))

    # Defaults when excitement_by_span is omitted -> mid-energy (1.06x).
    default_sched = content_aware_push_schedule(((0, 2_000),), step_ms=100)
    assert default_sched[-1] == (2_000, 1.06)

    # Extreme excitement values clamp safely and empty spans return ().
    clamped = content_aware_push_schedule(((0, 2_000),), excitement_by_span=(5.0,), step_ms=100)
    assert all(1.0 <= f <= 1.12 and f <= MAX_VERTICAL_ZOOM for _, f in clamped)
    assert content_aware_push_schedule(()) == ()

    # Invalid arguments are refused (fail-stop).
    with pytest.raises(ValueError, match="step_ms must be positive"):
        content_aware_push_schedule(spans, step_ms=0)
    with pytest.raises(ValueError, match="finite"):
        content_aware_push_schedule(((0, 2_000),), excitement_by_span=(math.nan,))

    # Integrates directly with crop_filter().
    chain = crop_filter(1920, 1080, focus_x=960, punch_ins=schedule)
    assert chain.startswith("sendcmd=c='")

    # D-364: min_push_span_ms holds dynamic multi-cam shots rock-steady at 1.0x (zero strobe).
    multi_cam = content_aware_push_schedule(
        ((0, 8_000), (8_000, 26_000)),
        excitement_by_span=(0.90, 0.80),
        step_ms=40,
        min_push_span_ms=15_000,
    )
    short_shot_factors = [f for t, f in multi_cam if t < 8_000]
    long_shot_factors = [f for t, f in multi_cam if t >= 8_000]
    assert short_shot_factors and all(f == 1.0 for f in short_shot_factors)
    assert max(long_shot_factors) > 1.09
