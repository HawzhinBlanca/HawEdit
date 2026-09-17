"""Unit tests for content-type profiles (Task T4.5, ADR D-265)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hawedit.captions import CaptionStyle
from hawedit.content_type import (
    CONTENT_TYPE_PROFILES,
    DEFAULT_CONTENT_TYPE,
    ContentType,
    get_content_type_profile,
)


def test_content_type_enum_members_and_string_values() -> None:
    """Task T4.5: ContentType enum exposes canonical genre identifiers."""
    assert ContentType.PODCAST.value == "podcast"
    assert ContentType.INTERVIEW.value == "interview"
    assert ContentType.NEWS.value == "news"
    assert ContentType.SOCIAL.value == "social"
    assert len(ContentType) == 4


def test_get_content_type_profile_returns_canonical_profiles() -> None:
    """Task T4.5: get_content_type_profile resolves enum and case-insensitive strings."""
    for ct in ContentType:
        prof_from_enum = get_content_type_profile(ct)
        prof_from_str = get_content_type_profile(ct.value)
        prof_from_upper = get_content_type_profile(ct.value.upper())
        assert prof_from_enum == prof_from_str == prof_from_upper == CONTENT_TYPE_PROFILES[ct]


def test_get_content_type_profile_defaults_to_podcast_on_none() -> None:
    """Task T4.5: None defaults to the PODCAST profile."""
    assert get_content_type_profile(None) == CONTENT_TYPE_PROFILES[DEFAULT_CONTENT_TYPE]


def test_get_content_type_profile_raises_on_unknown_string() -> None:
    """Task T4.5: Unknown content type strings raise ValueError naming valid choices."""
    with pytest.raises(ValueError, match="unrecognized content_type 'documentary'"):
        get_content_type_profile("documentary")


def test_news_profile_disables_punch_ins_and_eased_push() -> None:
    """Task T4.5: News profile disables jump-cut punch-ins and enables tighter framing."""
    news = get_content_type_profile(ContentType.NEWS)
    assert news.punch_in_cadence_ms == 0
    assert news.eased_push is False
    assert news.min_clip_ms == 15_000
    assert news.target_face_height_share == 0.18
    assert news.caption_style == CaptionStyle.LINE


def test_social_profile_uses_word_highlight_and_fast_cadence() -> None:
    """Task T4.5: Social profile uses energetic punch-ins and karaoke caption styling."""
    social = get_content_type_profile(ContentType.SOCIAL)
    assert social.punch_in_cadence_ms == 2_500
    assert social.eased_push is False
    assert social.min_clip_ms == 15_000
    assert social.caption_style == CaptionStyle.WORD_HIGHLIGHT


def test_podcast_profile_preserves_ep29_defaults() -> None:
    """Task T4.5: Podcast profile maintains 30s floor and relaxed pacing."""
    podcast = get_content_type_profile(ContentType.PODCAST)
    assert podcast.min_clip_ms == 30_000
    assert podcast.punch_in_cadence_ms == 4_000
    assert podcast.eased_push is False
    assert podcast.caption_style == CaptionStyle.WORD_HIGHLIGHT


def test_interview_profile_sets_moderate_cadence() -> None:
    """Task T4.5: Interview profile sets 25s span and 3s punch-in cadence."""
    interview = get_content_type_profile(ContentType.INTERVIEW)
    assert interview.min_clip_ms == 25_000
    assert interview.punch_in_cadence_ms == 3_000
    assert interview.eased_push is False
    assert interview.caption_style == CaptionStyle.WORD_HIGHLIGHT


def test_effective_configuration_preserves_explicit_overrides() -> None:
    """AC-08 / Task T05: Effective configuration resolves defaults, content-type profile,
    preset, and explicit overrides with documented precedence.
    """
    from hawedit.content_type import (
        ContentType,
        EffectiveConfiguration,
        resolve_effective_configuration,
        resolve_effective_configuration_from_args,
    )
    from hawedit.pipeline import build_parser

    # 1. Base defaults resolution
    base_cfg = resolve_effective_configuration()
    assert isinstance(base_cfg, EffectiveConfiguration)
    assert base_cfg.content_type == ContentType.PODCAST
    assert base_cfg.preset is None
    assert base_cfg.caption_style == CaptionStyle.WORD_HIGHLIGHT
    assert base_cfg.min_clip_ms == 30_000
    assert base_cfg.punch_in_cadence_ms == 4_000
    assert base_cfg.silence_threshold_ms == 0
    assert base_cfg.silence_target_gap_ms == 150
    assert base_cfg.two_person_split == "auto"
    assert base_cfg.static_crop is False
    assert base_cfg.hook_banner is False
    assert base_cfg.policy_version == "1.0"
    assert base_cfg.provenance_for("caption_style") == "content_type:podcast"

    # 2. Content-type overrides defaults
    news_cfg = resolve_effective_configuration(content_type="news")
    assert news_cfg.content_type == ContentType.NEWS
    assert news_cfg.caption_style == CaptionStyle.LINE
    assert news_cfg.min_clip_ms == 15_000
    assert news_cfg.punch_in_cadence_ms == 0
    assert news_cfg.target_face_height_share == 0.18
    assert news_cfg.provenance_for("caption_style") == "content_type:news"

    # 3. Preset overrides content-type
    viral_news_cfg = resolve_effective_configuration(content_type="news", preset="viral")
    assert viral_news_cfg.content_type == ContentType.NEWS
    assert viral_news_cfg.preset == "viral"
    assert viral_news_cfg.caption_style == CaptionStyle.RTL_WORD_HIGHLIGHT  # viral wins over news
    assert viral_news_cfg.silence_threshold_ms == 250
    assert viral_news_cfg.silence_target_gap_ms == 100
    assert viral_news_cfg.excise_fillers is True
    assert viral_news_cfg.hook_banner is True
    # News properties not overridden by viral preset are retained
    assert viral_news_cfg.min_clip_ms == 15_000
    assert viral_news_cfg.target_face_height_share == 0.18
    assert viral_news_cfg.provenance_for("caption_style") == "preset:viral"

    # 4. Explicit overrides win over BOTH preset and content-type
    explicit_cfg = resolve_effective_configuration(
        content_type="news",
        preset="viral",
        caption_style=CaptionStyle.LINE,
        min_clip_seconds=45,
        silence_threshold_ms=300,
        silence_target_gap_ms=120,
        excise_fillers=False,
        two_person_split="never",
    )
    assert explicit_cfg.caption_style == CaptionStyle.LINE
    assert explicit_cfg.provenance_for("caption_style") == "explicit"
    assert explicit_cfg.min_clip_ms == 45_000
    assert explicit_cfg.provenance_for("min_clip_ms") == "explicit"
    assert explicit_cfg.silence_threshold_ms == 300
    assert explicit_cfg.provenance_for("silence_threshold_ms") == "explicit"
    assert explicit_cfg.silence_target_gap_ms == 120
    assert explicit_cfg.provenance_for("silence_target_gap_ms") == "explicit"
    assert explicit_cfg.excise_fillers is False
    assert explicit_cfg.provenance_for("excise_fillers") == "explicit"
    assert explicit_cfg.two_person_split == "never"
    assert explicit_cfg.provenance_for("two_person_split") == "explicit"

    # 5. CLI arguments preserve explicit overrides
    parser = build_parser()
    args1 = parser.parse_args(
        ["video.mp4", "--preset", "broadcast", "--silence-threshold-ms", "200"]
    )
    cfg1 = resolve_effective_configuration_from_args(args1)
    assert cfg1.preset == "broadcast"
    assert cfg1.caption_style == CaptionStyle.BROADCAST_STUDIO
    assert cfg1.silence_threshold_ms == 200  # Explicit override beats broadcast preset default 0
    assert cfg1.provenance_for("silence_threshold_ms") == "explicit"

    args2 = parser.parse_args(["video.mp4", "--preset", "viral", "--caption-style", "line"])
    cfg2 = resolve_effective_configuration_from_args(args2)
    assert cfg2.preset == "viral"
    assert cfg2.caption_style == CaptionStyle.LINE  # Explicit override beats viral preset default
    assert cfg2.provenance_for("caption_style") == "explicit"
    assert cfg2.silence_threshold_ms == 250  # Unoverridden preset value intact

    args3 = parser.parse_args(["video.mp4", "--preset", "split", "--two-person-split", "never"])
    cfg3 = resolve_effective_configuration_from_args(args3)
    assert cfg3.preset == "split"
    assert cfg3.two_person_split == "never"  # Explicit override beats split preset default "always"
    assert cfg3.provenance_for("two_person_split") == "explicit"


def test_incompatible_configuration_refuses_before_model_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC-08 / Task T05: Incompatible configurations fail before model loading or expensive work."""
    from hawedit.content_type import resolve_effective_configuration
    from hawedit.pipeline import _build_and_run, build_parser

    # 1. static_crop + two_person_split='always' is mutually exclusive
    with pytest.raises(ValueError, match="static crop and two-person split are mutually exclusive"):
        resolve_effective_configuration(static_crop=True, two_person_split="always")

    # 2. static_crop + preset='split' is mutually exclusive
    with pytest.raises(ValueError, match="static crop and preset 'split' are mutually exclusive"):
        resolve_effective_configuration(static_crop=True, preset="split")

    # 3. silence_target_gap_ms >= silence_threshold_ms is invalid
    with pytest.raises(
        ValueError, match="silence_target_gap_ms .* must be strictly less than silence_threshold_ms"
    ):
        resolve_effective_configuration(silence_threshold_ms=200, silence_target_gap_ms=200)

    with pytest.raises(
        ValueError, match="silence_target_gap_ms .* must be strictly less than silence_threshold_ms"
    ):
        resolve_effective_configuration(silence_threshold_ms=200, silence_target_gap_ms=250)

    # 4. min_clip_ms must be positive
    with pytest.raises(ValueError, match="min_clip_ms must be positive"):
        resolve_effective_configuration(min_clip_ms=0)

    # 5. punch_in_cadence_ms under 1000ms causes visual strobe
    with pytest.raises(ValueError, match="punch_in_cadence_ms must be at least 1000 ms"):
        resolve_effective_configuration(punch_in_cadence_ms=500)

    # 6. Verify refusal in _build_and_run happens BEFORE any model loading or external call
    def forbidden_producer(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Model loader was invoked despite incompatible configuration!")

    import hawedit.asr as asr_mod

    monkeypatch.setattr(asr_mod, "create_omni_asr_producer", forbidden_producer)

    parser = build_parser()
    bad_args = parser.parse_args(
        [
            "video.mp4",
            "--omni-asr",
            "--preset",
            "split",
            "--static-crop",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )

    with pytest.raises(ValueError, match="static crop and preset 'split' are mutually exclusive"):
        _build_and_run(bad_args)
