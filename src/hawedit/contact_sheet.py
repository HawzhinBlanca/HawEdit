"""CPU-only per-reel visual inspection contact sheets (E1, D-353)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np

from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.edit_plan import VisualEditPlan
from hawedit.measure import (
    MeasureError,
    _ass_time_to_ms,
    probe_container,
    probe_scene_cuts,
)

__all__ = [
    "CAPTION_BAND_RATIO",
    "CONTACT_SHEET_SUFFIX",
    "FILLER_BG_BGR",
    "GRID_COLUMNS",
    "MAX_CUT_PAIRS",
    "TILE_BANNER_HEIGHT",
    "TILE_HEIGHT",
    "TILE_WIDTH",
    "ContactSheetResult",
    "main",
    "render_reel_contact_sheet",
]

CONTACT_SHEET_SUFFIX: Final[str] = ".contact-sheet.jpg"
GRID_COLUMNS: Final[int] = 4
MAX_CUT_PAIRS: Final[int] = 12
CAPTION_BAND_RATIO: Final[float] = 0.34
TILE_WIDTH: Final[int] = 270
TILE_HEIGHT: Final[int] = 480
TILE_BANNER_HEIGHT: Final[int] = 28
FILLER_BG_BGR: Final[tuple[int, int, int]] = (42, 48, 56)

_AN_TAG_RE: Final = re.compile(r"\\an([1-9])")
_NON_CAPTION_STYLES: Final[frozenset[str]] = frozenset({"hook", "speaker", "endcard"})


@dataclass(frozen=True, slots=True)
class ContactSheetResult:
    """Metadata describing a rendered per-reel contact sheet."""

    sheet_path: Path
    reel_path: Path
    tile_count: int
    filler_count: int
    cut_timestamps_ms: tuple[int, ...]
    caption_timestamp_ms: int
    caption_source: str
    sheet_width: int
    sheet_height: int
    sha256: str


def _resolve_ffmpeg_and_ffprobe(ffmpeg: Path | None) -> tuple[Path, Path]:
    binary = ffmpeg if ffmpeg is not None else find_ffmpeg()
    if binary is None or not binary.is_file():
        raise FileNotFoundError("Pinned ffmpeg executable not found; run scripts/fetch-ffmpeg.sh")
    probe = ffprobe_for(binary)
    if not probe.is_file():
        raise FileNotFoundError(f"Matching ffprobe executable not found next to ffmpeg: {probe}")
    return binary, probe


def _load_edit_plan(
    mp4_path: Path, edit_plan: VisualEditPlan | Path | None
) -> VisualEditPlan | None:
    if isinstance(edit_plan, VisualEditPlan):
        return edit_plan
    plan_path = (
        edit_plan if isinstance(edit_plan, Path) else mp4_path.with_suffix(".edit_plan.json")
    )
    if isinstance(edit_plan, Path) and not plan_path.is_file():
        raise FileNotFoundError(f"Explicit edit_plan file does not exist: {plan_path}")
    if not plan_path.is_file():
        return None
    return VisualEditPlan.from_json(plan_path.read_text(encoding="utf-8"))


def _dedupe_cuts(
    cuts_ms: Sequence[int], *, min_ms: int, max_ms: int, min_gap_ms: int
) -> tuple[int, ...]:
    filtered = sorted(t for t in cuts_ms if min_ms <= t <= max_ms)
    deduped: list[int] = []
    for ts in filtered:
        if not deduped or ts - deduped[-1] >= min_gap_ms:
            deduped.append(ts)
    return tuple(deduped[:MAX_CUT_PAIRS])


def _cuts_from_edit_plan(
    plan: VisualEditPlan, *, duration_ms: int, frame_ms: float
) -> tuple[int, ...]:
    raw_cuts: list[int] = []
    accumulated = 0
    intervals = plan.time_mapping.retained_intervals_ms
    for idx, (start, end) in enumerate(intervals):
        accumulated += end - start
        if idx < len(intervals) - 1:
            raw_cuts.append(accumulated)
    # pipeline.py stores VisualEditPlan.shot_cuts_ms in 0-based output offsets (`clip_in_ms + pc`).
    for out_cut in plan.shot_cuts_ms:
        raw_cuts.append(int(out_cut))
    guard = max(1, math.ceil(frame_ms))
    return _dedupe_cuts(
        raw_cuts, min_ms=guard, max_ms=max(guard, duration_ms - guard), min_gap_ms=guard
    )


def _parse_ass_style_bands(text: str) -> dict[str, str]:
    bands: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("Style:"):
            parts = line[6:].split(",")
            if len(parts) >= 19:
                name = parts[0].strip().lower()
                align = parts[18].strip()
                if align in {"7", "8", "9"}:
                    bands[name] = "top"
                elif align in {"1", "2", "3"}:
                    bands[name] = "bottom"
    return bands


def _parse_ass_dialogue_entries(text: str) -> list[tuple[int, int, str, str | None]]:
    entries: list[tuple[int, int, str, str | None]] = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        try:
            start_ms = _ass_time_to_ms(parts[1].strip())
            end_ms = _ass_time_to_ms(parts[2].strip())
        except Exception:
            continue
        if end_ms <= start_ms:
            continue
        style_name = parts[3].strip().lower()
        inline_band: str | None = None
        for match in _AN_TAG_RE.finditer(parts[9]):
            if match.group(1) in {"7", "8", "9"}:
                inline_band = "top"
            elif match.group(1) in {"1", "2", "3"}:
                inline_band = "bottom"
        entries.append((start_ms, end_ms, style_name, inline_band))
    return entries


def _detect_caption_band(ass_path: Path) -> str:
    if not ass_path.is_file():
        return "bottom"
    text = ass_path.read_text(encoding="utf-8", errors="replace")
    style_bands = _parse_ass_style_bands(text)
    top_votes = 0
    bottom_votes = 0
    for _start, _end, style_name, inline_band in _parse_ass_dialogue_entries(text):
        if style_name in _NON_CAPTION_STYLES:
            continue
        band = inline_band or style_bands.get(style_name)
        if band == "top":
            top_votes += 1
        elif band == "bottom":
            bottom_votes += 1
    if top_votes or bottom_votes:
        return "top" if top_votes > bottom_votes else "bottom"
    for style_name, band in style_bands.items():
        if style_name in _NON_CAPTION_STYLES:
            continue
        if band == "top":
            top_votes += 1
        elif band == "bottom":
            bottom_votes += 1
    return "top" if top_votes > bottom_votes else "bottom"


def _resolve_caption_target(
    mp4_path: Path,
    ass_path: Path | None,
    *,
    duration_ms: int,
) -> tuple[int, str, str]:
    candidate_ass = ass_path if ass_path is not None else mp4_path.with_suffix(".ass")
    if ass_path is not None and not candidate_ass.is_file():
        raise FileNotFoundError(f"Explicit ASS subtitle file does not exist: {candidate_ass}")
    if candidate_ass.is_file():
        text = candidate_ass.read_text(encoding="utf-8", errors="replace")
        style_bands = _parse_ass_style_bands(text)
        all_entries = [
            (max(0, start), min(duration_ms, end), style_name, inline_band)
            for start, end, style_name, inline_band in _parse_ass_dialogue_entries(text)
            if end > 0 and start < duration_ms
        ]
        valid = [entry for entry in all_entries if entry[1] > entry[0]]
        speech = [entry for entry in valid if entry[2] not in _NON_CAPTION_STYLES]
        pool = speech if speech else valid
        if pool:
            best_s, best_e, best_style, best_inline = max(
                pool, key=lambda entry: entry[1] - entry[0]
            )
            mid_ms = min(max(0, (best_s + best_e) // 2), max(0, duration_ms - 1))
            band = best_inline or style_bands.get(best_style) or _detect_caption_band(candidate_ass)
            return mid_ms, "ass_midpoint", band
        return max(0, duration_ms // 2), "ass_empty_midpoint", _detect_caption_band(candidate_ass)
    return max(0, duration_ms // 2), "video_midpoint_no_ass", "bottom"


def _extract_frame_at_ms(
    mp4_path: Path,
    ffmpeg: Path,
    timestamp_ms: float,
    *,
    duration_ms: int,
    frame_ms: float,
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    max_seek_ms = max(0.0, float(duration_ms) - frame_ms)
    clamped_ms = min(max(0.0, timestamp_ms), max_seek_ms)
    cmd = [
        str(ffmpeg),
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{clamped_ms / 1000.0:.6f}",
        "-i",
        str(mp4_path),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False, timeout=60.0)
    if proc.returncode != 0 or not proc.stdout:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"ffmpeg failed extracting frame at {clamped_ms:.1f} ms from {mp4_path}: {stderr}"
        )
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise RuntimeError(f"Decoded empty frame at {clamped_ms:.1f} ms from {mp4_path}")
    return frame.astype(np.uint8, copy=False)


def _letterbox_tile(
    frame: np.ndarray[Any, np.dtype[np.uint8]],
    *,
    label: str,
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    tile = np.full(
        (TILE_HEIGHT + TILE_BANNER_HEIGHT, TILE_WIDTH, 3),
        FILLER_BG_BGR,
        dtype=np.uint8,
    )
    tile[:TILE_BANNER_HEIGHT, :] = (24, 27, 32)
    cv2.putText(
        tile,
        label[:34],
        (8, TILE_BANNER_HEIGHT - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (240, 244, 248),
        1,
        cv2.LINE_AA,
    )
    src_h, src_w = frame.shape[:2]
    scale = min(TILE_WIDTH / max(1, src_w), TILE_HEIGHT / max(1, src_h))
    dst_w = max(1, int(round(src_w * scale)))
    dst_h = max(1, int(round(src_h * scale)))
    resized = cv2.resize(frame, (dst_w, dst_h), interpolation=cv2.INTER_AREA)
    x0 = (TILE_WIDTH - dst_w) // 2
    y0 = TILE_BANNER_HEIGHT + (TILE_HEIGHT - dst_h) // 2
    tile[y0 : y0 + dst_h, x0 : x0 + dst_w] = resized
    return tile


def _make_filler_tile() -> np.ndarray[Any, np.dtype[np.uint8]]:
    tile = np.full(
        (TILE_HEIGHT + TILE_BANNER_HEIGHT, TILE_WIDTH, 3),
        FILLER_BG_BGR,
        dtype=np.uint8,
    )
    tile[:TILE_BANNER_HEIGHT, :] = (32, 37, 44)
    cv2.putText(
        tile,
        "FILLER / NO TILE",
        (8, TILE_BANNER_HEIGHT - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (170, 178, 188),
        1,
        cv2.LINE_AA,
    )
    return tile


def _make_caption_crop_strip(
    frame: np.ndarray[Any, np.dtype[np.uint8]],
    *,
    sheet_width: int,
    band: str,
    caption_ms: int,
    caption_source: str,
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    src_h, src_w = frame.shape[:2]
    band_h = max(32, min(src_h, int(round(src_h * CAPTION_BAND_RATIO))))
    crop = frame[:band_h, :] if band == "top" else frame[src_h - band_h :, :]

    scale = sheet_width / max(1, src_w)
    out_h = max(64, int(round(band_h * scale)))
    interp = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
    enlarged = cv2.resize(crop, (sheet_width, out_h), interpolation=interp)

    banner = np.full((TILE_BANNER_HEIGHT + 4, sheet_width, 3), (20, 24, 30), dtype=np.uint8)
    label = (
        f"ENLARGED CAPTION CROP ({band.upper()}) @ {caption_ms / 1000.0:.3f}s [{caption_source}]"
    )
    cv2.putText(
        banner,
        label[:96],
        (12, TILE_BANNER_HEIGHT - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 224, 130),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([banner, enlarged]).astype(np.uint8, copy=False)


def _atomic_write_jpg(path: Path, canvas: np.ndarray[Any, np.dtype[np.uint8]]) -> str:
    ok, encoded = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok or encoded is None:
        raise RuntimeError(f"Failed encoding contact sheet JPEG for {path}")
    payload = encoded.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".cs-{os.getpid()}.tmp")
    try:
        tmp_path.write_bytes(payload)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()


def render_reel_contact_sheet(
    mp4_path: Path,
    *,
    output_path: Path | None = None,
    ass_path: Path | None = None,
    edit_plan: VisualEditPlan | Path | None = None,
    cut_timestamps_ms: Sequence[int] | None = None,
    ffmpeg: Path | None = None,
) -> ContactSheetResult:
    """Render a 4-column per-reel contact sheet next to ``mp4_path``."""
    if not mp4_path.is_file():
        raise FileNotFoundError(f"Reel MP4 file does not exist: {mp4_path}")

    ffmpeg_bin, ffprobe_bin = _resolve_ffmpeg_and_ffprobe(ffmpeg)
    try:
        video_meta, _, _ = probe_container(mp4_path, ffprobe_bin)
    except MeasureError as exc:
        raise RuntimeError(f"Unreadable video stream for contact sheet: {exc}") from exc

    if video_meta.duration_ms <= 0 or video_meta.frames_count <= 0:
        raise RuntimeError(f"Reel has no decodable video frames: {mp4_path}")

    fps = video_meta.fps if video_meta.fps > 0 else 25.0
    frame_ms = 1000.0 / fps
    loaded_plan = _load_edit_plan(mp4_path, edit_plan)

    guard = max(1, math.ceil(frame_ms))
    if cut_timestamps_ms is not None:
        resolved_cuts = _dedupe_cuts(
            cut_timestamps_ms,
            min_ms=guard,
            max_ms=max(guard, video_meta.duration_ms - guard),
            min_gap_ms=guard,
        )
    elif loaded_plan is not None:
        resolved_cuts = _cuts_from_edit_plan(
            loaded_plan, duration_ms=video_meta.duration_ms, frame_ms=frame_ms
        )
    else:
        detected = probe_scene_cuts(mp4_path, ffmpeg_bin)
        resolved_cuts = _dedupe_cuts(
            detected,
            min_ms=guard,
            max_ms=max(guard, video_meta.duration_ms - guard),
            min_gap_ms=guard,
        )

    caption_ms, caption_source, caption_band = _resolve_caption_target(
        mp4_path, ass_path, duration_ms=video_meta.duration_ms
    )

    tiles: list[np.ndarray[Any, np.dtype[np.uint8]]] = []
    first_frame = _extract_frame_at_ms(
        mp4_path, ffmpeg_bin, 0.0, duration_ms=video_meta.duration_ms, frame_ms=frame_ms
    )
    tiles.append(_letterbox_tile(first_frame, label="FIRST 0.000s"))

    for idx, cut_ms in enumerate(resolved_cuts, start=1):
        pre_ms = max(0.0, float(cut_ms) - frame_ms)
        post_ms = float(cut_ms)
        pre_frame = _extract_frame_at_ms(
            mp4_path, ffmpeg_bin, pre_ms, duration_ms=video_meta.duration_ms, frame_ms=frame_ms
        )
        post_frame = _extract_frame_at_ms(
            mp4_path, ffmpeg_bin, post_ms, duration_ms=video_meta.duration_ms, frame_ms=frame_ms
        )
        tiles.append(_letterbox_tile(pre_frame, label=f"CUT #{idx} PRE {pre_ms / 1000.0:.3f}s"))
        tiles.append(_letterbox_tile(post_frame, label=f"CUT #{idx} POST {post_ms / 1000.0:.3f}s"))

    tile_count = len(tiles)
    rem = tile_count % GRID_COLUMNS
    filler_count = (GRID_COLUMNS - rem) if rem != 0 else 0
    for _ in range(filler_count):
        tiles.append(_make_filler_tile())

    rows: list[np.ndarray[Any, np.dtype[np.uint8]]] = []
    for row_start in range(0, len(tiles), GRID_COLUMNS):
        row_strip = np.hstack(tiles[row_start : row_start + GRID_COLUMNS])
        rows.append(row_strip.astype(np.uint8, copy=False))
    grid = np.vstack(rows).astype(np.uint8, copy=False)

    caption_frame = _extract_frame_at_ms(
        mp4_path,
        ffmpeg_bin,
        float(caption_ms),
        duration_ms=video_meta.duration_ms,
        frame_ms=frame_ms,
    )
    sheet_width = grid.shape[1]
    caption_strip = _make_caption_crop_strip(
        caption_frame,
        sheet_width=sheet_width,
        band=caption_band,
        caption_ms=caption_ms,
        caption_source=caption_source,
    )
    canvas = np.vstack([grid, caption_strip]).astype(np.uint8, copy=False)

    target_path = (
        output_path if output_path is not None else mp4_path.with_suffix(CONTACT_SHEET_SUFFIX)
    )
    sha256 = _atomic_write_jpg(target_path, canvas)
    return ContactSheetResult(
        sheet_path=target_path,
        reel_path=mp4_path,
        tile_count=tile_count,
        filler_count=filler_count,
        cut_timestamps_ms=resolved_cuts,
        caption_timestamp_ms=caption_ms,
        caption_source=caption_source,
        sheet_width=int(canvas.shape[1]),
        sheet_height=int(canvas.shape[0]),
        sha256=sha256,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.contact_sheet"),
        description="Generate a 4-column per-reel contact sheet next to a rendered MP4.",
    )
    parser.add_argument("mp4", type=Path, help="Rendered reel MP4 path.")
    parser.add_argument("--ass", type=Path, default=None, help="Optional ASS subtitle path.")
    parser.add_argument(
        "--edit-plan", type=Path, default=None, help="Optional .edit_plan.json path."
    )
    parser.add_argument("--out", type=Path, default=None, help="Explicit output JPG path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON metadata to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint (`python -m hawedit.contact_sheet`)."""
    use_utf8_streams()
    args = _build_parser().parse_args(argv)
    try:
        result = render_reel_contact_sheet(
            args.mp4,
            output_path=args.out,
            ass_path=args.ass,
            edit_plan=args.edit_plan,
        )
        if args.json:
            payload = {
                **asdict(result),
                "sheet_path": str(result.sheet_path),
                "reel_path": str(result.reel_path),
            }
            with machine_readable_stdout() as out:
                out.write(json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            print(
                f"Wrote {result.sheet_path} ({result.sheet_width}x{result.sheet_height}, "
                f"tiles={result.tile_count}, cuts={len(result.cut_timestamps_ms)})"
            )
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
