"""HawEdit V8 lean clip compiler & Watch-Before-Ship orchestrator (D-382..D-386)."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import re
import struct
import subprocess
import tempfile
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Literal, Protocol, TypeVar

from hawedit.assembly import AssemblySpan, plan_viral_story_cut
from hawedit.atomic_fs import write_text_atomic
from hawedit.boundary import Boundary
from hawedit.brand import BrandKit, ProgressBarConfig
from hawedit.caption_polish import repair_kurdish_asr_orthography
from hawedit.captions import find_ffmpeg
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Provenance, Qc
from hawedit.ingest import probe_duration_ms, probe_stream
from hawedit.render import (
    BRollItem,
    Reframe,
    frame_rate,
    render_clip,
    resolve_encoder,
    vertical_crop_size,
    vertical_framing,
)
from hawedit.sentences import Sentence, segment_sentences
from hawedit.silence import (
    KURDISH_FILLER_TOKENS,
    SilencePlan,
    plan_silence_tightening,
    remap_timestamp,
    tighten_ctc_word_onsets,
)
from hawedit.transcripts import AsrProvenance, Word
from hawedit.v8.asd import (
    ActiveSpeakerError,
    ActiveSpeakerScore,
    FaceDetectionFrame,
    LockedShotCrop,
    compute_locked_shot_crops,
    detect_exact_assembled_cuts_ms,
    detect_exact_shot_cuts_ms,
    locked_crops_to_render_inputs,
    score_active_speakers,
    snap_locked_crops_to_cuts,
)
from hawedit.v8.broll import (
    DEFAULT_BROLL_CACHE_DIR,
    extract_kurdish_stat_interrupts,
    resolve_visual_cues_to_broll,
)
from hawedit.v8.director import (
    DirectorUnavailable,
    LocalDirectorModality,
    OfflineRestrainedDirector,
    create_director_brain,
    critique_rendered_clip,
)
from hawedit.v8.schema import (
    CAMERA_MAX_SCALE,
    CAMERA_MIN_SCALE,
    CameraMove,
    CaptionBeat,
    CritiqueVerdict,
    DirectorScript,
    DirectorScriptError,
    VisualInterrupt,
    WordRepair,
    compile_restrained_camera_filter,
    snap_camera_moves_to_cuts,
    validate_director_script,
)
from hawedit.v8.story_editor import VisualCue, _source_quote_hook
from hawedit.v8.styles import ClientStylePreset, get_client_style_preset
from hawedit.v8.tiktok_subs import (
    END_CARD_DURATION_MS,
    VISUAL_INTERRUPT_MIN_START_MS,
    TikTokSubtitleError,
    build_viral_tiktok_ass,
    pace_viral_captions,
    render_tiktok_overlay_video,
)
from hawedit.v8.visual_aware import (
    ShotVisualProfile,
    analyze_shot_visual_profiles,
    apply_visual_groundings_to_profiles,
    choreograph_cut_covers,
    format_visual_groundings_for_director,
    protect_visual_gestures_in_cuts,
    run_local_video_awareness,
)

__all__ = [
    "MAX_CRITIQUE_REVISIONS",
    "PATCHABLE_DIRECTOR_FIELDS",
    "CachedDirectorScriptBrain",
    "DefaultV8ActiveSpeakerTracker",
    "DefaultV8ClipRenderer",
    "DefaultV8SubtitleRenderer",
    "DirectorBackend",
    "LockedCropWindow",
    "SubtitleArtifact",
    "SubtitleEngine",
    "V8ActiveSpeakerTrackerProtocol",
    "V8ClipRendererProtocol",
    "V8CompileConfig",
    "V8CompileError",
    "V8CompileResult",
    "V8DirectorProtocol",
    "V8SubtitleRendererProtocol",
    "VideoGrillReport",
    "apply_critique_patch",
    "apply_word_repairs",
    "compile_v8_clip",
    "grill_rendered_v8_video",
    "load_transcript_words",
    "parse_sentence_indices",
    "rebase_words_to_clip",
    "select_clip_span_from_sentences",
]

DirectorBackend = Literal["gemini", "local-omni", "offline"]
SubtitleEngine = Literal["skia", "libass"]
_T = TypeVar("_T")

_DIRECTOR_BACKENDS: Final[frozenset[str]] = frozenset({"gemini", "local-omni", "offline"})
_SUBTITLE_ENGINES: Final[frozenset[str]] = frozenset({"skia", "libass"})
_LOCAL_MODALITIES: Final[frozenset[str]] = frozenset({"omni", "vision", "text"})
MAX_CRITIQUE_REVISIONS: Final[int] = 1
PATCHABLE_DIRECTOR_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "hook_title_ckb",
        "word_repairs",
        "cuts",
        "camera_moves",
        "caption_beats",
        "visual_interrupts",
        "cold_open_span_ms",
    }
)
_SENTENCE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[sS]?(\d+)(?:-(\d+))?$")
_SHOWINFO_PTS_RE: Final[re.Pattern[str]] = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
_SILENCE_START_RE: Final[re.Pattern[str]] = re.compile(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)")
_SILENCE_END_RE: Final[re.Pattern[str]] = re.compile(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)")
_FLAT_FACTOR_RE: Final[re.Pattern[str]] = re.compile(
    r"Flat factor:\s*([0-9]+(?:\.[0-9]+)?|nan|inf)", re.IGNORECASE
)
_ARABIC_KURDISH_RE: Final[re.Pattern[str]] = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]"
)
_GRILL_CUT_MAD_THRESHOLD: Final[float] = 18.0
_GRILL_TRAILING_WINDOW_S: Final[float] = 0.80
_GRILL_SCAN_W: Final[int] = 135
_GRILL_SCAN_H: Final[int] = 240
_DEFAULT_PROGRESS_BAR_COLOR: Final[str] = "#FFD700"
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_DEFAULT_FONTS_DIR: Final[Path] = _REPO_ROOT / "assets" / "fonts"
_DEFAULT_YUNET_MODEL: Final[Path] = _REPO_ROOT / "models" / "face_detection_yunet.onnx"
_YUNET_CANDIDATES: Final[tuple[Path, ...]] = (
    _REPO_ROOT / "models" / "face_detection_yunet_2023mar.onnx",
    _DEFAULT_YUNET_MODEL,
    Path(r"D:\HawEdit-media\models\face_detection_yunet_2023mar.onnx"),
)
_ASD_ONNX_CANDIDATES: Final[tuple[Path, ...]] = (
    _REPO_ROOT / "models" / "lr_asd_talkset.onnx",
    _REPO_ROOT / "models" / "light_asd_talkset.onnx",
    Path(r"D:\HawEdit-media\models\lr_asd_talkset.onnx"),
)
_MAJOR_JUMP_CUT_MIN_REMOVED_MS: Final[int] = 600


def _resolve_default_yunet(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit
    env_p = os.environ.get("HAWEDIT_YUNET_ONNX", "").strip()
    if env_p:
        return Path(env_p)
    for cand in _YUNET_CANDIDATES:
        if cand.is_file():
            return cand
    return None


def _resolve_default_asd_onnx(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit
    env_p = os.environ.get("HAWEDIT_ASD_ONNX", "").strip()
    if env_p:
        return Path(env_p)
    for cand in _ASD_ONNX_CANDIDATES:
        if cand.is_file():
            return cand
    return None


class V8CompileError(RuntimeError):
    """Raised on any strict fail-stop violation during V8 compilation."""


class ReelQualityError(V8CompileError):
    """A candidate failed an editorial or forensic reel quality check."""


@dataclass(frozen=True, slots=True)
class LockedCropWindow:
    """One rock-steady median crop window for a shot or active-speaker hold (D-385)."""

    start_ms: int
    end_ms: int
    focus_x_px: int
    face_center_y_px: int
    face_height_px: int
    active_track_id: int | None = None

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise V8CompileError(f"LockedCropWindow invalid span [{self.start_ms}, {self.end_ms})")
        if self.focus_x_px < 0 or self.face_center_y_px < 0 or self.face_height_px < 0:
            raise V8CompileError("LockedCropWindow requires valid face geometry")
        if self.active_track_id is not None and self.face_height_px <= 0:
            raise V8CompileError(
                "LockedCropWindow requires face_height_px > 0 when active_track_id is set"
            )


@dataclass(frozen=True, slots=True)
class SubtitleArtifact:
    """Rendered viral subtitle payload produced by ``tiktok_subs.py`` (D-383)."""

    engine: SubtitleEngine
    ass_path: Path | None = None
    overlay_path: Path | None = None
    chunk_count: int = 0

    def __post_init__(self) -> None:
        if self.engine not in _SUBTITLE_ENGINES:
            raise V8CompileError(f"Unsupported subtitle engine: {self.engine!r}")
        if self.ass_path is None and self.overlay_path is None:
            raise V8CompileError("SubtitleArtifact needs at least one of ass_path or overlay_path")
        if self.chunk_count < 0:
            raise V8CompileError(f"chunk_count must be >= 0, got {self.chunk_count}")


@dataclass(frozen=True, slots=True)
class V8CompileConfig:
    """Explicit configuration for one V8 clip compilation (zero silent fallbacks)."""

    director_backend: DirectorBackend = "offline"
    sub_engine: SubtitleEngine = "skia"
    fps: float = 25.0
    width: int = 1080
    height: int = 1920
    anchor_y: float = 0.33
    cinema_grade: bool = True
    enable_critique: bool = True
    max_critique_revisions: int = MAX_CRITIQUE_REVISIONS
    enable_asd: bool = True
    encoder: str = "h264_nvenc"
    ffmpeg: Path | None = None
    condense: bool = False
    cold_open: bool = False
    silence_threshold_ms: int = 420
    silence_target_gap_ms: int = 140
    excise_fillers: bool = True
    progress_bar: bool = True
    deliverable: bool = True
    asd_onnx_path: Path | None = None
    fonts_dir: Path | None = None
    director_model: str | None = None
    omni_url: str | None = None
    local_modality: LocalDirectorModality | None = None
    enable_grill: bool = True
    style_preset: str = "viral_gold"
    brand_accent_hex: str | None = None
    speaker_name_ckb: str | None = None
    speaker_role_ckb: str | None = None
    end_card_title_ckb: str | None = None
    end_card_subtitle_ckb: str | None = None
    end_card_handle: str | None = None
    keep_overlay: bool = False
    allow_web_stock: bool = False
    enable_broll: bool = False
    broll_dir: Path | None = None
    broll_cache_dir: Path | None = None
    enable_banter_split: bool = True
    music_mood: Literal["none", "curious", "cinematic", "energetic"] = "none"
    enable_local_vlm: bool = True

    def __post_init__(self) -> None:
        if self.director_backend not in _DIRECTOR_BACKENDS:
            raise V8CompileError(f"Unsupported director_backend: {self.director_backend!r}")
        if self.sub_engine not in _SUBTITLE_ENGINES:
            raise V8CompileError(f"Unsupported sub_engine: {self.sub_engine!r}")
        if self.local_modality is not None and self.local_modality not in _LOCAL_MODALITIES:
            raise V8CompileError(f"Unsupported local_modality: {self.local_modality!r}")
        if not math.isfinite(self.fps) or self.fps <= 0.0:
            raise V8CompileError(f"fps must be positive finite, got {self.fps!r}")
        if self.width < 2 or self.height < 2:
            raise V8CompileError(f"Invalid output dimensions: {self.width}x{self.height}")
        if not math.isfinite(self.anchor_y):
            raise V8CompileError(f"anchor_y must be finite, got {self.anchor_y!r}")
        if not (0 <= self.max_critique_revisions <= MAX_CRITIQUE_REVISIONS):
            raise V8CompileError(
                f"max_critique_revisions must be in [0, {MAX_CRITIQUE_REVISIONS}] (D-386)"
            )
        if not self.encoder.strip():
            raise V8CompileError("encoder must be a non-empty string")
        if self.silence_threshold_ms < 0 or self.silence_target_gap_ms < 0:
            raise V8CompileError("silence thresholds must be non-negative")
        try:
            get_client_style_preset(self.style_preset, accent_hex_override=self.brand_accent_hex)
        except ValueError as exc:
            raise V8CompileError(f"Invalid V9 style/brand config: {exc}") from exc


@dataclass(frozen=True, slots=True)
class VideoGrillReport:
    """Forensic post-render video & audio grill report (D-387)."""

    mp4_path: Path
    duration_ms: int
    fps: float
    frame_count: int
    cut_times_s: tuple[float, ...]
    double_cuts: tuple[tuple[float, float], ...]
    trailing_cuts: tuple[float, ...]
    long_silences: tuple[tuple[float, float], ...]
    audio_flat_factor: float
    passed: bool
    defects: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mp4_path": str(self.mp4_path),
            "duration_ms": self.duration_ms,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "cut_times_s": list(self.cut_times_s),
            "double_cuts": [list(pair) for pair in self.double_cuts],
            "trailing_cuts": list(self.trailing_cuts),
            "long_silences": [list(pair) for pair in self.long_silences],
            "audio_flat_factor": self.audio_flat_factor,
            "passed": self.passed,
            "defects": list(self.defects),
        }


@dataclass(frozen=True, slots=True)
class V8CompileResult:
    """Immutable audit record of one completed V8 clip compilation."""

    clip_id: str
    output_mp4: Path
    script: DirectorScript
    script_path: Path
    repaired_words: tuple[Word, ...]
    camera_filter: str
    camera_jump_cuts_ms: tuple[int, ...]
    subtitles: SubtitleArtifact
    locked_crops: tuple[LockedCropWindow, ...]
    critique: CritiqueVerdict | None
    critique_revisions: int
    director_backend: DirectorBackend
    sub_engine: SubtitleEngine
    grill_report: VideoGrillReport | None = None
    retained_intervals_ms: tuple[tuple[int, int], ...] | None = None


class V8DirectorProtocol(Protocol):
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
    ) -> DirectorScript: ...

    def critique_clip(
        self, *, rendered_mp4: Path, script: DirectorScript, words: Sequence[Word]
    ) -> CritiqueVerdict: ...


class V8SubtitleRendererProtocol(Protocol):
    def render_subtitles(
        self,
        *,
        words: Sequence[Word],
        script: DirectorScript,
        clip_duration_ms: int,
        out_dir: Path,
        engine: SubtitleEngine,
    ) -> SubtitleArtifact: ...


class V8ActiveSpeakerTrackerProtocol(Protocol):
    def plan_locked_crops(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[LockedCropWindow, ...]: ...


class V8ClipRendererProtocol(Protocol):
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
    ) -> Path: ...


def _resolve_ffmpeg(ffmpeg: Path | None) -> Path:
    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise V8CompileError("No ffmpeg binary available; run scripts/fetch-ffmpeg.sh")
    return binary


def _resolve_fonts_dir(fonts_dir: Path | None) -> Path:
    candidate = fonts_dir if fonts_dir is not None else _DEFAULT_FONTS_DIR
    if not candidate.is_dir():
        raise V8CompileError(f"Fonts directory not found: {candidate}")
    return candidate


def _extract_clip_wav(
    source_mp4: Path, clip_in_ms: int, clip_out_ms: int, dest_wav: Path, *, ffmpeg: Path
) -> Path:
    dur_s = (clip_out_ms - clip_in_ms) / 1000.0
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{clip_in_ms / 1000.0:.3f}",
            "-t",
            f"{dur_s:.3f}",
            "-i",
            str(source_mp4),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(dest_wav),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(60.0, dur_s * 3.0),
    )
    if proc.returncode != 0 or not dest_wav.is_file() or dest_wav.stat().st_size == 0:
        raise V8CompileError(f"Failed to extract clip WAV: {proc.stderr.strip()[:400]}")
    return dest_wav


def _extract_clip_proxy(
    source_mp4: Path,
    clip_in_ms: int,
    clip_out_ms: int,
    dest_mp4: Path,
    *,
    ffmpeg: Path,
    width: int = 640,
    fps: float = 5.0,
) -> Path:
    dur_s = (clip_out_ms - clip_in_ms) / 1000.0
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{clip_in_ms / 1000.0:.3f}",
            "-t",
            f"{dur_s:.3f}",
            "-i",
            str(source_mp4),
            "-vf",
            f"fps={fps:g},scale={width}:-2",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(dest_mp4),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(60.0, dur_s * 4.0),
    )
    if proc.returncode != 0 or not dest_mp4.is_file() or dest_mp4.stat().st_size == 0:
        raise V8CompileError(f"Failed to extract clip tracking proxy: {proc.stderr.strip()[:400]}")
    return dest_mp4


def _detect_clip_shot_cuts_ms(
    proxy_mp4: Path, *, ffmpeg: Path, threshold: float = 0.30
) -> tuple[int, ...]:
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-i",
            str(proxy_mp4),
            "-vf",
            f"select='gt(scene,{threshold:.2f})',showinfo",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60.0,
    )
    if proc.returncode != 0:
        raise V8CompileError(
            f"Shot-cut detection failed on {proxy_mp4}: {proc.stderr.strip()[:400]}"
        )
    cuts: list[int] = []
    for match in _SHOWINFO_PTS_RE.finditer(proc.stderr):
        at_ms = int(round(float(match.group(1)) * 1000.0))
        if at_ms > 250 and (not cuts or at_ms - cuts[-1] >= 400):
            cuts.append(at_ms)
    return tuple(cuts)


def _probe_video_dims(source_mp4: Path, *, ffmpeg: Path) -> tuple[int, int]:
    try:
        raw = probe_stream(source_mp4, "stream=width,height", ffmpeg=ffmpeg, video_only=True)
        w_str, h_str = raw.strip().split("x", 1)
        w, h = int(w_str), int(h_str)
    except Exception as exc:
        raise V8CompileError(f"Failed to probe video dimensions of {source_mp4}: {exc}") from exc
    if w < 2 or h < 2:
        raise V8CompileError(f"Invalid video dimensions {w}x{h} for {source_mp4}")
    return w, h


def _remap_words_with_silence_plan(words: Sequence[Word], plan: SilencePlan) -> tuple[Word, ...]:
    remapped: list[Word] = []
    for word in words:
        mid = (word.start_ms + word.end_ms) // 2
        if any(rs <= mid < re_ for rs, re_ in plan.removed_intervals_ms):
            continue
        new_s = remap_timestamp(word.start_ms, plan)
        new_e = remap_timestamp(word.end_ms, plan)
        if new_e <= new_s:
            new_e = new_s + max(20, word.end_ms - word.start_ms)
        remapped.append(Word(w=word.w, start_ms=new_s, end_ms=new_e, conf=word.conf))
    return tuple(remapped)


def _remap_crops_to_assembly_spans(
    crops: Sequence[LockedCropWindow],
    spans: Sequence[AssemblySpan],
    *,
    clip_in_ms: int,
) -> tuple[LockedCropWindow, ...]:
    if not crops or not spans:
        return ()
    remapped: list[LockedCropWindow] = []
    offset_ms = 0
    for sp in spans:
        rel_in = sp.source_in_ms - clip_in_ms
        rel_out = sp.source_out_ms - clip_in_ms
        covered = [c for c in crops if c.end_ms > rel_in and c.start_ms < rel_out]
        if not covered:
            nearest = min(crops, key=lambda c: abs(((c.start_ms + c.end_ms) // 2) - rel_in))
            remapped.append(
                LockedCropWindow(
                    start_ms=offset_ms,
                    end_ms=offset_ms + sp.duration_ms,
                    focus_x_px=nearest.focus_x_px,
                    face_center_y_px=nearest.face_center_y_px,
                    face_height_px=nearest.face_height_px,
                    active_track_id=nearest.active_track_id,
                )
            )
        else:
            for c in covered:
                seg_s = max(rel_in, c.start_ms)
                seg_e = min(rel_out, c.end_ms)
                if seg_e <= seg_s:
                    continue
                remapped.append(
                    LockedCropWindow(
                        start_ms=offset_ms + (seg_s - rel_in),
                        end_ms=offset_ms + (seg_e - rel_in),
                        focus_x_px=c.focus_x_px,
                        face_center_y_px=c.face_center_y_px,
                        face_height_px=c.face_height_px,
                        active_track_id=c.active_track_id,
                    )
                )
        offset_ms += sp.duration_ms
    return tuple(remapped)


@dataclass(frozen=True, slots=True)
class _PreparedTimeline:
    source_width: int
    source_height: int
    source_fps: float
    effective_duration_ms: int
    effective_words: tuple[Word, ...]
    raw_shot_cuts_ms: tuple[int, ...]
    effective_shot_cuts_ms: tuple[int, ...]
    effective_jump_cuts_ms: tuple[int, ...]
    silence_plan: SilencePlan | None
    assembly_spans: tuple[AssemblySpan, ...] | None
    clip_wav_path: Path
    proxy_mp4_path: Path
    director_proxy_mp4: Path | None


class CachedDirectorScriptBrain:
    """Explicit replay director loading a previously saved ``DirectorScript`` JSON (D-387)."""

    def __init__(self, script_path: Path) -> None:
        if not script_path.is_file():
            raise V8CompileError(f"Cached DirectorScript not found: {script_path}")
        try:
            self._cached = DirectorScript.from_json(script_path.read_text(encoding="utf-8"))
        except (OSError, DirectorScriptError) as exc:
            raise V8CompileError(f"Invalid cached DirectorScript {script_path}: {exc}") from exc
        self._critic = OfflineRestrainedDirector()

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
        _ = (source_mp4, shot_cuts_ms, jump_cuts_ms)
        duration_ms = clip_out_ms - clip_in_ms
        # Re-align cached word_repairs strictly on exact original-text match (within +-4 tokens
        # if tightened silence/filler excision shifted indices).
        repairs: list[WordRepair] = []
        used_idx: set[int] = set()
        for r in self._cached.word_repairs:
            matched: int | None = None
            if 0 <= r.word_index < len(words) and words[r.word_index].w == r.original:
                matched = r.word_index
            else:
                for delta in (1, -1, 2, -2, 3, -3, 4, -4):
                    cand = r.word_index + delta
                    if (
                        0 <= cand < len(words)
                        and cand not in used_idx
                        and words[cand].w == r.original
                    ):
                        matched = cand
                        break
            if matched is not None and matched not in used_idx:
                used_idx.add(matched)
                repairs.append(
                    WordRepair(
                        word_index=matched,
                        original=r.original,
                        repaired=r.repaired,
                        reason=r.reason,
                    )
                )

        # Re-align cached camera moves & visual interrupts to the current duration_ms cleanly.
        moves = tuple(
            CameraMove(
                start_ms=m.start_ms,
                end_ms=min(duration_ms, m.end_ms),
                kind=m.kind,
                scale_start=m.scale_start,
                scale_end=m.scale_end,
                reason=m.reason,
            )
            for m in self._cached.camera_moves
            if m.start_ms < duration_ms and min(duration_ms, m.end_ms) > m.start_ms
        )
        beats = tuple(
            CaptionBeat(
                word_indices=b.word_indices,
                power_word_index=b.power_word_index,
                accent_color=b.accent_color,
            )
            for b in self._cached.caption_beats
            if all(0 <= wi < len(words) for wi in b.word_indices)
            and (b.power_word_index is None or 0 <= b.power_word_index < len(words))
        )
        interrupts = tuple(
            VisualInterrupt(
                start_ms=vi.start_ms,
                end_ms=min(duration_ms, vi.end_ms),
                text_ckb=vi.text_ckb,
                position=vi.position,
            )
            for vi in self._cached.visual_interrupts
            if vi.start_ms < duration_ms and min(duration_ms, vi.end_ms) > vi.start_ms
        )
        return DirectorScript(
            clip_id=clip_id,
            hook_title_ckb=self._cached.hook_title_ckb,
            word_repairs=tuple(sorted(repairs, key=lambda r: r.word_index)),
            cuts=(),
            camera_moves=moves,
            caption_beats=beats,
            visual_interrupts=interrupts,
            cold_open_span_ms=None,
        )

    def critique_clip(
        self, *, rendered_mp4: Path, script: DirectorScript, words: Sequence[Word]
    ) -> CritiqueVerdict:
        return self._critic.critique_clip(rendered_mp4=rendered_mp4, script=script, words=words)


class DefaultV8SubtitleRenderer:
    """Default V8 subtitle renderer wired to ``hawedit.v8.tiktok_subs`` (D-383)."""

    def __init__(
        self,
        *,
        fonts_dir: Path | None = None,
        fps: float = 25.0,
        width: int = 1080,
        height: int = 1920,
        y_center_px: int = 1380,
        ffmpeg: Path | None = None,
        style_preset: ClientStylePreset | str | None = None,
        speaker_bio: tuple[str, str | None] | None = None,
        end_card: tuple[str, str | None, str | None] | None = None,
    ) -> None:
        self._fonts_dir = fonts_dir
        self._fps = fps
        self._width = width
        self._height = height
        self._y_center_px = y_center_px
        self._hook_y_top_px = 135.0
        self._split_screen_windows_ms: tuple[tuple[int, int], ...] = ()
        self._ffmpeg = ffmpeg
        self._style_preset = style_preset
        self._speaker_bio = speaker_bio
        self._end_card = end_card

    def protect_outro_faces(
        self,
        crops: Sequence[LockedCropWindow],
        source_width: int,
        source_height: int,
        duration_ms: int,
        split_windows: Sequence[tuple[int, int]],
    ) -> None:
        """Leave a crowded or untracked outro clear; delivery includes the CTA in post.txt."""
        if self._end_card is None:
            return
        start = max(0, duration_ms - END_CARD_DURATION_MS)
        covered = start
        cw, ch = vertical_crop_size(source_width, source_height, self._width, self._height)
        for crop in crops:
            if crop.end_ms <= start or crop.start_ms >= duration_ms:
                continue
            if crop.start_ms > covered or crop.face_height_px <= 0:
                self._end_card = None
                return
            _, height, top = vertical_framing(
                source_height, cw, ch, crop.face_center_y_px, crop.face_height_px
            )
            face_top = (crop.face_center_y_px - crop.face_height_px / 2 - top) / height
            face_bottom = (crop.face_center_y_px + crop.face_height_px / 2 - top) / height
            if face_top < 0.72 and face_bottom > 0.13:
                self._end_card = None
                return
            covered = max(covered, crop.end_ms)
        if covered < duration_ms or any(s < duration_ms and e > start for s, e in split_windows):
            self._end_card = None

    def set_hook_y_top_px(self, hook_y_top_px: float) -> None:
        self._hook_y_top_px = hook_y_top_px

    def set_split_screen_windows(self, windows_ms: Sequence[tuple[int, int]]) -> None:
        self._split_screen_windows_ms = tuple((int(s), int(e)) for s, e in windows_ms if e > s)

    def render_subtitles(
        self,
        *,
        words: Sequence[Word],
        script: DirectorScript,
        clip_duration_ms: int,
        out_dir: Path,
        engine: SubtitleEngine,
    ) -> SubtitleArtifact:
        fonts_dir = _resolve_fonts_dir(self._fonts_dir)
        power_indices = frozenset(
            beat.power_word_index
            for beat in script.caption_beats
            if beat.power_word_index is not None
        )
        vis_interrupts = tuple(
            (max(VISUAL_INTERRUPT_MIN_START_MS, vi.start_ms), vi.end_ms, vi.text_ckb, vi.position)
            for vi in script.visual_interrupts
            if vi.end_ms > max(VISUAL_INTERRUPT_MIN_START_MS, vi.start_ms)
        )
        try:
            chunks = pace_viral_captions(
                words, duration_ms=clip_duration_ms, power_word_indices=power_indices
            )
            ass_text = build_viral_tiktok_ass(
                chunks,
                clip_in_ms=0,
                clip_duration_ms=clip_duration_ms,
                play_res_x=self._width,
                play_res_y=self._height,
                hook_title_ckb=script.hook_title_ckb or None,
                hook_y_top_px=min(self._hook_y_top_px, self._height - 1),
                visual_interrupts=vis_interrupts,
                style_preset=self._style_preset,
                speaker_bio=self._speaker_bio,
                end_card=self._end_card,
            )
        except (TikTokSubtitleError, ValueError) as exc:
            raise V8CompileError(f"Viral subtitle chunking/ASS build failed: {exc}") from exc

        ass_path = out_dir / f"{script.clip_id}.v8.ass"
        write_text_atomic(ass_path, ass_text)

        if engine == "libass":
            return SubtitleArtifact(
                engine="libass", ass_path=ass_path, overlay_path=None, chunk_count=len(chunks)
            )

        font_path = fonts_dir / "Vazirmatn.ttf"
        if not font_path.is_file():
            raise V8CompileError(f"Missing required Sorani font for Skia overlay: {font_path}")
        overlay_path = out_dir / f"{script.clip_id}.v8.overlay.mov"
        try:
            render_tiktok_overlay_video(
                chunks,
                duration_ms=clip_duration_ms,
                output_mov_or_mkv=overlay_path,
                font_path=font_path,
                hook_title_ckb=script.hook_title_ckb or None,
                fps=self._fps,
                width=self._width,
                height=self._height,
                y_center_px=self._y_center_px,
                hook_y_top_px=self._hook_y_top_px,
                split_screen_windows_ms=self._split_screen_windows_ms,
                visual_interrupts=vis_interrupts,
                ffmpeg=self._ffmpeg,
                style_preset=self._style_preset,
                speaker_bio=self._speaker_bio,
                end_card=self._end_card,
            )
        except (TikTokSubtitleError, RuntimeError, ValueError, FileNotFoundError) as exc:
            raise V8CompileError(f"Skia TikTok subtitle overlay render failed: {exc}") from exc

        return SubtitleArtifact(
            engine="skia", ass_path=ass_path, overlay_path=overlay_path, chunk_count=len(chunks)
        )


class DefaultV8ActiveSpeakerTracker:
    """Default V8 active speaker tracker wired to YuNet + ``hawedit.v8.asd`` (D-385)."""

    def __init__(
        self,
        *,
        onnx_model_path: Path | None = None,
        yunet_model_path: Path | None = None,
        sample_fps: float = 5.0,
        ffmpeg: Path | None = None,
        precomputed_proxy: Path | None = None,
        precomputed_wav: Path | None = None,
        source_dims: tuple[int, int] | None = None,
    ) -> None:
        self._onnx_model_path = _resolve_default_asd_onnx(onnx_model_path)
        self._yunet_model_path = _resolve_default_yunet(yunet_model_path)
        self._sample_fps = (
            25.0 if (self._onnx_model_path is not None and sample_fps == 5.0) else sample_fps
        )
        self._ffmpeg = ffmpeg
        self._precomputed_proxy = precomputed_proxy
        self._precomputed_wav = precomputed_wav
        self._source_dims = source_dims
        self.last_detections: tuple[FaceDetectionFrame, ...] = ()
        self.last_scores: tuple[ActiveSpeakerScore, ...] = ()
        self.last_proxy_dims: tuple[int, int] | None = None

    def plan_locked_crops(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[LockedCropWindow, ...]:
        import cv2

        binary = _resolve_ffmpeg(self._ffmpeg)
        src_w, src_h = (
            self._source_dims
            if self._source_dims is not None
            else _probe_video_dims(source_mp4, ffmpeg=binary)
        )
        duration_ms = clip_out_ms - clip_in_ms
        if self._yunet_model_path is not None and not self._yunet_model_path.is_file():
            raise V8CompileError(f"Missing YuNet face detector model: {self._yunet_model_path}")

        with tempfile.TemporaryDirectory(prefix="hawedit-v8-asd-") as tmp_dir:
            tmp = Path(tmp_dir)
            proxy_mp4 = (
                self._precomputed_proxy
                if self._precomputed_proxy is not None and self._precomputed_proxy.is_file()
                else _extract_clip_proxy(
                    source_mp4,
                    clip_in_ms,
                    clip_out_ms,
                    tmp / "asd_proxy.mp4",
                    ffmpeg=binary,
                    width=640,
                    fps=self._sample_fps,
                )
            )
            clip_wav = (
                self._precomputed_wav
                if self._precomputed_wav is not None and self._precomputed_wav.is_file()
                else _extract_clip_wav(
                    source_mp4, clip_in_ms, clip_out_ms, tmp / "asd_clip.wav", ffmpeg=binary
                )
            )

            cap = cv2.VideoCapture(str(proxy_mp4))
            if not cap.isOpened():
                raise V8CompileError(f"OpenCV failed to open ASD proxy: {proxy_mp4}")
            try:
                proxy_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                proxy_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = float(cap.get(cv2.CAP_PROP_FPS)) or self._sample_fps
                yunet_detector: Any = None
                if self._yunet_model_path is not None and hasattr(cv2, "FaceDetectorYN"):
                    yunet_detector = cv2.FaceDetectorYN.create(
                        str(self._yunet_model_path),
                        "",
                        (proxy_w, proxy_h),
                        score_threshold=0.55,
                        nms_threshold=0.3,
                        top_k=10,
                    )
                cv2_mod: Any = cv2
                cascades_root = Path(cv2_mod.data.haarcascades)
                frontal = cv2.CascadeClassifier(
                    str(cascades_root / "haarcascade_frontalface_default.xml")
                )
                profile = cv2.CascadeClassifier(str(cascades_root / "haarcascade_profileface.xml"))
                if frontal.empty() or profile.empty():
                    raise V8CompileError("OpenCV Haar face cascades failed to load")

                detections: list[FaceDetectionFrame] = []
                active_tracks: dict[int, tuple[float, float]] = {}
                next_track_id = 1
                sorted_cuts = sorted(c for c in shot_cuts_ms if 0 < c < duration_ms)
                cut_idx = 0
                frame_idx = 0
                while True:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    at_ms = int(round((frame_idx / fps) * 1000.0))
                    frame_idx += 1
                    if at_ms >= duration_ms:
                        break
                    while cut_idx < len(sorted_cuts) and at_ms >= sorted_cuts[cut_idx]:
                        active_tracks.clear()
                        cut_idx += 1

                    raw_boxes: list[tuple[float, float, float, float]] = []
                    if yunet_detector is not None:
                        _, y_faces = yunet_detector.detect(frame)
                        if y_faces is not None:
                            faces_rows: Any = y_faces
                            for row in faces_rows:
                                raw_boxes.append(
                                    (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
                                )
                    else:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        min_side = max(24, int(round(proxy_w * 0.06)))
                        f_hits: Any = frontal.detectMultiScale(
                            gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_side, min_side)
                        )
                        p_hits: Any = profile.detectMultiScale(
                            gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_side, min_side)
                        )
                        pf_hits: Any = profile.detectMultiScale(
                            cv2.flip(gray, 1),
                            scaleFactor=1.1,
                            minNeighbors=5,
                            minSize=(min_side, min_side),
                        )
                        for bx, by, bw, bh in f_hits:
                            raw_boxes.append((float(bx), float(by), float(bw), float(bh)))
                        for bx, by, bw, bh in p_hits:
                            raw_boxes.append((float(bx), float(by), float(bw), float(bh)))
                        for bx, by, bw, bh in pf_hits:
                            raw_boxes.append(
                                (
                                    float(proxy_w - (int(bx) + int(bw))),
                                    float(by),
                                    float(bw),
                                    float(bh),
                                )
                            )

                    # Deduplicate overlapping frontal/profile boxes (NMS IoU > 0.40) and
                    # discard spurious top-edge artifacts.
                    raw_boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
                    deduped: list[tuple[float, float, float, float]] = []
                    for bx, by, bw, bh in raw_boxes:
                        if bw <= 16.0 or bh <= 16.0 or by < proxy_h * 0.06:
                            continue
                        overlap = False
                        for kx, ky, kw, kh in deduped:
                            ix0, iy0 = max(bx, kx), max(by, ky)
                            ix1, iy1 = min(bx + bw, kx + kw), min(by + bh, ky + kh)
                            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
                            union = bw * bh + kw * kh - inter
                            if union > 0.0 and inter / union > 0.40:
                                overlap = True
                                break
                        if not overlap:
                            deduped.append((bx, by, bw, bh))

                    used_ids: set[int] = set()
                    for fx, fy, fw, fh in deduped:
                        cx = max(0.0, min(float(proxy_w - 1), fx + fw * 0.5))
                        cy = max(0.0, min(float(proxy_h - 1), fy + fh * 0.5))
                        best_tid: int | None = None
                        best_dist = proxy_w * 0.14
                        for tid, (px, py) in active_tracks.items():
                            if tid in used_ids:
                                continue
                            dist = math.hypot(cx - px, cy - py)
                            if dist < best_dist:
                                best_dist = dist
                                best_tid = tid
                        if best_tid is None:
                            best_tid = next_track_id
                            next_track_id += 1
                        used_ids.add(best_tid)
                        active_tracks[best_tid] = (cx, cy)
                        detections.append(
                            FaceDetectionFrame(
                                at_ms=at_ms,
                                track_id=best_tid,
                                cx=cx,
                                cy=cy,
                                w=fw,
                                h=fh,
                            )
                        )
            finally:
                cap.release()

            if not detections:
                return (
                    LockedCropWindow(
                        start_ms=0,
                        end_ms=duration_ms,
                        focus_x_px=src_w // 2,
                        face_center_y_px=src_h // 2,
                        face_height_px=0,
                        active_track_id=None,
                    ),
                )

            try:
                scores = score_active_speakers(
                    proxy_mp4,
                    clip_wav,
                    detections,
                    onnx_model_path=self._onnx_model_path,
                )
                proxy_crops = compute_locked_shot_crops(
                    detections,
                    scores,
                    source_width=proxy_w,
                    source_height=proxy_h,
                    shot_cuts_ms=shot_cuts_ms,
                    clip_duration_ms=duration_ms,
                )
            except (ActiveSpeakerError, FileNotFoundError, ValueError) as exc:
                raise V8CompileError(f"Active speaker detection failed: {exc}") from exc

            sx = src_w / float(proxy_w)
            sy = src_h / float(proxy_h)
            self.last_detections = tuple(detections)
            self.last_scores = tuple(scores)
            self.last_proxy_dims = (proxy_w, proxy_h)
            return tuple(
                LockedCropWindow(
                    start_ms=c.start_ms,
                    end_ms=c.end_ms,
                    focus_x_px=max(0, min(src_w - 1, int(round(c.focus_x_px * sx)))),
                    face_center_y_px=max(0, min(src_h - 1, int(round(c.face_center_y_px * sy)))),
                    face_height_px=(
                        max(1, min(src_h, int(round(c.face_height_px * sy))))
                        if c.face_height_px > 0
                        else 0
                    ),
                    active_track_id=c.active_track_id,
                )
                for c in proxy_crops
            )


class DefaultV8ClipRenderer:
    """Default V8 NVENC/x264 clip renderer wired to ``hawedit.render.render_clip``."""

    def __init__(
        self,
        *,
        source_width: int,
        source_height: int,
        silence_plan: SilencePlan | None = None,
        assembly_spans: Sequence[AssemblySpan] | None = None,
    ) -> None:
        self._source_width = source_width
        self._source_height = source_height
        self._silence_plan = silence_plan
        self._assembly_spans = tuple(assembly_spans) if assembly_spans else None
        self._b_roll: tuple[BRollItem, ...] = ()
        self._assembly_crossfade_ms: int = 0
        self._split_screen_windows: tuple[
            tuple[int, int, tuple[int, int, int, int], tuple[int, int, int, int]], ...
        ] = ()

    def set_visual_extras(
        self,
        *,
        b_roll: Sequence[BRollItem] = (),
        assembly_crossfade_ms: int = 0,
        split_screen_windows: Sequence[
            tuple[int, int, tuple[int, int, int, int], tuple[int, int, int, int]]
        ] = (),
    ) -> None:
        self._b_roll = tuple(b_roll)
        self._assembly_crossfade_ms = max(0, int(assembly_crossfade_ms))
        self._split_screen_windows = tuple(split_screen_windows)

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
        _ = camera_jump_cuts_ms
        if subtitles.ass_path is None:
            raise V8CompileError("DefaultV8ClipRenderer requires subtitles.ass_path for §4.3 audit")
        binary = _resolve_ffmpeg(config.ffmpeg)
        fonts_dir = _resolve_fonts_dir(config.fonts_dir)
        encoder = resolve_encoder(config.encoder, binary)

        raw_text = " ".join(w.w for w in words)
        with source_mp4.open("rb") as media_fh:
            media_sha256 = hashlib.file_digest(media_fh, "sha256").hexdigest()
        clip_obj = Clip(
            clip_id=script.clip_id,
            media_id=source_mp4.stem,
            media_sha256=media_sha256,
            in_ms=clip_in_ms,
            out_ms=clip_out_ms,
            discovery_path=DiscoveryPath.VERBAL,
            boundary=Boundary(
                anchor_in_ms=clip_in_ms,
                anchor_out_ms=clip_out_ms,
                final_in_ms=clip_in_ms,
                final_out_ms=clip_out_ms,
                in_extended_by=None,
                out_extended_by=None,
                sentence_complete=True,
                confidence=1.0,
            ),
            transcript=ClipTranscript(
                raw_ckb=raw_text,
                norm_ckb=raw_text,
                en_aux=None,
                words=tuple(words),
                asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
            ),
            editorial=Editorial(
                hook_score=0.85,
                self_contained=True,
                meaning_fidelity=1.0,
                misleading_edit_risk=0.0,
                cultural_landing=0.85,
                narrative_role="v8_director",
                judge="gemini-4-carbon",
            ),
            output=Output(
                title_ckb=script.hook_title_ckb or script.clip_id,
                description_ckb=script.hook_title_ckb or script.clip_id,
                crop_target="active_speaker_locked",
                caption_style=f"tiktok_{subtitles.engine}",
                durations=(clip_out_ms - clip_in_ms,),
            ),
            qc=Qc(auto_pass=True),
            provenance=Provenance.current(),
        )

        # Build zero-skew hold-and-step focus points + per-shot face boxes from LockedCropWindow
        # via locked_crops_to_render_inputs (D-387: x, y, w, h all switch on the exact same frame).
        shot_crops = tuple(
            LockedShotCrop(
                start_ms=crop.start_ms,
                end_ms=crop.end_ms,
                focus_x_px=crop.focus_x_px,
                face_center_y_px=crop.face_center_y_px,
                face_height_px=crop.face_height_px,
                active_track_id=crop.active_track_id,
            )
            for crop in locked_crops
        )
        focus_points, per_shot_boxes = locked_crops_to_render_inputs(
            shot_crops, clip_in_ms=clip_in_ms
        )

        reframe_mode = Reframe.FACE_TRACKED if focus_points else Reframe.STATIC_CENTRE
        resolved_style = get_client_style_preset(
            config.style_preset, accent_hex_override=config.brand_accent_hex
        )
        brand_kit = (
            BrandKit(
                progress_bar=ProgressBarConfig(
                    enabled=True,
                    color=resolved_style.progress_bar_hex or _DEFAULT_PROGRESS_BAR_COLOR,
                    height_px=6,
                    position="top",
                )
            )
            if config.progress_bar
            else None
        )

        sfx_events_ms = tuple(sorted({int(t) for t in camera_jump_cuts_ms if t > 0}))
        pop_events_ms = tuple(
            sorted(
                {
                    *(int(vi.start_ms) for vi in script.visual_interrupts if vi.start_ms > 0),
                    *(int(bi.start_ms) for bi in self._b_roll if bi.start_ms > 0),
                }
            )
        )
        riser_events_ms: tuple[int, ...] = ()
        if self._assembly_spans:
            co_acc = 0
            for sp in self._assembly_spans:
                if sp.role == "cold_open":
                    co_acc += sp.duration_ms
                else:
                    if co_acc > 0:
                        riser_events_ms = (co_acc,)
                    break
        speech_intervals = tuple((int(w.start_ms), int(w.end_ms)) for w in words)

        render_clip(
            clip_obj,
            source_mp4,
            subtitles.ass_path,
            fonts_dir,
            output_mp4,
            self._source_width,
            self._source_height,
            encoder=encoder,
            focus_points=tuple(focus_points),
            ffmpeg=binary,
            reframe=reframe_mode,
            fps=config.fps,
            deliverable=config.deliverable,
            speech_chain=True,
            two_pass_loudness=config.deliverable,
            silence_plan=self._silence_plan if self._assembly_spans is None else None,
            for_review=True,
            assembly_spans=self._assembly_spans,
            assembly_crossfade_ms=self._assembly_crossfade_ms,
            b_roll=self._b_roll,
            split_screen_windows=self._split_screen_windows,
            brand_kit=brand_kit,
            per_shot_boxes=tuple(per_shot_boxes),
            cinema_motion=camera_filter or None,
            cinema_sfx_events_ms=sfx_events_ms,
            cinema_pop_events_ms=pop_events_ms,
            cinema_riser_events_ms=riser_events_ms,
            cinema_music_mood=config.music_mood,
            cinema_speech_intervals_ms=speech_intervals,
            subtitle_overlay_path=subtitles.overlay_path if subtitles.engine == "skia" else None,
        )
        return output_mp4


def _build_spliced_director_proxy(
    source_mp4: Path,
    *,
    clip_in_ms: int,
    clip_out_ms: int,
    silence_plan: SilencePlan | None,
    assembly_spans: Sequence[AssemblySpan] | None,
    out_mp4: Path,
    ffmpeg: Path,
) -> Path:
    """Build a compact 360p @ 1 fps + 16 kHz AAC proxy matching the exact effective timeline."""
    from hawedit.assembly import assembled_splice_filter, assembly_seek_args
    from hawedit.silence import silence_trim_filter

    if assembly_spans:
        seek_args, seek_offset = assembly_seek_args(assembly_spans)
        splice = assembled_splice_filter(assembly_spans, input_offset_ms=seek_offset)
        fc = f"{splice};[v_concat]fps=1,scale=-2:360[v_out];[a_concat]aresample=16000[a_out]"
        cmd = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            *seek_args,
            "-i",
            str(source_mp4),
            "-filter_complex",
            fc,
            "-map",
            "[v_out]",
            "-map",
            "[a_out]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ac",
            "1",
            "-y",
            str(out_mp4),
        ]
    elif silence_plan is not None and silence_plan.total_removed_ms > 0:
        stf = silence_trim_filter(silence_plan.retained_intervals_ms, video_in="[0:v]")
        dur_s = (clip_out_ms - clip_in_ms) / 1000.0
        fc = f"{stf};[v_tightened]fps=1,scale=-2:360[v_out];[a_tightened]aresample=16000[a_out]"
        cmd = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{clip_in_ms / 1000.0:.3f}",
            "-t",
            f"{dur_s:.3f}",
            "-i",
            str(source_mp4),
            "-filter_complex",
            fc,
            "-map",
            "[v_out]",
            "-map",
            "[a_out]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ac",
            "1",
            "-y",
            str(out_mp4),
        ]
    else:
        return source_mp4

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=180.0)
    if proc.returncode != 0 or not out_mp4.is_file() or out_mp4.stat().st_size == 0:
        raise V8CompileError(f"Failed to build spliced director proxy: {proc.stderr.strip()[:400]}")
    return out_mp4


def _tighten_internal_word_silences(
    words: Sequence[Word],
    audio_wav: Path,
    *,
    min_word_ms: int = 650,
    min_silence_ms: int = 400,
    floor_db: float = -35.0,
    frame_ms: int = 20,
    pad_after_speech_ms: int = 35,
    pad_before_next_ms: int = 25,
) -> tuple[Word, ...]:
    """Expose dead-air troughs trapped inside CTC-smeared single words (D-387)."""
    if not words or not audio_wav.is_file():
        return tuple(words)
    with wave.open(str(audio_wav), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            return tuple(words)
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if not raw or sr <= 0:
        return tuple(words)
    total_samples = len(raw) // 2
    samples = struct.unpack(f"<{total_samples}h", raw)
    step = max(1, (sr * frame_ms) // 1000)
    floor_rms = 32768.0 * (10.0 ** (floor_db / 20.0))

    def _frame_rms(ms: int) -> float:
        i0 = max(0, min(total_samples - 1, int(ms * sr / 1000)))
        i1 = min(total_samples, i0 + step)
        if i1 <= i0:
            return 0.0
        sq = sum(s * s for s in samples[i0:i1])
        return math.sqrt(sq / (i1 - i0))

    out = list(words)
    for idx in range(len(out)):
        w = out[idx]
        if w.end_ms - w.start_ms < min_word_ms:
            continue
        # Scan 20 ms frames across [w.start_ms, w.end_ms] for the longest dead-air trough.
        best_s = -1
        best_e = -1
        run_s = -1
        voiced_frames: list[int] = []
        t = w.start_ms
        while t < w.end_ms:
            if _frame_rms(t) < floor_rms:
                if run_s < 0:
                    run_s = t
            else:
                if run_s >= 0:
                    if t - run_s > best_e - best_s:
                        best_s, best_e = run_s, t
                    run_s = -1
                voiced_frames.append(t)
            t += frame_ms
        if run_s >= 0 and w.end_ms - run_s > best_e - best_s:
            best_s, best_e = run_s, w.end_ms
        if best_s < 0 or (best_e - best_s) < min_silence_ms:
            continue

        voiced_before_ms = sum(frame_ms for vt in voiced_frames if vt < best_s)
        voiced_after_ms = sum(frame_ms for vt in voiced_frames if vt >= best_e)

        # Case 1: Leading silence or <= 100 ms bleeding tail from the previous word before
        # a dead-air trough, with the actual spoken word sitting after the trough.
        if voiced_before_ms <= 100 and voiced_after_ms > voiced_before_ms:
            new_start = max(w.start_ms, best_e - pad_before_next_ms)
            if w.end_ms - new_start < 40:
                continue
            out[idx] = Word(w=w.w, start_ms=new_start, end_ms=w.end_ms, conf=w.conf)
            if voiced_before_ms > 0 and idx > 0:
                prev = out[idx - 1]
                if w.start_ms - prev.end_ms <= 60:
                    new_prev_e = min(new_start - 10, best_s + pad_after_speech_ms)
                    if new_prev_e > prev.end_ms:
                        out[idx - 1] = Word(
                            w=prev.w, start_ms=prev.start_ms, end_ms=new_prev_e, conf=prev.conf
                        )
            continue

        # Case 2: True speech sits before the trough; retract end_ms and snap the next word
        # back if CTC smeared its onset into this word's tail.
        if voiced_before_ms < 40:
            continue
        new_end = min(w.end_ms, best_s + pad_after_speech_ms)
        if new_end <= w.start_ms + 40:
            continue
        out[idx] = Word(w=w.w, start_ms=w.start_ms, end_ms=new_end, conf=w.conf)
        if idx + 1 < len(out) and voiced_after_ms >= 40:
            nxt = out[idx + 1]
            if nxt.start_ms - w.end_ms <= 120:
                new_nxt_s = max(new_end + 10, best_e - pad_before_next_ms)
                if new_nxt_s < nxt.start_ms and new_nxt_s < nxt.end_ms:
                    out[idx + 1] = Word(
                        w=nxt.w, start_ms=new_nxt_s, end_ms=nxt.end_ms, conf=nxt.conf
                    )
    return tuple(out)


def _extract_assembled_proxy_and_wav(
    source_mp4: Path,
    assembly_spans: Sequence[AssemblySpan],
    proxy_out_mp4: Path,
    wav_out: Path,
    *,
    ffmpeg: Path,
    width: int = 640,
    fps: float = 25.0,
) -> tuple[Path, Path]:
    """Extract a spliced tracking proxy + 16 kHz WAV matching exact semantic assembly spans."""
    from hawedit.assembly import assembled_splice_filter, assembly_seek_args

    seek_args, seek_offset = assembly_seek_args(assembly_spans)
    splice = assembled_splice_filter(assembly_spans, crossfade_ms=24, input_offset_ms=seek_offset)
    fc = f"{splice};[v_concat]fps={fps:g},scale={width}:-2[v_out];[a_concat]aresample=16000[a_out]"
    dur_s = sum(sp.duration_ms for sp in assembly_spans) / 1000.0
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            *seek_args,
            "-i",
            str(source_mp4),
            "-filter_complex",
            fc,
            "-map",
            "[v_out]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-y",
            str(proxy_out_mp4),
            "-map",
            "[a_out]",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-vn",
            "-y",
            str(wav_out),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(90.0, dur_s * 5.0),
    )
    if (
        proc.returncode != 0
        or not proxy_out_mp4.is_file()
        or proxy_out_mp4.stat().st_size == 0
        or not wav_out.is_file()
        or wav_out.stat().st_size == 0
    ):
        raise V8CompileError(
            f"Failed to extract assembled semantic proxy/WAV: {proc.stderr.strip()[:400]}"
        )
    return proxy_out_mp4, wav_out


def _prepare_real_timeline(
    *,
    source_mp4: Path,
    clip_in_ms: int,
    clip_out_ms: int,
    clip_words: tuple[Word, ...],
    work_dir: Path,
    config: V8CompileConfig,
    explicit_shot_cuts_ms: Sequence[int],
    explicit_jump_cuts_ms: Sequence[int],
    source_sentences: Sequence[Sentence] | None = None,
    semantic_assembly_spans: Sequence[AssemblySpan] | None = None,
    semantic_words: Sequence[Word] | None = None,
) -> _PreparedTimeline:
    binary = _resolve_ffmpeg(config.ffmpeg)
    src_w, src_h = _probe_video_dims(source_mp4, ffmpeg=binary)
    src_fps = frame_rate(source_mp4, binary)
    source_ms = probe_duration_ms(source_mp4, binary)
    if clip_out_ms > source_ms:
        raise V8CompileError(
            f"Clip span [{clip_in_ms}, {clip_out_ms}] exceeds {source_mp4.name} ({source_ms} ms)"
        )

    proxy_fps = 25.0 if _resolve_default_asd_onnx(config.asd_onnx_path) is not None else 5.0

    # V10.2 Semantic Multi-Cut fast path: pre-planned non-contiguous spans already have
    # prosody-snapped boundaries & meaning-verified word pruning.
    if semantic_assembly_spans:
        spans_tuple = tuple(semantic_assembly_spans)
        for sp in spans_tuple:
            if sp.source_out_ms > source_ms:
                raise V8CompileError(
                    f"Semantic span [{sp.source_in_ms}, {sp.source_out_ms}] exceeds {source_ms} ms"
                )
        eff_dur_ms = sum(sp.duration_ms for sp in spans_tuple)
        proxy_mp4, clip_wav = _extract_assembled_proxy_and_wav(
            source_mp4,
            spans_tuple,
            work_dir / "clip_track_proxy.mp4",
            work_dir / "clip_16k.wav",
            ffmpeg=binary,
            width=640,
            fps=proxy_fps,
        )
        sem_eff_words = tuple(semantic_words) if semantic_words else clip_words
        cfr_cuts = (
            tuple(explicit_shot_cuts_ms)
            if explicit_shot_cuts_ms
            else detect_exact_assembled_cuts_ms(
                source_mp4,
                [(sp.source_in_ms, sp.source_out_ms) for sp in spans_tuple],
                fps=src_fps,
                ffmpeg=binary,
            )
        )
        sem_director_proxy: Path | None = None
        if config.director_backend != "offline":
            sem_director_proxy = _build_spliced_director_proxy(
                source_mp4,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                silence_plan=None,
                assembly_spans=spans_tuple,
                out_mp4=work_dir / "director_spliced_proxy.mp4",
                ffmpeg=binary,
            )
        return _PreparedTimeline(
            source_width=src_w,
            source_height=src_h,
            source_fps=src_fps,
            effective_duration_ms=eff_dur_ms,
            effective_words=sem_eff_words,
            raw_shot_cuts_ms=cfr_cuts,
            effective_shot_cuts_ms=cfr_cuts,
            effective_jump_cuts_ms=tuple(
                sorted({j for j in explicit_jump_cuts_ms if 0 < j < eff_dur_ms})
            ),
            silence_plan=None,
            assembly_spans=spans_tuple,
            clip_wav_path=clip_wav,
            proxy_mp4_path=proxy_mp4,
            director_proxy_mp4=sem_director_proxy,
        )

    raw_dur_ms = clip_out_ms - clip_in_ms
    clip_wav = _extract_clip_wav(
        source_mp4, clip_in_ms, clip_out_ms, work_dir / "clip_16k.wav", ffmpeg=binary
    )
    proxy_mp4 = _extract_clip_proxy(
        source_mp4,
        clip_in_ms,
        clip_out_ms,
        work_dir / "clip_track_proxy.mp4",
        ffmpeg=binary,
        width=640,
        fps=proxy_fps,
    )
    raw_shots = (
        tuple(explicit_shot_cuts_ms)
        if explicit_shot_cuts_ms
        else detect_exact_shot_cuts_ms(
            source_mp4, clip_in_ms=clip_in_ms, clip_out_ms=clip_out_ms, ffmpeg=binary
        )
    )

    # D-377 + D-387: VAD sub-word onset + internal dead-air trough tightening.
    tightened_words = _tighten_internal_word_silences(
        tighten_ctc_word_onsets(clip_words, clip_wav), clip_wav
    )
    fillers = KURDISH_FILLER_TOKENS if config.excise_fillers else None

    silence_plan: SilencePlan | None = None
    assembly_spans: tuple[AssemblySpan, ...] | None = None
    eff_words: tuple[Word, ...] = tightened_words
    eff_dur_ms = raw_dur_ms
    eff_shots = raw_shots
    eff_jumps = list(explicit_jump_cuts_ms)

    if config.condense or config.cold_open:
        raw_abs_words = tuple(
            Word(w=w.w, start_ms=clip_in_ms + w.start_ms, end_ms=clip_in_ms + w.end_ms, conf=w.conf)
            for w in clip_words
        )
        tight_abs_words = tuple(
            Word(w=w.w, start_ms=clip_in_ms + w.start_ms, end_ms=clip_in_ms + w.end_ms, conf=w.conf)
            for w in tightened_words
        )
        raw_sentences = (
            tuple(source_sentences)
            if source_sentences is not None
            and sum(len(s.words) for s in source_sentences) == len(tight_abs_words)
            else segment_sentences(raw_abs_words)
        )
        tight_sentences: list[Sentence] = []
        cursor = 0
        for sent in raw_sentences:
            n = len(sent.words)
            tight_sentences.append(
                Sentence(words=tight_abs_words[cursor : cursor + n], complete=sent.complete)
            )
            cursor += n
        story = plan_viral_story_cut(
            tight_sentences,
            clip_in_ms,
            clip_out_ms,
            enable_cold_open=config.cold_open,
            enable_condense=config.condense,
        )
        # Apply interior silence/filler cuts cleanly inside each body span (D-377 + D-378).
        expanded_spans: list[AssemblySpan] = []
        assembled_words: list[Word] = []
        out_cursor_ms = 0
        out_shots: list[int] = []
        for sp in story.spans:
            sp_words_rel = tuple(
                Word(
                    w=w.w,
                    start_ms=max(0, w.start_ms - sp.source_in_ms),
                    end_ms=min(sp.duration_ms, w.end_ms - sp.source_in_ms),
                    conf=w.conf,
                )
                for sent in sp.sentences
                for w in sent.words
                if w.end_ms > sp.source_in_ms and w.start_ms < sp.source_out_ms
            )
            sub_intervals: tuple[tuple[int, int], ...] = ((0, sp.duration_ms),)
            if sp.role != "cold_open" and config.silence_threshold_ms > 0 and sp_words_rel:
                sp_plan = plan_silence_tightening(
                    sp_words_rel,
                    0,
                    sp.duration_ms,
                    threshold_ms=config.silence_threshold_ms,
                    target_gap_ms=config.silence_target_gap_ms,
                    filler_tokens=fillers,
                )
                if sp_plan.total_removed_ms > 0 and sp_plan.retained_intervals_ms:
                    sub_intervals = sp_plan.retained_intervals_ms
            for sub_s, sub_e in sub_intervals:
                abs_s = sp.source_in_ms + sub_s
                abs_e = sp.source_in_ms + sub_e
                if abs_e <= abs_s:
                    continue
                if expanded_spans:
                    gap_src = abs_s - expanded_spans[-1].source_out_ms
                    if abs(gap_src) >= _MAJOR_JUMP_CUT_MIN_REMOVED_MS:
                        eff_jumps.append(out_cursor_ms)
                sub_dur = abs_e - abs_s
                expanded_spans.append(
                    AssemblySpan(
                        span_index=len(expanded_spans),
                        source_in_ms=abs_s,
                        source_out_ms=abs_e,
                        duration_ms=sub_dur,
                        sentences=sp.sentences,
                        role=sp.role,
                    )
                )
                for w in sp_words_rel:
                    mid = (w.start_ms + w.end_ms) // 2
                    if sub_s <= mid < sub_e:
                        ws = out_cursor_ms + max(0, w.start_ms - sub_s)
                        we = out_cursor_ms + min(sub_dur, w.end_ms - sub_s)
                        if we > ws:
                            assembled_words.append(Word(w=w.w, start_ms=ws, end_ms=we, conf=w.conf))
                for sc in raw_shots:
                    sc_abs = clip_in_ms + sc
                    if abs_s < sc_abs < abs_e:
                        out_shots.append(out_cursor_ms + (sc_abs - abs_s))
                out_cursor_ms += sub_dur
        if expanded_spans and assembled_words:
            assembly_spans = tuple(expanded_spans)
            eff_words = tuple(assembled_words)
            eff_dur_ms = out_cursor_ms
            eff_shots = tuple(sorted(set(out_shots)))
    elif config.silence_threshold_ms > 0:
        plan = plan_silence_tightening(
            tightened_words,
            0,
            raw_dur_ms,
            threshold_ms=config.silence_threshold_ms,
            target_gap_ms=config.silence_target_gap_ms,
            filler_tokens=fillers,
        )
        if plan.total_removed_ms > 0:
            silence_plan = plan
            eff_words = _remap_words_with_silence_plan(tightened_words, plan)
            eff_dur_ms = raw_dur_ms - plan.total_removed_ms
            eff_shots = tuple(
                sorted(
                    {
                        remap_timestamp(sc, plan)
                        for sc in raw_shots
                        if 0 < remap_timestamp(sc, plan) < eff_dur_ms
                    }
                )
            )
            for rs, re_ in plan.removed_intervals_ms:
                if re_ - rs >= _MAJOR_JUMP_CUT_MIN_REMOVED_MS:
                    eff_jumps.append(remap_timestamp(rs, plan))

    # Build a compact spliced proxy if the Director needs native video+audio on a modified timeline.
    director_proxy: Path | None = None
    if config.director_backend != "offline" and (
        assembly_spans is not None or silence_plan is not None
    ):
        director_proxy = _build_spliced_director_proxy(
            source_mp4,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            silence_plan=silence_plan,
            assembly_spans=assembly_spans,
            out_mp4=work_dir / "director_spliced_proxy.mp4",
            ffmpeg=binary,
        )

    return _PreparedTimeline(
        source_width=src_w,
        source_height=src_h,
        source_fps=src_fps,
        effective_duration_ms=eff_dur_ms,
        effective_words=eff_words,
        raw_shot_cuts_ms=raw_shots,
        effective_shot_cuts_ms=eff_shots,
        effective_jump_cuts_ms=tuple(sorted({j for j in eff_jumps if 0 < j < eff_dur_ms})),
        silence_plan=silence_plan,
        assembly_spans=assembly_spans,
        clip_wav_path=clip_wav,
        proxy_mp4_path=proxy_mp4,
        director_proxy_mp4=director_proxy,
    )


def _sanitize_kurdish_repaired_token(text: str) -> str:
    """Remove stray ASCII hyphens inside Kurdish/Arabic tokens while preserving Latin names."""
    if "-" not in text or _ARABIC_KURDISH_RE.search(text) is None:
        return text
    cleaned = " ".join(text.replace("-", " ").split())
    return cleaned if cleaned else text


def apply_word_repairs(words: Sequence[Word], repairs: Sequence[WordRepair]) -> tuple[Word, ...]:
    """Return a new word tuple with audio-grounded repairs applied (preserving CTC timing).

    Sanitizes stray ASCII hyphens inside Kurdish tokens (D-387, e.g. ``'جوابت-ئەداتەوە'`` ->
    ``'جوابت ئەداتەوە'``) while preserving 1:1 word count, exact CTC timing, and pure-Latin
    hyphenated names like ``'GPT-4'``.
    """
    out = list(words)
    seen: set[int] = set()
    for r in repairs:
        if r.word_index >= len(out):
            raise DirectorScriptError(
                f"WordRepair.word_index ({r.word_index}) out of bounds for {len(out)} words"
            )
        if r.word_index in seen:
            raise DirectorScriptError(f"Duplicate WordRepair for word_index {r.word_index}")
        seen.add(r.word_index)
        orig = out[r.word_index]
        if orig.w != r.original:
            raise DirectorScriptError(
                f"WordRepair[{r.word_index}].original ({r.original!r}) != word ({orig.w!r})"
            )
        repaired_surface = _sanitize_kurdish_repaired_token(r.repaired)
        out[r.word_index] = Word(
            w=repaired_surface, start_ms=orig.start_ms, end_ms=orig.end_ms, conf=orig.conf
        )
    return tuple(out)


def grill_rendered_v8_video(
    mp4_path: Path,
    *,
    expected_duration_ms: int | None = None,
    max_silence_s: float = 0.48,
    double_cut_window_s: float = 0.20,
    ffmpeg: Path | None = None,
) -> VideoGrillReport:
    """Forensically grill a rendered V8 MP4 for double-cuts, trailing cuts, silences & clipping.

    Checks (D-387):
    - (a) ``double_cuts``: consecutive visual cuts (``MAD > 18.0``) ``<= double_cut_window_s``
      apart — MUST be ``0``.
    - (b) ``trailing_cuts``: any visual cut in the final ``0.80 s`` — MUST be ``0``.
    - (c) ``long_silences``: audio silences ``>= max_silence_s`` at ``-35 dB`` — MUST be ``0``.
    - (d) ``audio_flat_factor``: ``astats`` ``Flat factor`` — MUST be ``0.0`` (zero clipping).
    - (e) ``expected_duration_ms`` sanity check when supplied.
    """
    import numpy as np

    if not mp4_path.is_file():
        raise V8CompileError(f"Cannot grill missing MP4: {mp4_path}")
    if max_silence_s <= 0.0 or not math.isfinite(max_silence_s):
        raise V8CompileError(f"max_silence_s must be positive finite, got {max_silence_s!r}")
    if double_cut_window_s <= 0.0 or not math.isfinite(double_cut_window_s):
        raise V8CompileError(
            f"double_cut_window_s must be positive finite, got {double_cut_window_s!r}"
        )

    binary = _resolve_ffmpeg(ffmpeg)
    duration_ms = probe_duration_ms(mp4_path, binary)
    fps = frame_rate(mp4_path, binary)
    duration_s = duration_ms / 1000.0

    # 1. Visual forensic scan: pipe downscaled grayscale frames for vectorized MAD cut detection.
    v_proc = subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(mp4_path),
            "-vf",
            f"scale={_GRILL_SCAN_W}:{_GRILL_SCAN_H}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
        check=False,
        timeout=max(60.0, duration_s * 3.0),
    )
    if v_proc.returncode != 0:
        err = v_proc.stderr.decode("utf-8", errors="replace").strip()[:400]
        raise V8CompileError(f"Video grill frame scan failed on {mp4_path}: {err}")

    frame_bytes = _GRILL_SCAN_W * _GRILL_SCAN_H
    frame_count = len(v_proc.stdout) // frame_bytes
    if frame_count < 2:
        raise V8CompileError(f"Video grill decoded < 2 frames from {mp4_path} ({frame_count})")
    frames = np.frombuffer(v_proc.stdout[: frame_count * frame_bytes], dtype=np.uint8).reshape(
        (frame_count, _GRILL_SCAN_H, _GRILL_SCAN_W)
    )
    diffs = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16))
    mads = np.mean(diffs, axis=(1, 2))
    cut_indices = np.where(mads > _GRILL_CUT_MAD_THRESHOLD)[0]
    cut_times_s = tuple(round(float(idx + 1) / fps, 3) for idx in cut_indices)

    double_cuts: list[tuple[float, float]] = []
    for prev_t, cur_t in pairwise(cut_times_s):
        if (cur_t - prev_t) <= double_cut_window_s + 1e-6:
            double_cuts.append((prev_t, cur_t))

    trailing_cuts = tuple(
        t for t in cut_times_s if (duration_s - t) <= _GRILL_TRAILING_WINDOW_S + 1e-6
    )

    # 2. Audio forensic scan: silencedetect (-35 dB, >= max_silence_s) + astats Flat factor.
    a_proc = subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-i",
            str(mp4_path),
            "-vn",
            "-af",
            f"silencedetect=noise=-35dB:d={max_silence_s:.3f},aformat=sample_fmts=s16,astats=reset=0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=max(60.0, duration_s * 2.0),
    )
    if a_proc.returncode != 0:
        raise V8CompileError(
            f"Audio grill scan failed on {mp4_path}: {a_proc.stderr.strip()[:400]}"
        )

    long_silences: list[tuple[float, float]] = []
    open_start: float | None = None
    flat_factors: list[float] = []
    for line in a_proc.stderr.splitlines():
        if (m_start := _SILENCE_START_RE.search(line)) is not None:
            open_start = float(m_start.group(1))
        if (m_end := _SILENCE_END_RE.search(line)) is not None:
            end_s = float(m_end.group(1))
            start_s = open_start if open_start is not None else max(0.0, end_s - max_silence_s)
            if (end_s - start_s) >= max_silence_s - 1e-3:
                long_silences.append((round(start_s, 3), round(end_s, 3)))
            open_start = None
        if (m_flat := _FLAT_FACTOR_RE.search(line)) is not None:
            raw_ff = m_flat.group(1).lower()
            if raw_ff not in ("nan", "inf"):
                flat_factors.append(float(raw_ff))
    if open_start is not None and (duration_s - open_start) >= max_silence_s - 1e-3:
        long_silences.append((round(open_start, 3), round(duration_s, 3)))

    audio_flat_factor = max(flat_factors) if flat_factors else 0.0

    defects: list[str] = []
    if double_cuts:
        pairs = ", ".join(f"{a:.2f}s->{b:.2f}s" for a, b in double_cuts)
        defects.append(
            f"double_cuts: {len(double_cuts)} flash(es) <= {double_cut_window_s:.2f}s apart "
            f"({pairs})"
        )
    if trailing_cuts:
        times = ", ".join(f"{t:.2f}s" for t in trailing_cuts)
        defects.append(
            f"trailing_cuts: {len(trailing_cuts)} cut(s) within final "
            f"{_GRILL_TRAILING_WINDOW_S:.2f}s ({times})"
        )
    if long_silences:
        spans = ", ".join(f"{s:.2f}s..{e:.2f}s" for s, e in long_silences)
        defects.append(
            f"long_silences: {len(long_silences)} silence(s) >= {max_silence_s:.2f}s at -35 dB "
            f"({spans})"
        )
    if audio_flat_factor > 0.0:
        defects.append(f"audio_clipping: Flat factor {audio_flat_factor:.6f} > 0.0")
    if expected_duration_ms is not None:
        tol_ms = max(500, int(round(expected_duration_ms * 0.05)))
        if abs(duration_ms - expected_duration_ms) > tol_ms:
            defects.append(
                f"duration_mismatch: rendered {duration_ms} ms vs expected "
                f"{expected_duration_ms} ms (tol {tol_ms} ms)"
            )

    return VideoGrillReport(
        mp4_path=mp4_path,
        duration_ms=duration_ms,
        fps=fps,
        frame_count=frame_count,
        cut_times_s=cut_times_s,
        double_cuts=tuple(double_cuts),
        trailing_cuts=trailing_cuts,
        long_silences=tuple(long_silences),
        audio_flat_factor=audio_flat_factor,
        passed=not defects,
        defects=tuple(defects),
    )


def apply_critique_patch(script: DirectorScript, patch: Mapping[str, Any]) -> DirectorScript:
    """Apply one surgical Watch-Before-Ship JSON patch to ``script`` (D-386)."""
    if not isinstance(patch, Mapping):
        raise DirectorScriptError(
            f"Critique patch must be a JSON object, got {type(patch).__name__}"
        )
    if not patch:
        raise DirectorScriptError("Critique patch must not be empty")
    if invalid := set(patch.keys()) - PATCHABLE_DIRECTOR_FIELDS:
        raise DirectorScriptError(f"Critique patch contains disallowed field(s): {sorted(invalid)}")
    merged = script.to_dict()
    merged.update(patch)
    return DirectorScript.from_dict(merged)


def rebase_words_to_clip(
    words: Sequence[Word], *, clip_in_ms: int, clip_out_ms: int
) -> tuple[Word, ...]:
    """Extract and rebase source-timeline words into clip-relative ``[0, duration_ms]``."""
    if clip_in_ms < 0 or clip_out_ms <= clip_in_ms:
        raise V8CompileError(f"Invalid clip span [{clip_in_ms}, {clip_out_ms})")
    dur = clip_out_ms - clip_in_ms
    rebased = [
        Word(w=w.w, start_ms=s, end_ms=e, conf=w.conf)
        for w in words
        if w.end_ms > clip_in_ms
        and w.start_ms < clip_out_ms
        and (e := min(dur, w.end_ms - clip_in_ms)) > (s := max(0, w.start_ms - clip_in_ms))
    ]
    if not rebased:
        raise V8CompileError(f"No transcript words fall within [{clip_in_ms}, {clip_out_ms})")
    return tuple(rebased)


def parse_sentence_indices(spec: str) -> tuple[int, ...]:
    """Parse ``--sentences`` spec (e.g. ``'86-87'``, ``'s86-87'``, ``'19,20,21'``, ``'7'``)."""
    text = spec.strip()
    if not text:
        raise V8CompileError("--sentences spec must not be empty")
    indices: list[int] = []
    for raw in text.split(","):
        token = raw.strip()
        m = _SENTENCE_TOKEN_RE.fullmatch(token)
        if m is None:
            raise V8CompileError(f"Invalid --sentences token {token!r}")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) is not None else start
        if end < start:
            raise V8CompileError(f"Reversed --sentences range {token!r}")
        indices.extend(range(start, end + 1))
    return tuple(dict.fromkeys(indices))


def load_transcript_words(transcript_path: Path) -> tuple[Word, ...]:
    """Load aligned ``Word`` entries from a HawEdit transcript JSON file."""
    if not transcript_path.is_file():
        raise V8CompileError(f"Transcript file not found: {transcript_path}")
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V8CompileError(f"Failed to read transcript JSON {transcript_path}: {exc}") from exc

    raw_words: Any = (
        payload["words"]
        if isinstance(payload, dict) and isinstance(payload.get("words"), list)
        else payload
        if isinstance(payload, list)
        else None
    )
    if raw_words is None:
        raise V8CompileError(f"Transcript JSON {transcript_path} must contain a 'words' list")
    words: list[Word] = []
    for idx, item in enumerate(raw_words):
        if not isinstance(item, Mapping):
            raise V8CompileError(f"Transcript word[{idx}] must be a JSON object")
        try:
            words.append(Word(item["w"], item["start_ms"], item["end_ms"], item.get("conf", 1.0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise V8CompileError(f"Invalid transcript word[{idx}]: {exc}") from exc
    if not words:
        raise V8CompileError(f"Transcript {transcript_path} contains zero words")
    return tuple(words)


def select_clip_span_from_sentences(
    words: Sequence[Word],
    sentence_indices: Sequence[int],
    *,
    pad_before_ms: int = 120,
    pad_after_ms: int = 150,
) -> tuple[int, int, tuple[Word, ...]]:
    """Resolve ``sentence_indices`` via ``segment_sentences`` into ``(in_ms, out_ms, words)``."""
    if not sentence_indices or pad_before_ms < 0 or pad_after_ms < 0:
        raise V8CompileError("sentence_indices must be non-empty and padding non-negative")
    sentences = segment_sentences(words)
    for idx in sentence_indices:
        if not (0 <= idx < len(sentences)):
            raise V8CompileError(f"Sentence index {idx} out of range ({len(sentences)} sentences)")
    ordered = sorted(sentence_indices)
    clip_in = max(0, sentences[ordered[0]].start_ms - pad_before_ms)
    clip_out = sentences[ordered[-1]].end_ms + pad_after_ms
    return clip_in, clip_out, rebase_words_to_clip(words, clip_in_ms=clip_in, clip_out_ms=clip_out)


def _enforce_style_camera_restraint(
    moves: Sequence[CameraMove],
    style: ClientStylePreset,
) -> tuple[CameraMove, ...]:
    """Enforce preset camera policy (D-388): broadcast_news locks 1.00x; cap scale to preset."""
    if not moves or not style.allow_camera_moves:
        return ()
    max_s = min(CAMERA_MAX_SCALE, float(style.max_camera_scale))
    out: list[CameraMove] = []
    for move in moves:
        s0 = max(CAMERA_MIN_SCALE, min(max_s, float(move.scale_start)))
        s1 = max(CAMERA_MIN_SCALE, min(max_s, float(move.scale_end)))
        if s0 <= CAMERA_MIN_SCALE + 1e-4 and s1 <= CAMERA_MIN_SCALE + 1e-4:
            continue
        out.append(
            CameraMove(
                start_ms=move.start_ms,
                end_ms=move.end_ms,
                kind=move.kind,
                scale_start=round(s0, 4),
                scale_end=round(s1, 4),
                reason=move.reason,
            )
        )
    return tuple(out)


def compile_v8_clip(
    *,
    source_mp4: Path,
    clip_id: str,
    clip_in_ms: int,
    clip_out_ms: int,
    words: Sequence[Word],
    out_dir: Path,
    config: V8CompileConfig | None = None,
    director: V8DirectorProtocol | None = None,
    subtitle_renderer: V8SubtitleRendererProtocol | None = None,
    speaker_tracker: V8ActiveSpeakerTrackerProtocol | None = None,
    clip_renderer: V8ClipRendererProtocol | None = None,
    shot_cuts_ms: Sequence[int] = (),
    jump_cuts_ms: Sequence[int] = (),
    source_sentences: Sequence[Sentence] | None = None,
    video_griller: Callable[[Path], VideoGrillReport] | None = None,
    semantic_assembly_spans: Sequence[AssemblySpan] | None = None,
    semantic_words: Sequence[Word] | None = None,
    semantic_cut_times_ms: Sequence[tuple[int, int]] = (),
    semantic_visual_cues: Sequence[VisualCue] = (),
    semantic_word_idx_to_ms: Mapping[int, int] | None = None,
    semantic_hook_title_ckb: str | None = None,
) -> V8CompileResult:
    """Compile one V8/V10.2 clip: Perceive -> Direct -> Validate -> Compile -> Critique."""
    cfg = config if config is not None else V8CompileConfig()
    if not clip_id.strip() or not source_mp4.is_file():
        raise V8CompileError(f"Invalid clip_id or missing source video: {source_mp4}")
    if clip_in_ms < 0 or clip_out_ms <= clip_in_ms:
        raise V8CompileError(f"Invalid clip span [{clip_in_ms}, {clip_out_ms})")
    raw_duration_ms = clip_out_ms - clip_in_ms
    clip_words = tuple(words)
    if not clip_words or (
        not semantic_assembly_spans and any(w.end_ms > raw_duration_ms for w in clip_words)
    ):
        raise V8CompileError(f"words must be non-empty and within [0, {raw_duration_ms}] ms")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_mp4 = out_dir / f"{clip_id}.v8.mp4"
    script_path = out_dir / f"{clip_id}.director.json"

    use_real_media = clip_renderer is None
    with tempfile.TemporaryDirectory(prefix=f"hawedit-v8-{clip_id[:16]}-") as work_str:
        work_dir = Path(work_str)
        prepared: _PreparedTimeline | None = None
        if use_real_media:
            sem_jumps = tuple(
                sorted(
                    {
                        *jump_cuts_ms,
                        *(at_ms for at_ms, rem_ms in semantic_cut_times_ms if rem_ms >= 250),
                    }
                )
            )
            prepared = _prepare_real_timeline(
                source_mp4=source_mp4,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                clip_words=clip_words,
                work_dir=work_dir,
                config=cfg,
                explicit_shot_cuts_ms=shot_cuts_ms,
                explicit_jump_cuts_ms=sem_jumps,
                source_sentences=source_sentences,
                semantic_assembly_spans=semantic_assembly_spans,
                semantic_words=semantic_words,
            )

        effective_duration_ms = (
            prepared.effective_duration_ms if prepared is not None else raw_duration_ms
        )
        effective_words = prepared.effective_words if prepared is not None else clip_words
        effective_shot_cuts = (
            prepared.effective_shot_cuts_ms if prepared is not None else tuple(shot_cuts_ms)
        )
        effective_jump_cuts = (
            prepared.effective_jump_cuts_ms if prepared is not None else tuple(jump_cuts_ms)
        )
        raw_shot_cuts = prepared.raw_shot_cuts_ms if prepared is not None else tuple(shot_cuts_ms)
        effective_fps = (
            prepared.source_fps
            if (prepared is not None and cfg.fps == 25.0 and abs(prepared.source_fps - 25.0) > 0.1)
            else cfg.fps
        )
        active_cfg = replace(cfg, fps=effective_fps) if effective_fps != cfg.fps else cfg
        resolved_style = get_client_style_preset(
            active_cfg.style_preset, accent_hex_override=active_cfg.brand_accent_hex
        )
        speaker_bio: tuple[str, str | None] | None = (
            (active_cfg.speaker_name_ckb, active_cfg.speaker_role_ckb)
            if active_cfg.speaker_name_ckb
            else None
        )
        end_card: tuple[str, str | None, str | None] | None = (
            (
                active_cfg.end_card_title_ckb,
                active_cfg.end_card_subtitle_ckb,
                active_cfg.end_card_handle,
            )
            if active_cfg.end_card_title_ckb
            else None
        )

        # Wire real default collaborators when caller didn't inject test doubles.
        if director is not None:
            active_dir: V8DirectorProtocol = director
        else:
            try:
                active_dir = create_director_brain(
                    active_cfg.director_backend,
                    model_id=active_cfg.director_model,
                    base_url=active_cfg.omni_url,
                    modality=active_cfg.local_modality,
                    audio_wav=prepared.clip_wav_path if prepared is not None else None,
                    ffmpeg=active_cfg.ffmpeg,
                )
            except (DirectorUnavailable, ValueError) as exc:
                raise V8CompileError(f"Failed to initialize V8 director: {exc}") from exc

        active_sub: V8SubtitleRendererProtocol = (
            subtitle_renderer
            if subtitle_renderer is not None
            else DefaultV8SubtitleRenderer(
                fonts_dir=active_cfg.fonts_dir,
                fps=active_cfg.fps,
                width=active_cfg.width,
                height=active_cfg.height,
                ffmpeg=active_cfg.ffmpeg,
                style_preset=resolved_style,
                speaker_bio=speaker_bio,
                end_card=end_card,
            )
        )

        active_tracker: V8ActiveSpeakerTrackerProtocol | None = (
            speaker_tracker
            if speaker_tracker is not None
            else (
                DefaultV8ActiveSpeakerTracker(
                    onnx_model_path=active_cfg.asd_onnx_path,
                    ffmpeg=active_cfg.ffmpeg,
                    precomputed_proxy=prepared.proxy_mp4_path if prepared is not None else None,
                    precomputed_wav=prepared.clip_wav_path if prepared is not None else None,
                    source_dims=(
                        (prepared.source_width, prepared.source_height)
                        if prepared is not None
                        else None
                    ),
                )
                if active_cfg.enable_asd and use_real_media
                else None
            )
        )

        active_rnd: V8ClipRendererProtocol = (
            clip_renderer
            if clip_renderer is not None
            else DefaultV8ClipRenderer(
                source_width=prepared.source_width if prepared is not None else 1920,
                source_height=prepared.source_height if prepared is not None else 1080,
                silence_plan=prepared.silence_plan if prepared is not None else None,
                assembly_spans=prepared.assembly_spans if prepared is not None else None,
            )
        )

        track_in_ms = 0 if semantic_assembly_spans else clip_in_ms
        track_out_ms = effective_duration_ms if semantic_assembly_spans else clip_out_ms
        raw_crops: tuple[LockedCropWindow, ...] = (
            tuple(
                active_tracker.plan_locked_crops(
                    source_mp4=source_mp4,
                    clip_in_ms=track_in_ms,
                    clip_out_ms=track_out_ms,
                    shot_cuts_ms=raw_shot_cuts,
                )
            )
            if active_cfg.enable_asd and active_tracker is not None
            else ()
        )
        if prepared is not None and prepared.assembly_spans is not None:
            remapped_crops = (
                raw_crops
                if semantic_assembly_spans
                else _remap_crops_to_assembly_spans(
                    raw_crops, prepared.assembly_spans, clip_in_ms=clip_in_ms
                )
            )
            cfr_cuts = (
                prepared.effective_shot_cuts_ms
                if semantic_assembly_spans
                else detect_exact_assembled_cuts_ms(
                    source_mp4,
                    [(sp.source_in_ms, sp.source_out_ms) for sp in prepared.assembly_spans],
                    fps=effective_fps,
                    ffmpeg=active_cfg.ffmpeg,
                )
            )
            snapped_shot_crops = snap_locked_crops_to_cuts(
                tuple(
                    LockedShotCrop(
                        start_ms=c.start_ms,
                        end_ms=c.end_ms,
                        focus_x_px=c.focus_x_px,
                        face_center_y_px=c.face_center_y_px,
                        face_height_px=c.face_height_px,
                        active_track_id=c.active_track_id,
                    )
                    for c in remapped_crops
                ),
                cfr_cuts,
            )
            locked_crops = tuple(
                LockedCropWindow(
                    start_ms=c.start_ms,
                    end_ms=c.end_ms,
                    focus_x_px=c.focus_x_px,
                    face_center_y_px=c.face_center_y_px,
                    face_height_px=c.face_height_px,
                    active_track_id=c.active_track_id,
                )
                for c in snapped_shot_crops
            )
            effective_shot_cuts = tuple(sorted(set(effective_shot_cuts) | set(cfr_cuts)))
        else:
            locked_crops = raw_crops

        # V10.2/V10.3 Visual-Aware Scene Profiling, §7 VideoChat3/TimeLens2 Grounding & B-Roll.
        shot_profiles: tuple[ShotVisualProfile, ...] = ()
        visual_groundings = (
            run_local_video_awareness(
                prepared.proxy_mp4_path,
                effective_duration_ms,
                device="cuda:1",
                strict=False,
            )
            if (use_real_media and prepared is not None and active_cfg.enable_local_vlm)
            else None
        )
        if visual_groundings is not None and visual_groundings.models_used:
            write_text_atomic(
                out_dir / f"{clip_id}.visual.json",
                json.dumps(visual_groundings.to_dict(), ensure_ascii=False, indent=2) + "\n",
            )
        if (
            prepared is not None
            and isinstance(active_tracker, DefaultV8ActiveSpeakerTracker)
            and locked_crops
        ):
            p_w, p_h = active_tracker.last_proxy_dims or (
                prepared.source_width,
                prepared.source_height,
            )
            shot_profiles = apply_visual_groundings_to_profiles(
                analyze_shot_visual_profiles(
                    active_tracker.last_detections,
                    active_tracker.last_scores,
                    locked_crops,
                    source_width=prepared.source_width,
                    source_height=prepared.source_height,
                    proxy_width=p_w,
                    proxy_height=p_h,
                    proxy_mp4=prepared.proxy_mp4_path,
                ),
                visual_groundings,
            )

        resolved_broll: tuple[BRollItem, ...] = ()
        cue_stat_interrupts: tuple[VisualInterrupt, ...] = ()
        if (
            use_real_media
            and active_cfg.enable_broll
            and semantic_visual_cues
            and semantic_word_idx_to_ms
        ):
            cover_actions = protect_visual_gestures_in_cuts(
                choreograph_cut_covers(
                    semantic_cut_times_ms,
                    shot_profiles,
                    semantic_visual_cues,
                    semantic_word_idx_to_ms,
                    duration_ms=effective_duration_ms,
                    existing_shot_cuts_ms=effective_shot_cuts,
                ),
                visual_groundings,
            )
            # Align B-roll cues chosen as cut-covers & downgrade cues overlapping TimeLens2 peaks.
            aligned_map = dict(semantic_word_idx_to_ms)
            protected_cues = list(semantic_visual_cues)
            for act in cover_actions:
                if act.cue_index is not None and act.cue_index < len(protected_cues):
                    orig_cue = protected_cues[act.cue_index]
                    aligned_map[orig_cue.anchor_word_idx] = act.start_ms
                    if act.kind == "broll_pip" and orig_cue.layout == "broll_fullscreen":
                        protected_cues[act.cue_index] = replace(orig_cue, layout="broll_pip")
            resolved_broll, cue_stat_interrupts = resolve_visual_cues_to_broll(
                protected_cues,
                aligned_map,
                duration_ms=effective_duration_ms,
                cache_dir=active_cfg.broll_cache_dir or DEFAULT_BROLL_CACHE_DIR,
                broll_dir=active_cfg.broll_dir,
                enable_web_stock=active_cfg.allow_web_stock,
                enable_ai_images=(active_cfg.director_backend == "gemini"),
                verify_with_gemini=(active_cfg.director_backend == "gemini"),
                verify_with_local_vision=(active_cfg.director_backend == "local-omni"),
                local_vision_url=active_cfg.omni_url,
                local_vision_model=active_cfg.director_model,
                ffmpeg=active_cfg.ffmpeg,
            )
            # Never overlay floating top_pip (y=150) across a closeup speaker's face/eyes.
            if resolved_broll and shot_profiles:
                resolved_broll = tuple(
                    bi
                    for bi in resolved_broll
                    if bi.position != "top_pip"
                    or not any(
                        p.shot_scale == "closeup"
                        and p.start_ms <= (bi.start_ms + bi.duration_ms // 2) < p.end_ms
                        for p in shot_profiles
                    )
                )

        split_windows: tuple[
            tuple[int, int, tuple[int, int, int, int], tuple[int, int, int, int]], ...
        ] = (
            tuple(
                (p.start_ms, p.end_ms, p.split_crops[0], p.split_crops[1])
                for p in shot_profiles
                if p.dual_active_banter and p.split_crops is not None
            )
            if active_cfg.enable_banter_split and shot_profiles
            else ()
        )
        if isinstance(active_rnd, DefaultV8ClipRenderer):
            active_rnd.set_visual_extras(
                b_roll=resolved_broll,
                assembly_crossfade_ms=24 if semantic_assembly_spans else 0,
                split_screen_windows=split_windows,
            )
        if isinstance(active_sub, DefaultV8SubtitleRenderer) and prepared is not None:
            split_timings = [(s, e) for s, e, _, _ in split_windows]
            active_sub.protect_outro_faces(
                locked_crops,
                prepared.source_width,
                prepared.source_height,
                effective_duration_ms,
                split_timings,
            )
            active_sub.set_split_screen_windows(split_timings)
            if any(s < 2_400 and e > 0 for s, e, _, _ in split_windows):
                active_sub.set_hook_y_top_px(76.0)
            elif (
                locked_crops
                and locked_crops[0].face_height_px > 0
                and (locked_crops[0].face_height_px / float(prepared.source_height)) >= 0.22
            ):
                active_sub.set_hook_y_top_px(1030.0)
            else:
                active_sub.set_hook_y_top_px(140.0)

        dir_source = (
            prepared.director_proxy_mp4
            if (prepared is not None and prepared.director_proxy_mp4 is not None)
            else source_mp4
        )
        dir_in_ms = (
            0
            if (
                prepared is not None
                and (
                    prepared.director_proxy_mp4 is not None
                    or prepared.assembly_spans is not None
                    or prepared.silence_plan is not None
                )
            )
            else clip_in_ms
        )
        dir_out_ms = dir_in_ms + effective_duration_ms

        director_visual_context = format_visual_groundings_for_director(
            visual_groundings, shot_profiles
        )
        dir_kwargs: dict[str, Any] = {
            "source_mp4": dir_source,
            "clip_in_ms": dir_in_ms,
            "clip_out_ms": dir_out_ms,
            "clip_id": clip_id,
            "words": effective_words,
            "shot_cuts_ms": effective_shot_cuts,
            "jump_cuts_ms": effective_jump_cuts,
        }
        if director_visual_context:
            try:
                sig = inspect.signature(active_dir.direct_clip)
                if "visual_context" in sig.parameters or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                ):
                    dir_kwargs["visual_context"] = director_visual_context
            except (TypeError, ValueError):
                pass

        try:
            script = active_dir.direct_clip(**dir_kwargs)
        except DirectorUnavailable as exc:
            raise V8CompileError(
                f"V8 director failed ({active_cfg.director_backend}): {exc}"
            ) from exc

        # Prefer Story Architect's full-episode Kurdish hook title when supplied in Kurdish script.
        if (
            semantic_hook_title_ckb
            and semantic_hook_title_ckb.strip()
            and _ARABIC_KURDISH_RE.search(semantic_hook_title_ckb) is not None
        ):
            script = DirectorScript(
                clip_id=script.clip_id,
                hook_title_ckb=semantic_hook_title_ckb.strip(),
                word_repairs=script.word_repairs,
                cuts=script.cuts,
                camera_moves=script.camera_moves,
                caption_beats=script.caption_beats,
                visual_interrupts=script.visual_interrupts,
                cold_open_span_ms=script.cold_open_span_ms,
            )
        auto_stat_interrupts: tuple[VisualInterrupt, ...] = ()
        if use_real_media and director is None and effective_words:
            raw_auto_stats = extract_kurdish_stat_interrupts(
                effective_words,
                duration_ms=effective_duration_ms,
                existing_interrupts=(*script.visual_interrupts, *cue_stat_interrupts),
                occupied_broll_ms=tuple(
                    (bi.start_ms, bi.start_ms + bi.duration_ms) for bi in resolved_broll
                ),
                max_cards=max(0, 2 - len(script.visual_interrupts) - len(cue_stat_interrupts)),
            )
            routed_stats: list[VisualInterrupt] = []
            for svi in raw_auto_stats:
                mid = (svi.start_ms + svi.end_ms) // 2
                prof = next((p for p in shot_profiles if p.start_ms <= mid < p.end_ms), None)
                if prof is not None and prof.shot_scale == "closeup":
                    if prof.safe_overlay_zone == "chest":
                        routed_stats.append(
                            VisualInterrupt(
                                start_ms=svi.start_ms,
                                end_ms=svi.end_ms,
                                text_ckb=svi.text_ckb,
                                position="chest",
                            )
                        )
                    # Skip top Stat Card on closeup shots with active hand gestures (face-safe).
                else:
                    routed_stats.append(svi)
            auto_stat_interrupts = tuple(routed_stats)

        all_extra_stats = (*cue_stat_interrupts, *auto_stat_interrupts)
        if all_extra_stats:
            merged_vis = list(script.visual_interrupts)
            for cvi in all_extra_stats:
                if len(merged_vis) >= 3:
                    break
                if all(abs(cvi.start_ms - ex.start_ms) >= 6_000 for ex in merged_vis):
                    merged_vis.append(cvi)
            merged_vis.sort(key=lambda v: v.start_ms)
            if tuple(merged_vis) != script.visual_interrupts:
                script = DirectorScript(
                    clip_id=script.clip_id,
                    hook_title_ckb=script.hook_title_ckb,
                    word_repairs=script.word_repairs,
                    cuts=script.cuts,
                    camera_moves=script.camera_moves,
                    caption_beats=script.caption_beats,
                    visual_interrupts=tuple(merged_vis),
                    cold_open_span_ms=script.cold_open_span_ms,
                )

        # Augment multimodal Director repairs with deterministic Sorani ASR orthography fixes
        # on untouched word indices (Director's audio-grounded repairs always win on overlap).
        if use_real_media and director is None and effective_words:
            repaired_sents, _ = repair_kurdish_asr_orthography(
                [Sentence(words=effective_words, complete=True)]
            )
            repaired_ortho = repaired_sents[0].words
            existing_idxs = {r.word_index for r in script.word_repairs}
            extra_repairs = [
                WordRepair(
                    word_index=idx,
                    original=orig.w,
                    repaired=rep.w,
                    reason="deterministic Sorani ASR orthography repair (D-381)",
                )
                for idx, (orig, rep) in enumerate(zip(effective_words, repaired_ortho, strict=True))
                if orig.w != rep.w and idx not in existing_idxs
            ]
            if extra_repairs:
                merged_repairs = tuple(
                    sorted((*script.word_repairs, *extra_repairs), key=lambda r: r.word_index)
                )
                script = DirectorScript(
                    clip_id=script.clip_id,
                    hook_title_ckb=script.hook_title_ckb,
                    word_repairs=merged_repairs,
                    cuts=script.cuts,
                    camera_moves=script.camera_moves,
                    caption_beats=script.caption_beats,
                    visual_interrupts=script.visual_interrupts,
                    cold_open_span_ms=script.cold_open_span_ms,
                )

        def _run(
            cur: DirectorScript,
        ) -> tuple[DirectorScript, tuple[Word, ...], str, tuple[int, ...], SubtitleArtifact, Path]:
            validate_director_script(cur, duration_ms=effective_duration_ms, words=effective_words)
            effective_script = cur
            styled_moves = _enforce_style_camera_restraint(cur.camera_moves, resolved_style)
            if styled_moves and (effective_shot_cuts or effective_jump_cuts):
                styled_moves = snap_camera_moves_to_cuts(
                    styled_moves,
                    effective_shot_cuts,
                    effective_jump_cuts,
                    effective_duration_ms,
                )
            if styled_moves != cur.camera_moves:
                effective_script = DirectorScript(
                    clip_id=cur.clip_id,
                    hook_title_ckb=cur.hook_title_ckb,
                    word_repairs=cur.word_repairs,
                    cuts=cur.cuts,
                    camera_moves=styled_moves,
                    caption_beats=cur.caption_beats,
                    visual_interrupts=cur.visual_interrupts,
                    cold_open_span_ms=cur.cold_open_span_ms,
                )
            if prepared is not None and locked_crops and effective_script.visual_interrupts:
                src_h_f = float(prepared.source_height)
                placed_vis = []
                changed_vis = False
                for vi in effective_script.visual_interrupts:
                    new_pos = vi.position
                    if new_pos == "top":
                        cov = next(
                            (c for c in locked_crops if c.start_ms <= vi.start_ms < c.end_ms),
                            locked_crops[0],
                        )
                        if cov.face_height_px > 0 and (cov.face_height_px / src_h_f) >= 0.22:
                            new_pos = "chest"
                            changed_vis = True
                    placed_vis.append(
                        VisualInterrupt(
                            start_ms=vi.start_ms,
                            end_ms=vi.end_ms,
                            text_ckb=vi.text_ckb,
                            position=new_pos,
                        )
                    )
                if changed_vis:
                    effective_script = DirectorScript(
                        clip_id=effective_script.clip_id,
                        hook_title_ckb=effective_script.hook_title_ckb,
                        word_repairs=effective_script.word_repairs,
                        cuts=effective_script.cuts,
                        camera_moves=effective_script.camera_moves,
                        caption_beats=effective_script.caption_beats,
                        visual_interrupts=tuple(placed_vis),
                        cold_open_span_ms=effective_script.cold_open_span_ms,
                    )
            repaired = apply_word_repairs(effective_words, effective_script.word_repairs)
            if use_real_media and director is None:
                hook_words = tuple(
                    word
                    for word in repaired
                    if not any(
                        cut.start_ms <= word.start_ms < cut.end_ms for cut in effective_script.cuts
                    )
                )
                grounded_hook = _source_quote_hook(
                    effective_script.hook_title_ckb, clip_words, retained_words=hook_words
                )
                if not grounded_hook:
                    grounded_hook = _source_quote_hook(effective_script.hook_title_ckb, hook_words)
                if not grounded_hook:
                    raise ReelQualityError(f"No complete grounded Sorani headline for {clip_id}")
                effective_script = replace(effective_script, hook_title_ckb=grounded_hook)
            cam_flt, cam_jumps = compile_restrained_camera_filter(
                effective_duration_ms,
                effective_script.camera_moves,
                fps=active_cfg.fps,
                width=active_cfg.width,
                height=active_cfg.height,
                anchor_y=active_cfg.anchor_y,
                cinema_grade=active_cfg.cinema_grade,
                shot_cuts_ms=effective_shot_cuts,
                jump_cuts_ms=effective_jump_cuts,
            )
            sub_art = active_sub.render_subtitles(
                words=repaired,
                script=effective_script,
                clip_duration_ms=effective_duration_ms,
                out_dir=out_dir,
                engine=active_cfg.sub_engine,
            )
            rendered = active_rnd.render_clip_media(
                source_mp4=source_mp4,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                script=effective_script,
                words=repaired,
                camera_filter=cam_flt,
                camera_jump_cuts_ms=cam_jumps,
                subtitles=sub_art,
                locked_crops=locked_crops,
                output_mp4=output_mp4,
                config=active_cfg,
            )
            write_text_atomic(script_path, effective_script.to_json(indent=2) + "\n")
            return effective_script, repaired, cam_flt, cam_jumps, sub_art, rendered

        grill_path = out_dir / f"{clip_id}.grill.json"

        def _grill(cur_mp4: Path) -> VideoGrillReport | None:
            if not active_cfg.enable_grill:
                return None
            if video_griller is not None:
                report = video_griller(cur_mp4)
            elif use_real_media:
                max_sil = (
                    max(0.48, active_cfg.silence_threshold_ms / 1000.0)
                    if active_cfg.silence_threshold_ms > 0
                    else 0.48
                )
                report = grill_rendered_v8_video(
                    cur_mp4,
                    expected_duration_ms=effective_duration_ms,
                    max_silence_s=max_sil,
                    ffmpeg=active_cfg.ffmpeg,
                )
            else:
                return None
            write_text_atomic(
                grill_path, json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
            )
            return report

        def _enforce_grill(
            cur_script: DirectorScript,
            cur_repaired: tuple[Word, ...],
            cur_cam_flt: str,
            cur_cam_jumps: tuple[int, ...],
            cur_subs: SubtitleArtifact,
            cur_mp4: Path,
        ) -> tuple[
            DirectorScript,
            tuple[Word, ...],
            str,
            tuple[int, ...],
            SubtitleArtifact,
            Path,
            VideoGrillReport | None,
        ]:
            report = _grill(cur_mp4)
            if report is not None and not report.passed:
                # Auto-repair camera-induced double/trailing cuts by locking to 1.00x tripod.
                if cur_script.camera_moves and (report.double_cuts or report.trailing_cuts):
                    repaired_script = apply_critique_patch(cur_script, {"camera_moves": []})
                    if use_real_media and cur_mp4.is_file():
                        cur_mp4.unlink()
                    (
                        cur_script,
                        cur_repaired,
                        cur_cam_flt,
                        cur_cam_jumps,
                        cur_subs,
                        cur_mp4,
                    ) = _run(repaired_script)
                    report = _grill(cur_mp4)
                if report is not None and not report.passed:
                    defect_msg = "; ".join(report.defects) if report.defects else "unspecified"
                    raise ReelQualityError(
                        f"Forensic video grill failed for {clip_id}: {defect_msg}"
                    )
            return cur_script, cur_repaired, cur_cam_flt, cur_cam_jumps, cur_subs, cur_mp4, report

        script, repaired_words, camera_filter, camera_jumps, subtitles, rendered_mp4 = _run(script)
        (
            script,
            repaired_words,
            camera_filter,
            camera_jumps,
            subtitles,
            rendered_mp4,
            grill_report,
        ) = _enforce_grill(
            script, repaired_words, camera_filter, camera_jumps, subtitles, rendered_mp4
        )

        verdict: CritiqueVerdict | None = None
        revisions = 0
        if active_cfg.enable_critique:

            def _critique(
                cur_mp4: Path, cur_script: DirectorScript, cur_words: Sequence[Word]
            ) -> CritiqueVerdict:
                try:
                    if director is None and use_real_media:
                        return critique_rendered_clip(
                            active_dir,  # type: ignore[arg-type]
                            rendered_mp4=cur_mp4,
                            script=cur_script,
                            words=cur_words,
                            ffmpeg=active_cfg.ffmpeg,
                        )
                    return active_dir.critique_clip(
                        rendered_mp4=cur_mp4, script=cur_script, words=cur_words
                    )
                except DirectorUnavailable as exc:
                    raise V8CompileError(f"Watch-Before-Ship critique failed: {exc}") from exc

            verdict = _critique(rendered_mp4, script, repaired_words)
            if not verdict.approved:
                if revisions < active_cfg.max_critique_revisions and verdict.patch is not None:
                    script = apply_critique_patch(script, verdict.patch)
                    if use_real_media and rendered_mp4.is_file():
                        rendered_mp4.unlink()
                    (
                        script,
                        repaired_words,
                        camera_filter,
                        camera_jumps,
                        subtitles,
                        rendered_mp4,
                    ) = _run(script)
                    (
                        script,
                        repaired_words,
                        camera_filter,
                        camera_jumps,
                        subtitles,
                        rendered_mp4,
                        grill_report,
                    ) = _enforce_grill(
                        script,
                        repaired_words,
                        camera_filter,
                        camera_jumps,
                        subtitles,
                        rendered_mp4,
                    )
                    revisions += 1
                    verdict = _critique(rendered_mp4, script, repaired_words)
                if not verdict.approved:
                    issues = "; ".join(verdict.issues) if verdict.issues else "unspecified"
                    raise V8CompileError(
                        f"Watch-Before-Ship critique rejected {clip_id} after {revisions} "
                        f"revision(s) (score={verdict.score:.2f}): {issues}"
                    )

        if (
            use_real_media
            and not active_cfg.keep_overlay
            and subtitles.overlay_path is not None
            and subtitles.overlay_path.is_file()
            and rendered_mp4.is_file()
            and rendered_mp4.stat().st_size > 0
            and (grill_report is None or grill_report.passed)
        ):
            subtitles.overlay_path.unlink()

        if prepared is not None and prepared.assembly_spans is not None:
            retained_intervals_ms: tuple[tuple[int, int], ...] = tuple(
                (sp.source_in_ms, sp.source_out_ms) for sp in prepared.assembly_spans
            )
        elif (
            prepared is not None
            and prepared.silence_plan is not None
            and prepared.silence_plan.retained_intervals_ms
        ):
            retained_intervals_ms = tuple(
                (clip_in_ms + s, clip_in_ms + e)
                for s, e in prepared.silence_plan.retained_intervals_ms
            )
        else:
            retained_intervals_ms = ((clip_in_ms, clip_out_ms),)

        return V8CompileResult(
            clip_id=clip_id,
            output_mp4=rendered_mp4,
            script=script,
            script_path=script_path,
            repaired_words=repaired_words,
            camera_filter=camera_filter,
            camera_jump_cuts_ms=camera_jumps,
            subtitles=subtitles,
            locked_crops=locked_crops,
            critique=verdict,
            critique_revisions=revisions,
            director_backend=active_cfg.director_backend,
            sub_engine=active_cfg.sub_engine,
            grill_report=grill_report,
            retained_intervals_ms=retained_intervals_ms,
        )
