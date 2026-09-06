"""Unified visual edit contract and time mapping (Task VE-01 / V01).

Implements:
- `EditorialBrief`: Intended viewer takeaway, content type, target duration range,
  and protected content regions.
- `EffectiveConfiguration`: Single resolved configuration with validation of
  conflicting options and policy versioning.
- `SourceTimeMapping`: Precise, reversible mapping between canonical source timestamps,
  clip timeline, and output timeline.
- `VisualEditPlan`: Versioned, immutable edit contract from which all deliverable sidecars
  (ASS, SRT, multi-cut EDL, OTIO) derive deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.captions import CaptionStyle
from hawedit.content_type import ContentType, get_content_type_profile
from hawedit.delivery import build_edl, build_srt
from hawedit.sentences import Sentence
from hawedit.timeline import _marker, _rational_time, _time_range
from hawedit.transcripts import Word

__all__ = [
    "CURRENT_PLAN_VERSION",
    "EditorialBrief",
    "EffectiveConfiguration",
    "SourceTimeMapping",
    "VisualEditPlan",
]

CURRENT_PLAN_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class EditorialBrief:
    """Editorial brief establishing the communicative intent and constraints of the edit."""

    viewer_takeaway: str
    content_type: ContentType
    target_duration_ms: tuple[int, int]
    protected_regions: tuple[str, ...] = ("lower_third_captions", "speaker_face")

    def __post_init__(self) -> None:
        if not self.viewer_takeaway.strip():
            raise ValueError("viewer_takeaway cannot be empty")
        min_dur, max_dur = self.target_duration_ms
        if min_dur <= 0 or max_dur < min_dur:
            raise ValueError(f"invalid target_duration_ms range: ({min_dur}, {max_dur})")

    @classmethod
    def default_for_content(
        cls,
        content_type: ContentType | str | None,
        duration_ms: int = 30_000,
    ) -> EditorialBrief:
        """Create a conservative default brief for unspecified inputs."""
        ct = ContentType(content_type) if content_type is not None else ContentType.PODCAST
        profile = get_content_type_profile(ct)
        min_dur = max(profile.min_clip_ms, min(duration_ms, 15_000))
        max_dur = max(min_dur, duration_ms)
        return cls(
            viewer_takeaway="Intended communicative takeaway from spoken Kurdish discussion",
            content_type=ct,
            target_duration_ms=(min_dur, max_dur),
            protected_regions=("lower_third_captions", "speaker_face"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewer_takeaway": self.viewer_takeaway,
            "content_type": self.content_type.value,
            "target_duration_ms": list(self.target_duration_ms),
            "protected_regions": list(self.protected_regions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EditorialBrief:
        dur = data["target_duration_ms"]
        return cls(
            viewer_takeaway=str(data["viewer_takeaway"]),
            content_type=ContentType(data["content_type"]),
            target_duration_ms=(int(dur[0]), int(dur[1])),
            protected_regions=tuple(str(r) for r in data.get("protected_regions", ())),
        )


@dataclass(frozen=True, slots=True)
class EffectiveConfiguration:
    """Resolved, validated configuration policy for visual editing."""

    content_type: ContentType
    caption_style: CaptionStyle
    reframe_mode: str
    silence_threshold_ms: int
    silence_target_gap_ms: int
    punch_in_cadence_ms: int
    eased_push: bool
    two_person_split: str
    keyword_emphasis: bool
    fps: float
    policy_version: str = "1.0.0"

    def assert_valid(self) -> None:
        """Validate configuration combinations, failing fast before GPU or media work."""
        if self.two_person_split not in ("auto", "always", "never"):
            raise ValueError(
                f"two_person_split must be 'auto', 'always', or 'never', "
                f"got {self.two_person_split!r}"
            )
        if self.silence_threshold_ms < 0:
            raise ValueError(
                f"silence_threshold_ms cannot be negative: {self.silence_threshold_ms}"
            )
        if self.silence_target_gap_ms < 0:
            raise ValueError(
                f"silence_target_gap_ms cannot be negative: {self.silence_target_gap_ms}"
            )
        if (
            self.silence_threshold_ms > 0
            and self.silence_target_gap_ms >= self.silence_threshold_ms
        ):
            raise ValueError(
                f"silence_target_gap_ms ({self.silence_target_gap_ms}) must be strictly less than "
                f"silence_threshold_ms ({self.silence_threshold_ms})"
            )
        if self.fps <= 0:
            raise ValueError(f"fps must be positive, got {self.fps}")

        # News profile restrictions: broadcast studio standards prohibit informal jump zooms
        if self.content_type is ContentType.NEWS:
            if self.punch_in_cadence_ms > 0:
                raise ValueError(
                    "incompatible configuration: NEWS content prohibits punch-in cadence > 0"
                )
            if self.eased_push:
                raise ValueError(
                    "incompatible configuration: NEWS content prohibits eased continuous push-in"
                )

    @classmethod
    def resolve(
        cls,
        content_type: ContentType | str | None = None,
        caption_style: CaptionStyle | str | None = None,
        reframe_mode: str = "speaker_tracked",
        silence_threshold_ms: int | None = None,
        silence_target_gap_ms: int | None = None,
        punch_in_cadence_ms: int | None = None,
        eased_push: bool | None = None,
        two_person_split: str = "auto",
        keyword_emphasis: bool = True,
        fps: float = 25.0,
        policy_version: str = "1.0.0",
    ) -> EffectiveConfiguration:
        """Resolve defaults from content profile and caller overrides once."""
        profile = get_content_type_profile(content_type)
        style = CaptionStyle(caption_style) if caption_style is not None else profile.caption_style
        sil_thresh = (
            silence_threshold_ms
            if silence_threshold_ms is not None
            else profile.silence_threshold_ms
        )
        sil_gap = silence_target_gap_ms if silence_target_gap_ms is not None else 150
        punch_cadence = (
            punch_in_cadence_ms if punch_in_cadence_ms is not None else profile.punch_in_cadence_ms
        )
        push = eased_push if eased_push is not None else profile.eased_push

        cfg = cls(
            content_type=profile.content_type,
            caption_style=style,
            reframe_mode=reframe_mode,
            silence_threshold_ms=sil_thresh,
            silence_target_gap_ms=sil_gap,
            punch_in_cadence_ms=punch_cadence,
            eased_push=push,
            two_person_split=two_person_split,
            keyword_emphasis=keyword_emphasis,
            fps=fps,
            policy_version=policy_version,
        )
        cfg.assert_valid()
        return cfg

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "caption_style": self.caption_style.value,
            "reframe_mode": self.reframe_mode,
            "silence_threshold_ms": self.silence_threshold_ms,
            "silence_target_gap_ms": self.silence_target_gap_ms,
            "punch_in_cadence_ms": self.punch_in_cadence_ms,
            "eased_push": self.eased_push,
            "two_person_split": self.two_person_split,
            "keyword_emphasis": self.keyword_emphasis,
            "fps": self.fps,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EffectiveConfiguration:
        cfg = cls(
            content_type=ContentType(data["content_type"]),
            caption_style=CaptionStyle(data["caption_style"]),
            reframe_mode=str(data["reframe_mode"]),
            silence_threshold_ms=int(data["silence_threshold_ms"]),
            silence_target_gap_ms=int(data["silence_target_gap_ms"]),
            punch_in_cadence_ms=int(data["punch_in_cadence_ms"]),
            eased_push=bool(data["eased_push"]),
            two_person_split=str(data["two_person_split"]),
            keyword_emphasis=bool(data["keyword_emphasis"]),
            fps=float(data["fps"]),
            policy_version=str(data.get("policy_version", "1.0.0")),
        )
        cfg.assert_valid()
        return cfg


@dataclass(frozen=True, slots=True)
class SourceTimeMapping:
    """Exact, reversible mapping between source media intervals and output timeline."""

    clip_in_ms: int
    clip_out_ms: int
    retained_intervals_ms: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if self.clip_in_ms < 0:
            raise ValueError(f"clip_in_ms cannot be negative: {self.clip_in_ms}")
        if self.clip_out_ms <= self.clip_in_ms:
            raise ValueError(
                f"clip_out_ms ({self.clip_out_ms}) must be > clip_in_ms ({self.clip_in_ms})"
            )
        if not self.retained_intervals_ms:
            raise ValueError("retained_intervals_ms cannot be empty")

        last_end = self.clip_in_ms
        for start, end in self.retained_intervals_ms:
            if start < last_end or end <= start or end > self.clip_out_ms:
                raise ValueError(
                    f"invalid retained interval ({start}, {end}) inside clip "
                    f"{self.clip_in_ms}..{self.clip_out_ms}"
                )
            last_end = end

    @classmethod
    def continuous(cls, clip_in_ms: int, clip_out_ms: int) -> SourceTimeMapping:
        """A single continuous source span without internal trims."""
        return cls(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            retained_intervals_ms=((clip_in_ms, clip_out_ms),),
        )

    @property
    def output_duration_ms(self) -> int:
        """Actual total duration in output milliseconds."""
        return sum(end - start for start, end in self.retained_intervals_ms)

    def source_to_output_ms(self, source_ms: int, *, clamp_excised: bool = True) -> int | None:
        """Map canonical source milliseconds to output milliseconds.

        If source_ms falls inside an excised silence interval:
        - returns the excised cut boundary if clamp_excised is True
        - returns None if clamp_excised is False
        """
        if source_ms <= self.clip_in_ms:
            return 0
        if source_ms >= self.clip_out_ms:
            return self.output_duration_ms

        accumulated_output = 0
        for start, end in self.retained_intervals_ms:
            if source_ms < start:
                return accumulated_output if clamp_excised else None
            if source_ms <= end:
                return accumulated_output + (source_ms - start)
            accumulated_output += end - start

        return self.output_duration_ms

    def output_to_source_ms(self, output_ms: int) -> int:
        """Reverse an output millisecond timestamp back to canonical source time."""
        if output_ms <= 0:
            return self.retained_intervals_ms[0][0]
        accumulated = 0
        for start, end in self.retained_intervals_ms:
            duration = end - start
            if output_ms <= accumulated + duration:
                return start + (output_ms - accumulated)
            accumulated += duration
        return self.retained_intervals_ms[-1][1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_in_ms": self.clip_in_ms,
            "clip_out_ms": self.clip_out_ms,
            "retained_intervals_ms": [list(item) for item in self.retained_intervals_ms],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceTimeMapping:
        intervals = tuple((int(item[0]), int(item[1])) for item in data["retained_intervals_ms"])
        return cls(
            clip_in_ms=int(data["clip_in_ms"]),
            clip_out_ms=int(data["clip_out_ms"]),
            retained_intervals_ms=intervals,
        )


@dataclass(frozen=True, slots=True)
class VisualEditPlan:
    """Unified immutable visual edit plan (Task VE-01 / V01)."""

    version: int
    clip_id: str
    media_id: str
    media_sha256: str
    brief: EditorialBrief
    config: EffectiveConfiguration
    time_mapping: SourceTimeMapping
    shot_cuts_ms: tuple[int, ...] = ()
    punch_in_ms: tuple[int, ...] = ()
    speaker_turns: tuple[tuple[int, int, str], ...] = ()
    sentences: tuple[Sentence, ...] = ()

    def derive_sentences_for_output(self) -> tuple[Sentence, ...]:
        """Derive sentences with words mapped strictly to output timeline (0-based)."""
        remapped_sentences: list[Sentence] = []
        for s in self.sentences:
            remapped_words: list[Word] = []
            for w in s.words:
                out_start = self.time_mapping.source_to_output_ms(w.start_ms, clamp_excised=True)
                out_end = self.time_mapping.source_to_output_ms(w.end_ms, clamp_excised=True)
                if out_start is not None and out_end is not None and out_end > out_start:
                    remapped_words.append(
                        Word(w=w.w, start_ms=out_start, end_ms=out_end, conf=w.conf)
                    )
            if remapped_words:
                remapped_sentences.append(
                    Sentence(words=tuple(remapped_words), complete=s.complete)
                )
        return tuple(remapped_sentences)

    def derive_srt(self, max_chars_per_line: int = 32) -> str:
        """Derive SRT subtitle sidecar text conforming to the output timeline."""
        out_sentences = self.derive_sentences_for_output()
        return build_srt(
            out_sentences,
            clip_in_ms=0,
            clip_duration_ms=self.time_mapping.output_duration_ms,
            max_chars_per_line=max_chars_per_line,
        )

    def derive_edl(self, title: str = "HAWEDIT CLIP") -> str:
        """Derive CMX 3600 EDL sidecar with distinct events for all retained source intervals."""
        return build_edl(
            clip_in_ms=self.time_mapping.clip_in_ms,
            clip_out_ms=self.time_mapping.clip_out_ms,
            fps=self.config.fps,
            title=title,
            retained_intervals=self.time_mapping.retained_intervals_ms,
        )

    def derive_otio(
        self,
        source_media_path: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Derive an OpenTimelineIO schema dictionary with clips and editorial markers."""
        fps = self.config.fps
        name = title or f"HawEdit_{self.clip_id}"

        media_ref = {
            "OTIO_SCHEMA": "ExternalReference.1",
            "name": Path(source_media_path).name,
            "target_url": str(source_media_path),
        }

        # Build markers on output timeline
        markers: list[dict[str, Any]] = []

        # 1. Hook marker (Red): 0-3s
        hook_ms = min(3000, self.time_mapping.output_duration_ms)
        hook_frames = max(1, round(hook_ms * fps / 1000.0))
        markers.append(
            _marker(
                name="Hook (0-3s)",
                color="RED",
                start_frame=0,
                duration_frames=hook_frames,
                rate=fps,
                metadata={"type": "hook", "duration_ms": hook_ms},
            )
        )

        # 2. Punch-in markers (Yellow)
        for p_source_ms in self.punch_in_ms:
            p_out_ms = self.time_mapping.source_to_output_ms(p_source_ms, clamp_excised=False)
            if p_out_ms is not None and 0 <= p_out_ms <= self.time_mapping.output_duration_ms:
                p_frame = round(p_out_ms * fps / 1000.0)
                p_duration = max(1, round(500 * fps / 1000.0))
                markers.append(
                    _marker(
                        name="Punch-In Reframe Cut",
                        color="YELLOW",
                        start_frame=p_frame,
                        duration_frames=p_duration,
                        rate=fps,
                        metadata={"type": "punch_in", "source_timestamp_ms": p_source_ms},
                    )
                )

        # 3. Speaker turn markers (Cyan)
        for turn_in, turn_out, speaker in self.speaker_turns:
            out_in = self.time_mapping.source_to_output_ms(turn_in, clamp_excised=True)
            out_out = self.time_mapping.source_to_output_ms(turn_out, clamp_excised=True)
            if out_in is not None and out_out is not None and out_out > out_in:
                t_frame = round(out_in * fps / 1000.0)
                t_duration = max(1, round((out_out - out_in) * fps / 1000.0))
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

        video_items: list[dict[str, Any]] = []
        audio_items: list[dict[str, Any]] = []
        for idx, (s_in, s_out) in enumerate(self.time_mapping.retained_intervals_ms, start=1):
            s_in_frame = round(s_in * fps / 1000.0)
            seg_frames = max(1, round((s_out - s_in) * fps / 1000.0))
            v_item = {
                "OTIO_SCHEMA": "Clip.1",
                "name": f"{self.clip_id}_v{idx}",
                "source_range": _time_range(s_in_frame, seg_frames, fps),
                "media_reference": media_ref,
                "markers": markers if idx == 1 else [],
            }
            a_item = {
                "OTIO_SCHEMA": "Clip.1",
                "name": f"{self.clip_id}_a{idx}",
                "source_range": _time_range(s_in_frame, seg_frames, fps),
                "media_reference": media_ref,
                "markers": [],
            }
            video_items.append(v_item)
            audio_items.append(a_item)

        return {
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
                    "generator": "hawedit.edit_plan",
                    "plan_version": self.version,
                    "clip_id": self.clip_id,
                    "media_id": self.media_id,
                    "in_ms": self.time_mapping.clip_in_ms,
                    "out_ms": self.time_mapping.clip_out_ms,
                    "output_duration_ms": self.time_mapping.output_duration_ms,
                    "fps": fps,
                }
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "clip_id": self.clip_id,
            "media_id": self.media_id,
            "media_sha256": self.media_sha256,
            "brief": self.brief.to_dict(),
            "config": self.config.to_dict(),
            "time_mapping": self.time_mapping.to_dict(),
            "shot_cuts_ms": list(self.shot_cuts_ms),
            "punch_in_ms": list(self.punch_in_ms),
            "speaker_turns": [list(turn) for turn in self.speaker_turns],
            "sentences": [
                {
                    "words": [
                        {
                            "w": w.w,
                            "start_ms": w.start_ms,
                            "end_ms": w.end_ms,
                            "conf": w.conf,
                        }
                        for w in s.words
                    ],
                    "complete": s.complete,
                }
                for s in self.sentences
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualEditPlan:
        sentences: list[Sentence] = []
        for s_data in data.get("sentences", ()):
            words = tuple(
                Word(
                    w=str(w["w"]),
                    start_ms=int(w["start_ms"]),
                    end_ms=int(w["end_ms"]),
                    conf=float(w["conf"]),
                )
                for w in s_data["words"]
            )
            sentences.append(Sentence(words=words, complete=bool(s_data["complete"])))

        speaker_turns = tuple(
            (int(t[0]), int(t[1]), str(t[2])) for t in data.get("speaker_turns", ())
        )

        return cls(
            version=int(data["version"]),
            clip_id=str(data["clip_id"]),
            media_id=str(data["media_id"]),
            media_sha256=str(data["media_sha256"]),
            brief=EditorialBrief.from_dict(data["brief"]),
            config=EffectiveConfiguration.from_dict(data["config"]),
            time_mapping=SourceTimeMapping.from_dict(data["time_mapping"]),
            shot_cuts_ms=tuple(int(x) for x in data.get("shot_cuts_ms", ())),
            punch_in_ms=tuple(int(x) for x in data.get("punch_in_ms", ())),
            speaker_turns=speaker_turns,
            sentences=tuple(sentences),
        )

    @classmethod
    def from_json(cls, json_text: str) -> VisualEditPlan:
        data = json.loads(json_text)
        return cls.from_dict(data)
