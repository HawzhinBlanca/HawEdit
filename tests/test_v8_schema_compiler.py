"""Unit & real-FFmpeg tests for HawEdit V8 schema, camera restraint, and compiler (D-382, D-386)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hawedit.captions import find_ffmpeg
from hawedit.transcripts import Word
from hawedit.v8 import (
    CAMERA_MAX_SCALE,
    CAMERA_MIN_SCALE,
    STUDIO_GRADE_FILTER,
    CameraMove,
    CaptionBeat,
    CritiqueVerdict,
    CutRegion,
    DirectorScript,
    DirectorScriptError,
    LockedCropWindow,
    SubtitleArtifact,
    SubtitleEngine,
    V8CompileConfig,
    V8CompileError,
    VisualInterrupt,
    WordRepair,
    apply_critique_patch,
    apply_word_repairs,
    compile_restrained_camera_filter,
    compile_v8_clip,
    load_transcript_words,
    max_camera_moves_for_duration,
    parse_sentence_indices,
    rebase_words_to_clip,
    select_clip_span_from_sentences,
    validate_director_script,
)
from hawedit.v8.__main__ import build_parser, main
from hawedit.v8.compiler import VideoGrillReport, grill_rendered_v8_video
from hawedit.v8.schema import snap_camera_moves_to_cuts


def _sample_words() -> tuple[Word, ...]:
    """Six clip-relative Kurdish Sorani words spanning 0..10_000 ms with clear gaps."""
    return (
        Word("ئەزانی", 200, 700, 0.96),
        Word("مۆدەی", 900, 1_400, 0.72),
        Word("لە", 2_000, 2_300, 0.98),
        Word("ناو", 2_400, 2_750, 0.97),
        Word("ماڵ", 2_850, 3_300, 0.99),
        Word("کوردییەکەیان.", 5_000, 5_900, 0.95),
    )


def _valid_script() -> DirectorScript:
    return DirectorScript(
        clip_id="ai-s86-87",
        hook_title_ckb="ئەزانی مۆدێلی کوردی چۆنە؟",
        word_repairs=(
            WordRepair(
                word_index=1,
                original="مۆدەی",
                repaired="مۆدێل",
                reason="Audio clearly pronounces English loanword 'model'",
            ),
        ),
        cuts=(
            CutRegion(
                start_ms=1_450,
                end_ms=1_950,
                kind="silence",
                reason="Trim 500 ms dead air between phrases",
            ),
        ),
        camera_moves=(
            CameraMove(
                start_ms=4_000,
                end_ms=6_000,
                kind="slow_push",
                scale_start=1.00,
                scale_end=1.08,
                reason="Build emotional emphasis into payoff",
            ),
            CameraMove(
                start_ms=7_500,
                end_ms=9_000,
                kind="punch_cut",
                scale_start=1.12,
                scale_end=1.12,
                reason="Mask jump cut with clean B-cam tightness",
            ),
        ),
        caption_beats=(
            CaptionBeat(word_indices=(0, 1), power_word_index=1, accent_color="#B8FF2E"),
            CaptionBeat(word_indices=(2, 3, 4)),  # 'لە ناو ماڵ' = 10 chars <= 14
            CaptionBeat(word_indices=(5,), power_word_index=5),
        ),
        visual_interrupts=(
            VisualInterrupt(
                start_ms=5_000,
                end_ms=6_800,
                text_ckb="داهاتووی زیرەکی دەستکرد",
                position="top",
            ),
        ),
        cold_open_span_ms=(5_000, 5_900),
    )


# ---------------------------------------------------------------------------
# 1. Schema & strict JSON round-trip
# ---------------------------------------------------------------------------


def test_director_script_dict_and_json_round_trip() -> None:
    script = _valid_script()
    validate_director_script(script, duration_ms=10_000, words=_sample_words())

    as_dict = script.to_dict()
    assert DirectorScript.from_dict(as_dict) == script

    raw_json = script.to_json(indent=2)
    assert "کوردییەکەیان" not in raw_json or "مۆدێل" in raw_json
    assert "مۆدێل" in raw_json
    assert DirectorScript.from_json(raw_json) == script


def test_critique_verdict_round_trip_and_strict_checks() -> None:
    verdict = CritiqueVerdict(
        approved=False,
        score=6.5,
        issues=("Camera push too strong",),
        patch={"hook_title_ckb": "مۆدێلی نوێی کوردی"},
    )
    assert CritiqueVerdict.from_dict(verdict.to_dict()) == verdict
    assert CritiqueVerdict.from_json(verdict.to_json()) == verdict

    approved = CritiqueVerdict(approved=True, score=9.4)
    assert approved.issues == ()
    assert approved.patch is None
    assert CritiqueVerdict.from_json(approved.to_json()) == approved

    with pytest.raises(DirectorScriptError, match="score"):
        CritiqueVerdict(approved=True, score=-0.1)
    with pytest.raises(DirectorScriptError, match="score"):
        CritiqueVerdict(approved=True, score=101.0)
    with pytest.raises(DirectorScriptError, match="Invalid CritiqueVerdict JSON"):
        CritiqueVerdict.from_json("{not json")


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("{bad", "Invalid DirectorScript JSON"),
        ("[]", "JSON object"),
        ('{"clip_id": "x"}', "missing required"),
        ('{"clip_id": "x", "hook_title_ckb": "", "cam_moves": []}', "unknown field"),
        ('{"clip_id": 123, "hook_title_ckb": ""}', "must be a string"),
        ('{"clip_id": "x", "hook_title_ckb": "line1\\nline2"}', "single line"),
        (
            '{"clip_id": "x", "hook_title_ckb": "", "cold_open_span_ms": [1000, 500]}',
            "must be > start_ms",
        ),
        (
            '{"clip_id": "x", "hook_title_ckb": "", "word_repairs": '
            '[{"word_index": true, "original": "a", "repaired": "b", "reason": "r"}]}',
            "must be an integer",
        ),
        (
            '{"clip_id": "x", "hook_title_ckb": "", "camera_moves": '
            '[{"start_ms": 0, "end_ms": 1000, "kind": "sway", '
            '"scale_start": 1.0, "scale_end": 1.05, "reason": "bad"}]}',
            "CameraMove.kind invalid",
        ),
        (
            '{"clip_id": "x", "hook_title_ckb": "", "caption_beats": '
            '[{"word_indices": [0, 1], "power_word_index": 2}]}',
            "must belong to word_indices",
        ),
        (
            '{"clip_id": "x", "hook_title_ckb": "", "caption_beats": '
            '[{"word_indices": [0], "accent_color": "yellow"}]}',
            "#RRGGBB",
        ),
    ],
)
def test_director_script_from_json_rejects_malformed(raw: str, match: str) -> None:
    with pytest.raises(DirectorScriptError, match=match):
        DirectorScript.from_json(raw)


# ---------------------------------------------------------------------------
# 2. Hard Camera Restraint Law (D-382)
# ---------------------------------------------------------------------------


def test_camera_restraint_rejects_scale_out_of_bounds() -> None:
    words = _sample_words()
    too_low = DirectorScript(
        clip_id="c1",
        hook_title_ckb="",
        camera_moves=(CameraMove(1_000, 2_000, "slow_push", 0.98, 1.05, "below min scale"),),
    )
    with pytest.raises(DirectorScriptError, match="scale_start"):
        validate_director_script(too_low, duration_ms=10_000, words=words)

    too_high = DirectorScript(
        clip_id="c2",
        hook_title_ckb="",
        camera_moves=(CameraMove(1_000, 2_000, "slow_push", 1.00, 1.17, "above max scale"),),
    )
    with pytest.raises(DirectorScriptError, match="scale_end"):
        validate_director_script(too_high, duration_ms=10_000, words=words)

    # Exact bounds [1.00, 1.16] are permitted.
    at_bounds = DirectorScript(
        clip_id="c3",
        hook_title_ckb="",
        camera_moves=(
            CameraMove(
                1_000, 2_000, "slow_push", CAMERA_MIN_SCALE, CAMERA_MAX_SCALE, "exact bounds"
            ),
        ),
    )
    validate_director_script(at_bounds, duration_ms=10_000, words=words)


def test_camera_restraint_max_moves_budget() -> None:
    words = _sample_words()
    assert max_camera_moves_for_duration(10_000) == 2
    assert max_camera_moves_for_duration(30_000) == 2
    assert max_camera_moves_for_duration(45_000) == 3
    assert max_camera_moves_for_duration(60_000) == 4

    # 4 active moves on a 60 s clip: allowed.
    four_moves = tuple(
        CameraMove(i * 12_000, i * 12_000 + 3_000, "punch_cut", 1.10, 1.10, f"beat {i}")
        for i in range(4)
    )
    script_ok = DirectorScript(
        clip_id="c60",
        hook_title_ckb="",
        camera_moves=(
            *four_moves,
            CameraMove(50_000, 58_000, "locked", 1.00, 1.00, "explicit locked tripod"),
        ),
    )
    validate_director_script(script_ok, duration_ms=60_000, words=words)

    # 5 active moves on a 60 s clip: rejected!
    five_moves = tuple(
        CameraMove(i * 11_000, i * 11_000 + 2_000, "punch_cut", 1.10, 1.10, f"beat {i}")
        for i in range(5)
    )
    script_too_many = DirectorScript(clip_id="c60-bad", hook_title_ckb="", camera_moves=five_moves)
    with pytest.raises(DirectorScriptError, match="Too many active camera moves: 5 > max 4"):
        validate_director_script(script_too_many, duration_ms=60_000, words=words)


def test_camera_restraint_moving_screen_time_cap_25_percent() -> None:
    words = _sample_words()
    # Exact 25.0% (15_000 / 60_000 ms): allowed.
    exact_25 = DirectorScript(
        clip_id="c25-ok",
        hook_title_ckb="",
        camera_moves=(
            CameraMove(5_000, 12_500, "slow_push", 1.00, 1.07, "push 1"),
            CameraMove(30_000, 37_500, "slow_push", 1.00, 1.08, "push 2"),
        ),
    )
    validate_director_script(exact_25, duration_ms=60_000, words=words)

    # 25.002% (15_001 / 60_000 ms): rejected!
    over_25 = DirectorScript(
        clip_id="c25-bad",
        hook_title_ckb="",
        camera_moves=(
            CameraMove(5_000, 12_500, "slow_push", 1.00, 1.07, "push 1"),
            CameraMove(30_000, 37_501, "slow_push", 1.00, 1.08, "push 2"),
        ),
    )
    with pytest.raises(DirectorScriptError, match="exceeds 25.0% restraint budget"):
        validate_director_script(over_25, duration_ms=60_000, words=words)


def test_camera_restraint_rejects_overlap_and_moving_locked() -> None:
    words = _sample_words()
    overlap = DirectorScript(
        clip_id="ov",
        hook_title_ckb="",
        camera_moves=(
            CameraMove(1_000, 3_000, "punch_cut", 1.10, 1.10, "a"),
            CameraMove(2_500, 4_000, "punch_cut", 1.12, 1.12, "b"),
        ),
    )
    with pytest.raises(DirectorScriptError, match="Overlapping CameraMove"):
        validate_director_script(overlap, duration_ms=10_000, words=words)

    moving_locked = DirectorScript(
        clip_id="ml",
        hook_title_ckb="",
        camera_moves=(CameraMove(1_000, 2_000, "locked", 1.00, 1.08, "contradiction"),),
    )
    with pytest.raises(DirectorScriptError, match="kind='locked' cannot change scale"):
        validate_director_script(moving_locked, duration_ms=10_000, words=words)


# ---------------------------------------------------------------------------
# 3. E3 Cuts, Word Repairs, Caption Beats (D-383), Visual Interrupts
# ---------------------------------------------------------------------------


def test_validate_rejects_mid_word_cuts_and_caption_law_violations() -> None:
    words = _sample_words()

    # Mid-word cut inside word[0] [200, 700].
    mid_cut = DirectorScript(
        clip_id="mid",
        hook_title_ckb="",
        cuts=(CutRegion(450, 850, "silence", "bad cut"),),
    )
    with pytest.raises(DirectorScriptError, match="slices word\\[0\\]"):
        validate_director_script(mid_cut, duration_ms=10_000, words=words)

    # Mid-word cold open.
    mid_cold = DirectorScript(
        clip_id="mid-co",
        hook_title_ckb="",
        cold_open_span_ms=(5_200, 5_900),
    )
    with pytest.raises(DirectorScriptError, match="slices word\\[5\\]"):
        validate_director_script(mid_cold, duration_ms=10_000, words=words)

    # 4-word caption beat is strictly forbidden.
    four_words = DirectorScript(
        clip_id="cap4",
        hook_title_ckb="",
        caption_beats=(CaptionBeat(word_indices=(0, 1, 2, 3)),),
    )
    with pytest.raises(DirectorScriptError, match="maximum is 3"):
        validate_director_script(four_words, duration_ms=10_000, words=words)

    # 3-word caption beat exceeding 14 chars ('ئەزانی مۆدەی لە' = 15 chars) is forbidden.
    long_three = DirectorScript(
        clip_id="cap3-long",
        hook_title_ckb="",
        caption_beats=(CaptionBeat(word_indices=(0, 1, 2)),),
    )
    with pytest.raises(DirectorScriptError, match="exceeds <= 14 char limit"):
        validate_director_script(long_three, duration_ms=10_000, words=words)

    # Duplicate word index across caption beats is forbidden.
    dup_cap = DirectorScript(
        clip_id="cap-dup",
        hook_title_ckb="",
        caption_beats=(CaptionBeat((0, 1)), CaptionBeat((1, 2))),
    )
    with pytest.raises(DirectorScriptError, match="duplicates word_index 1"):
        validate_director_script(dup_cap, duration_ms=10_000, words=words)

    # Mismatched WordRepair original is rejected.
    bad_repair = DirectorScript(
        clip_id="rep-bad",
        hook_title_ckb="",
        word_repairs=(WordRepair(1, "هەڵە", "مۆدێل", "wrong original"),),
    )
    with pytest.raises(DirectorScriptError, match="does not match transcript word"):
        validate_director_script(bad_repair, duration_ms=10_000, words=words)


# ---------------------------------------------------------------------------
# 4. Restrained Camera Filter Compiler + REAL FFmpeg Verification
# ---------------------------------------------------------------------------


def test_compile_restrained_camera_filter_static_fast_path_and_zero_sway() -> None:
    # Empty camera_moves -> ZERO zoompan overhead, ONLY studio grade!
    flt_grade, jumps_grade = compile_restrained_camera_filter(30_000, ())
    assert flt_grade == STUDIO_GRADE_FILTER
    assert "zoompan" not in flt_grade
    assert "sin(" not in flt_grade
    assert jumps_grade == ()

    flt_bare, jumps_bare = compile_restrained_camera_filter(30_000, (), cinema_grade=False)
    assert flt_bare == ""
    assert jumps_bare == ()

    # All-1.00x locked moves -> still ZERO zoompan overhead!
    locked_only = (CameraMove(0, 15_000, "locked", 1.00, 1.00, "locked"),)
    flt_locked, jumps_locked = compile_restrained_camera_filter(30_000, locked_only)
    assert flt_locked == STUDIO_GRADE_FILTER
    assert "zoompan" not in flt_locked
    assert jumps_locked == ()

    # Earned slow_push + punch_cut + wide_release on a 45 s clip (max_moves=3):
    # zero sin(), rock-steady center x!
    moves = (
        CameraMove(4_000, 7_000, "slow_push", 1.00, 1.08, "emotional build"),
        CameraMove(14_000, 18_000, "punch_cut", 1.00, 1.12, "mask jump cut"),
        CameraMove(18_000, 22_000, "wide_release", 1.12, 1.00, "release to wide"),
    )
    flt, jumps = compile_restrained_camera_filter(45_000, moves, fps=25.0)
    assert "zoompan=" in flt
    assert "sin(" not in flt
    assert ":x='iw/2-(iw/zoom/2)'" in flt
    assert "cos(PI*" in flt
    assert STUDIO_GRADE_FILTER in flt
    # Mid-shot slow_push (4000..7000) eases out smoothly over 450 ms (no harsh snap-back jump!),
    # so jump cuts occur only at punch_cut (14000) and wide_release (18000).
    assert jumps == (14_000, 18_000)


def test_real_ffmpeg_restrained_camera_zero_sway_locked_and_scurve_push(tmp_path: Path) -> None:
    """Real FFmpeg test proving 0.00 px locked drift, 0.00 horizontal sway, and S-curve push."""
    ffmpeg = find_ffmpeg()
    width, height, fps = 180, 320, 25.0
    duration_s = 4.0
    duration_ms = int(duration_s * 1_000)

    # 1. Generate a crisp static synthetic source video with a white box centered horizontally
    #    at x=90 (width=40, height=40) and centered at y=height*0.33 (anchor_y=0.33).
    src_mp4 = tmp_path / "static_target.mp4"
    box_w, box_h = 40, 40
    box_x = (width - box_w) // 2
    box_y = round(height * 0.33) - box_h // 2
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r={int(fps)}:d={duration_s}",
            "-vf",
            f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color=white:t=fill",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "0",
            str(src_mp4),
        ],
        check=True,
        capture_output=True,
    )

    # 2. Compile restrained filter: 80% locked 1.00x tripod, ONE earned 800 ms slow_push
    #    (20% moving time <= 25% law) from 1.00x -> 1.15x across [1200ms, 2000ms].
    moves = (
        CameraMove(
            start_ms=1_200,
            end_ms=2_000,
            kind="slow_push",
            scale_start=1.00,
            scale_end=1.15,
            reason="Earned payoff push",
        ),
    )
    cam_filter, jumps = compile_restrained_camera_filter(
        duration_ms,
        moves,
        fps=fps,
        width=width,
        height=height,
        anchor_y=0.33,
        cinema_grade=False,
    )
    assert "sin(" not in cam_filter
    # Mid-shot slow_push appends a smooth 450 ms cosine ease-out [2000..2450] -> zero hard snap!
    assert jumps == ()

    # 3. Run real FFmpeg filtergraph and read raw grayscale frames directly into numpy!
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-i",
            str(src_mp4),
            "-vf",
            cam_filter,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    frame_bytes = width * height
    total_frames = len(proc.stdout) // frame_bytes
    assert total_frames == int(duration_s * fps)
    frames = np.frombuffer(proc.stdout[: total_frames * frame_bytes], dtype=np.uint8).reshape(
        (total_frames, height, width)
    )

    # A) Locked pre-move window (frames 2..28 = 80ms..1120ms): ZERO drift / ZERO sway!
    pre_locked = frames[2:29].astype(np.int16)
    pre_diffs = np.max(np.abs(np.diff(pre_locked, axis=0)))
    assert int(pre_diffs) == 0, f"Expected 0.00 px drift in pre-move locked tripod, got {pre_diffs}"

    # B) Locked post-ease-out window (frames 64..96 = 2560ms..3840ms): ZERO drift & matches pre!
    post_locked = frames[64:97].astype(np.int16)
    post_diffs = np.max(np.abs(np.diff(post_locked, axis=0)))
    assert int(post_diffs) == 0, (
        f"Expected 0.00 px drift in post-move locked tripod, got {post_diffs}"
    )
    assert int(np.max(np.abs(frames[10].astype(np.int16) - frames[70].astype(np.int16)))) == 0

    # C) Earned slow_push window (frames 30..49) + smooth 450 ms ease-out (frames 50..61):
    #    smooth zoom-in expansion followed by smooth ease-out return with ZERO sway!
    x_grid = np.arange(width, dtype=np.float64)[None, :]

    def _box_metrics(frame: np.ndarray[Any, np.dtype[np.uint8]]) -> tuple[float, float]:
        weights = frame.astype(np.float64)
        total = float(weights.sum())
        assert total > 0.0
        cx = float((weights * x_grid).sum() / total)
        area_px = total / 255.0
        return cx, area_px

    locked_cx, locked_area = _box_metrics(frames[10])
    _, push_early_area = _box_metrics(frames[35])
    _, push_mid_area = _box_metrics(frames[40])
    _, push_end_area = _box_metrics(frames[48])
    _, ease_out_mid_area = _box_metrics(frames[55])

    # Sub-pixel luminance area grows smoothly across the cosine S-curve push (1.00x -> 1.15x)
    # and eases back down smoothly during [2000..2450 ms] instead of hard-snapping!
    assert push_early_area > locked_area
    assert push_mid_area > push_early_area
    assert push_end_area > push_mid_area
    assert push_end_area / locked_area >= 1.25  # 1.15^2 = 1.3225
    assert locked_area < ease_out_mid_area < push_end_area

    # Horizontal center of mass: EXACT 0.0000 px drift on every locked frame, and strictly
    # non-oscillatory (within yuv420p integer crop floor rounding <= 2.5 px, never swinging left)
    # during the earned slow_push — proving ZERO sinusoidal sway!
    for idx in (*range(2, 29), *range(64, 97)):
        cx, _ = _box_metrics(frames[idx])
        assert abs(cx - locked_cx) == 0.0, f"Locked frame {idx} drifted horizontally: {cx}"
    for idx in range(total_frames):
        cx, _ = _box_metrics(frames[idx])
        assert -0.05 <= (cx - locked_cx) <= 2.5, (
            f"Frame {idx} showed unexpected horizontal sway: {cx} vs {locked_cx}"
        )

    # 4. Prove instant 1-frame punch_cut holds rock-steady (0.00 px internal drift) in real FFmpeg!
    punch_filter, punch_jumps = compile_restrained_camera_filter(
        duration_ms,
        (CameraMove(1_200, 2_000, "punch_cut", 1.00, 1.12, "B-cam jump mask"),),
        fps=fps,
        width=width,
        height=height,
        anchor_y=0.33,
        cinema_grade=False,
    )
    assert punch_jumps == (1_200, 2_000)
    punch_proc = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-i",
            str(src_mp4),
            "-vf",
            punch_filter,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    pframes = np.frombuffer(
        punch_proc.stdout[: total_frames * frame_bytes], dtype=np.uint8
    ).reshape((total_frames, height, width))
    # Inside punch_cut hold (frames 32..48): rock-steady 0.00 px diff & zoomed ~1.12^2 area!
    assert int(np.max(np.abs(np.diff(pframes[32:49].astype(np.int16), axis=0)))) == 0
    _, punch_area = _box_metrics(pframes[40])
    assert punch_area / locked_area >= 1.18

    # 5. Also prove empty camera_moves with cinema_grade=True runs cleanly with ZERO zoompan!
    grade_only, grade_jumps = compile_restrained_camera_filter(duration_ms, (), cinema_grade=True)
    assert "zoompan" not in grade_only
    assert grade_jumps == ()
    grade_proc = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-i",
            str(src_mp4),
            "-vf",
            grade_only,
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    assert grade_proc.returncode == 0


# ---------------------------------------------------------------------------
# 5. Compiler helpers, Watch-Before-Ship bounded critique, and CLI
# ---------------------------------------------------------------------------


def test_apply_word_repairs_and_apply_critique_patch() -> None:
    words = _sample_words()
    repaired = apply_word_repairs(
        words,
        (WordRepair(1, "مۆدەی", "مۆدێل", "audio repair"),),
    )
    assert repaired[1].w == "مۆدێل"
    assert repaired[1].start_ms == words[1].start_ms
    assert repaired[1].end_ms == words[1].end_ms
    assert repaired[1].conf == words[1].conf
    # Original input tuple untouched.
    assert words[1].w == "مۆدەی"

    with pytest.raises(DirectorScriptError, match="out of bounds"):
        apply_word_repairs(words, (WordRepair(99, "a", "b", "bad"),))
    with pytest.raises(DirectorScriptError, match="Duplicate"):
        apply_word_repairs(
            words,
            (
                WordRepair(1, "مۆدەی", "مۆدێل", "r1"),
                WordRepair(1, "مۆدەی", "مۆدێلی", "r2"),
            ),
        )

    script = _valid_script()
    patched = apply_critique_patch(
        script,
        {
            "hook_title_ckb": "مۆدێلە نوێیەکە",
            "camera_moves": [],
        },
    )
    assert patched.clip_id == script.clip_id
    assert patched.hook_title_ckb == "مۆدێلە نوێیەکە"
    assert patched.camera_moves == ()
    assert patched.word_repairs == script.word_repairs

    with pytest.raises(DirectorScriptError, match="must not be empty"):
        apply_critique_patch(script, {})
    with pytest.raises(DirectorScriptError, match="disallowed field"):
        apply_critique_patch(script, {"clip_id": "hijacked"})
    with pytest.raises(DirectorScriptError, match="disallowed field"):
        apply_critique_patch(script, {"unknown_key": 1})


def test_sentence_parsing_and_transcript_loading(tmp_path: Path) -> None:
    assert parse_sentence_indices("86-87") == (86, 87)
    assert parse_sentence_indices("s19-22") == (19, 20, 21, 22)
    assert parse_sentence_indices("7-7") == (7,)
    assert parse_sentence_indices("0, 2, 2, 4-5") == (0, 2, 4, 5)

    for bad in ("", "87-86", "abc", "-1", "1-2-3"):
        with pytest.raises(V8CompileError):
            parse_sentence_indices(bad)

    transcript = tmp_path / "transcript.raw.json"
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    {"w": "سڵاو", "start_ms": 1_000, "end_ms": 1_400, "conf": 0.99},
                    {"w": "هاوڕێ.", "start_ms": 1_500, "end_ms": 2_000, "conf": 0.98},
                    {"w": "ئەمە", "start_ms": 3_200, "end_ms": 3_600, "conf": 0.97},
                    {"w": "تاقیکردنەوەیە.", "start_ms": 3_700, "end_ms": 4_400, "conf": 0.96},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = load_transcript_words(transcript)
    assert len(loaded) == 4

    clip_in, clip_out, clip_words = select_clip_span_from_sentences(loaded, (1,))
    assert clip_in == 3_080
    assert clip_out == 4_550
    assert [w.w for w in clip_words] == ["ئەمە", "تاقیکردنەوەیە."]
    assert clip_words[0].start_ms == 120

    rebased = rebase_words_to_clip(loaded, clip_in_ms=1_000, clip_out_ms=2_000)
    assert rebased[0].start_ms == 0
    assert rebased[-1].end_ms == 1_000


class _FakeDirector:
    def __init__(self, script: DirectorScript, verdicts: Sequence[CritiqueVerdict]) -> None:
        self._script = script
        self._verdicts = list(verdicts)
        self.direct_calls = 0
        self.critique_calls = 0

    def direct_clip(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        clip_id: str,
        words: Sequence[Word],
        shot_cuts_ms: Sequence[int] = (),
        jump_cuts_ms: Sequence[int] = (),
    ) -> DirectorScript:
        self.direct_calls += 1
        return self._script

    def critique_clip(
        self,
        *,
        rendered_mp4: Path,
        script: DirectorScript,
        words: Sequence[Word],
    ) -> CritiqueVerdict:
        idx = min(self.critique_calls, len(self._verdicts) - 1)
        self.critique_calls += 1
        return self._verdicts[idx]


class _FakeSubRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], SubtitleEngine]] = []

    def render_subtitles(
        self,
        *,
        words: Sequence[Word],
        script: DirectorScript,
        clip_duration_ms: int,
        out_dir: Path,
        engine: SubtitleEngine,
    ) -> SubtitleArtifact:
        self.calls.append((tuple(w.w for w in words), engine))
        if engine == "skia":
            overlay = out_dir / f"{script.clip_id}.subs.mov"
            overlay.write_bytes(b"rgba-overlay")
            return SubtitleArtifact(engine="skia", overlay_path=overlay, chunk_count=len(words))
        ass = out_dir / f"{script.clip_id}.subs.ass"
        ass.write_text("[Script Info]\n", encoding="utf-8")
        return SubtitleArtifact(engine="libass", ass_path=ass, chunk_count=len(words))


class _FakeSpeakerTracker:
    def plan_locked_crops(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[LockedCropWindow, ...]:
        return (
            LockedCropWindow(
                start_ms=0,
                end_ms=clip_out_ms - clip_in_ms,
                focus_x_px=1280,
                face_center_y_px=480,
                face_height_px=310,
                active_track_id=1,
            ),
        )


class _FakeClipRenderer:
    def __init__(self) -> None:
        self.filters_seen: list[str] = []

    def render_clip_media(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        script: DirectorScript,
        words: Sequence[Word],
        camera_filter: str,
        camera_jump_cuts_ms: tuple[int, ...],
        subtitles: SubtitleArtifact,
        locked_crops: tuple[LockedCropWindow, ...],
        output_mp4: Path,
        config: V8CompileConfig,
    ) -> Path:
        self.filters_seen.append(camera_filter)
        output_mp4.write_bytes(b"fake-mp4")
        return output_mp4


def test_compile_v8_clip_watch_before_ship_max_one_revision(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-bytes")
    out_dir = tmp_path / "out"
    words = _sample_words()
    script = _valid_script()

    # Pass 1 rejects with a surgical patch removing camera moves; Pass 2 approves!
    director = _FakeDirector(
        script,
        verdicts=(
            CritiqueVerdict(
                approved=False,
                score=7.0,
                issues=("Remove camera moves for maximum stillness",),
                patch={"camera_moves": []},
            ),
            CritiqueVerdict(approved=True, score=9.5, issues=()),
        ),
    )
    subs = _FakeSubRenderer()
    tracker = _FakeSpeakerTracker()
    renderer = _FakeClipRenderer()

    result = compile_v8_clip(
        source_mp4=source,
        clip_id="ai-s86-87",
        clip_in_ms=0,
        clip_out_ms=10_000,
        words=words,
        out_dir=out_dir,
        config=V8CompileConfig(director_backend="offline", sub_engine="skia"),
        director=director,
        subtitle_renderer=subs,
        speaker_tracker=tracker,
        clip_renderer=renderer,
    )

    assert result.critique_revisions == 1
    assert result.critique is not None and result.critique.approved is True
    assert director.direct_calls == 1
    assert director.critique_calls == 2
    assert result.script.camera_moves == ()
    assert result.camera_filter == STUDIO_GRADE_FILTER
    assert "zoompan" in renderer.filters_seen[0]
    assert "zoompan" not in renderer.filters_seen[1]
    assert result.repaired_words[1].w == "مۆدێل"
    assert len(result.locked_crops) == 1
    assert result.script_path.is_file()
    assert DirectorScript.from_json(result.script_path.read_text(encoding="utf-8")) == result.script


def test_compile_v8_clip_strict_fail_stop_bounds(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-bytes")
    words = _sample_words()
    script = _valid_script()

    # 1. Corrupt/unreadable media with default wired pipeline -> loud fail-stop (zero fallback).
    with pytest.raises(V8CompileError, match="Failed to probe video dimensions"):
        compile_v8_clip(
            source_mp4=source,
            clip_id="fail-corrupt-media",
            clip_in_ms=0,
            clip_out_ms=10_000,
            words=words,
            out_dir=tmp_path / "u",
        )

    # 2. Critic keeps rejecting after max 1 revision -> loud fail-stop, never loops to rev 2!
    always_reject = _FakeDirector(
        script,
        verdicts=(
            CritiqueVerdict(
                approved=False,
                score=5.0,
                issues=("Too much motion",),
                patch={"camera_moves": []},
            ),
            CritiqueVerdict(
                approved=False,
                score=5.5,
                issues=("Still bad",),
                patch={"hook_title_ckb": "should never apply"},
            ),
        ),
    )
    renderer = _FakeClipRenderer()
    with pytest.raises(V8CompileError, match="rejected fail-rev after 1 revision"):
        compile_v8_clip(
            source_mp4=source,
            clip_id="fail-rev",
            clip_in_ms=0,
            clip_out_ms=10_000,
            words=words,
            out_dir=tmp_path / "r",
            director=always_reject,
            subtitle_renderer=_FakeSubRenderer(),
            clip_renderer=renderer,
        )
    assert always_reject.critique_calls == 2
    assert len(renderer.filters_seen) == 2

    # 3. Critic emits an illegal patch (>1.16 scale) -> blocked by validate_director_script!
    bad_patch_director = _FakeDirector(
        script,
        verdicts=(
            CritiqueVerdict(
                approved=False,
                score=6.0,
                issues=("Zoom closer",),
                patch={
                    "camera_moves": [
                        {
                            "start_ms": 1_000,
                            "end_ms": 2_000,
                            "kind": "slow_push",
                            "scale_start": 1.00,
                            "scale_end": 1.35,
                            "reason": "illegal zoom",
                        }
                    ]
                },
            ),
        ),
    )
    with pytest.raises(DirectorScriptError, match="scale_end"):
        compile_v8_clip(
            source_mp4=source,
            clip_id="fail-patch",
            clip_in_ms=0,
            clip_out_ms=10_000,
            words=words,
            out_dir=tmp_path / "p",
            director=bad_patch_director,
            subtitle_renderer=_FakeSubRenderer(),
            clip_renderer=_FakeClipRenderer(),
        )

    # 4. Config forbids max_critique_revisions > 1 (D-386 bounded loop).
    with pytest.raises(V8CompileError, match="max_critique_revisions"):
        V8CompileConfig(max_critique_revisions=2)


def test_cli_entrypoint_success_and_error_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "video.mp4",
            "--transcript",
            "t.json",
            "--sentences",
            "86-87",
            "--out-dir",
            "out",
            "--director",
            "gemini",
            "--sub-engine",
            "libass",
        ]
    )
    assert parsed.director == "gemini"
    assert parsed.sub_engine == "libass"

    source = tmp_path / "episode.mp4"
    source.write_bytes(b"mp4")
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    {"w": "سڵاو", "start_ms": 1_000, "end_ms": 1_500, "conf": 0.99},
                    {"w": "کوردستان.", "start_ms": 1_600, "end_ms": 2_400, "conf": 0.98},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "reels"

    script = DirectorScript(clip_id="episode-s0-0", hook_title_ckb="سڵاو کوردستان")
    rc = main(
        [
            str(source),
            "--transcript",
            str(transcript),
            "--sentences",
            "0-0",
            "--out-dir",
            str(out_dir),
            "--director",
            "offline",
            "--sub-engine",
            "libass",
        ],
        director=_FakeDirector(script, verdicts=(CritiqueVerdict(True, 9.8),)),
        subtitle_renderer=_FakeSubRenderer(),
        clip_renderer=_FakeClipRenderer(),
    )
    assert rc == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["clip_id"] == "episode-s0-0"
    assert payload["director_backend"] == "offline"
    assert payload["sub_engine"] == "libass"
    assert payload["critique_approved"] is True

    # Missing collaborators from bare CLI -> fail-stop exit code 2.
    rc_err = main(
        [
            str(source),
            "--transcript",
            str(transcript),
            "--sentences",
            "0-0",
            "--out-dir",
            str(out_dir),
            "--director",
            "offline",
            "--sub-engine",
            "skia",
        ]
    )
    assert rc_err == 2
    assert "hawedit.v8 error:" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 6. D-387 Grill Fixes: Cut Snapping, Kurdish Hyphen Sanitizer & Video Griller
# ---------------------------------------------------------------------------


def test_snap_camera_moves_to_cuts_and_invisible_cut_release() -> None:
    """D-387: punch_cut snaps onto real cuts (zero ramp); slow_push releases cleanly on cuts."""
    moves = (
        CameraMove(31_130, 34_500, "slow_push", 1.00, 1.08, "push before 34.44s cut"),
        CameraMove(44_080, 48_000, "punch_cut", 1.00, 1.12, "punch 0.48s before 44.56s cut"),
    )
    snapped = snap_camera_moves_to_cuts(
        moves,
        shot_cuts_ms=(34_440, 44_560),
        jump_cuts_ms=(48_200,),
        duration_ms=60_000,
    )
    assert len(snapped) == 2
    # slow_push end snapped cleanly onto 34_440 (within 60 ms <= 700 ms).
    assert snapped[0].kind == "slow_push"
    assert snapped[0].start_ms == 31_130
    assert snapped[0].end_ms == 34_440
    # punch_cut start snapped onto 44_560 (480 ms <= 700 ms), end onto 48_200 (200 ms <= 700 ms),
    # and normalized to constant 1.12x (zero ramp!).
    assert snapped[1].kind == "punch_cut"
    assert snapped[1].start_ms == 44_560
    assert snapped[1].end_ms == 48_200
    assert snapped[1].scale_start == 1.12
    assert snapped[1].scale_end == 1.12
    assert snapped[1].is_moving is False

    # Compiling with shot_cuts_ms releases slow_push right on 34_440 (no post-cut ease-out!).
    flt, jumps = compile_restrained_camera_filter(
        60_000,
        moves,
        fps=25.0,
        shot_cuts_ms=(34_440, 44_560),
        jump_cuts_ms=(48_200,),
        cinema_grade=False,
    )
    assert "sin(" not in flt
    assert jumps == (34_440, 44_560, 48_200)
    # Only ONE cosine expression (the slow_push itself — no extra ease-out return after cut!).
    assert flt.count("cos(PI*") == 1

    # Snapping slow_push forward must never breach the <= 25% moving-camera budget!
    tight_push = (CameraMove(20_000, 29_900, "slow_push", 1.00, 1.08, "near 25% cap"),)
    snapped_tight = snap_camera_moves_to_cuts(
        tight_push, shot_cuts_ms=(30_400,), jump_cuts_ms=(), duration_ms=40_000
    )
    assert snapped_tight[0].end_ms == 30_400
    assert snapped_tight[0].end_ms - snapped_tight[0].start_ms == 9_900  # <= 10_000 (25%)


def test_apply_word_repairs_sanitizes_kurdish_ascii_hyphens_only() -> None:
    words = (
        Word("جوابتەداتەوە", 100, 600, 0.80),
        Word("جیپیتی", 700, 1_100, 0.75),
        Word("مۆدێلینوی", 1_200, 1_800, 0.78),
    )
    repaired = apply_word_repairs(
        words,
        (
            WordRepair(0, "جوابتەداتەوە", "جوابت-ئەداتەوە", "model emitted hyphenated Kurdish"),
            WordRepair(1, "جیپیتی", "GPT-4", "English model name keeps hyphen"),
            WordRepair(2, "مۆدێلینوی", "  مۆدێل - ی - نوێ  ", "multi-hyphen Kurdish"),
        ),
    )
    assert len(repaired) == 3
    assert repaired[0].w == "جوابت ئەداتەوە"
    assert repaired[0].start_ms == 100 and repaired[0].end_ms == 600
    assert repaired[1].w == "GPT-4"
    assert repaired[2].w == "مۆدێل ی نوێ"


def _make_grill_mp4(
    ffmpeg: Path,
    dest: Path,
    *,
    video_filter: str,
    audio_filter: str,
) -> Path:
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-filter_complex",
            f"{video_filter};{audio_filter}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def test_grill_rendered_v8_video_real_ffmpeg_checks(tmp_path: Path) -> None:
    """Real FFmpeg tests for clean pass, double-cut flash, trailing cut, silence, and clipping."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None

    # 1. Clean 3.0 s MP4 with 1 crisp cut at 1.20 s (well before final 0.8 s) & clean tone.
    clean_mp4 = _make_grill_mp4(
        ffmpeg,
        tmp_path / "clean.mp4",
        video_filter=(
            "color=c=0x102030:s=180x320:r=25:d=1.2[v0];"
            "color=c=0xD0C0B0:s=180x320:r=25:d=1.8[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[v]"
        ),
        audio_filter="sine=frequency=440:sample_rate=48000:duration=3.0,volume=0.25[a]",
    )
    clean = grill_rendered_v8_video(clean_mp4, expected_duration_ms=3_000, ffmpeg=ffmpeg)
    assert clean.passed is True, clean.defects
    assert clean.double_cuts == ()
    assert clean.trailing_cuts == ()
    assert clean.long_silences == ()
    assert clean.audio_flat_factor == 0.0
    assert len(clean.cut_times_s) == 1
    assert abs(clean.cut_times_s[0] - 1.20) <= 0.08

    # 2. Double-cut 1-frame flash (40 ms flash at 1.20s..1.24s) -> MUST FAIL!
    flash_mp4 = _make_grill_mp4(
        ffmpeg,
        tmp_path / "flash.mp4",
        video_filter=(
            "color=c=0x101010:s=180x320:r=25:d=1.20[v0];"
            "color=c=0xF0F0F0:s=180x320:r=25:d=0.04[v1];"
            "color=c=0x303030:s=180x320:r=25:d=1.76[v2];"
            "[v0][v1][v2]concat=n=3:v=1:a=0[v]"
        ),
        audio_filter="sine=frequency=440:sample_rate=48000:duration=3.0,volume=0.25[a]",
    )
    flash = grill_rendered_v8_video(flash_mp4, ffmpeg=ffmpeg)
    assert flash.passed is False
    assert len(flash.double_cuts) == 1
    assert any("double_cuts" in d for d in flash.defects)

    # 3. Trailing cut inside final 0.80 s (at 2.60 s of 3.0 s clip) -> MUST FAIL!
    trail_mp4 = _make_grill_mp4(
        ffmpeg,
        tmp_path / "trailing.mp4",
        video_filter=(
            "color=c=0x102030:s=180x320:r=25:d=2.60[v0];"
            "color=c=0xE0E0E0:s=180x320:r=25:d=0.40[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[v]"
        ),
        audio_filter="sine=frequency=440:sample_rate=48000:duration=3.0,volume=0.25[a]",
    )
    trail = grill_rendered_v8_video(trail_mp4, ffmpeg=ffmpeg)
    assert trail.passed is False
    assert len(trail.trailing_cuts) == 1
    assert any("trailing_cuts" in d for d in trail.defects)

    # 4. Long silence (>= 0.48 s at -35 dB) -> MUST FAIL!
    silent_mp4 = _make_grill_mp4(
        ffmpeg,
        tmp_path / "silence.mp4",
        video_filter="color=c=0x202020:s=180x320:r=25:d=3.0[v]",
        audio_filter=(
            "sine=frequency=440:sample_rate=48000:duration=1.0,volume=0.25[a0];"
            "anullsrc=r=48000:cl=mono:d=0.70[a1];"
            "sine=frequency=440:sample_rate=48000:duration=1.3,volume=0.25[a2];"
            "[a0][a1][a2]concat=n=3:v=0:a=1[a]"
        ),
    )
    silent = grill_rendered_v8_video(silent_mp4, ffmpeg=ffmpeg)
    assert silent.passed is False
    assert len(silent.long_silences) == 1
    assert any("long_silences" in d for d in silent.defects)

    # 5. Clipped audio (Flat factor > 0.0) -> MUST FAIL!
    clipped_mp4 = _make_grill_mp4(
        ffmpeg,
        tmp_path / "clipped.mp4",
        video_filter="color=c=0x202020:s=180x320:r=25:d=2.0[v]",
        audio_filter="sine=frequency=440:sample_rate=48000:duration=2.0,volume=10.0,aformat=sample_fmts=s16[a]",
    )
    clipped = grill_rendered_v8_video(clipped_mp4, ffmpeg=ffmpeg)
    assert clipped.passed is False
    assert clipped.audio_flat_factor > 0.0
    assert any("audio_clipping" in d for d in clipped.defects)


