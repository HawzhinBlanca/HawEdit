"""OpenTimelineIO (.otio) editorial timeline generator for DaVinci Resolve handoff.

HawEdit acts as the Sorani Kurdish editorial brain; DaVinci Resolve Studio acts as the
finishing room. This module emits schema-valid OpenTimelineIO JSON files conforming the
selected sentence-complete clips back to the original source video with coloured editorial
markers for Hook (Red), Payoff (Blue), Punch-In cut points (Yellow), Speaker Turns (Cyan),
and Sentences (Green).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hawedit.clip import Clip


def _rational_time(value: float | int, rate: float) -> dict[str, Any]:
    """An OpenTimelineIO RationalTime.1 object."""
    return {
        "OTIO_SCHEMA": "RationalTime.1",
        "value": float(value),
        "rate": float(rate),
    }


def _time_range(
    start_frame: float | int, duration_frames: float | int, rate: float
) -> dict[str, Any]:
    """An OpenTimelineIO TimeRange.1 object."""
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _rational_time(start_frame, rate),
        "duration": _rational_time(duration_frames, rate),
    }


def _marker(
    name: str,
    color: str,
    start_frame: float | int,
    duration_frames: float | int,
    rate: float,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """An OpenTimelineIO Marker.1 object."""
    return {
        "OTIO_SCHEMA": "Marker.1",
        "name": name,
        "color": color.upper(),
        "marked_range": _time_range(start_frame, duration_frames, rate),
        "metadata": metadata or {},
    }


def _ms_to_frames(ms: int, fps: float) -> int:
    """Convert milliseconds to integer frame count at given fps."""
    return round(ms * fps / 1000.0)


def build_clip_markers(
    clip: Clip,
    fps: float,
    punch_ins: tuple[int, ...] = (),
    speaker_turns: tuple[tuple[int, int, str], ...] = (),
) -> list[dict[str, Any]]:
    """Build DaVinci Resolve timeline markers for one clip."""
    markers: list[dict[str, Any]] = []
    clip_in_frame = _ms_to_frames(clip.in_ms, fps)
    clip_duration_ms = clip.out_ms - clip.in_ms

    # 1. Hook Marker (Red) - opening 0-3 seconds
    hook_ms = min(3000, clip_duration_ms)
    hook_frames = max(1, _ms_to_frames(hook_ms, fps))
    markers.append(
        _marker(
            name="Hook (0-3s)",
            color="RED",
            start_frame=clip_in_frame,
            duration_frames=hook_frames,
            rate=fps,
            metadata={"type": "hook", "duration_ms": hook_ms},
        )
    )

    # 2. Payoff Marker (Blue) - editorial climax/insight
    if clip.editorial and clip.editorial.payoff_at_ms is not None:
        payoff_ms = clip.editorial.payoff_at_ms
        if clip.in_ms <= payoff_ms <= clip.out_ms:
            payoff_frame = _ms_to_frames(payoff_ms, fps)
            payoff_duration_frames = max(1, _ms_to_frames(1500, fps))
            markers.append(
                _marker(
                    name="Payoff / Core Insight",
                    color="BLUE",
                    start_frame=payoff_frame,
                    duration_frames=payoff_duration_frames,
                    rate=fps,
                    metadata={"type": "payoff", "timestamp_ms": payoff_ms},
                )
            )

    # 3. Punch-In Markers (Yellow) - key emphasis reframe points
    for p_ms in punch_ins:
        if clip.in_ms <= p_ms <= clip.out_ms:
            p_frame = _ms_to_frames(p_ms, fps)
            p_duration = max(1, _ms_to_frames(500, fps))
            markers.append(
                _marker(
                    name="Punch-In Reframe Cut",
                    color="YELLOW",
                    start_frame=p_frame,
                    duration_frames=p_duration,
                    rate=fps,
                    metadata={"type": "punch_in", "timestamp_ms": p_ms},
                )
            )

    # 4. Speaker Turn Markers (Cyan) - active speaker changes
    for turn_in, turn_out, speaker in speaker_turns:
        bounded_in = max(clip.in_ms, turn_in)
        bounded_out = min(clip.out_ms, turn_out)
        if bounded_out > bounded_in:
            t_frame = _ms_to_frames(bounded_in, fps)
            t_duration = max(1, _ms_to_frames(bounded_out - bounded_in, fps))
            markers.append(
                _marker(
                    name=f"Speaker: {speaker}",
                    color="CYAN",
                    start_frame=t_frame,
                    duration_frames=t_duration,
                    rate=fps,
                    metadata={"type": "speaker_turn", "speaker": speaker},
                )
            )

    return markers


def build_otio_timeline(
    clip: Clip,
    source_media_path: str,
    fps: float,
    punch_ins: tuple[int, ...] = (),
    speaker_turns: tuple[tuple[int, int, str], ...] = (),
    timeline_name: str | None = None,
) -> dict[str, Any]:
    """Generate a schema-compliant OpenTimelineIO (OTIO) dictionary for one clip."""
    name = timeline_name or f"HawEdit_{clip.clip_id}"
    source_in_frame = _ms_to_frames(clip.in_ms, fps)
    duration_frames = max(1, _ms_to_frames(clip.out_ms - clip.in_ms, fps))

    # Media reference
    media_ref = {
        "OTIO_SCHEMA": "ExternalReference.1",
        "name": Path(source_media_path).name,
        "target_url": str(source_media_path),
    }

    # Markers
    markers = build_clip_markers(clip, fps, punch_ins=punch_ins, speaker_turns=speaker_turns)

    # Video item
    video_item = {
        "OTIO_SCHEMA": "Clip.1",
        "name": f"{clip.clip_id}_video",
        "source_range": _time_range(source_in_frame, duration_frames, fps),
        "media_reference": media_ref,
        "markers": markers,
    }

    # Audio item
    audio_item = {
        "OTIO_SCHEMA": "Clip.1",
        "name": f"{clip.clip_id}_audio",
        "source_range": _time_range(source_in_frame, duration_frames, fps),
        "media_reference": media_ref,
        "markers": [],
    }

    timeline = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": name,
        "global_start_time": _rational_time(0, fps),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": [
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "V1 - Source Video",
                    "kind": "Video",
                    "children": [video_item],
                },
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "A1 - Kurdish Dialogue",
                    "kind": "Audio",
                    "children": [audio_item],
                },
            ],
        },
        "metadata": {
            "hawedit": {
                "generator": "hawedit.timeline",
                "version": "1.0",
                "clip_id": clip.clip_id,
                "media_id": clip.media_id,
                "in_ms": clip.in_ms,
                "out_ms": clip.out_ms,
                "fps": fps,
                "title_ckb": clip.output.title_ckb if clip.output else "",
            }
        },
    }
    return timeline


def build_episode_otio_timeline(
    clips: list[Clip],
    source_media_path: str,
    fps: float,
    episode_title: str = "HawEdit Episode",
) -> dict[str, Any]:
    """Generate an OpenTimelineIO (OTIO) dictionary assembling all N clips onto one timeline."""
    video_children: list[dict[str, Any]] = []
    audio_children: list[dict[str, Any]] = []

    media_ref = {
        "OTIO_SCHEMA": "ExternalReference.1",
        "name": Path(source_media_path).name,
        "target_url": str(source_media_path),
    }

    for idx, clip in enumerate(clips, 1):
        source_in_frame = _ms_to_frames(clip.in_ms, fps)
        duration_frames = max(1, _ms_to_frames(clip.out_ms - clip.in_ms, fps))
        markers = build_clip_markers(clip, fps)

        video_item = {
            "OTIO_SCHEMA": "Clip.1",
            "name": f"Clip_{idx:02d}_{clip.clip_id}",
            "source_range": _time_range(source_in_frame, duration_frames, fps),
            "media_reference": media_ref,
            "markers": markers,
        }
        audio_item = {
            "OTIO_SCHEMA": "Clip.1",
            "name": f"Clip_{idx:02d}_{clip.clip_id}_audio",
            "source_range": _time_range(source_in_frame, duration_frames, fps),
            "media_reference": media_ref,
            "markers": [],
        }
        video_children.append(video_item)
        audio_children.append(audio_item)

    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": episode_title,
        "global_start_time": _rational_time(0, fps),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": [
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "V1 - Candidate Clips",
                    "kind": "Video",
                    "children": video_children,
                },
                {
                    "OTIO_SCHEMA": "Track.1",
                    "name": "A1 - Dialogue",
                    "kind": "Audio",
                    "children": audio_children,
                },
            ],
        },
        "metadata": {
            "hawedit": {
                "generator": "hawedit.timeline",
                "version": "1.0",
                "clip_count": len(clips),
                "fps": fps,
            }
        },
    }


def serialize_otio(timeline_dict: dict[str, Any]) -> str:
    """Serialize an OpenTimelineIO dictionary to formatted JSON string."""
    return json.dumps(timeline_dict, ensure_ascii=False, indent=2) + "\n"
