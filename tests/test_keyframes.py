from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.keyframes import KeyframeError, extract_judge_frames

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


def test_keyframes_never_promote_stale_outputs_from_a_prior_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tuple(tmp_path / f"judge-{index:03d}.jpg" for index in range(1, 21))
    for path in stale:
        path.write_bytes(b"stale")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        pattern = command[-1]
        for index in range(1, 6):
            Path(pattern.replace("%03d", f"{index:03d}")).write_bytes(f"new-{index}".encode())
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("hawedit.keyframes.subprocess.run", fake_run)
    frames = extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=5, ffmpeg=Path("ffmpeg"))

    assert [frame.data for frame in frames] == [f"new-{index}".encode() for index in range(1, 6)]
    assert all(path.read_bytes() == b"stale" for path in stale)
    assert not list(tmp_path.glob(".judge-*"))


def test_keyframe_ffmpeg_launch_failure_is_normalized_and_cleans_owned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError("binary disappeared")

    monkeypatch.setattr("hawedit.keyframes.subprocess.run", refuse)
    with pytest.raises(KeyframeError, match="cannot launch ffmpeg") as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=5, ffmpeg=Path("missing-ffmpeg"))

    assert isinstance(caught.value.__cause__, FileNotFoundError)
    assert not list(tmp_path.glob(".judge-*"))
