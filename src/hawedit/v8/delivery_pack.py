"""HawEdit V9 complete client delivery pack & HTML review gallery (D-389, D-390).

Produces the full agency/client deliverable bundle for every compiled V8 reel:
- ``<clip_id>.v8.srt`` — post-repair, post-trim Kurdish SRT (via ``hawedit.delivery.build_srt``)
- ``<clip_id>.v8.edl``      — CMX 3600 conform EDL (via ``hawedit.delivery.build_edl``)
- ``<clip_id>.v8.otio``     — OpenTimelineIO JSON for Premiere Pro / DaVinci Resolve
- ``<clip_id>.v8.cover.png`` — crisp 1080×1920 cover thumbnail at ``t = 0.6 s``
- ``<clip_id>.director.json`` & ``<clip_id>.grill.json`` (verified present & non-empty)
- Cleans up bulky temporary ``<clip_id>.v8.overlay.mov`` after verifying ``.v8.mp4`` passed grill
- ``client-review.html``    — self-contained, zero-CDN, RTL Kurdish dark-studio review gallery
"""

from __future__ import annotations

import html
import json
import math
import os
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from hawedit.atomic_fs import write_text_atomic
from hawedit.captions import find_ffmpeg
from hawedit.delivery import DeliveryError, build_edl, build_srt, parse_srt_times
from hawedit.ingest import probe_duration_ms
from hawedit.sentences import Sentence, UndeliverableOrder
from hawedit.timeline import _marker, _rational_time, _time_range, serialize_otio
from hawedit.transcripts import Word
from hawedit.v8.blind_review import write_blind_review
from hawedit.v8.compiler import LockedCropWindow, V8CompileResult, VideoGrillReport
from hawedit.v8.dubbing import dub_reel
from hawedit.v8.localization import translate_sidecar
from hawedit.v8.media_settings import media_setting
from hawedit.v8.tiktok_subs import chunk_viral_kurdish_words

__all__ = [
    "ClientDeliveryPack",
    "DeliveryPackError",
    "build_v8_otio_timeline",
    "extract_v8_cover_png",
    "verify_client_pack_complete",
    "write_client_delivery_pack",
    "write_client_review_html",
]


class DeliveryPackError(RuntimeError):
    """Raised on any strict fail-stop violation while building or verifying a client pack."""


@dataclass(frozen=True, slots=True)
class ClientDeliveryPack:
    """Immutable manifest of all client-ready deliverables for one compiled V8 reel."""

    clip_id: str
    mp4_path: Path
    srt_path: Path
    edl_path: Path
    otio_path: Path
    cover_png_path: Path
    director_json_path: Path
    grill_json_path: Path | None
    ass_path: Path | None = None
    overlay_cleaned: bool = False
    overlay_bytes_reclaimed: int = 0
    duration_ms: int = 0
    face_share: float = 0.0
    hook_title_ckb: str = ""
    grill_passed: bool | None = None
    grill_summary: str = ""
    double_cuts_count: int = 0
    trailing_cuts_count: int = 0
    long_silences_count: int = 0
    audio_flat_factor: float = 0.0
    loudness_lufs: float | None = None
    social_zip_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "mp4_path": str(self.mp4_path),
            "srt_path": str(self.srt_path),
            "social_zip_path": str(self.social_zip_path) if self.social_zip_path else None,
            "edl_path": str(self.edl_path),
            "otio_path": str(self.otio_path),
            "cover_png_path": str(self.cover_png_path),
            "director_json_path": str(self.director_json_path),
            "grill_json_path": str(self.grill_json_path) if self.grill_json_path else None,
            "ass_path": str(self.ass_path) if self.ass_path else None,
            "overlay_cleaned": self.overlay_cleaned,
            "overlay_bytes_reclaimed": self.overlay_bytes_reclaimed,
            "duration_ms": self.duration_ms,
            "duration_s": round(self.duration_ms / 1000.0, 3),
            "face_share": round(self.face_share, 4),
            "hook_title_ckb": self.hook_title_ckb,
            "grill_passed": self.grill_passed,
            "grill_summary": self.grill_summary,
            "double_cuts_count": self.double_cuts_count,
            "trailing_cuts_count": self.trailing_cuts_count,
            "long_silences_count": self.long_silences_count,
            "audio_flat_factor": self.audio_flat_factor,
            "loudness_lufs": self.loudness_lufs,
        }


