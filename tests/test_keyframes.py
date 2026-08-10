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


# --- what adversarial pass #13 found unprotected (D-126) --------------------------------

# The fixture is three static shots, so each one's span has its own pixels. Measured:
#   0..1400 -> sha 46f2c52ce626999c, 3,332 bytes
#   1400..2800 -> sha 51f35b218c7a4534, 2,624 bytes
#   2800..4162 -> sha d700e83a931dfb52, 3,424 bytes
# The test above asserts the *timestamps*, and those are arithmetic over `in_ms`/`out_ms` — the
# request echoed back, M3.4's lesson. Replacing `-ss in_ms` with `-ss 0` left them unchanged and
# the suite green, so the bytes reaching a billed judge could come from anywhere in the media.
SHOT_SPANS = ((0, 1_400), (1_400, 2_800), (2_800, 4_162))
FIXTURE_DURATION_MS = 4_162


def _expected_frame_stamps(in_ms: int, out_ms: int, count: int, produced: int) -> list[int]:
    step_ms = (out_ms - in_ms) / count
    return [round(in_ms + (index + 0.5) * step_ms) for index in range(produced)]


@needs_ffmpeg
@pytest.mark.parametrize(
    ("in_ms", "out_ms", "count"),
    ((0, 13_000, 20), (0, 4_000, 20), (100, 4_100, 5)),
)
def test_keyframe_timestamps_follow_the_requested_sampling_cadence(
    tmp_path: Path, in_ms: int, out_ms: int, count: int
) -> None:
    frames = extract_judge_frames(FIXTURE, in_ms, out_ms, tmp_path, count=count)
    stamps = [frame.timestamp_ms for frame in frames]

    assert stamps == _expected_frame_stamps(in_ms, out_ms, count, len(frames))
    assert not [stamp for stamp in stamps if stamp > FIXTURE_DURATION_MS]


@needs_ffmpeg
def test_a_span_past_the_source_returns_real_partial_frames_without_invented_times(
    tmp_path: Path,
) -> None:
    frames = extract_judge_frames(FIXTURE, 0, 13_000, tmp_path, count=20)
    assert 2 <= len(frames) < 20
    assert all(frame.data.startswith(b"\xff\xd8") for frame in frames)
    assert max(frame.timestamp_ms for frame in frames) <= FIXTURE_DURATION_MS


@needs_ffmpeg
def test_the_bytes_come_from_the_candidate_span_and_not_the_start_of_the_media(
    tmp_path: Path,
) -> None:
    """Asserted on the payloads, because the timestamps cannot tell.

    Each of the fixture's three shots is a different picture, so the same request against three
    different spans must return three different images. Sampling from 0 regardless of `in_ms`
    would return the first shot's pixels three times with the timestamps still arithmetically
    correct — a judgement about footage nobody sent, on a request that is charged for.
    """
    payloads = []
    for index, (in_ms, out_ms) in enumerate(SHOT_SPANS):
        frames = extract_judge_frames(FIXTURE, in_ms, out_ms, tmp_path / f"shot{index}", count=2)
        assert frames, (in_ms, out_ms)
        payloads.append(frames[0].data)
    assert len({bytes(p) for p in payloads}) == 3, (
        "two different candidate spans returned the same picture — the frames are not being "
        "cut from the span that was asked for"
    )


@needs_ffmpeg
def test_a_later_span_is_not_the_first_shot(tmp_path: Path) -> None:
    """The control, stated the other way round: the last shot's frames must differ from the
    first shot's *specifically*, which is the substitution `-ss 0` makes."""
    first = extract_judge_frames(FIXTURE, 0, 1_400, tmp_path / "a", count=1)[0].data
    last = extract_judge_frames(FIXTURE, 2_800, 4_162, tmp_path / "b", count=1)[0].data
    assert first != last


def test_a_span_with_no_duration_is_refused(tmp_path: Path) -> None:
    """The cell claims this refusal and nothing held it. A zero-length span would divide by
    zero building the fps filter, or produce whatever ffmpeg makes of `-t 0.000`."""
    for in_ms, out_ms in ((1_000, 1_000), (2_000, 1_500)):
        with pytest.raises(ValueError, match="no duration"):
            extract_judge_frames(FIXTURE, in_ms, out_ms, tmp_path, count=2)


def test_a_count_below_one_is_refused(tmp_path: Path) -> None:
    """The ceiling was tested and the floor was not. `count=0` divides the span by nothing and
    asks ffmpeg for zero frames, which is the empty request this module exists to prevent."""
    with pytest.raises(ValueError, match=r"1\.\.20"):
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=0)


def test_no_ffmpeg_is_refused_rather_than_returning_no_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The cell's own words: refused "rather than returning an empty tuple that would read as
    'no frames here'". An empty tuple is exactly what a text-only request looks like."""
    monkeypatch.setattr("hawedit.keyframes.find_ffmpeg", lambda: None)
    with pytest.raises(KeyframeError, match="ffmpeg"):
        extract_judge_frames(FIXTURE, 100, 4_100, tmp_path, count=2, ffmpeg=None)


@needs_ffmpeg
def test_an_ffmpeg_failure_is_refused_rather_than_returning_no_frames(tmp_path: Path) -> None:
    """A source ffmpeg cannot decode must not read as a candidate with no interesting frames."""
    not_a_video = tmp_path / "not-a-video.mp4"
    not_a_video.write_bytes(b"this is not a container")
    with pytest.raises(KeyframeError):
        extract_judge_frames(not_a_video, 0, 1_000, tmp_path / "work", count=2)


@needs_ffmpeg
def test_an_earlier_larger_run_cannot_inflate_a_later_result(tmp_path: Path) -> None:
    """Every invocation owns a private namespace, so stale output is never enumerated.

    The upstream adversarial test expected a second call to refuse because both calls shared one
    directory. HawEdit's stronger D-107 implementation instead gives each ffmpeg invocation a
    unique private directory: the later call must succeed with exactly the requested fresh count.
    """
    work = tmp_path / "stage4"
    first = extract_judge_frames(FIXTURE, 100, 4_100, work, count=8)
    second = extract_judge_frames(FIXTURE, 100, 4_100, work, count=2)
    assert len(first) == 8
    assert len(second) == 2
    assert not list(work.glob(".judge-*")), "private Stage 4 frames must be removed after copying"
