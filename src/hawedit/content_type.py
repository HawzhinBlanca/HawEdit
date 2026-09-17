"""Content-type profiles driving editorial defaults (Task T4.5, ADR D-265)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

from hawedit.captions import CaptionStyle
from hawedit.clip import MIN_CANDIDATE_SPAN_MS

__all__ = [
    "CONTENT_TYPE_PROFILES",
    "DEFAULT_CONTENT_TYPE",
    "ContentType",
    "ContentTypeProfile",
    "EffectiveConfiguration",
    "get_content_type_profile",
    "resolve_effective_configuration",
    "resolve_effective_configuration_from_args",
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
        caption_style=CaptionStyle.WORD_HIGHLIGHT,
        punch_in_cadence_ms=4_000,  # relaxed cadence for longform discussion
        eased_push=False,
        target_face_height_share=0.15,
        silence_threshold_ms=0,
    ),
    ContentType.INTERVIEW: ContentTypeProfile(
        content_type=ContentType.INTERVIEW,
        min_clip_ms=25_000,  # 25s
        caption_style=CaptionStyle.WORD_HIGHLIGHT,
        punch_in_cadence_ms=3_000,  # moderate cadence for back-and-forth Q&A
        eased_push=False,
        target_face_height_share=0.15,
        silence_threshold_ms=0,
    ),
    ContentType.NEWS: ContentTypeProfile(
        content_type=ContentType.NEWS,
        min_clip_ms=15_000,  # 15s
        caption_style=CaptionStyle.LINE,  # formal lower band line captions for broadcast news
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
        eased_push=False,
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


@dataclass(frozen=True, slots=True)
class EffectiveConfiguration:
    """Resolved, immutable pipeline configuration with documented precedence (AC-08, Task T05).

    Precedence order:
    1. Base defaults (system baseline)
    2. Content-type profile (editorial defaults for genre)
    3. Production preset (workflow defaults: broadcast, viral, split)
    4. Explicit options (operator overrides)
    """

    content_type: ContentType
    preset: str | None
    caption_style: CaptionStyle
    min_clip_ms: int
    punch_in_cadence_ms: int
    eased_push: bool
    target_face_height_share: float
    silence_threshold_ms: int
    silence_target_gap_ms: int
    excise_fillers: bool
    two_person_split: str  # "auto" | "always" | "never"
    static_crop: bool
    hook_banner: bool
    keyword_emphasis: bool = True
    brand_kit: str | None = None
    logo: str | None = None
    speaker_metadata: str | None = None
    progress_bar: bool = False
    end_card: bool = False
    music_bed: str | None = None
    music_ducking_volume: float = 0.25
    policy_version: str = "1.0"
    provenance: tuple[tuple[str, str], ...] = ()

    def provenance_for(self, key: str) -> str | None:
        """Return the source provenance for a specific configuration parameter."""
        for k, src in self.provenance:
            if k == key:
                return src
        return None


def resolve_effective_configuration(
    *,
    content_type: ContentType | str | None = None,
    preset: str | None = None,
    caption_style: CaptionStyle | str | None = None,
    min_clip_ms: int | None = None,
    min_clip_seconds: float | None = None,
    punch_in_cadence_ms: int | None = None,
    eased_push: bool | None = None,
    target_face_height_share: float | None = None,
    silence_threshold_ms: int | None = None,
    silence_target_gap_ms: int | None = None,
    excise_fillers: bool | None = None,
    two_person_split: str | None = None,
    static_crop: bool | None = None,
    hook_banner: bool | None = None,
    keyword_emphasis: bool | None = None,
    brand_kit: str | None = None,
    logo: str | None = None,
    speaker_metadata: str | None = None,
    progress_bar: bool | None = None,
    end_card: bool | None = None,
    music_bed: str | None = None,
    music_ducking_volume: float | None = None,
    work_dir: Path | None = None,
    explicit_keys: set[str] | frozenset[str] | None = None,
) -> EffectiveConfiguration:
    """Resolve content type, preset, defaults, and explicit options into one EffectiveConfiguration.

    Enforces documented precedence (defaults -> content_type -> preset -> explicit overrides)
    and strictly validates constraints, rejecting incompatible inputs before expensive
    model loading.

    Raises:
        ValueError: if inputs are incompatible or invalid.
    """
    prov: dict[str, str] = {}

    # 1. Determine which keys were explicitly supplied by the caller
    explicit: set[str]
    if explicit_keys is not None:
        explicit = set(explicit_keys)
    else:
        explicit = set()
        if content_type is not None:
            explicit.add("content_type")
        if preset is not None:
            explicit.add("preset")
        if caption_style is not None:
            explicit.add("caption_style")
        if min_clip_ms is not None:
            explicit.add("min_clip_ms")
        if min_clip_seconds is not None:
            explicit.add("min_clip_seconds")
            explicit.add("min_clip_ms")
        if punch_in_cadence_ms is not None:
            explicit.add("punch_in_cadence_ms")
        if eased_push is not None:
            explicit.add("eased_push")
        if target_face_height_share is not None:
            explicit.add("target_face_height_share")
        if silence_threshold_ms is not None:
            explicit.add("silence_threshold_ms")
        if silence_target_gap_ms is not None:
            explicit.add("silence_target_gap_ms")
        if excise_fillers is not None:
            explicit.add("excise_fillers")
        if two_person_split is not None:
            explicit.add("two_person_split")
        if static_crop is not None:
            explicit.add("static_crop")
        if hook_banner is not None:
            explicit.add("hook_banner")
        if keyword_emphasis is not None:
            explicit.add("keyword_emphasis")
        if brand_kit is not None:
            explicit.add("brand_kit")
        if logo is not None:
            explicit.add("logo")
        if speaker_metadata is not None:
            explicit.add("speaker_metadata")
        if progress_bar is not None:
            explicit.add("progress_bar")
        if end_card is not None:
            explicit.add("end_card")
        if music_bed is not None:
            explicit.add("music_bed")
        if music_ducking_volume is not None:
            explicit.add("music_ducking_volume")

    # 2. Resolve content type
    ct: ContentType
    if content_type is None:
        ct = DEFAULT_CONTENT_TYPE
        prov["content_type"] = "default"
    elif isinstance(content_type, ContentType):
        ct = content_type
        prov["content_type"] = "explicit" if "content_type" in explicit else "default"
    else:
        try:
            ct = ContentType(content_type.lower())
        except ValueError:
            valid = ", ".join(repr(c.value) for c in ContentType)
            raise ValueError(
                f"unrecognized content_type {content_type!r}; expected one of: {valid}"
            ) from None
        prov["content_type"] = "explicit" if "content_type" in explicit else "default"

    ct_profile = get_content_type_profile(ct)
    ct_source = f"content_type:{ct.value}"

    # 3. Base values from content_type profile
    res_caption_style = ct_profile.caption_style
    prov["caption_style"] = ct_source
    res_min_clip_ms = ct_profile.min_clip_ms
    prov["min_clip_ms"] = ct_source
    res_punch_in_cadence_ms = ct_profile.punch_in_cadence_ms
    prov["punch_in_cadence_ms"] = ct_source
    res_eased_push = ct_profile.eased_push
    prov["eased_push"] = ct_source
    res_target_face_height_share = ct_profile.target_face_height_share
    prov["target_face_height_share"] = ct_source
    res_silence_threshold_ms = ct_profile.silence_threshold_ms
    prov["silence_threshold_ms"] = ct_source

    res_silence_target_gap_ms = 150
    prov["silence_target_gap_ms"] = "default"
    res_excise_fillers = False
    prov["excise_fillers"] = "default"
    res_two_person_split = "auto"
    prov["two_person_split"] = "default"
    res_static_crop = False
    prov["static_crop"] = "default"
    res_hook_banner = False
    prov["hook_banner"] = "default"
    res_keyword_emphasis = True
    prov["keyword_emphasis"] = "default"

    res_brand_kit = brand_kit
    res_logo = logo
    res_speaker_metadata = speaker_metadata
    res_progress_bar = bool(progress_bar) if progress_bar is not None else False
    res_end_card = bool(end_card) if end_card is not None else False
    res_music_bed = music_bed
    res_music_ducking_volume = music_ducking_volume if music_ducking_volume is not None else 0.25

    # 4. Preset application
    resolved_preset: str | None = None
    if preset is not None:
        resolved_preset = preset.lower()
        if resolved_preset not in ("broadcast", "viral", "split"):
            raise ValueError(
                f"unrecognized preset {preset!r}; expected one of: 'broadcast', 'viral', 'split'"
            )
        preset_src = f"preset:{resolved_preset}"

        if resolved_preset == "broadcast":
            if "caption_style" not in explicit:
                res_caption_style = CaptionStyle.BROADCAST_STUDIO
                prov["caption_style"] = preset_src
            if "silence_threshold_ms" not in explicit:
                res_silence_threshold_ms = 0
                prov["silence_threshold_ms"] = preset_src
            if "hook_banner" not in explicit:
                res_hook_banner = True
                prov["hook_banner"] = preset_src
            if work_dir is not None:
                if "brand_kit" not in explicit and res_brand_kit is None:
                    bk = work_dir / "brand_kit.json"
                    if bk.is_file():
                        res_brand_kit = str(bk)
                        prov["brand_kit"] = preset_src
                if "logo" not in explicit and res_logo is None:
                    lg = work_dir / "zar_logo.png"
                    if lg.is_file():
                        res_logo = str(lg)
                        prov["logo"] = preset_src
                if "speaker_metadata" not in explicit and res_speaker_metadata is None:
                    sm = work_dir / "speaker_metadata.json"
                    if sm.is_file():
                        res_speaker_metadata = str(sm)
                        prov["speaker_metadata"] = preset_src
        elif resolved_preset == "viral":
            if "caption_style" not in explicit:
                res_caption_style = CaptionStyle.RTL_WORD_HIGHLIGHT
                prov["caption_style"] = preset_src
            if "silence_threshold_ms" not in explicit:
                res_silence_threshold_ms = 250
                prov["silence_threshold_ms"] = preset_src
            if "silence_target_gap_ms" not in explicit:
                res_silence_target_gap_ms = 100
                prov["silence_target_gap_ms"] = preset_src
            if "excise_fillers" not in explicit:
                res_excise_fillers = True
                prov["excise_fillers"] = preset_src
            if "hook_banner" not in explicit:
                res_hook_banner = True
                prov["hook_banner"] = preset_src
        elif resolved_preset == "split":
            if "two_person_split" not in explicit:
                res_two_person_split = "always"
                prov["two_person_split"] = preset_src
            if "caption_style" not in explicit:
                res_caption_style = CaptionStyle.BROADCAST_STUDIO
                prov["caption_style"] = preset_src

    # 5. Apply explicit overrides
    if "caption_style" in explicit and caption_style is not None:
        res_caption_style = CaptionStyle(caption_style)
        prov["caption_style"] = "explicit"
    if "min_clip_seconds" in explicit and min_clip_seconds is not None:
        if min_clip_seconds <= 0:
            raise ValueError("--min-clip-seconds must be greater than 0")
        res_min_clip_ms = int(min_clip_seconds * 1000)
        prov["min_clip_ms"] = "explicit"
    elif "min_clip_ms" in explicit and min_clip_ms is not None:
        res_min_clip_ms = min_clip_ms
        prov["min_clip_ms"] = "explicit"
    if "punch_in_cadence_ms" in explicit and punch_in_cadence_ms is not None:
        res_punch_in_cadence_ms = punch_in_cadence_ms
        prov["punch_in_cadence_ms"] = "explicit"
    if "eased_push" in explicit and eased_push is not None:
        res_eased_push = eased_push
        prov["eased_push"] = "explicit"
    if "target_face_height_share" in explicit and target_face_height_share is not None:
        res_target_face_height_share = target_face_height_share
        prov["target_face_height_share"] = "explicit"
    if "silence_threshold_ms" in explicit and silence_threshold_ms is not None:
        res_silence_threshold_ms = silence_threshold_ms
        prov["silence_threshold_ms"] = "explicit"
    if "silence_target_gap_ms" in explicit and silence_target_gap_ms is not None:
        res_silence_target_gap_ms = silence_target_gap_ms
        prov["silence_target_gap_ms"] = "explicit"
    if "excise_fillers" in explicit and excise_fillers is not None:
        res_excise_fillers = excise_fillers
        prov["excise_fillers"] = "explicit"
    if "two_person_split" in explicit and two_person_split is not None:
        res_two_person_split = two_person_split
        prov["two_person_split"] = "explicit"
    if "static_crop" in explicit and static_crop is not None:
        res_static_crop = static_crop
        prov["static_crop"] = "explicit"
    if "hook_banner" in explicit and hook_banner is not None:
        res_hook_banner = hook_banner
        prov["hook_banner"] = "explicit"
    if "keyword_emphasis" in explicit and keyword_emphasis is not None:
        res_keyword_emphasis = keyword_emphasis
        prov["keyword_emphasis"] = "explicit"
    if "brand_kit" in explicit and brand_kit is not None:
        res_brand_kit = brand_kit
        prov["brand_kit"] = "explicit"
    if "logo" in explicit and logo is not None:
        res_logo = logo
        prov["logo"] = "explicit"
    if "speaker_metadata" in explicit and speaker_metadata is not None:
        res_speaker_metadata = speaker_metadata
        prov["speaker_metadata"] = "explicit"
    if "progress_bar" in explicit and progress_bar is not None:
        res_progress_bar = progress_bar
        prov["progress_bar"] = "explicit"
    if "end_card" in explicit and end_card is not None:
        res_end_card = end_card
        prov["end_card"] = "explicit"
    if "music_bed" in explicit and music_bed is not None:
        res_music_bed = music_bed
        prov["music_bed"] = "explicit"
    if "music_ducking_volume" in explicit and music_ducking_volume is not None:
        res_music_ducking_volume = music_ducking_volume
        prov["music_ducking_volume"] = "explicit"

    # 6. Reject incompatible configurations before expensive work
    if res_two_person_split not in ("auto", "always", "never"):
        raise ValueError(
            f"two_person_split must be 'auto', 'always', or 'never', got {res_two_person_split!r}"
        )

    if res_static_crop and resolved_preset == "split" and "two_person_split" not in explicit:
        raise ValueError("static crop and preset 'split' are mutually exclusive")

    if res_static_crop and res_two_person_split == "always":
        raise ValueError("static crop and two-person split are mutually exclusive")

    if res_silence_threshold_ms > 0 and res_silence_target_gap_ms >= res_silence_threshold_ms:
        raise ValueError(
            f"silence_target_gap_ms ({res_silence_target_gap_ms}) must be strictly less than "
            f"silence_threshold_ms ({res_silence_threshold_ms})"
        )

    if res_min_clip_ms <= 0:
        raise ValueError(f"min_clip_ms must be positive, got {res_min_clip_ms}")

    if res_punch_in_cadence_ms < 0:
        raise ValueError(f"punch_in_cadence_ms must be non-negative, got {res_punch_in_cadence_ms}")
    if 0 < res_punch_in_cadence_ms < 1000:
        raise ValueError(
            f"punch_in_cadence_ms must be at least 1000 ms to prevent visual strobe effects, "
            f"got {res_punch_in_cadence_ms}"
        )

    if not (0.0 < res_target_face_height_share <= 1.0):
        raise ValueError(
            f"target_face_height_share must be in (0.0, 1.0], got {res_target_face_height_share}"
        )

    if not (0.0 <= res_music_ducking_volume <= 1.0):
        raise ValueError(
            f"music_ducking_volume must be in [0.0, 1.0], got {res_music_ducking_volume}"
        )

    return EffectiveConfiguration(
        content_type=ct,
        preset=resolved_preset,
        caption_style=res_caption_style,
        min_clip_ms=res_min_clip_ms,
        punch_in_cadence_ms=res_punch_in_cadence_ms,
        eased_push=res_eased_push,
        target_face_height_share=res_target_face_height_share,
        silence_threshold_ms=res_silence_threshold_ms,
        silence_target_gap_ms=res_silence_target_gap_ms,
        excise_fillers=res_excise_fillers,
        two_person_split=res_two_person_split,
        static_crop=res_static_crop,
        hook_banner=res_hook_banner,
        keyword_emphasis=res_keyword_emphasis,
        brand_kit=res_brand_kit,
        logo=res_logo,
        speaker_metadata=res_speaker_metadata,
        progress_bar=res_progress_bar,
        end_card=res_end_card,
        music_bed=res_music_bed,
        music_ducking_volume=res_music_ducking_volume,
        policy_version="1.0",
        provenance=tuple(sorted(prov.items())),
    )


def resolve_effective_configuration_from_args(args: Any) -> EffectiveConfiguration:
    """Resolve effective configuration from an argparse.Namespace."""
    explicit_keys = getattr(args, "_explicit_keys", None)
    return resolve_effective_configuration(
        content_type=getattr(args, "content_type", None),
        preset=getattr(args, "preset", None),
        caption_style=getattr(args, "caption_style", None),
        min_clip_seconds=getattr(args, "min_clip_seconds", None),
        silence_threshold_ms=getattr(args, "silence_threshold_ms", None),
        silence_target_gap_ms=getattr(args, "silence_target_gap_ms", None),
        excise_fillers=getattr(args, "excise_fillers", None),
        two_person_split=getattr(args, "two_person_split", None),
        static_crop=getattr(args, "static_crop", None),
        hook_banner=getattr(args, "hook_banner", None),
        keyword_emphasis=getattr(args, "keyword_emphasis", None),
        brand_kit=getattr(args, "brand_kit", None),
        logo=getattr(args, "logo", None),
        speaker_metadata=getattr(args, "speaker_metadata", None),
        progress_bar=getattr(args, "progress_bar", None),
        end_card=getattr(args, "end_card", None),
        music_bed=getattr(args, "music_bed", None),
        music_ducking_volume=getattr(args, "music_ducking_volume", None),
        work_dir=getattr(args, "work_dir", None),
        explicit_keys=explicit_keys,
    )