def _ms_to_frames(ms: int, fps: float) -> int:
    return round(ms * fps / 1000.0)


def _compute_face_share(crops: Sequence[LockedCropWindow], duration_ms: int) -> float:
    if not crops or duration_ms <= 0:
        return 0.0
    covered = sum(max(0, c.end_ms - c.start_ms) for c in crops if c.face_height_px > 0)
    return round(min(1.0, covered / float(duration_ms)), 4)


def _format_grill_summary(report: VideoGrillReport | None) -> str:
    if report is None:
        return "GRILL NOT RUN"
    if report.passed:
        return (
            f"PASSED (0 double-cuts, 0 trailing, 0 silences, "
            f"flat={report.audio_flat_factor:.3f}, {report.duration_ms / 1000.0:.2f}s)"
        )
    detail = "; ".join(report.defects) if report.defects else "unspecified defects"
    return f"FAILED: {detail}"


def _build_speaker_spans(crops: Sequence[LockedCropWindow]) -> tuple[tuple[int, int, str], ...]:
    spans: list[tuple[int, int, str]] = []
    for c in crops:
        if c.active_track_id is None:
            continue
        label = f"speaker_{c.active_track_id}"
        if spans and spans[-1][2] == label and abs(c.start_ms - spans[-1][1]) <= 120:
            prev_s, _prev_e, _ = spans[-1]
            spans[-1] = (prev_s, max(spans[-1][1], c.end_ms), label)
        else:
            spans.append((c.start_ms, c.end_ms, label))
    return tuple(spans)


