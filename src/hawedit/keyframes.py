"""Source-grounded keyframes for Stage 4's multimodal Gemini request."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from hawedit.captions import find_ffmpeg
from hawedit.judge import MAX_JUDGE_FRAME_BYTES, JudgeFrame

__all__ = ["KeyframeError", "extract_judge_frames"]


class KeyframeError(RuntimeError):
    """The candidate could not be represented by real image bytes."""


def _read_keyframe(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_JUDGE_FRAME_BYTES + 1)
    except OSError as exc:
        raise KeyframeError(f"could not read extracted Stage 4 keyframe {path}: {exc}") from exc
    if not payload:
        raise KeyframeError(f"extracted Stage 4 keyframe {path} is empty")
    if len(payload) > MAX_JUDGE_FRAME_BYTES:
        raise KeyframeError(f"extracted Stage 4 keyframe {path} exceeds the 5 MiB ceiling")
    return payload


def _remove_private_keyframes(extraction_dir: Path) -> None:
    """Remove owned source pixels, without replacing an exception already in flight."""
    active_error = sys.exception()
    try:
        shutil.rmtree(extraction_dir)
    except FileNotFoundError:
        # Absence is the desired privacy state. This also makes cleanup idempotent if an
        # external quarantine tool already removed the uniquely owned directory.
        return
    except OSError as cleanup_error:
        message = f"private Stage 4 keyframe cleanup failed for {extraction_dir}: {cleanup_error}"
        if active_error is not None:
            # Keep the original type, traceback and cause (including programmer/schema errors),
            # but make the retained-pixels privacy failure visible in the same traceback.
            active_error.add_note(message)
            return
        raise KeyframeError(message) from cleanup_error


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
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        extraction_dir = Path(tempfile.mkdtemp(prefix=".judge-", dir=work_dir))
    except OSError as exc:
        raise KeyframeError(
            f"could not create a private Stage 4 keyframe directory under {work_dir}: {exc}"
        ) from exc
    try:
        duration_s = (out_ms - in_ms) / 1000
        pattern = extraction_dir / "judge-%03d.jpg"
        try:
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
        except OSError as exc:
            raise KeyframeError(f"cannot launch ffmpeg for Stage 4 keyframes: {exc}") from exc
        try:
            paths = tuple(sorted(extraction_dir.glob("judge-*.jpg")))
        except OSError as exc:
            raise KeyframeError(
                f"could not enumerate extracted Stage 4 keyframes in {extraction_dir}: {exc}"
            ) from exc
        if result.returncode != 0 or not paths:
            raise KeyframeError(
                f"ffmpeg failed to extract judge keyframes ({result.returncode}): "
                f"{result.stderr.decode('utf-8', 'replace')[-400:]}"
            )
        if len(paths) > count:
            raise KeyframeError(f"asked for {count} keyframes and ffmpeg produced {len(paths)}")
        # Stamp from the cadence ffmpeg was told to sample at, not from the number of frames that
        # happened to come back. If the source ends before the requested span, dividing by
        # len(paths) stretches surviving frames across time the video never had.
        step_ms = (out_ms - in_ms) / count
        frames = tuple(
            JudgeFrame(
                timestamp_ms=min(out_ms, round(in_ms + (index + 0.5) * step_ms)),
                mime_type="image/jpeg",
                data=_read_keyframe(path),
            )
            for index, path in enumerate(paths)
        )
        return frames
    finally:
        # The directory was atomically created by this call, and JudgeFrame owns the bytes in
        # memory. Delete only that owned directory; never touch caller files whose names merely
        # resemble an earlier extraction.
        _remove_private_keyframes(extraction_dir)
