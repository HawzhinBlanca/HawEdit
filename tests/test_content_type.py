"""Unit tests for content-type profiles (Task T4.5, ADR D-265)."""

from __future__ import annotations

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
