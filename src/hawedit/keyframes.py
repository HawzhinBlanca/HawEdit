"""Source-grounded keyframes for Stage 4's multimodal Gemini request."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hawedit.captions import find_ffmpeg
from hawedit.judge import JudgeFrame

__all__ = ["KeyframeError", "extract_judge_frames"]


class KeyframeError(RuntimeError):
    """The candidate could not be represented by real image bytes."""


def extract_judge_frames(
    source: Path,
    in_ms: int,
    out_ms: int,
    work_dir: Path,
    *,
    count: int = 20,
    ffmpeg: Path | None = None,
) -> tuple[JudgeFrame, ...]:
    """Sample up to 20 evenly spaced JPEGs from exactly the candidate slice."""
    if out_ms <= in_ms:
        raise ValueError(f"keyframe span has no duration: {in_ms}..{out_ms}ms")
    if not 1 <= count <= 20:
        raise ValueError(f"keyframe count must be within 1..20, got {count}")
    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise KeyframeError("Stage 4 keyframes need ffmpeg")
    work_dir.mkdir(parents=True, exist_ok=True)
    duration_s = (out_ms - in_ms) / 1000
    pattern = work_dir / "judge-%03d.jpg"
    result = subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{in_ms / 1000:.3f}",
            "-t",
            f"{duration_s:.3f}",
            "-i",
            str(source),
            "-vf",
            f"fps={count / duration_s:.8f},scale='min(768,iw)':-2",
            "-frames:v",
            str(count),
            "-q:v",
            "3",
            "-y",
            str(pattern),
        ],
        capture_output=True,
        check=False,
    )
    paths = tuple(sorted(work_dir.glob("judge-*.jpg")))
    if result.returncode != 0 or not paths:
        raise KeyframeError(
            f"ffmpeg failed to extract judge keyframes ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')[-400:]}"
        )
    if len(paths) > count:
        raise KeyframeError(f"asked for {count} keyframes and ffmpeg produced {len(paths)}")
    step_ms = (out_ms - in_ms) / len(paths)
    return tuple(
        JudgeFrame(
            timestamp_ms=min(out_ms, round(in_ms + (index + 0.5) * step_ms)),
            mime_type="image/jpeg",
            data=path.read_bytes(),
        )
        for index, path in enumerate(paths)
    )
