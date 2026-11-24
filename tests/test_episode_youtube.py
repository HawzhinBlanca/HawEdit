import json
from pathlib import Path

import pytest

from hawedit.v8.youtube import resolve_youtube_source, youtube_video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/RO1PmSoqmCM?t=10",
        "https://www.youtube.com/watch?v=RO1PmSoqmCM&list=test",
        "https://youtube.com/shorts/RO1PmSoqmCM",
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
    "url", ["https://example.org/watch?v=RO1PmSoqmCM", "https://youtube.com/playlist?list=abc"]
)
def test_unsupported_sources(url: str) -> None:
    with pytest.raises(ValueError):
        youtube_video_id(url)
