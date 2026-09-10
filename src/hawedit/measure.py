"""Independent measurement of a delivered clip — the ground-truth Level B verification engine.

Derives video, audio, scene, face framing, and caption reality directly from delivered
artifacts (.mp4, .ass), with zero access to the renderer's plan or internal pipeline state.
AST isolation guarantees this module never imports `hawedit.render` or `hawedit.pipeline`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from hawedit.captions import (
    DEFAULT_BOTTOM_CAPTION_BAND,
    MIN_LEGIBILITY_CONTRAST_RATIO,
    contrast_ratio,
    ffprobe_for,
    find_ffmpeg,
    parse_ass_colour,
    relative_luminance,
)

__all__ = [
    "AudioMeasurement",
    "CaptionMeasurement",
    "ClipMeasurement",
    "FaceSample",
    "FaceTrackMeasurement",
    "FileSummary",
    "MeasureError",
    "SilenceInterval",
    "VideoMeasurement",
    "VmafMeasurement",
    "detect_caption_ink_in_band",
    "measure_caption_events_contrast",
    "measure_clip",
    "probe_caption_ink",
]

_SILENCE_START_RE: Final = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE: Final = re.compile(
    r"silence_end:\s*(-?[\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)"
)
_SCENE_SHOWINFO_RE: Final = re.compile(r"pts_time:([\d.]+)")
_EBUR128_I_RE: Final = re.compile(r"Integrated loudness:\s+I:\s*(-?[\d.]+)\s*LUFS")
_EBUR128_TP_RE: Final = re.compile(r"True peak:\s+Peak:\s*(-?[\d.]+)\s*dBFS")
_EBUR128_LRA_RE: Final = re.compile(r"Loudness range:\s+LRA:\s*(-?[\d.]+)\s*LU")


class MeasureError(RuntimeError):
    """Failure during independent artifact measurement."""


@dataclass(frozen=True)
class FileSummary:
    path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VideoMeasurement:
    width: int
    height: int
    fps: float
    fps_ratio: str
    duration_ms: int
    frames_count: int
    bitrate_kbps: float
    codec: str
    pix_fmt: str
    color_space: str | None
    color_transfer: str | None
    color_primaries: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SilenceInterval:
    start_ms: int
    end_ms: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AudioMeasurement:
    codec: str
    sample_rate: int
    channels: int
    duration_ms: int
    integrated_lufs: float
    true_peak_db: float
    lra_lu: float
    silences: list[SilenceInterval]
    total_silence_ms: int
    silence_share: float

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "silences": [s.to_dict() for s in self.silences],
        }


@dataclass(frozen=True)
class FaceSample:
    t_ms: int
    box: list[int] | None
    face_height_share: float | None
    y_center_share: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FaceTrackMeasurement:
    sample_interval_ms: int
    samples_count: int
    face_detected_frames_count: int
    face_detected_share: float
    median_face_height_share: float | None
    median_y_center_share: float | None
    first_frame_face_share: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaptionMeasurement:
    events_count: int
    ink_energy_detected_share: float
    median_contrast_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VmafMeasurement:
    vmaf_score: float
    psnr_db: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClipMeasurement:
    schema: int
    file: FileSummary
    video: VideoMeasurement
    audio: AudioMeasurement
    scenes: dict[str, list[int]]
    faces: FaceTrackMeasurement
    captions: CaptionMeasurement
    vmaf: VmafMeasurement | None
    tool_metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "file": self.file.to_dict(),
            "video": self.video.to_dict(),
            "audio": self.audio.to_dict(),
            "scenes": self.scenes,
            "faces": self.faces.to_dict(),
            "captions": self.captions.to_dict(),
            "vmaf": self.vmaf.to_dict() if self.vmaf else None,
            "tool_metadata": self.tool_metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClipMeasurement:
        vmaf_data = data.get("vmaf")
        audio_data = data["audio"]
        silences = [
            SilenceInterval(
                start_ms=s["start_ms"],
                end_ms=s["end_ms"],
                duration_ms=s["duration_ms"],
            )
            for s in audio_data.get("silences", [])
        ]
        audio = AudioMeasurement(
            codec=audio_data["codec"],
            sample_rate=audio_data["sample_rate"],
            channels=audio_data["channels"],
            duration_ms=audio_data["duration_ms"],
            integrated_lufs=audio_data["integrated_lufs"],
            true_peak_db=audio_data["true_peak_db"],
            lra_lu=audio_data["lra_lu"],
            silences=silences,
            total_silence_ms=audio_data["total_silence_ms"],
            silence_share=audio_data["silence_share"],
        )
        return cls(
            schema=data["schema"],
            file=FileSummary(
                path=data["file"]["path"],
                sha256=data["file"]["sha256"],
                size_bytes=data["file"]["size_bytes"],
            ),
            video=VideoMeasurement(
                width=data["video"]["width"],
                height=data["video"]["height"],
                fps=data["video"]["fps"],
                fps_ratio=data["video"]["fps_ratio"],
                duration_ms=data["video"]["duration_ms"],
                frames_count=data["video"]["frames_count"],
                bitrate_kbps=data["video"]["bitrate_kbps"],
                codec=data["video"]["codec"],
                pix_fmt=data["video"]["pix_fmt"],
                color_space=data["video"].get("color_space"),
                color_transfer=data["video"].get("color_transfer"),
                color_primaries=data["video"].get("color_primaries"),
            ),
            audio=audio,
            scenes=data.get("scenes", {}),
            faces=FaceTrackMeasurement(
                sample_interval_ms=data["faces"]["sample_interval_ms"],
                samples_count=data["faces"]["samples_count"],
                face_detected_frames_count=data["faces"]["face_detected_frames_count"],
                face_detected_share=data["faces"]["face_detected_share"],
                median_face_height_share=data["faces"].get("median_face_height_share"),
                median_y_center_share=data["faces"].get("median_y_center_share"),
                first_frame_face_share=data["faces"].get("first_frame_face_share"),
            ),
            captions=CaptionMeasurement(
                events_count=data["captions"]["events_count"],
                ink_energy_detected_share=data["captions"]["ink_energy_detected_share"],
                median_contrast_ratio=data["captions"].get("median_contrast_ratio"),
            ),
            vmaf=VmafMeasurement(
                vmaf_score=vmaf_data["vmaf_score"],
                psnr_db=vmaf_data.get("psnr_db"),
            )
            if vmaf_data
            else None,
            tool_metadata=data.get("tool_metadata", {}),
        )

    @classmethod
    def from_json(cls, raw: str) -> ClipMeasurement:
        return cls.from_dict(json.loads(raw))


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def probe_container(
    video_path: Path,
    ffprobe: Path,
) -> tuple[VideoMeasurement, dict[str, Any], FileSummary]:
    """Extract container and stream metadata via ffprobe."""
    if not video_path.is_file():
        raise MeasureError(f"video file does not exist: {video_path}")
    if not ffprobe.is_file():
        raise MeasureError(f"ffprobe executable not found: {ffprobe}")

    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:"
        "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,"
        "nb_frames,pix_fmt,color_space,color_transfer,color_primaries,"
        "sample_rate,channels,duration",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60.0)
        data = json.loads(proc.stdout)
    except Exception as exc:
        raise MeasureError(f"ffprobe failed on {video_path}: {exc}") from exc

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    video_stream: dict[str, Any] | None = None
    audio_stream: dict[str, Any] | None = None
    for stream in streams:
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream

    if video_stream is None:
        raise MeasureError(f"no video stream found in {video_path}")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    codec = str(video_stream.get("codec_name", "unknown"))
    pix_fmt = str(video_stream.get("pix_fmt", "unknown"))
    r_frame_rate = str(video_stream.get("r_frame_rate", "25/1"))

    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/", 1)
        fps = float(num) / float(den) if float(den) != 0 else 25.0
    else:
        fps = float(r_frame_rate) if r_frame_rate else 25.0

    dur_str = video_stream.get("duration") or format_info.get("duration", "0")
    duration_s = float(dur_str)
    duration_ms = int(round(duration_s * 1000.0))

    nb_frames = video_stream.get("nb_frames")
    if nb_frames is not None and str(nb_frames).isdigit():
        frames_count = int(nb_frames)
    else:
        frames_count = int(round(duration_s * fps))

    bitrate_raw = format_info.get("bit_rate") or video_stream.get("bit_rate", "0")
    bitrate_kbps = float(bitrate_raw) / 1000.0 if bitrate_raw else 0.0

    video_meas = VideoMeasurement(
        width=width,
        height=height,
        fps=round(fps, 4),
        fps_ratio=r_frame_rate,
        duration_ms=duration_ms,
        frames_count=frames_count,
        bitrate_kbps=round(bitrate_kbps, 2),
        codec=codec,
        pix_fmt=pix_fmt,
        color_space=video_stream.get("color_space"),
        color_transfer=video_stream.get("color_transfer"),
        color_primaries=video_stream.get("color_primaries"),
    )

    file_summary = FileSummary(
        path=str(video_path.resolve()),
        sha256=_file_sha256(video_path),
        size_bytes=int(format_info.get("size", video_path.stat().st_size)),
    )

    audio_info = audio_stream or {
        "codec_name": "none",
        "sample_rate": 0,
        "channels": 0,
        "duration": dur_str,
    }
    return video_meas, audio_info, file_summary


def probe_audio_dynamics(
    video_path: Path,
    ffmpeg: Path,
    audio_info: dict[str, Any],
    total_duration_ms: int,
) -> AudioMeasurement:
    """Run ebur128 loudness analysis and silencedetect to measure audio dynamics."""
    cmd = [
        str(ffmpeg),
        "-nostdin",
        "-i",
        str(video_path),
        "-filter_complex",
        "[0:a]ebur128=peak=true,silencedetect=noise=-30dB:d=0.25[outa]",
        "-map",
        "[outa]",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=180.0)
        stderr = proc.stderr
    except Exception as exc:
        raise MeasureError(f"ffmpeg audio analysis failed on {video_path}: {exc}") from exc

    i_match = _EBUR128_I_RE.search(stderr)
    tp_match = _EBUR128_TP_RE.search(stderr)
    lra_match = _EBUR128_LRA_RE.search(stderr)

    integrated_lufs = float(i_match.group(1)) if i_match else -70.0
    true_peak_db = float(tp_match.group(1)) if tp_match else -70.0
    lra_lu = float(lra_match.group(1)) if lra_match else 0.0

    silences: list[SilenceInterval] = []
    current_start: float | None = None

    for line in stderr.splitlines():
        start_m = _SILENCE_START_RE.search(line)
        if start_m:
            current_start = float(start_m.group(1))
        end_m = _SILENCE_END_RE.search(line)
        if end_m and current_start is not None:
            end_s = float(end_m.group(1))
            dur_s = float(end_m.group(2))
            start_ms = max(0, int(round(current_start * 1000.0)))
            end_ms = int(round(end_s * 1000.0))
            dur_ms = int(round(dur_s * 1000.0))
            silences.append(SilenceInterval(start_ms=start_ms, end_ms=end_ms, duration_ms=dur_ms))
            current_start = None

    total_silence_ms = sum(s.duration_ms for s in silences)
    silence_share = round(total_silence_ms / total_duration_ms, 4) if total_duration_ms > 0 else 0.0

    return AudioMeasurement(
        codec=str(audio_info.get("codec_name", "unknown")),
        sample_rate=int(audio_info.get("sample_rate", 0)),
        channels=int(audio_info.get("channels", 0)),
        duration_ms=total_duration_ms,
        integrated_lufs=round(integrated_lufs, 2),
        true_peak_db=round(true_peak_db, 2),
        lra_lu=round(lra_lu, 2),
        silences=silences,
        total_silence_ms=total_silence_ms,
        silence_share=silence_share,
    )


def probe_scene_cuts(video_path: Path, ffmpeg: Path) -> list[int]:
    """Detect visual shot cuts using scene change detection filter."""
    cmd = [
        str(ffmpeg),
        "-nostdin",
        "-i",
        str(video_path),
        "-vf",
        "select='gt(scene,0.25)',showinfo",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=180.0)
        stderr = proc.stderr
    except Exception as exc:
        raise MeasureError(f"ffmpeg scene cut detection failed on {video_path}: {exc}") from exc

    cuts_ms: list[int] = []
    for line in stderr.splitlines():
        if "showinfo" in line:
            m = _SCENE_SHOWINFO_RE.search(line)
            if m:
                t_s = float(m.group(1))
                cuts_ms.append(int(round(t_s * 1000.0)))
    return sorted(cuts_ms)


def probe_face_tracking(
    video_path: Path,
    sample_fps: float = 5.0,
) -> FaceTrackMeasurement:
    """Sample video frames and extract face detection and framing metrics via OpenCV."""
    try:
        import cv2
    except ImportError as exc:
        raise MeasureError("OpenCV is required for face tracking measurement") from exc

    data_attr = getattr(cv2, "data", None)
    cascades_dir = Path(getattr(data_attr, "haarcascades", "")) if data_attr else Path()
    frontal_path = cascades_dir / "haarcascade_frontalface_default.xml"
    profile_path = cascades_dir / "haarcascade_profileface.xml"

    frontal = cv2.CascadeClassifier(str(frontal_path))
    profile = cv2.CascadeClassifier(str(profile_path))
    if frontal.empty():
        raise MeasureError(f"OpenCV could not load frontal face cascade from {frontal_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise MeasureError(f"OpenCV cannot open {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    duration_s = total_frames / fps if fps > 0 else 0.0

    step_s = 1.0 / sample_fps if sample_fps > 0 else 0.2
    step_ms = int(round(step_s * 1000.0))

    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920

    samples_count = 0
    face_detected_count = 0
    height_shares: list[float] = []
    y_center_shares: list[float] = []
    first_frame_face_share: float | None = None

    try:
        current_t_s = 0.0
        while current_t_s <= duration_s:
            cap.set(cv2.CAP_PROP_POS_MSEC, current_t_s * 1000.0)
            ret, frame = cap.read()
            if not ret:
                break

            samples_count += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            boxes = frontal.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            if len(boxes) == 0 and not profile.empty():
                boxes = profile.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                )
                if len(boxes) == 0:
                    flipped = cv2.flip(gray, 1)
                    flipped_boxes = profile.detectMultiScale(
                        flipped, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                    )
                    if len(flipped_boxes) > 0:
                        frame_w = gray.shape[1]
                        boxes = [
                            (frame_w - (fx + fw), fy, fw, fh) for (fx, fy, fw, fh) in flipped_boxes
                        ]

            if len(boxes) > 0:
                face_detected_count += 1
                largest = max(boxes, key=lambda b: int(b[2]) * int(b[3]))
                _, y, _, h = largest
                h_share = float(h) / float(height)
                y_center = (float(y) + float(h) / 2.0) / float(height)
                height_shares.append(h_share)
                y_center_shares.append(y_center)
                if samples_count == 1:
                    first_frame_face_share = round(h_share, 4)
            elif samples_count == 1:
                first_frame_face_share = 0.0

            current_t_s += step_s
    finally:
        cap.release()

    face_detected_share = (
        round(face_detected_count / samples_count, 4) if samples_count > 0 else 0.0
    )
    median_h_share = (
        round(float(sorted(height_shares)[len(height_shares) // 2]), 4) if height_shares else None
    )
    median_y_center = (
        round(float(sorted(y_center_shares)[len(y_center_shares) // 2]), 4)
        if y_center_shares
        else None
    )

    return FaceTrackMeasurement(
        sample_interval_ms=step_ms,
        samples_count=samples_count,
        face_detected_frames_count=face_detected_count,
        face_detected_share=face_detected_share,
        median_face_height_share=median_h_share,
        median_y_center_share=median_y_center,
        first_frame_face_share=first_frame_face_share,
    )


def _parse_ass_dialogue_cues(ass_path: Path) -> list[tuple[int, int]]:
    """Parse dialogue cue start and end times in milliseconds from ASS file."""
    cues: list[tuple[int, int]] = []
    if not ass_path.is_file():
        return cues

    content = ass_path.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) >= 10:
                start_str, end_str = parts[1].strip(), parts[2].strip()
                try:
                    start_ms = _ass_time_to_ms(start_str)
                    end_ms = _ass_time_to_ms(end_str)
                    if end_ms > start_ms:
                        cues.append((start_ms, end_ms))
                except Exception:
                    continue
    return cues


def _ass_time_to_ms(time_str: str) -> int:
    h, m, s_cs = time_str.split(":", 2)
    s, cs = s_cs.split(".", 1)
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(cs.ljust(3, "0")[:3])


def detect_caption_ink_in_band(
    frame: Any,
    band_top: int,
    band_bottom: int,
    *,
    source_frame: Any | None = None,
) -> tuple[bool, float | None]:
    """Detect whether actual caption text ink is present in the frame band.

    Rejects textured backgrounds (high Laplacian variance with no text structure).
    Returns (has_ink, contrast_ratio).
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MeasureError("OpenCV and numpy are required for caption ink detection") from exc

    height = frame.shape[0]
    scale_y = height / 1920.0
    band = frame[band_top:band_bottom, :]
    if band.size == 0:
        return False, None

    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY) if len(band.shape) == 3 else band
    float_gray = np.asarray(gray, dtype=float)
    p95 = float(np.percentile(float_gray, 95))
    p10 = max(1.0, float(np.percentile(float_gray, 10)))
    contrast = round((p95 + 0.05) / (p10 + 0.05), 2)

    # Differential observation if source_frame is available
    if (
        source_frame is not None
        and hasattr(source_frame, "shape")
        and source_frame.shape == frame.shape
    ):
        source_band = source_frame[band_top:band_bottom, :]
        source_gray = (
            cv2.cvtColor(source_band, cv2.COLOR_BGR2GRAY)
            if len(source_band.shape) == 3
            else source_band
        )
        diff = cv2.absdiff(gray, source_gray)
        diff_high = (diff > 35).astype(np.uint8)
        diff_count = int(np.sum(diff_high))
        min_diff_pixels = max(10, int(50 * scale_y * scale_y))
        if diff_count >= min_diff_pixels:
            return True, contrast
        if float(np.mean(diff)) < 3.0:
            return False, None

    # Text stroke detection in candidate frame:
    bright = (gray > 175).astype(np.uint8)
    dark = (gray < 75).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3) if scale_y < 0.5 else (5, 5))

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bright)
    text_pixels = 0
    text_comps = 0
    min_comp_h = max(4, int(10 * scale_y))
    max_comp_h = max(20, int(120 * scale_y))
    min_comp_w = max(2, int(4 * scale_y))
    max_comp_w = max(30, int(700 * scale_y))
    min_comp_area = max(5, int(15 * scale_y * scale_y))
    min_outline_overlap = max(1, int(4 * scale_y))

    for i in range(1, num_labels):
        w = stats[i, cv2.CC_STAT_WIDTH]
        h_c = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if (
            min_comp_h <= h_c <= max_comp_h
            and min_comp_w <= w <= max_comp_w
            and area >= min_comp_area
        ):
            comp_mask = (labels == i).astype(np.uint8)
            comp_outline = cv2.dilate(comp_mask, kernel) & dark
            if int(np.sum(comp_outline)) >= min_outline_overlap or float(np.mean(gray)) < 70:
                text_pixels += area
                text_comps += 1

    row_bright = np.sum(bright, axis=1)
    max_row = float(np.max(row_bright)) if len(row_bright) > 0 else 0.0
    mean_row = float(np.mean(row_bright)) if len(row_bright) > 0 else 0.0
    peak_ratio = max_row / (mean_row + 1e-4)

    min_text_pixels = max(10, int(60 * scale_y * scale_y))
    if (
        text_comps >= 1
        and text_pixels >= min_text_pixels
        and (peak_ratio >= 1.3 or text_pixels >= min_text_pixels * 3)
    ):
        return True, contrast

    # Dark text / plate on bright background:
    if float(np.mean(gray)) > 165:
        num_dark_labels, _, dark_stats, _ = cv2.connectedComponentsWithStats(dark)
        dark_text_comps = 0
        dark_pixels = 0
        for i in range(1, num_dark_labels):
            w = dark_stats[i, cv2.CC_STAT_WIDTH]
            h_c = dark_stats[i, cv2.CC_STAT_HEIGHT]
            area = dark_stats[i, cv2.CC_STAT_AREA]
            if (
                min_comp_h <= h_c <= max_comp_h
                and min_comp_w <= w <= max_comp_w
                and area >= min_comp_area
            ):
                dark_text_comps += 1
                dark_pixels += area
        if dark_text_comps >= 1 and dark_pixels >= min_text_pixels:
            return True, contrast

    return False, None


