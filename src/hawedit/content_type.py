"""Content-type profiles driving editorial defaults (Task T4.5, ADR D-265)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from hawedit.captions import CaptionStyle
from hawedit.clip import MIN_CANDIDATE_SPAN_MS

__all__ = [
    "CONTENT_TYPE_PROFILES",
    "DEFAULT_CONTENT_TYPE",
    "ContentType",
    "ContentTypeProfile",
    "get_content_type_profile",
]


class ContentType(str, Enum):
    """Supported content types per source material (Task T4.5)."""

    PODCAST = "podcast"
    INTERVIEW = "interview"
    NEWS = "news"
    SOCIAL = "social"


@dataclass(frozen=True, slots=True)
class ContentTypeProfile:
    """Editorial, visual, and pacing thresholds driven by content type (Task T4.5).

    Attributes:
        content_type: the ContentType enum value.
        min_clip_ms: minimum duration for candidate clips in milliseconds.
        caption_style: default caption styling layout.
        punch_in_cadence_ms: interval between dynamic punch-ins in milliseconds (0 to disable).
        eased_push: whether continuous eased creep zooms are enabled per shot.
        target_face_height_share: target face framing share (default 0.15, news 0.18).
        silence_threshold_ms: silence tightening pause floor in ms (0 to disable).
    """

    content_type: ContentType
    min_clip_ms: int
    caption_style: CaptionStyle
    punch_in_cadence_ms: int
    eased_push: bool
    target_face_height_share: float
    silence_threshold_ms: int = 0


CONTENT_TYPE_PROFILES: Final[dict[ContentType, ContentTypeProfile]] = {
    ContentType.PODCAST: ContentTypeProfile(
        content_type=ContentType.PODCAST,
        min_clip_ms=MIN_CANDIDATE_SPAN_MS,  # 30_000 (30s)
        caption_style=CaptionStyle.LINE,
        punch_in_cadence_ms=4_000,  # relaxed cadence for longform discussion
        eased_push=True,
        target_face_height_share=0.15,
        silence_threshold_ms=0,
    ),
    ContentType.INTERVIEW: ContentTypeProfile(
        content_type=ContentType.INTERVIEW,
        min_clip_ms=25_000,  # 25s
        caption_style=CaptionStyle.LINE,
        punch_in_cadence_ms=3_000,  # moderate cadence for back-and-forth Q&A
        eased_push=True,
        target_face_height_share=0.15,
        silence_threshold_ms=0,
    ),
    ContentType.NEWS: ContentTypeProfile(
        content_type=ContentType.NEWS,
        min_clip_ms=15_000,  # 15s
        caption_style=CaptionStyle.LINE,
        punch_in_cadence_ms=0,  # disabled: news broadcast anchors are never jump-zoomed
        eased_push=False,  # stable locked broadcast camera
        target_face_height_share=0.18,  # anchor seated closer to camera
        silence_threshold_ms=0,
    ),
    ContentType.SOCIAL: ContentTypeProfile(
        content_type=ContentType.SOCIAL,
        min_clip_ms=15_000,  # 15s
        caption_style=CaptionStyle.WORD_HIGHLIGHT,  # vibrant word-by-word animated karaoke
        punch_in_cadence_ms=2_500,  # energetic cadence
        eased_push=True,
        target_face_height_share=0.15,
        silence_threshold_ms=0,
    ),
}

DEFAULT_CONTENT_TYPE: Final[ContentType] = ContentType.PODCAST


def get_content_type_profile(content_type: ContentType | str | None) -> ContentTypeProfile:
    """Retrieve the ContentTypeProfile for the given content type.

    Args:
        content_type: ContentType enum, string representation, or None (defaults to PODCAST).

    Returns:
        ContentTypeProfile with associated editorial thresholds.

    Raises:
        ValueError: if content_type string is unrecognized.
    """
    if content_type is None:
        return CONTENT_TYPE_PROFILES[DEFAULT_CONTENT_TYPE]
    if isinstance(content_type, str):
        try:
            content_type = ContentType(content_type.lower())
        except ValueError:
            valid = ", ".join(repr(c.value) for c in ContentType)
            raise ValueError(
                f"unrecognized content_type {content_type!r}; expected one of: {valid}"
            ) from None
    return CONTENT_TYPE_PROFILES[content_type]
