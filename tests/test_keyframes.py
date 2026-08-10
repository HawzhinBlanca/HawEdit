from __future__ import annotations

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


# --- what adversarial pass #13 found unprotected (D-126) --------------------------------

# The fixture is three static shots, so each one's span has its own pixels. Measured:
#   0..1400 -> sha 46f2c52ce626999c, 3,332 bytes
#   1400..2800 -> sha 51f35b218c7a4534, 2,624 bytes
#   2800..4162 -> sha d700e83a931dfb52, 3,424 bytes
# The test above asserts the *timestamps*, and those are arithmetic over `in_ms`/`out_ms` — the
# request echoed back, M3.4's lesson. Replacing `-ss in_ms` with `-ss 0` left them unchanged and
# the suite green, so the bytes reaching a billed judge could come from anywhere in the media.
SHOT_SPANS = ((0, 1_400), (1_400, 2_800), (2_800, 4_162))


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
def test_frames_left_in_the_work_directory_by_an_earlier_run_are_refused(tmp_path: Path) -> None:
    """`len(paths) > count` had no test, and the state it guards is reachable: the work
    directory is named after the candidate, so asking for fewer frames than a previous run
    leaves that run's extra JPEGs behind for `glob` to find and send."""
    work = tmp_path / "stage4"
    extract_judge_frames(FIXTURE, 100, 4_100, work, count=8)
    with pytest.raises(KeyframeError, match="from an earlier run"):
        extract_judge_frames(FIXTURE, 100, 4_100, work, count=2)


def test_an_earlier_runs_frames_are_refused_even_when_the_count_is_unchanged(
    tmp_path: Path,
) -> None:
    """The hole the `len(paths) > count` form left open, and it is the reachable one.

    ffmpeg overwrites `judge-001.jpg` upward, so a run producing *fewer* frames than the last
    leaves the older, higher-numbered files behind and the total never exceeds `count`. Measured
    on this fixture: 20 frames from `0..4000`, then `0..13000` produced 6 and the call returned
    **20** — 14 of them from the previous extraction, handed to the judge as this candidate's
    evidence. D-153.
    """
    work = tmp_path / "stage4"
    extract_judge_frames(FIXTURE, 0, 4_000, work, count=20)
    with pytest.raises(KeyframeError, match="from an earlier run"):
        extract_judge_frames(FIXTURE, 0, 13_000, work, count=20)


# --- D-153: a frame must carry the time it came from -----------------------------------------
#
# `step_ms` was `(out_ms - in_ms) / len(paths)` — the number of frames that came back, not the
# rate ffmpeg was told to sample at. Those differ whenever the source runs out before the span
# does, and the surviving frames are then stretched across the whole request. Measured on this
# 4.162 s fixture, a `0..13000 ms` span returned 6 frames stamped 1083, 3250, 5417, 7583, 9750,
# 11917 — four past the end of the file, and two pairs were the same image.
# `evidence/frames-stamped-with-times-they-did-not-come-from.md`.
# =========================================================================================

FIXTURE_DURATION_MS = 4_162


def _expected_stamps(in_ms: int, out_ms: int, count: int, produced: int) -> list[int]:
    """Where the frames ffmpeg produced actually came from, at the rate it was given."""
    step = (out_ms - in_ms) / count
    return [round(in_ms + (index + 0.5) * step) for index in range(produced)]


@pytest.mark.parametrize(
    ("in_ms", "out_ms", "count"),
    [
        (0, 13_000, 20),  # span runs 8.8 s past the end of the file
        (0, 4_000, 20),  # the control: a span wholly inside it
        (100, 4_100, 5),
    ],
)
def test_a_frame_carries_the_time_it_came_from(
    tmp_path: Path, in_ms: int, out_ms: int, count: int
) -> None:
    """Asserted on the decoded frames, because the failure is invisible anywhere else.

    A mis-stamped frame is a valid JPEG of real pixels; `JudgeRequest` checks only that the
    timestamp lies inside the candidate span, which a stretched stamp does. The judge is simply
    told the shot is from a moment the video never had.
    """
    frames = extract_judge_frames(FIXTURE, in_ms, out_ms, tmp_path / "w", count=count)
    stamps = [frame.timestamp_ms for frame in frames]

    assert stamps == _expected_stamps(in_ms, out_ms, count, len(frames)), (
        "stamps were derived from the number of frames returned rather than the sampling rate"
    )
    past = [stamp for stamp in stamps if stamp > FIXTURE_DURATION_MS]
    assert not past, f"frames stamped past the end of a {FIXTURE_DURATION_MS} ms source: {past}"


def test_a_span_past_the_source_yields_fewer_frames_rather_than_invented_ones(
    tmp_path: Path,
) -> None:
    """The control that keeps the test above from passing on an empty result.

    Asking for a span three times the file's length must still return real frames from the part
    that exists — refusing everything, or returning one frame, would satisfy "nothing is stamped
    past the end" while measuring nothing.
    """
    frames = extract_judge_frames(FIXTURE, 0, 13_000, tmp_path / "w", count=20)
    assert 2 <= len(frames) < 20, f"expected a partial extraction, got {len(frames)}"
    assert all(frame.data.startswith(b"\xff\xd8") for frame in frames), "not JPEG payloads"
    assert max(frame.timestamp_ms for frame in frames) <= FIXTURE_DURATION_MS
