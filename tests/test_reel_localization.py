from pathlib import Path

import pytest

from hawedit.v8.localization import assemble_translation, read_phrases


def test_translated_phrases_keep_speech_clock(tmp_path: Path) -> None:
    path = tmp_path / "clip.srt"
    path.write_text(
        "1\n00:00:00,100 --> 00:00:00,500\nسڵاو\n\n"
        "2\n00:00:00,550 --> 00:00:01,100\nهاوڕێ\n\n"
        "3\n00:00:02,900 --> 00:00:03,900\nباشی؟\n",
        encoding="utf-8",
    )
    phrases = read_phrases(path)
    assert len(phrases) == 2
    result = assemble_translation(
        phrases, [{"id": 1, "text": "Hello, friend."}, {"id": 2, "text": "How are you?"}]
    )
    assert "00:00:00,100 --> 00:00:01,100" in result and "How are you?" in result
    with pytest.raises(ValueError, match="cue"):
        assemble_translation(phrases, [{"id": 2, "text": "missing"}])
