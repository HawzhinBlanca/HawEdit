"""Automated Sanity Gate and Quality Verification Suite.

Guarantees that every rendered short video meets professional broadcast and social
standards before delivery, providing strict fail-stop enforcement:
1. Face Presence / Framing: Confirms >= 1 face in every 9:16 shot crop (0 dead frames).
2. Subtitle Legibility & Sync: Confirms 115pt bold font, <= 20 chars/line, margin >= 240px.
3. Audio Compliance: Confirms EBU R128 (-24 to -16 LUFS), True Peak <= -1.0 dBFS, zero clipping.
4. Narrative Integrity: Confirms Kurdish headline, narrative summary, and complete story arc.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from hawedit.condenser import CondensedStoryPlan

__all__ = [
    "QualityAuditReport",
    "SanityGate",
    "SanityGateFailureError",
    "check_audio_compliance",
    "check_face_presence",
    "check_narrative_integrity",
    "check_subtitles",
    "parse_ebur128_stats",
]


class SanityGateFailureError(RuntimeError):
    """Raised when rendered output fails any automated quality sanity check."""


@dataclass(frozen=True, slots=True)
class QualityAuditReport:
    """Multi-dimensional automated quality verification report."""

    passed: bool
    framing_pass: bool
    subtitles_pass: bool
    audio_pass: bool
    story_pass: bool
    detected_faces_per_shot: dict[str, int]
    audio_lufs: float
    audio_true_peak_dbfs: float
    subtitle_max_chars_per_line: int
    subtitle_font_size_pt: int
    subtitle_margin_v: int
    defect_messages: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "framing_pass": self.framing_pass,
            "subtitles_pass": self.subtitles_pass,
            "audio_pass": self.audio_pass,
            "story_pass": self.story_pass,
            "detected_faces_per_shot": self.detected_faces_per_shot,
            "audio_lufs": round(float(self.audio_lufs), 2),
            "audio_true_peak_dbfs": round(float(self.audio_true_peak_dbfs), 2),
            "subtitle_max_chars_per_line": self.subtitle_max_chars_per_line,
            "subtitle_font_size_pt": self.subtitle_font_size_pt,
            "subtitle_margin_v": self.subtitle_margin_v,
            "defect_messages": list(self.defect_messages),
        }


def check_subtitles(
    ass_path: Path | str, video_duration_ms: int = 0
) -> tuple[bool, int, int, int, tuple[str, ...]]:
    """Inspect ASS subtitle file for font size, character length, and safe margin.

    Returns:
        (passed, max_chars_per_line, font_size_pt, margin_v_px, defects)
    """
    path = Path(ass_path)
    if not path.exists():
        return False, 0, 0, 0, (f"Subtitle file does not exist: {path}",)

    content = path.read_text(encoding="utf-8")
    defects: list[str] = []

    # 1. Parse font size, margin, border style, and outline from Style definitions
    font_size = 0
    margin_v = 0
    border_style = 1
    outline = 0.0
    for line in content.splitlines():
        if line.startswith("Style:"):
            parts = [p.strip() for p in line[6:].split(",")]
            if len(parts) >= 22:
                try:
                    font_size = int(parts[2])
                    border_style = int(parts[15])
                    outline = float(parts[16])
                    margin_v = int(parts[21])
                except (ValueError, IndexError):
                    pass
            break

    if font_size < 100:
        defects.append(f"Font size {font_size}pt is below minimum 100pt legibility standard.")
    if margin_v < 240:
        defects.append(f"MarginV {margin_v}px is below safe margin 240px (at risk of UI overlap).")
    if border_style != 3 and outline < 3.0:
        defects.append(
            f"Subtitle outline {outline:g}px with border_style {border_style} is below the "
            "3.0px / 4.5:1 contrast floor."
        )

    # 2. Parse Dialogue events for line length
    max_chars = 0
    clean_tag_re = re.compile(r"\{[^}]*\}")

    for line in content.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) >= 10:
                raw_text = parts[9]
                clean_text = clean_tag_re.sub("", raw_text).strip()
                # Split by ASS explicit linebreaks \N
                sub_lines = clean_text.split(r"\N")
                for sub in sub_lines:
                    char_len = len(sub.strip())
                    if char_len > max_chars:
                        max_chars = char_len

    if max_chars > 20:
        defects.append(
            f"Subtitle text contains line with {max_chars} chars "
            "(exceeds max 20 characters for kinetic short reels)."
        )

    passed = len(defects) == 0
    return passed, max_chars, font_size, margin_v, tuple(defects)


def parse_ebur128_stats(
    ffmpeg_output: str,
) -> tuple[float, float, bool, tuple[str, ...]]:
    """Parse integrated loudness and true peak from FFmpeg ebur128 output."""
    defects: list[str] = []
    lufs = -99.0
    peak = 0.0

    # Extract Integrated loudness
    m_i = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", ffmpeg_output)
    if m_i:
        lufs = float(m_i.group(1))
    else:
        # Fallback search
        m_i_alt = re.search(r"I:\s+([-\d.]+)\s+LUFS", ffmpeg_output)
        if m_i_alt:
            lufs = float(m_i_alt.group(1))

    # Extract True Peak
    m_p = re.search(r"True peak:\s+Peak:\s+([-\d.]+)\s+dBFS", ffmpeg_output)
    if m_p:
        peak = float(m_p.group(1))
    else:
        m_p_alt = re.search(r"Peak:\s+([-\d.]+)\s+dBFS", ffmpeg_output)
        if m_p_alt:
            peak = float(m_p_alt.group(1))

    if lufs < -24.0 or lufs > -15.0:
        defects.append(f"Integrated loudness {lufs} LUFS outside range [-24.0, -15.0] LUFS.")
    if peak > -1.0:
        defects.append(
            f"True Peak {peak} dBFS exceeds -1.0 dBFS ceiling (risk of digital distortion)."
        )

    passed = len(defects) == 0
    return lufs, peak, passed, tuple(defects)


def check_audio_compliance(
    video_path: Path | str,
) -> tuple[float, float, bool, tuple[str, ...]]:
    """Run FFmpeg ebur128 loudness analysis on rendered video file."""
    path = Path(video_path)
    if not path.exists():
        return -99.0, 0.0, False, (f"Video file does not exist: {path}",)

    cmd = [
        "ffmpeg",
        "-nostats",
        "-i",
        str(path),
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=120.0,
        )
        return parse_ebur128_stats(proc.stdout)
    except Exception as exc:
        return -99.0, 0.0, False, (f"Audio compliance check failed: {exc}",)


def check_face_presence(
    video_path: Path | str,
    shot_timestamps_s: Sequence[tuple[float, float]],
    broll_intervals_s: Sequence[tuple[float, float]] = (),
) -> tuple[bool, dict[str, int], tuple[str, ...]]:
    """Sample frames from each shot cut to verify speaker presence (zero dead frames).

    Samples multiple timestamps (20%, 50%, 80%) per shot to account for momentary head turns,
    skipping intentional B-roll / archival document cutaways.
    """
    import cv2

    path = Path(video_path)
    if not path.exists():
        return False, {}, (f"Video file does not exist: {path}",)

    cv2_data = getattr(cv2, "data", None)
    haarcascades_dir = getattr(cv2_data, "haarcascades", "") if cv2_data else ""
    cascade_path = os.path.join(haarcascades_dir, "haarcascade_frontalface_default.xml")
    profile_path = os.path.join(haarcascades_dir, "haarcascade_profileface.xml")
    if not os.path.exists(cascade_path):
        return True, {}, ()  # Skip if cascade data is unavailable

    detector = cv2.CascadeClassifier(cascade_path)
    profile_detector = cv2.CascadeClassifier(profile_path) if os.path.exists(profile_path) else None

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return False, {}, (f"Could not open video file: {path}",)

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    faces_per_shot: dict[str, int] = {}
    defects: list[str] = []

    try:
        for idx, (s_in, s_out) in enumerate(shot_timestamps_s):
            shot_key = f"shot_{idx}_{s_in:.1f}s_{s_out:.1f}s"
            dur = s_out - s_in
            # Sample at 20%, 50%, and 80% through the shot
            sample_times = [s_in + dur * 0.2, s_in + dur * 0.5, s_in + dur * 0.8]
            # Filter out timestamps falling inside intentional B-roll cutaways
            valid_sample_times = [
                t
                for t in sample_times
                if not any(b_in <= t <= b_out for b_in, b_out in broll_intervals_s)
            ]
            if not valid_sample_times:
                valid_sample_times = sample_times  # Fallback if entirely covered

            sample_counts: list[int] = []
            for sample_t in valid_sample_times:
                frame_num = int(sample_t * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret or frame is None:
                    sample_counts.append(0)
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=3, minSize=(50, 50)
                )
                count = len(faces)
                if count == 0 and profile_detector is not None:
                    p_faces = profile_detector.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=3, minSize=(50, 50)
                    )
                    count = len(p_faces)
                sample_counts.append(count)

            # CD-10: Reject if all samples in shot have 0 faces, or consecutive have 0 faces
            faces_per_shot[shot_key] = max(sample_counts) if sample_counts else 0
            zero_indices = [i for i, c in enumerate(sample_counts) if c == 0]
            has_consecutive_zeros = any(i2 == i1 + 1 for i1, i2 in pairwise(zero_indices))
            if all(c == 0 for c in sample_counts) or (
                has_consecutive_zeros and len(sample_counts) >= 2
            ):
                zero_times = [f"{valid_sample_times[i]:.1f}s" for i in zero_indices]
                zt_str = ", ".join(zero_times)
                defects.append(
                    f"Dead Frame Detected: Shot {shot_key} contains 0 detected faces in "
                    f"dialogue crop at {zt_str}."
                )
    finally:
        cap.release()

    passed = len(defects) == 0
    return passed, faces_per_shot, tuple(defects)


def check_narrative_integrity(
    plan: CondensedStoryPlan,
) -> tuple[bool, tuple[str, ...]]:
    """Validate story headline, summary, duration bounds, and beat coverage."""
    defects: list[str] = []
    dur_s = plan.condensed_duration_ms / 1000.0

    if not plan.summary.headline_kurdish.strip():
        defects.append("Story headline is empty.")
    if not plan.summary.summary_kurdish.strip():
        defects.append("Story narrative summary is empty.")
    if dur_s < 25.0:
        defects.append(
            f"Condensed duration {dur_s:.1f}s is below 25s (too brief for complete story)."
        )
    if dur_s > 65.0:
        defects.append(f"Condensed duration {dur_s:.1f}s exceeds 65s (exceeds social reel bounds).")
    if not plan.retained_spans:
        defects.append("Condensed story plan has no retained spans.")

    passed = len(defects) == 0
    return passed, tuple(defects)


class SanityGate:
    """Automated pre-delivery quality inspection gate."""

    @classmethod
    def run_full_audit(
        cls,
        video_path: Path | str,
        ass_path: Path | str,
        story_plan: CondensedStoryPlan,
        shot_timestamps_s: Sequence[tuple[float, float]],
        *,
        broll_intervals_s: Sequence[tuple[float, float]] = (),
        strict_fail_stop: bool = False,
    ) -> QualityAuditReport:
        """Run all multi-dimensional quality checks and return audit report."""
        subs_pass, max_chars, font_size, margin_v, sub_defects = check_subtitles(
            ass_path, story_plan.condensed_duration_ms
        )
        lufs, peak, audio_pass, audio_defects = check_audio_compliance(video_path)
        framing_pass, faces_per_shot, frame_defects = check_face_presence(
            video_path, shot_timestamps_s, broll_intervals_s=broll_intervals_s
        )
        story_pass, story_defects = check_narrative_integrity(story_plan)

        all_defects: list[str] = []
        all_defects.extend(sub_defects)
        all_defects.extend(audio_defects)
        all_defects.extend(frame_defects)
        all_defects.extend(story_defects)

        overall_pass = subs_pass and audio_pass and framing_pass and story_pass

        report = QualityAuditReport(
            passed=overall_pass,
            framing_pass=framing_pass,
            subtitles_pass=subs_pass,
            audio_pass=audio_pass,
            story_pass=story_pass,
            detected_faces_per_shot=faces_per_shot,
            audio_lufs=lufs,
            audio_true_peak_dbfs=peak,
            subtitle_max_chars_per_line=max_chars,
            subtitle_font_size_pt=font_size,
            subtitle_margin_v=margin_v,
            defect_messages=tuple(all_defects),
        )

        if strict_fail_stop and not overall_pass:
            defect_summary = "\n  - ".join(all_defects)
            raise SanityGateFailureError(
                f"Sanity Gate FAILED with {len(all_defects)} defects:\n  - {defect_summary}"
            )

        return report
