import json
from pathlib import Path

import pytest

from hawedit.v8.youtube import resolve_youtube_source, youtube_video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/RO1PmSoqmCM?t=10",
        "  https://youtu.be/RO1PmSoqmCM/  ",
        "https://www.youtube.com/watch?v=RO1PmSoqmCM&list=test",
        "https://youtube.com/shorts/RO1PmSoqmCM/",
        "https://www.youtube.com/live/RO1PmSoqmCM/",
    ],
)
def test_one_episode_url(url: str) -> None:
    assert youtube_video_id(url) == "RO1PmSoqmCM"


def test_local_library_match_requires_same_video(tmp_path: Path) -> None:
    movie = tmp_path / "archived.mp4"
    movie.write_bytes(b"test-media")
    (tmp_path / "archived.info.json").write_text(
        json.dumps({"id": "RO1PmSoqmCM", "extractor": "youtube"})
    )
    assert resolve_youtube_source("https://youtu.be/RO1PmSoqmCM", tmp_path) == movie


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/watch?v=RO1PmSoqmCM",
        "https://youtube.com/playlist?list=abc",
        "https://youtube.com/shorts/RO1PmSoqmCM/extra",
    ],
)
def test_unsupported_sources(url: str) -> None:
    with pytest.raises(ValueError):
        youtube_video_id(url)


def test_stale_youtube_receipt_and_blank_media_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.studio_uploads import UploadStore
    from hawedit.studio_youtube import YouTubeImports
    from hawedit.v8.media_settings import media_setting

    monkeypatch.setenv("HAWEDIT_YOUTUBE_LIBRARY", "   ")
    monkeypatch.setattr("hawedit.v8.media_settings.ENV_FILE", tmp_path / ".env")
    assert media_setting("youtube_library") is None

    store = UploadStore(tmp_path / "uploads")
    receipts = store.root / "youtube-imports"
    receipts.mkdir(parents=True)
    stale = receipts / "RO1PmSoqmCM.json"
    stale.write_text(json.dumps({"source_id": "0" * 32}), encoding="utf-8")
    imports = YouTubeImports()
    status = imports.request(store, "https://youtu.be/RO1PmSoqmCM", start=False)
    assert status == {"state": "interrupted"}
    assert not stale.exists()