def build_v8_otio_timeline(
    result: V8CompileResult,
    *,
    source_mp4: Path,
    clip_in_ms: int,
    clip_out_ms: int,
    fps: float,
    media_id: str,
    hook_title_ckb: str,
    duration_ms: int,
    retained_intervals_ms: Sequence[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Build a schema-valid OpenTimelineIO ``Timeline.1`` dict for Premiere / Resolve."""
    if clip_in_ms < 0 or clip_out_ms <= clip_in_ms:
        raise DeliveryPackError(f"Invalid source span [{clip_in_ms}, {clip_out_ms}) for OTIO")
    if not math.isfinite(fps) or fps <= 0.0:
        raise DeliveryPackError(f"fps must be positive finite for OTIO, got {fps!r}")

    intervals: tuple[tuple[int, int], ...]
    if retained_intervals_ms is not None:
        if not retained_intervals_ms:
            raise DeliveryPackError("retained_intervals_ms cannot be empty")
        intervals = tuple(retained_intervals_ms)
    else:
        intervals = ((clip_in_ms, clip_out_ms),)

    media_ref = {
        "OTIO_SCHEMA": "ExternalReference.1",
        "name": source_mp4.name,
        "target_url": str(source_mp4),
    }

    markers: list[dict[str, Any]] = []
    hook_ms = min(3_000, max(1, duration_ms))
    markers.append(
        _marker(
            name="Hook (0-3s)",
            color="RED",
            start_frame=0,
            duration_frames=max(1, _ms_to_frames(hook_ms, fps)),
            rate=fps,
            metadata={"type": "hook", "hook_title_ckb": hook_title_ckb, "duration_ms": hook_ms},
        )
    )
    for move in result.script.camera_moves:
        markers.append(
            _marker(
                name=f"Camera: {move.kind} ({move.scale_start:.2f}x->{move.scale_end:.2f}x)",
                color="YELLOW",
                start_frame=_ms_to_frames(move.start_ms, fps),
                duration_frames=max(1, _ms_to_frames(move.end_ms - move.start_ms, fps)),
                rate=fps,
                metadata={
                    "type": "camera_move",
                    "kind": move.kind,
                    "scale_start": move.scale_start,
                    "scale_end": move.scale_end,
                    "reason": move.reason,
                },
            )
        )
    for vi in result.script.visual_interrupts:
        markers.append(
            _marker(
                name=f"Callout ({vi.position}): {vi.text_ckb}",
                color="BLUE",
                start_frame=_ms_to_frames(vi.start_ms, fps),
                duration_frames=max(1, _ms_to_frames(vi.end_ms - vi.start_ms, fps)),
                rate=fps,
                metadata={"type": "visual_interrupt", "position": vi.position, "text": vi.text_ckb},
            )
        )
    for sp_start, sp_end, sp_label in _build_speaker_spans(result.locked_crops):
        markers.append(
            _marker(
                name=f"Speaker: {sp_label}",
                color="CYAN",
                start_frame=_ms_to_frames(sp_start, fps),
                duration_frames=max(1, _ms_to_frames(sp_end - sp_start, fps)),
                rate=fps,
                metadata={"type": "speaker_turn", "speaker": sp_label},
            )
        )

    video_items: list[dict[str, Any]] = []
    audio_items: list[dict[str, Any]] = []
    for idx, (seg_in, seg_out) in enumerate(intervals, start=1):
        if seg_in < 0 or seg_out <= seg_in:
            raise DeliveryPackError(f"Invalid OTIO segment [{seg_in}, {seg_out})")
        in_frame = _ms_to_frames(seg_in, fps)
        dur_frames = max(1, _ms_to_frames(seg_out - seg_in, fps))
        video_items.append(
            {
                "OTIO_SCHEMA": "Clip.1",
                "name": f"{result.clip_id}_v{idx}",
                "source_range": _time_range(in_frame, dur_frames, fps),
                "media_reference": media_ref,
                "markers": markers if idx == 1 else [],
            }
        )
        audio_items.append(
            {
                "OTIO_SCHEMA": "Clip.1",
                "name": f"{result.clip_id}_a{idx}",
                "source_range": _time_range(in_frame, dur_frames, fps),
                "media_reference": media_ref,
                "markers": [],
            }
        )

    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": f"HawEdit_V8_{result.clip_id}",
        "global_start_time": _rational_time(0, fps),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": [
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "V1 - Source Video",
                    "kind": "Video",
                    "children": video_items,
                },
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "A1 - Kurdish Dialogue",
                    "kind": "Audio",
                    "children": audio_items,
                },
            ],
        },
        "metadata": {
            "hawedit": {
                "generator": "hawedit.v8.delivery_pack",
                "version": "9.0",
                "clip_id": result.clip_id,
                "media_id": media_id,
                "in_ms": clip_in_ms,
                "out_ms": clip_out_ms,
                "duration_ms": duration_ms,
                "fps": fps,
                "hook_title_ckb": hook_title_ckb,
                "director_backend": result.director_backend,
                "sub_engine": result.sub_engine,
                "grill_passed": result.grill_report.passed if result.grill_report else None,
            }
        },
    }


def extract_v8_cover_png(
    mp4_path: Path,
    output_png_path: Path,
    *,
    at_seconds: float = 0.6,
    ffmpeg: Path | None = None,
) -> Path:
    """Extract a crisp 1080×1920 PNG cover thumbnail from a rendered V8 MP4 at ``at_seconds``."""
    if not mp4_path.is_file() or mp4_path.stat().st_size == 0:
        raise DeliveryPackError(f"Cannot extract cover from missing or empty MP4: {mp4_path}")
    if not math.isfinite(at_seconds) or at_seconds < 0.0:
        raise DeliveryPackError(f"at_seconds must be non-negative finite, got {at_seconds!r}")

    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise DeliveryPackError("No ffmpeg binary available for cover PNG extraction")

    try:
        duration_ms = probe_duration_ms(mp4_path, binary)
    except Exception as exc:
        raise DeliveryPackError(f"Failed to probe MP4 duration for cover: {exc}") from exc

    seek_s = at_seconds
    if duration_ms <= int(round((at_seconds + 0.05) * 1000.0)):
        seek_s = max(0.0, (duration_ms / 1000.0) * 0.25)

    output_png_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{seek_s:.3f}",
            "-i",
            str(mp4_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v",
            "png",
            "-y",
            str(output_png_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    if proc.returncode != 0 or not output_png_path.is_file() or output_png_path.stat().st_size == 0:
        err = proc.stderr.strip()[:400]
        raise DeliveryPackError(f"FFmpeg cover PNG extraction failed for {mp4_path}: {err}")
    return output_png_path


def _sentences_for_v8_srt(
    result: V8CompileResult,
    explicit_sentences: Sequence[Sentence] | None,
) -> tuple[Sentence, ...]:
    if explicit_sentences is not None:
        return tuple(explicit_sentences)
    if not result.repaired_words:
        raise DeliveryPackError(f"Clip {result.clip_id} has zero repaired words for SRT")
    power_indices = frozenset(
        beat.power_word_index
        for beat in result.script.caption_beats
        if beat.power_word_index is not None
    )
    chunks = chunk_viral_kurdish_words(result.repaired_words, power_word_indices=power_indices)
    return tuple(
        Sentence(
            words=tuple(
                Word(w.text, w.start_ms, w.end_ms, result.repaired_words[w.index].conf)
                for w in chunk.words
            ),
            complete=True,
        )
        for chunk in chunks
    )


def write_social_handoff(
    mp4: Path,
    srt: Path,
    cover: Path,
    post_text: str,
    *,
    variants: Sequence[tuple[Path, str]] = (),
) -> Path:
    """Bundle the finished reel and posting assets using portable names."""
    target = mp4.with_suffix(".social.zip")
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".zip", delete=False) as temp:
        staged = Path(temp.name)
    try:
        with zipfile.ZipFile(staged, "w") as archive:
            archive.write(mp4, "reel.mp4")
            archive.write(srt, "captions.ckb.srt")
            archive.write(cover, "cover.png")
            for path, name in variants:
                archive.write(path, name)
            archive.writestr("post.txt", post_text.strip() + "\n")
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    return target


def write_client_delivery_pack(
    result: V8CompileResult,
    *,
    source_mp4: Path,
    clip_in_ms: int,
    clip_out_ms: int,
    fps: float = 25.0,
    media_id: str | None = None,
    hook_title_ckb: str | None = None,
    post_cta: Sequence[str | None] = (),
    subtitle_languages: Sequence[str] = (),
    dub_languages: Sequence[str] = (),
    translation_model: str | None = None,
    sentences: Sequence[Sentence] | None = None,
    retained_intervals_ms: Sequence[tuple[int, int]] | None = None,
    cover_at_seconds: float = 0.6,
    keep_overlay: bool = False,
    ffmpeg: Path | None = None,
    cover_extractor: Callable[[Path, Path, float], Path] | None = None,
    face_share: float | None = None,
    loudness_lufs: float | None = None,
) -> ClientDeliveryPack:
    """Emit the complete client delivery bundle for one compiled V8 reel (D-389).

    Writes ``.v8.srt``, ``.v8.edl``, ``.v8.otio``, and ``.v8.cover.png``, cleans up bulky
    temporary ``.v8.overlay.mov`` after verifying ``.v8.mp4`` exists and passed grill
    (unless ``keep_overlay=True``), and returns a ``ClientDeliveryPack``.
    """
    if not result.output_mp4.is_file() or result.output_mp4.stat().st_size == 0:
        raise DeliveryPackError(f"Rendered MP4 missing or empty: {result.output_mp4}")
    if not result.script_path.is_file() or result.script_path.stat().st_size == 0:
        raise DeliveryPackError(f"Director JSON missing or empty: {result.script_path}")
    if clip_in_ms < 0 or clip_out_ms <= clip_in_ms:
        raise DeliveryPackError(f"Invalid clip span [{clip_in_ms}, {clip_out_ms})")
    if not math.isfinite(fps) or fps <= 0.0:
        raise DeliveryPackError(f"fps must be positive finite, got {fps!r}")

    out_dir = result.output_mp4.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved_media_id = media_id or source_mp4.stem
    resolved_hook = (
        hook_title_ckb if hook_title_ckb is not None else result.script.hook_title_ckb
    ).strip()

    words_end_ms = max((w.end_ms for w in result.repaired_words), default=0)
    if result.grill_report is not None and result.grill_report.duration_ms > 0:
        duration_ms = result.grill_report.duration_ms
    elif words_end_ms > 0:
        duration_ms = words_end_ms
    else:
        duration_ms = clip_out_ms - clip_in_ms

    # a) .v8.srt — post-repair, post-trim Kurdish SRT via hawedit.delivery.build_srt
    srt_sentences = _sentences_for_v8_srt(result, sentences)
    try:
        srt_text = build_srt(srt_sentences, clip_in_ms=0, clip_duration_ms=duration_ms)
    except (DeliveryError, UndeliverableOrder) as exc:
        raise DeliveryPackError(f"Failed to build SRT for {result.clip_id}: {exc}") from exc
    srt_path = out_dir / f"{result.clip_id}.v8.srt"
    write_text_atomic(srt_path, srt_text)

    # b) .v8.edl (CMX 3600) AND .v8.otio (OpenTimelineIO JSON)
    effective_intervals = (
        retained_intervals_ms if retained_intervals_ms is not None else result.retained_intervals_ms
    )
    try:
        edl_text = build_edl(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            fps=fps,
            title=f"HawEdit {result.clip_id}",
            retained_intervals=effective_intervals,
        )
    except DeliveryError as exc:
        raise DeliveryPackError(f"Failed to build EDL for {result.clip_id}: {exc}") from exc
    edl_path = out_dir / f"{result.clip_id}.v8.edl"
    write_text_atomic(edl_path, edl_text)

    otio_doc = build_v8_otio_timeline(
        result,
        source_mp4=source_mp4,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        fps=fps,
        media_id=resolved_media_id,
        hook_title_ckb=resolved_hook,
        duration_ms=duration_ms,
        retained_intervals_ms=effective_intervals,
    )
    otio_path = out_dir / f"{result.clip_id}.v8.otio"
    write_text_atomic(otio_path, serialize_otio(otio_doc))

    # c) .v8.cover.png at t = 0.6 s
    cover_png_path = out_dir / f"{result.clip_id}.v8.cover.png"
    if cover_extractor is not None:
        extracted = cover_extractor(result.output_mp4, cover_png_path, cover_at_seconds)
        if not extracted.is_file() or extracted.stat().st_size == 0:
            raise DeliveryPackError(f"Cover extractor produced missing/empty file: {extracted}")
        cover_png_path = extracted
    else:
        extract_v8_cover_png(
            result.output_mp4,
            cover_png_path,
            at_seconds=cover_at_seconds,
            ffmpeg=ffmpeg,
        )

    # Resolve grill JSON path (written by compile_v8_clip alongside output_mp4 when grill ran)
    candidate_grill = out_dir / f"{result.clip_id}.grill.json"
    grill_json_path: Path | None = None
    if result.grill_report is not None:
        if not candidate_grill.is_file() or candidate_grill.stat().st_size == 0:
            write_text_atomic(
                candidate_grill,
                json.dumps(result.grill_report.to_dict(), ensure_ascii=False, indent=2) + "\n",
            )
        grill_json_path = candidate_grill
    elif candidate_grill.is_file() and candidate_grill.stat().st_size > 0:
        grill_json_path = candidate_grill

    # d) Clean up bulky temporary .v8.overlay.mov ONLY after verifying .v8.mp4 exists & passed grill
    overlay_cleaned = False
    overlay_bytes_reclaimed = 0
    overlay_path = result.subtitles.overlay_path
    grill_passed = result.grill_report.passed if result.grill_report is not None else None
    if (
        not keep_overlay
        and overlay_path is not None
        and overlay_path.is_file()
        and result.output_mp4.is_file()
        and result.output_mp4.stat().st_size > 0
        and grill_passed is True
    ):
        overlay_bytes_reclaimed = overlay_path.stat().st_size
        overlay_path.unlink()
        overlay_cleaned = True

    resolved_face_share = (
        round(max(0.0, min(1.0, float(face_share))), 4)
        if face_share is not None
        else _compute_face_share(result.locked_crops, duration_ms)
    )
    ass_path = (
        result.subtitles.ass_path
        if result.subtitles.ass_path is not None and result.subtitles.ass_path.is_file()
        else None
    )
    grill = result.grill_report
    pack = ClientDeliveryPack(
        clip_id=result.clip_id,
        mp4_path=result.output_mp4,
        srt_path=srt_path,
        edl_path=edl_path,
        otio_path=otio_path,
        cover_png_path=cover_png_path,
        director_json_path=result.script_path,
        grill_json_path=grill_json_path,
        ass_path=ass_path,
        overlay_cleaned=overlay_cleaned,
        overlay_bytes_reclaimed=overlay_bytes_reclaimed,
        duration_ms=duration_ms,
        face_share=resolved_face_share,
        hook_title_ckb=resolved_hook,
        grill_passed=grill_passed,
        grill_summary=_format_grill_summary(grill),
        double_cuts_count=len(grill.double_cuts) if grill is not None else 0,
        trailing_cuts_count=len(grill.trailing_cuts) if grill is not None else 0,
        long_silences_count=len(grill.long_silences) if grill is not None else 0,
        audio_flat_factor=grill.audio_flat_factor if grill is not None else 0.0,
        loudness_lufs=loudness_lufs,
    )
    verify_client_pack_complete(pack)
    copy = "\n\n".join(part.strip() for part in (resolved_hook, *post_cta) if part and part.strip())
    variants = []
    for lang in dict.fromkeys((*subtitle_languages, *dub_languages)):
        subtitle = translate_sidecar(
            srt_path, lang, translation_model or media_setting("translation_model")
        )
        variants.append((subtitle, f"captions.{lang}.draft.srt"))
        if lang in dub_languages:
            voice_python = media_setting("voice_python")
            weights = media_setting("voice_weights")
            if not voice_python or not weights:
                raise DeliveryPackError(
                    "Set HAWEDIT_VOICE_PYTHON and HAWEDIT_VOICE_WEIGHTS for dubbing"
                )
            dubbed = dub_reel(
                pack.mp4_path, subtitle, lang, worker=Path(voice_python), weights=Path(weights)
            )
            variants.append((dubbed, f"reel.{lang}.dub.mp4"))
    social = write_social_handoff(
        pack.mp4_path, pack.srt_path, pack.cover_png_path, copy, variants=variants
    )
    return replace(pack, social_zip_path=social)


def verify_client_pack_complete(pack: ClientDeliveryPack) -> None:
    """Assert every deliverable file in ``pack`` exists, is non-empty, and parses cleanly."""
    required: list[tuple[str, Path]] = [
        ("mp4_path", pack.mp4_path),
        ("srt_path", pack.srt_path),
        ("edl_path", pack.edl_path),
        ("otio_path", pack.otio_path),
        ("cover_png_path", pack.cover_png_path),
        ("director_json_path", pack.director_json_path),
    ]
    if pack.grill_json_path is not None:
        required.append(("grill_json_path", pack.grill_json_path))

    defects: list[str] = []
    for label, path in required:
        if not path.is_file():
            defects.append(f"{label} missing: {path}")
        elif path.stat().st_size == 0:
            defects.append(f"{label} is empty (0 bytes): {path}")

    if not defects:
        try:
            cues = parse_srt_times(pack.srt_path.read_text(encoding="utf-8"))
            if not cues:
                defects.append(f"srt_path contains zero cues: {pack.srt_path}")
        except (OSError, DeliveryError) as exc:
            defects.append(f"srt_path invalid: {exc}")

        try:
            otio = json.loads(pack.otio_path.read_text(encoding="utf-8"))
            if not isinstance(otio, dict) or otio.get("OTIO_SCHEMA") != "Timeline.1":
                defects.append(f"otio_path is not a valid Timeline.1 JSON: {pack.otio_path}")
        except (OSError, json.JSONDecodeError) as exc:
            defects.append(f"otio_path invalid JSON: {exc}")

        try:
            director_doc = json.loads(pack.director_json_path.read_text(encoding="utf-8"))
            if not isinstance(director_doc, dict) or "clip_id" not in director_doc:
                defects.append(f"director_json_path invalid object: {pack.director_json_path}")
        except (OSError, json.JSONDecodeError) as exc:
            defects.append(f"director_json_path invalid JSON: {exc}")

        if pack.grill_json_path is not None:
            try:
                grill_doc = json.loads(pack.grill_json_path.read_text(encoding="utf-8"))
                if not isinstance(grill_doc, dict) or "passed" not in grill_doc:
                    defects.append(f"grill_json_path invalid object: {pack.grill_json_path}")
            except (OSError, json.JSONDecodeError) as exc:
                defects.append(f"grill_json_path invalid JSON: {exc}")

    if defects:
        raise DeliveryPackError(
            f"Client delivery pack incomplete for {pack.clip_id}: " + "; ".join(defects)
        )


def _rel_href(base_dir: Path, target: Path) -> str:
    rel = os.path.relpath(str(target), str(base_dir)).replace("\\", "/")
    return quote(rel, safe="/:@-._~")


def write_client_review_html(
    packs: Sequence[ClientDeliveryPack],
    output_html_path: Path,
    *,
    episode_title: str = "HawEdit V9 Client Review",
    source_name: str = "",
    director_backend: str = "",
    total_wall_s: float | None = None,
    style_preset: str = "viral_gold",
) -> Path:
    """Write a self-contained, zero-CDN, RTL Kurdish dark-studio HTML review gallery (D-390)."""
    if not packs:
        raise DeliveryPackError("Cannot write client-review.html with zero delivery packs")

    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    base_dir = output_html_path.parent

    passed_count = sum(1 for p in packs if p.grill_passed is True)
    failed_count = sum(1 for p in packs if p.grill_passed is False)
    total_count = len(packs)
    reclaimed_mb = sum(p.overlay_bytes_reclaimed for p in packs) / (1024.0 * 1024.0)

    cards_html: list[str] = []
    for idx, pack in enumerate(packs, start=1):
        mp4_href = _rel_href(base_dir, pack.mp4_path)
        cover_href = _rel_href(base_dir, pack.cover_png_path)
        srt_href = _rel_href(base_dir, pack.srt_path)
        edl_href = _rel_href(base_dir, pack.edl_path)
        otio_href = _rel_href(base_dir, pack.otio_path)
        dir_href = _rel_href(base_dir, pack.director_json_path)

        if pack.grill_passed is True:
            badge_cls = "badge-pass"
            badge_txt = "GRILL PASSED ✓"
        elif pack.grill_passed is False:
            badge_cls = "badge-fail"
            badge_txt = "GRILL FAILED"
        else:
            badge_cls = "badge-warn"
            badge_txt = "GRILL NOT RUN"

        loud_str = (
            f"{pack.loudness_lufs:.1f} LUFS"
            if pack.loudness_lufs is not None
            else f"Flat {pack.audio_flat_factor:.3f}"
        )
        hook_display = html.escape(pack.hook_title_ckb or pack.clip_id, quote=True)
        clip_id_esc = html.escape(pack.clip_id, quote=True)
        summary_esc = html.escape(pack.grill_summary, quote=True)

        links: list[str] = [
            f'<a class="dl-btn dl-primary" href="{mp4_href}" download>MP4</a>',
            f'<a class="dl-btn" href="{srt_href}" download>SRT</a>',
            f'<a class="dl-btn" href="{edl_href}" download>EDL</a>',
            f'<a class="dl-btn" href="{otio_href}" download>OTIO</a>',
            f'<a class="dl-btn" href="{cover_href}" download>Cover PNG</a>',
            f'<a class="dl-btn" href="{dir_href}" download>Director JSON</a>',
        ]
        if pack.social_zip_path is not None:
            social_href = _rel_href(base_dir, pack.social_zip_path)
            links.insert(
                0, f'<a class="dl-btn dl-primary" href="{social_href}" download>Social ZIP</a>'
            )
        if pack.grill_json_path is not None:
            grill_href = _rel_href(base_dir, pack.grill_json_path)
            links.append(f'<a class="dl-btn" href="{grill_href}" download>Grill JSON</a>')

        cards_html.append(
            f"""
      <article class="reel-card">
        <div class="reel-head">
          <span class="reel-rank">#{idx:02d}</span>
          <span class="badge {badge_cls}" title="{summary_esc}">{badge_txt}</span>
        </div>
        <h2 class="hook-title" dir="rtl" lang="ckb">{hook_display}</h2>
        <div class="clip-id">{clip_id_esc}</div>
        <div class="media-grid">
          <div class="player-wrap">
            <video controls preload="metadata" poster="{cover_href}" playsinline>
              <source src="{mp4_href}" type="video/mp4">
            </video>
          </div>
          <div class="cover-wrap">
            <img src="{cover_href}" alt="Cover thumbnail for {clip_id_esc}" loading="lazy">
            <span class="cover-label">Cover @ 0.6s</span>
          </div>
        </div>
        <div class="stats-grid">
          <div class="stat">
            <span class="k">Duration</span>
            <span class="v">{pack.duration_ms / 1000.0:.2f}s</span>
          </div>
          <div class="stat">
            <span class="k">Double Cuts</span>
            <span class="v">{pack.double_cuts_count}</span>
          </div>
          <div class="stat">
            <span class="k">Silences</span>
            <span class="v">{pack.long_silences_count}</span>
          </div>
          <div class="stat">
            <span class="k">Loudness</span>
            <span class="v">{html.escape(loud_str)}</span>
          </div>
          <div class="stat">
            <span class="k">Face Share</span>
            <span class="v">{pack.face_share * 100.0:.0f}%</span>
          </div>
        </div>
        <div class="grill-note">{summary_esc}</div>
        <div class="dl-row">{"".join(links)}</div>
      </article>"""
        )

    title_esc = html.escape(episode_title, quote=True)
    source_esc = html.escape(source_name or "Episode", quote=True)
    dir_esc = html.escape(director_backend or "v8", quote=True)
    preset_esc = html.escape(style_preset, quote=True)
    wall_chip = f"<span>Wall: <strong>{total_wall_s:.1f}s</strong></span>" if total_wall_s else ""
    reclaim_chip = (
        f"<span>Overlay Cleaned: <strong>{reclaimed_mb:.1f} MB</strong></span>"
        if reclaimed_mb > 0.0
        else ""
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title_esc}</title>
  <style>
    :root {{
      --bg: #0b0e14;
      --surface: #141923;
      --surface-2: #1b2230;
      --border: #273145;
      --text: #f3f5f9;
      --muted: #9aa7bd;
      --accent: #ffd700;
      --pass-bg: rgba(34, 197, 94, 0.16);
      --pass-fg: #4ade80;
      --fail-bg: rgba(239, 68, 68, 0.18);
      --fail-fg: #f87171;
      --warn-bg: rgba(245, 158, 11, 0.18);
      --warn-fg: #fbbf24;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top, #151c2c 0%, var(--bg) 55%);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Tahoma, sans-serif;
      line-height: 1.5;
      min-height: 100vh;
    }}
    .wrap {{ max-width: 1380px; margin: 0 auto; padding: 28px 20px 64px; }}
    header {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 22px 26px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 1.5rem; letter-spacing: -0.01em; }}
    .sub {{ color: var(--muted); font-size: 0.92rem; }}
    .meta-pills {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 0.85rem; }}
    .meta-pills span {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 999px;
      color: var(--muted);
    }}
    .meta-pills strong {{ color: var(--text); }}
    .gallery {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 22px;
    }}
    .reel-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .reel-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }}
    .reel-rank {{
      font-weight: 700;
      color: var(--accent);
      font-size: 0.95rem;
      letter-spacing: 0.04em;
    }}
    .badge {{
      padding: 4px 11px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.03em;
    }}
    .badge-pass {{
      background: var(--pass-bg); color: var(--pass-fg); border: 1px solid #22c55e55;
    }}
    .badge-fail {{
      background: var(--fail-bg); color: var(--fail-fg); border: 1px solid #ef444455;
    }}
    .badge-warn {{
      background: var(--warn-bg); color: var(--warn-fg); border: 1px solid #f59e0b55;
    }}
    .hook-title {{
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
      font-family: "Vazirmatn", "Noto Naskh Arabic", "Segoe UI", Tahoma, sans-serif;
      color: #fff;
      text-align: right;
    }}
    .clip-id {{
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 0.78rem;
      color: var(--muted);
    }}
    .media-grid {{
      display: grid;
      grid-template-columns: 1.45fr 1fr;
      gap: 12px;
      align-items: stretch;
    }}
    .player-wrap, .cover-wrap {{
      background: #07090d;
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      position: relative;
      aspect-ratio: 9 / 16;
    }}
    video, .cover-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .cover-label {{
      position: absolute;
      bottom: 8px;
      left: 8px;
      background: rgba(11, 14, 20, 0.82);
      color: var(--accent);
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
    }}
    .stat {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 6px;
      text-align: center;
    }}
    .stat .k {{
      display: block; font-size: 0.68rem; color: var(--muted); text-transform: uppercase;
    }}
    .stat .v {{
      display: block; font-size: 0.9rem; font-weight: 700; color: var(--text); margin-top: 2px;
    }}
    .grill-note {{ font-size: 0.78rem; color: var(--muted); }}
    .dl-row {{ display: flex; flex-wrap: wrap; gap: 7px; padding-top: 4px; }}
    .dl-btn {{
      text-decoration: none;
      color: var(--text);
      background: var(--surface-2);
      border: 1px solid var(--border);
      padding: 6px 11px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 600;
    }}
    .dl-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .dl-primary {{ background: var(--accent); color: #0b0e14; border-color: var(--accent); }}
    .dl-primary:hover {{ color: #0b0e14; filter: brightness(1.06); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>{title_esc}</h1>
        <a class="dl-btn" href="blind-review.html">هەڵسەنگاندنی کلیپەکان</a>
        <div class="sub">Source: {source_esc}</div>
      </div>
      <div class="meta-pills">
        <span>Reels: <strong>{total_count}</strong></span>
        <span>Grill Passed: <strong>{passed_count}/{total_count}</strong></span>
        <span>Grill Failed: <strong>{failed_count}</strong></span>
        <span>Director: <strong>{dir_esc}</strong></span>
        <span>Preset: <strong>{preset_esc}</strong></span>
        {wall_chip}
        {reclaim_chip}
      </div>
    </header>
    <main class="gallery">{"".join(cards_html)}
    </main>
  </div>
</body>
</html>
"""
    write_blind_review([p.mp4_path for p in packs], base_dir / "blind-review.html")
    write_text_atomic(output_html_path, doc)
    return output_html_path