def test_compile_v8_clip_grill_auto_repair_and_fail_stop(tmp_path: Path) -> None:
    """compile_v8_clip auto-repairs camera-induced double cuts and fails loudly on other defects."""
    source = tmp_path / "src.mp4"
    source.write_bytes(b"src")
    words = _sample_words()
    script = _valid_script()

    # 1. First render triggers camera double-cut defect -> auto-repairs by locking to 1.00x!
    calls = 0

    def _repairing_griller(mp4: Path) -> VideoGrillReport:
        nonlocal calls
        calls += 1
        if calls == 1:
            return VideoGrillReport(
                mp4_path=mp4,
                duration_ms=10_000,
                fps=25.0,
                frame_count=250,
                cut_times_s=(4.0, 4.08),
                double_cuts=((4.0, 4.08),),
                trailing_cuts=(),
                long_silences=(),
                audio_flat_factor=0.0,
                passed=False,
                defects=("double_cuts: 1 flash(es) <= 0.20s apart (4.00s->4.08s)",),
            )
        return VideoGrillReport(
            mp4_path=mp4,
            duration_ms=10_000,
            fps=25.0,
            frame_count=250,
            cut_times_s=(),
            double_cuts=(),
            trailing_cuts=(),
            long_silences=(),
            audio_flat_factor=0.0,
            passed=True,
            defects=(),
        )

    renderer = _FakeClipRenderer()
    res = compile_v8_clip(
        source_mp4=source,
        clip_id="grill-repair",
        clip_in_ms=0,
        clip_out_ms=10_000,
        words=words,
        out_dir=tmp_path / "out1",
        config=V8CompileConfig(enable_critique=False, enable_grill=True),
        director=_FakeDirector(script, verdicts=()),
        subtitle_renderer=_FakeSubRenderer(),
        clip_renderer=renderer,
        video_griller=_repairing_griller,
    )
    assert calls == 2
    assert res.script.camera_moves == ()
    assert res.grill_report is not None and res.grill_report.passed is True
    assert (tmp_path / "out1" / "grill-repair.grill.json").is_file()

    # 2. Unrecoverable defect (audio clipping) -> strict fail-stop V8CompileError!
    def _clipping_griller(mp4: Path) -> VideoGrillReport:
        return VideoGrillReport(
            mp4_path=mp4,
            duration_ms=10_000,
            fps=25.0,
            frame_count=250,
            cut_times_s=(),
            double_cuts=(),
            trailing_cuts=(),
            long_silences=(),
            audio_flat_factor=12.5,
            passed=False,
            defects=("audio_clipping: Flat factor 12.500000 > 0.0",),
        )

    with pytest.raises(V8CompileError, match="Forensic video grill failed.*audio_clipping"):
        compile_v8_clip(
            source_mp4=source,
            clip_id="grill-fail",
            clip_in_ms=0,
            clip_out_ms=10_000,
            words=words,
            out_dir=tmp_path / "out2",
            config=V8CompileConfig(enable_critique=False, enable_grill=True),
            director=_FakeDirector(script, verdicts=()),
            subtitle_renderer=_FakeSubRenderer(),
            clip_renderer=_FakeClipRenderer(),
            video_griller=_clipping_griller,
        )
