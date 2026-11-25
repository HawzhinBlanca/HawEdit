"""Current-source tier: pin bytes, probe clocks/streams and decode a real 4K excerpt.

These are source admission and decode checks, not ASR/editorial/framing acceptance.
The legacy episode-29 assertions remain in test_real_media_tier.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hawedit.captions import ffprobe_for, find_ffmpeg
from media_profiles import current_media_records, validate_current_media


@pytest.fixture(scope="module")
def verified_current_media(media_root: Path) -> tuple[tuple[dict[str, Any], Path], ...]:
    return tuple(
        (record, validate_current_media(media_root, record)) for record in current_media_records()
    )


def test_current_sources_have_the_pinned_streams_and_container_clocks(
    verified_current_media: tuple[tuple[dict[str, Any], Path], ...],
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    for record, path in verified_current_media:
        result = subprocess.run(
            [
                str(ffprobe_for(ffmpeg)),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
        audio = next(stream for stream in data["streams"] if stream["codec_type"] == "audio")
        assert (video["width"], video["height"]) == (record["width"], record["height"])
        assert video["codec_name"] == record["video_codec"]
        assert video["r_frame_rate"] == record["fps"]
        assert audio["codec_name"] == record["audio_codec"]
        assert int(audio["sample_rate"]) == record["sample_rate"]
        assert audio["channels"] == record["channels"]
        assert abs(round(float(data["format"]["duration"]) * 1000) - record["duration_ms"]) <= 1


def test_current_4k_excerpt_decodes_video_and_original_audio(
    verified_current_media: tuple[tuple[dict[str, Any], Path], ...],
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    excerpt = next(
        path for record, path in verified_current_media if record["path"].startswith("excerpts/")
    )
    subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-xerror",
            "-nostdin",
            "-ss",
            "150",
            "-i",
            str(excerpt),
            "-t",
            "1",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
