from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.keyframes import extract_judge_frames

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg")


@needs_ffmpeg
def test_keyframes_are_real_jpegs_timestamped_inside_the_candidate(tmp_path: Path) -> None:
    frames = extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=5)
    assert len(frames) == 5
    assert [frame.timestamp_ms for frame in frames] == [500, 1_300, 2_100, 2_900, 3_700]
    assert all(frame.mime_type == "image/jpeg" for frame in frames)
    assert all(frame.data.startswith(b"\xff\xd8") and len(frame.data) > 1_000 for frame in frames)


def test_keyframes_refuse_more_than_the_stage_4_ceiling(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="1..20"):
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=21)
