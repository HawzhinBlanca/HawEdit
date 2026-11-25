"""Tests for V5 Human-Editor Director Engine (D-369..D-372).

Verifies:
- D-369: E3-safe Kurdish filler excision (touching CTC edges via ``filler_cut_edges_ms``),
  expanded Kurdish filler vocabulary (``نازانم چی و چی``, ``ئێ``, ``ئا``), and
  ``preserve_emphatic_repeats=True`` protecting intentional ``زۆر زۆر`` reduplications.
- D-370 / D-372: Sub-pixel floating-point ``zoompan`` director motion
  (``build_cinema_motion_filter``) with opening hook push-in, A/B cam scale toggles on
  jump-cuts, long-hold subdivision, payoff tightening, motorized-slider drift, studio color
  grade, and real FFmpeg exact AV sync with zero strobe.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pytest

from hawedit.captions import CaptionStyle, find_ffmpeg
from hawedit.content_type import ContentType, resolve_effective_configuration
from hawedit.edit_plan import (
    CURRENT_PLAN_VERSION,
    EditorialBrief,
    EditRuleViolationError,
    EffectiveConfiguration,
    SourceTimeMapping,
    VisualEditPlan,
    validate_edl,
)
from hawedit.pipeline import _resolve_cinema_motion
from hawedit.render import Reframe, build_cinema_motion_filter
from hawedit.sentences import Sentence
from hawedit.silence import (
    KURDISH_FILLER_TOKENS,
    plan_silence_tightening,
    tighten_sentences,
)
from hawedit.transcripts import Word


def _w(text: str, start_ms: int, end_ms: int, conf: float = 0.95) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=conf)


def test_d369_filler_excision_touching_words_clears_e3_and_preserves_emphatic_repeats() -> None:
    """Touching filler splices pass validate_edl via filler_cut_edges_ms while keeping زۆر زۆر."""
    clip_in_ms = 900
    clip_out_ms = 39_100
    words = (
        _w("ئەم", 1000, 1400),
        _w("زۆر", 1450, 1750),
        _w("زۆر", 1770, 2080),  # Emphatic Kurdish repeat -> MUST survive
        _w("گرنگە", 2100, 2600),
        _w("یەعنی", 2600, 2980),  # Touches previous word (0 ms gap) -> MUST excise cleanly
        _w("ئێمە", 2980, 3500),  # Touches filler end (0 ms gap) -> MUST survive
        _w("نازانم", 3550, 3900),
        _w("چی", 3920, 4120),
        _w("و", 4140, 4240),
        _w("چی", 4260, 4500),  # Multi-word Kurdish filler phrase -> MUST excise
        _w("دەست", 4550, 4850),
        _w("دەست", 4880, 5200),  # Non-emphatic stutter -> first copy excised
        _w("ئێ", 5220, 5450),  # Hesitation marker -> MUST excise
        # Dead-air pause: 5450..6950 (1500 ms)
        _w("بەردەوام", 6950, 22_000),
        _w("کار", 22_100, 38_950),
    )
    plan = plan_silence_tightening(
        words,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        threshold_ms=480,
        target_gap_ms=160,
        filler_tokens=KURDISH_FILLER_TOKENS,
        detect_restarts=True,
        preserve_emphatic_repeats=True,
    )
    # 1 ("یەعنی") + 4 ("نازانم چی و چی") + 1 ("دەست") + 1 ("ئێ") = 7 excised; both "زۆر" kept.
    assert plan.excised_word_count == 7
    assert plan.total_removed_ms > 1_500
    assert plan.filler_cut_edges_ms, "touching filler edges must be recorded for E3"

    tight_sents, _ = tighten_sentences(
        (Sentence(words=words, complete=True),),
        threshold_ms=480,
        target_gap_ms=160,
        filler_tokens=KURDISH_FILLER_TOKENS,
        detect_restarts=True,
        preserve_emphatic_repeats=True,
    )
    surviving_tokens = [w.w for s in tight_sents for w in s.words]
    assert surviving_tokens.count("زۆر") == 2
    assert "یەعنی" not in surviving_tokens
    assert "ئێ" not in surviving_tokens
    assert "نازانم" not in surviving_tokens
    assert surviving_tokens.count("دەست") == 1

    abs_retained = tuple((clip_in_ms + s, clip_in_ms + e) for s, e in plan.retained_intervals_ms)
    edl_plan = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="v5-d369-filler-test",
        media_id="media_v5",
        media_sha256="a" * 64,
        brief=EditorialBrief(
            viewer_takeaway="تێستی بڕینی وشە زیادەکان",
            content_type=ContentType.PODCAST,
            target_duration_ms=(30_000, 45_000),
        ),
        config=EffectiveConfiguration.resolve(
            content_type=ContentType.PODCAST,
            caption_style=CaptionStyle.WORD_HIGHLIGHT,
            silence_threshold_ms=480,
            silence_target_gap_ms=160,
        ),
        time_mapping=SourceTimeMapping(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            retained_intervals_ms=abs_retained,
        ),
        sentences=(Sentence(words=words, complete=True),),
        filler_cut_edges_ms=plan.filler_cut_edges_ms,
    )
    # Round-trip serialization preserves filler_cut_edges_ms
    round_tripped = VisualEditPlan.from_json(edl_plan.to_json())
    assert round_tripped.filler_cut_edges_ms == plan.filler_cut_edges_ms

    # E3 validation passes with filler_cut_edges_ms
    result = validate_edl(round_tripped, words=words)
    assert result.is_valid is True
    assert result.violations == ()

    # Without filler_cut_edges_ms, a 0 ms interior cut is STILL strictly rejected!
    strict_plan = VisualEditPlan(
        version=edl_plan.version,
        clip_id=edl_plan.clip_id,
        media_id=edl_plan.media_id,
        media_sha256=edl_plan.media_sha256,
        brief=edl_plan.brief,
        config=edl_plan.config,
        time_mapping=edl_plan.time_mapping,
        sentences=edl_plan.sentences,
        filler_cut_edges_ms=(),
    )
    with pytest.raises(EditRuleViolationError, match="padding 0 ms outside allowed"):
        validate_edl(strict_plan, words=words)


def test_d370_build_cinema_motion_filter_choreography_and_bounds() -> None:
    """Director builds hook push-in, A/B jump-cut toggles, payoff lock-in, and studio grade."""
    plan = build_cinema_motion_filter(
        duration_ms=32_000,
        shot_cuts_ms=(8_200, 21_500),
        jump_cuts_ms=(4_100, 14_300, 26_800),
        excitement_intervals_ms=((11_000, 12_500), (27_000, 29_500)),
        payoff_at_ms=28_000,
        fps=25.0,
        cinema_grade=True,
    )
    assert len(plan.beats) >= 6
    # Beat 0 is the smooth cosine S-curve opening hook push-in
    assert plan.beats[0][0] == 0
    assert plan.beats[0][2] == pytest.approx(1.00)
    assert plan.beats[0][3] == pytest.approx(1.14)
    # Every zoom level stays strictly in [1.00, 1.20]
    for b_s, b_e, z0, z1 in plan.beats:
        assert b_e > b_s
        assert 1.00 <= z0 <= 1.20
        assert 1.00 <= z1 <= 1.20
    # Jump-cuts produce real A/B scale changes recorded in jump_cuts_ms
    assert len(plan.jump_cuts_ms) >= 2
    assert "zoompan=z='" in plan.filter_str
    assert "0.5-0.5*cos(PI*" in plan.filter_str
    assert "d=1:s=1080x1920:fps=25" in plan.filter_str
    assert "eq=contrast=1.05:saturation=1.09:brightness=0.01" in plan.filter_str
    assert "unsharp=3:3:0.35:3:3:0.0,vignette=PI/7:eval=init" in plan.filter_str

    # Static news/split modes do not receive cinema motion zoom
    news_cfg = resolve_effective_configuration(content_type="news")
    assert (
        _resolve_cinema_motion(
            eased_push=True,
            profile="default",
            config=news_cfg,
            reframe_mode=Reframe.FACE_TRACKED,
            render_duration_ms=20_000,
            source_cuts=(),
            silence_plan=None,
            excited_intervals_ms=(),
            clip_in_ms=0,
            payoff_at_ms=None,
            fps=25.0,
        )
        is None
    )
    pod_cfg = resolve_effective_configuration(content_type="podcast")
    assert (
        _resolve_cinema_motion(
            eased_push=True,
            profile="default",
            config=pod_cfg,
            reframe_mode=Reframe.TWO_PERSON_SPLIT,
            render_duration_ms=20_000,
            source_cuts=(),
            silence_plan=None,
            excited_intervals_ms=(),
            clip_in_ms=0,
            payoff_at_ms=None,
            fps=25.0,
        )
        is None
    )


def test_d370_cinema_motion_ffmpeg_real_render_zero_strobe_and_exact_sync(tmp_path: Path) -> None:
    """Real FFmpeg execution proves exact duration/frame count and silky non-strobing zoom."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg not available")

    plan = build_cinema_motion_filter(
        duration_ms=4_000,
        jump_cuts_ms=(2_000,),
        fps=25.0,
        width=360,
        height=640,
        cinema_grade=True,
    )
    out_mp4 = tmp_path / "v5_motion.mp4"
    cmd = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=360x640:rate=25:duration=4",
        "-vf",
        plan.filter_str,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(out_mp4),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60.0)
    assert res.returncode == 0, f"ffmpeg zoompan failed: {res.stderr}"
    assert out_mp4.is_file() and out_mp4.stat().st_size > 1_000

    # Verify exact 100 frames (4.000 s @ 25 fps) and smooth non-strobing frame deltas
    raw_cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(out_mp4),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    raw = subprocess.run(raw_cmd, capture_output=True, check=True, timeout=30.0).stdout
    frame_bytes = 360 * 640
    n_frames = len(raw) // frame_bytes
    assert n_frames == 100

    # Measure even vs odd inter-frame L1 diff inside the smooth hook push (frames 5..40)
    even_diffs: list[float] = []
    odd_diffs: list[float] = []
    for idx in range(5, 40):
        f_prev = raw[(idx - 1) * frame_bytes : idx * frame_bytes : 17]
        f_curr = raw[idx * frame_bytes : (idx + 1) * frame_bytes : 17]
        mad = sum(abs(a - b) for a, b in zip(f_prev, f_curr, strict=True)) / len(f_prev)
        if idx % 2 == 0:
            even_diffs.append(mad)
        else:
            odd_diffs.append(mad)
    even_med = sorted(even_diffs)[len(even_diffs) // 2]
    odd_med = sorted(odd_diffs)[len(odd_diffs) // 2]
    assert even_med > 0.0 and odd_med > 0.0
    ratio = max(even_med, odd_med) / min(even_med, odd_med)
    assert math.isfinite(ratio) and ratio <= 1.25, f"strobe detected: {ratio:.2f}x"


def test_d373_balanced_two_line_hook_eliminates_third_line_orphan() -> None:
    """Long Kurdish hook titles balance cleanly into 2 lines with pop-in animation."""
    from hawedit.captions import CaptionStyle, build_ass

    title = "مەترسیی ڕاستەقینەی ژیریی دەستکرد تەنیا لەدەستدانی کار نییە"
    words = (_w("سڵاو", 1000, 1500), _w("هاوڕێیان", 1550, 2200))
    ass = build_ass(
        (Sentence(words=words, complete=True),),
        style=CaptionStyle.WORD_HIGHLIGHT,
        clip_in_ms=1000,
        clip_duration_ms=5000,
        title_ckb=title,
        face_intervals=((1000, 5000, 120, 620),),
    )
    hook_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 1,")]
    assert len(hook_lines) == 1
    hook = hook_lines[0]
    assert r"{\an2\pos(540,1260)\fad(0,250)}" in hook
    assert r"\fscx93\fscy93\t(0,160,\fscx100\fscy100)" in hook
    # Exactly 2 lines (one \N break) — never a dangling 1-word 3rd line like `نییە`
    assert hook.count(r"\N") == 1


def test_d376_procedural_cinema_sfx_wav_synthesis_and_spacing(tmp_path: Path) -> None:
    """Procedural SFX bed writes exact 48 kHz mono PCM WAV with tasteful spacing and safe peak."""
    import array
    import wave
    from itertools import pairwise

    from hawedit.sound_design import select_sfx_transitions_ms, write_cinema_sfx_wav

    chosen = select_sfx_transitions_ms(
        (800, 3_000, 4_500, 9_200, 15_000, 22_000, 28_000, 35_000, 42_000, 50_000),
        duration_ms=55_000,
    )
    assert len(chosen) <= 6
    assert all(2_000 <= t <= 53_500 for t in chosen)
    for a, b in pairwise(chosen):
        assert b - a >= 5_000

    wav_path = write_cinema_sfx_wav(
        tmp_path / "cinema.sfx.wav",
        duration_ms=6_000,
        transition_ms=(3_000,),
        sample_rate=48_000,
    )
    assert wav_path.is_file()
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48_000
        assert wf.getnframes() == 48_000 * 6
        samples = array.array("h")
        samples.frombytes(wf.readframes(wf.getnframes()))
    peak = max(abs(s) for s in samples) / 32767.0
    # Audible presence on hook + whoosh, strictly below -16 dBFS (~0.16) so dialogue always leads
    assert 0.03 <= peak <= 0.16
