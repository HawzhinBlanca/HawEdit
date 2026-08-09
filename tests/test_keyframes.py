from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
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


@pytest.mark.parametrize("failure_at", ["work-dir", "private-dir"])
def test_keyframe_directory_creation_failures_are_normalized_before_any_pixels_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: str
) -> None:
    work_dir = tmp_path / "work"
    if failure_at == "work-dir":
        work_dir.write_bytes(b"not a directory")
    else:
        monkeypatch.setattr(
            "hawedit.keyframes.tempfile.mkdtemp",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                PermissionError("private directory denied")
            ),
        )

    with pytest.raises(KeyframeError, match="private Stage 4 keyframe directory") as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, work_dir, count=1, ffmpeg=Path("ffmpeg"))

    assert isinstance(caught.value.__cause__, OSError)
    assert not list(tmp_path.glob(".judge-*"))
    private = list(work_dir.glob(".judge-*")) if work_dir.is_dir() else []
    assert not private


def test_keyframe_directory_creation_programmer_error_still_escapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = AssertionError("tempfile invariant broke")
    monkeypatch.setattr(
        "hawedit.keyframes.tempfile.mkdtemp",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(AssertionError) as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path / "work", count=1, ffmpeg=Path("ffmpeg"))

    assert caught.value is failure


def test_keyframe_enumeration_failure_is_normalized_and_cleans_owned_pixels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        Path(command[-1].replace("%03d", "001")).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    real_glob = Path.glob

    def fail_private_enumeration(path: Path, pattern: str) -> Iterator[Path]:
        if path.name.startswith(".judge-") and pattern == "judge-*.jpg":
            raise PermissionError("directory enumeration denied")
        return real_glob(path, pattern)

    monkeypatch.setattr("hawedit.keyframes.subprocess.run", fake_run)
    monkeypatch.setattr(Path, "glob", fail_private_enumeration)
    with pytest.raises(KeyframeError, match="could not enumerate") as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=1, ffmpeg=Path("ffmpeg"))

    assert isinstance(caught.value.__cause__, PermissionError)
    assert not list(real_glob(tmp_path, ".judge-*"))


def test_keyframe_payload_read_failure_is_normalized_and_private_frames_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        Path(command[-1].replace("%03d", "001")).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    real_read_bytes = Path.read_bytes

    def fail_keyframe_read(path: Path) -> bytes:
        if path.suffix == ".jpg" and path.parent.name.startswith(".judge-"):
            raise PermissionError("scanner locked the frame")
        return real_read_bytes(path)

    monkeypatch.setattr("hawedit.keyframes.subprocess.run", fake_run)
    monkeypatch.setattr(Path, "read_bytes", fail_keyframe_read)
    with pytest.raises(KeyframeError, match="could not read extracted Stage 4 keyframe") as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=1, ffmpeg=Path("ffmpeg"))

    assert isinstance(caught.value.__cause__, PermissionError)
    assert not list(tmp_path.glob(".judge-*"))


def test_cleanup_failure_after_success_refuses_to_return_frames_and_names_retained_pixels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        Path(command[-1].replace("%03d", "001")).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    real_rmtree = shutil.rmtree

    def fail_cleanup(path: Path) -> None:
        raise PermissionError("directory is locked")

    monkeypatch.setattr("hawedit.keyframes.subprocess.run", fake_run)
    monkeypatch.setattr("hawedit.keyframes.shutil.rmtree", fail_cleanup)
    with pytest.raises(KeyframeError, match="private Stage 4 keyframe cleanup failed") as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=1, ffmpeg=Path("ffmpeg"))

    assert isinstance(caught.value.__cause__, PermissionError)
    private = list(tmp_path.glob(".judge-*"))
    assert len(private) == 1
    real_rmtree(private[0])


def test_cleanup_failure_adds_privacy_note_without_masking_active_body_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body_error = KeyframeError("ffmpeg produced no usable frame")

    def fail_body(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        raise body_error

    real_rmtree = shutil.rmtree

    def fail_cleanup(path: Path) -> None:
        raise PermissionError("directory is locked")

    monkeypatch.setattr("hawedit.keyframes.subprocess.run", fail_body)
    monkeypatch.setattr("hawedit.keyframes.shutil.rmtree", fail_cleanup)
    with pytest.raises(KeyframeError) as caught:
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=1, ffmpeg=Path("ffmpeg"))

    assert caught.value is body_error
    assert str(caught.value) == "ffmpeg produced no usable frame"
    assert any("private Stage 4 keyframe cleanup failed" in note for note in caught.value.__notes__)
    private = list(tmp_path.glob(".judge-*"))
    assert len(private) == 1
    real_rmtree(private[0])