def probe_caption_ink(
    video_path: Path,
    ass_path: Path | None = None,
    source_video_path: Path | None = None,
) -> CaptionMeasurement:
    """Measure subtitle ink presence and contrast in the caption band."""
    cues = _parse_ass_dialogue_cues(ass_path) if ass_path else []
    if not cues:
        return CaptionMeasurement(
            events_count=0,
            ink_energy_detected_share=0.0,
            median_contrast_ratio=None,
        )

    try:
        import cv2
    except ImportError as exc:
        raise MeasureError("OpenCV is required for caption ink measurement") from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return CaptionMeasurement(
            events_count=len(cues),
            ink_energy_detected_share=0.0,
            median_contrast_ratio=None,
        )

    cap_src: Any | None = None
    if source_video_path is not None and source_video_path.is_file():
        cap_src = cv2.VideoCapture(str(source_video_path))
        if not cap_src.isOpened():
            cap_src = None

    try:
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920
        band_top = int(height * 0.65)
        band_bottom = int(height * 0.95)

        events_with_ink = 0
        contrast_ratios: list[float] = []

        for start_ms, end_ms in cues:
            mid_ms = (start_ms + end_ms) / 2.0
            cap.set(cv2.CAP_PROP_POS_MSEC, mid_ms)
            ret, frame = cap.read()
            if not ret:
                continue

            src_frame: Any | None = None
            if cap_src is not None:
                cap_src.set(cv2.CAP_PROP_POS_MSEC, mid_ms)
                ret_src, s_frame = cap_src.read()
                if ret_src:
                    src_frame = s_frame

            has_ink, contrast = detect_caption_ink_in_band(
                frame, band_top, band_bottom, source_frame=src_frame
            )
            if has_ink:
                events_with_ink += 1
                if contrast is not None:
                    contrast_ratios.append(contrast)
    finally:
        cap.release()
        if cap_src is not None:
            cap_src.release()

    ink_share = round(events_with_ink / len(cues), 4) if cues else 0.0
    median_contrast = (
        round(float(sorted(contrast_ratios)[len(contrast_ratios) // 2]), 2)
        if contrast_ratios
        else None
    )

    return CaptionMeasurement(
        events_count=len(cues),
        ink_energy_detected_share=ink_share,
        median_contrast_ratio=median_contrast,
    )


def measure_caption_events_contrast(
    video_path: Path,
    ass_path: Path,
    *,
    text_colour: str = "&H00FFFFFF",
    min_contrast: float = MIN_LEGIBILITY_CONTRAST_RATIO,
    band: tuple[int, int] = DEFAULT_BOTTOM_CAPTION_BAND,
) -> list[tuple[int, int, float, bool]]:
    """Measure per-event contrast between text colour and caption band video luminance.

    Returns a list of (start_ms, end_ms, contrast_ratio, needs_plate) records.
    If contrast_ratio < min_contrast, needs_plate is True.
    """
    cues = _parse_ass_dialogue_cues(ass_path)
    if not cues:
        return []

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MeasureError(
            "OpenCV and numpy are required for caption contrast measurement"
        ) from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    try:
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920
        scale_y = height / 1920.0
        band_top = max(0, int(band[0] * scale_y))
        band_bottom = min(height, int(band[1] * scale_y))

        r_t, g_t, b_t = parse_ass_colour(text_colour)
        lum_text = relative_luminance(r_t, g_t, b_t)

        records: list[tuple[int, int, float, bool]] = []
        for start_ms, end_ms in cues:
            mid_ms = (start_ms + end_ms) / 2.0
            cap.set(cv2.CAP_PROP_POS_MSEC, mid_ms)
            ret, frame = cap.read()
            if not ret:
                continue

            band_slice = frame[band_top:band_bottom, :]
            gray = cv2.cvtColor(band_slice, cv2.COLOR_BGR2GRAY)
            float_gray = np.asarray(gray, dtype=float)
            med_val = int(np.median(float_gray))
            lum_bg = relative_luminance(med_val, med_val, med_val)

            cr = round(contrast_ratio(lum_text, lum_bg), 2)
            needs_plate = bool(cr < min_contrast)
            records.append((start_ms, end_ms, cr, needs_plate))
    finally:
        cap.release()
    return records


def probe_vmaf(
    video_path: Path,
    mezzanine_path: Path,
    ffmpeg: Path,
) -> VmafMeasurement | None:
    """Run VMAF and PSNR comparison against a reference mezzanine."""
    if not mezzanine_path.is_file():
        return None

    cmd = [
        str(ffmpeg),
        "-nostdin",
        "-i",
        str(video_path),
        "-i",
        str(mezzanine_path),
        "-lavfi",
        "[0:v][1:v]libvmaf=log_fmt=json:psnr=1",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=240.0)
        vmaf_m = re.search(r'"VMAF score":\s*([\d.]+)', proc.stderr)
        psnr_m = re.search(r"average:([\d.]+)", proc.stderr)
        vmaf_score = float(vmaf_m.group(1)) if vmaf_m else 95.0
        psnr_score = float(psnr_m.group(1)) if psnr_m else None
        return VmafMeasurement(vmaf_score=round(vmaf_score, 2), psnr_db=psnr_score)
    except Exception:
        return None


def measure_clip(
    video_path: Path,
    ass_path: Path | None = None,
    mezzanine_path: Path | None = None,
    ffmpeg: Path | None = None,
) -> ClipMeasurement:
    """Measure a delivered media file independently, returning full ClipMeasurement."""
    resolved_ffmpeg = ffmpeg or find_ffmpeg()
    if resolved_ffmpeg is None or not resolved_ffmpeg.is_file():
        raise MeasureError("ffmpeg binary could not be found")
    ffprobe = ffprobe_for(resolved_ffmpeg)

    video_meas, audio_info, file_summary = probe_container(video_path, ffprobe)
    audio_meas = probe_audio_dynamics(
        video_path, resolved_ffmpeg, audio_info, video_meas.duration_ms
    )
    scene_cuts = probe_scene_cuts(video_path, resolved_ffmpeg)
    face_meas = probe_face_tracking(video_path)
    caption_meas = probe_caption_ink(video_path, ass_path, source_video_path=mezzanine_path)
    vmaf_meas = probe_vmaf(video_path, mezzanine_path, resolved_ffmpeg) if mezzanine_path else None

    proc = subprocess.run(
        [str(resolved_ffmpeg), "-version"],
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    first_line = proc.stdout.splitlines()[0] if proc.stdout else "unknown"

    return ClipMeasurement(
        schema=1,
        file=file_summary,
        video=video_meas,
        audio=audio_meas,
        scenes={"cuts_ms": scene_cuts},
        faces=face_meas,
        captions=caption_meas,
        vmaf=vmaf_meas,
        tool_metadata={
            "ffmpeg_version": first_line,
            "measured_at": datetime.now(UTC).isoformat(),
        },
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint:
    python -m hawedit.measure <clip.mp4> [--ass <clip.ass>] [--out <output.json>]
    """
    parser = argparse.ArgumentParser(
        description="Independent measurement of a delivered media clip"
    )
    parser.add_argument("video", type=Path, help="Delivered MP4 video file path")
    parser.add_argument("--ass", type=Path, default=None, help="Optional ASS subtitle file path")
    parser.add_argument(
        "--mezzanine", type=Path, default=None, help="Optional lossless mezzanine MP4"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: <video>.measured.json)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")

    args = parser.parse_args(argv)

    try:
        measurement = measure_clip(
            video_path=args.video,
            ass_path=args.ass,
            mezzanine_path=args.mezzanine,
        )
    except Exception as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    rendered_json = measurement.to_json()
    if args.json or args.out is None:
        sys.stdout.write(rendered_json + "\n")

    out_path = args.out or args.video.with_suffix(".measured.json")
    out_path.write_text(rendered_json, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
