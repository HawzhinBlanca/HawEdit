from pathlib import Path

import pytest

from hawedit.v8.localization import assemble_translation, read_phrases, translate_sidecar


def test_translated_phrases_keep_speech_clock(tmp_path: Path) -> None:
    path = tmp_path / "clip.srt"
    path.write_bytes(
        (
            "1\r\n00:00:00,100 --> 00:00:00,500\r\nسڵاو\r\n\r\n"
            "2\r\n00:00:00,550 --> 00:00:01,100\r\nهاوڕێ\r\n\r\n"
            "3\r\n00:00:02,900 --> 00:00:03,900\r\nباشی؟\r\n"
        ).encode()
    )
    phrases = read_phrases(path)
    assert len(phrases) == 2
    result = assemble_translation(
        phrases, [{"id": 1, "text": "Hello, friend."}, {"id": 2, "text": "How are you?"}]
    )
    assert "00:00:00,100 --> 00:00:01,100" in result and "How are you?" in result
    with pytest.raises(ValueError, match="cue"):
        assemble_translation(phrases, [{"id": 2, "text": "missing"}])


def test_translate_sidecar_requires_loopback_omni_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "clip.srt"
    path.write_text("1\n00:00:00,100 --> 00:00:01,000\nسڵاو\n", encoding="utf-8")
    monkeypatch.setenv("HAWEDIT_OMNI_URL", "https://remote.invalid/v1")
    with pytest.raises(ValueError, match="loopback"):
        translate_sidecar(path, "en", "local-model")
