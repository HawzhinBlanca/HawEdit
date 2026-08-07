"""§3 Stage 0 — ingest, run against a real media file rather than a mock.

Every assertion here that matters runs ffmpeg, PySceneDetect and Silero VAD for real, on
`fixtures/kurdish-speech-3cuts.mp4`. Its construction is the point: three 1.4-second colour
segments concatenated, so the shot cuts are known to be at exactly 1400 ms and 2800 ms, over
a Kurdish (Kurmanji) espeak-ng utterance of two sentences with a pause between them. Ground
truth is a property of how the file was built, not of what the detector happened to say.

The synthetic voice is a positive control for VAD wiring and **nothing else**. It is not
Sorani, it is not human, and no accuracy claim about §8.1 can be built on it — the real
labelled set is `BLOCKED.md` #1. What it does prove is that `detect_speech` finds speech
where speech is, finds none where it isn't, and that the two utterances come back as two
segments rather than one.

The most load-bearing test in this file is the one that measures why shot detection runs on
the source and not the proxy (D-023). §3 Stage 0 produces a 1 fps proxy and §3 Stage 5 matches
cuts against a 400 ms window; 1 fps cannot express 400 ms. That is an argument until it is
measured, so it is measured.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.ingest import (
    LOUDNORM_FILTER,
    MAX_SPEECH_DURATION_S,
    OMNIASR_CEILING_S,
    PROXY_CRF,
    PROXY_FPS,
    PROXY_HEIGHT,
    TARGET_SAMPLE_RATE,
    IngestError,
    IngestResult,
    SpeechSegment,
    assert_within_asr_ceiling,
    detect_shots,
    detect_speech,
    extract_audio,
    extract_proxy,
    ingest,
    media_stack_available,
    probe_duration_ms,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"

# How the fixture was built: three 1.4 s segments, so two cuts.
GROUND_TRUTH_CUTS_MS = (1_400, 2_800)
# §3 Stage 5 matches a shot cut against a 400 ms window. A detector whose error approaches
# that window is useless to Stage 5 even when it "finds" the cut, so the tolerance here is a
# quarter of it — tight enough that passing means something.
CUT_TOLERANCE_MS = 100

# Not `find_spec`: see ingest.media_stack_available. A module that imports and cannot
# work is exactly what slipped past CI-less local runs.
MEDIA_STACK = media_stack_available()

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
needs_media_stack = pytest.mark.skipif(
    not MEDIA_STACK, reason="media stack absent — install '.[media]'"
)


def test_the_fixture_is_committed() -> None:
    assert FIXTURE.exists(), f"ingest fixture missing at {FIXTURE}"


# --- §3 Stage 0's literal parameters ------------------------------------------------------


def test_the_stage_0_constants_are_the_blueprints() -> None:
    assert TARGET_SAMPLE_RATE == 16_000
    assert LOUDNORM_FILTER == "loudnorm=I=-23:TP=-2:LRA=7"
    assert (PROXY_FPS, PROXY_HEIGHT, PROXY_CRF) == (1, 720, 28)


def test_the_vad_ceiling_leaves_a_margin_under_the_asr_limit() -> None:
    """38 s is not a round number; it is 40 s minus room for VAD's own imprecision.

    §3 Stage 1 gives OmniASR a 40 s interface limit and §3 Stage 0 sets
    max_speech_duration_s=38. If the two were ever set equal, a segment measured at exactly
    the boundary would arrive at Stage 1 as a decode failure with nothing pointing back here.
    """
    assert MAX_SPEECH_DURATION_S < OMNIASR_CEILING_S
    assert OMNIASR_CEILING_S - MAX_SPEECH_DURATION_S >= 2.0


# --- §6: many single-threaded processes, not one with -threads 64 -------------------------


def _spy_commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture ffmpeg argv without running it."""
    seen: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr("hawedit.ingest._run", fake_run)
    monkeypatch.setattr("hawedit.ingest._assert_audio_format", lambda _p: None)
    return seen


def test_audio_extraction_is_single_threaded_and_loudness_normalised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§6: the 3990X is Zen 2 — modest single-thread speed, enormous parallelism.

    `-threads 1` is the kind of flag someone "optimises" away without reading §6, so it is
    asserted rather than trusted to survive.
    """
    seen = _spy_commands(monkeypatch)
    extract_audio(FIXTURE, tmp_path / "a.wav", ffmpeg=Path("/bin/ffmpeg"))
    (command,) = seen
    assert "-threads" in command and command[command.index("-threads") + 1] == "1"
    assert LOUDNORM_FILTER in command
    assert command[command.index("-ar") + 1] == str(TARGET_SAMPLE_RATE)
    assert command[command.index("-ac") + 1] == "1"


def test_proxy_extraction_is_single_threaded_and_matches_the_blueprint_filter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = _spy_commands(monkeypatch)
    extract_proxy(FIXTURE, tmp_path / "p.mp4", ffmpeg=Path("/bin/ffmpeg"))
    (command,) = seen
    assert "-threads" in command and command[command.index("-threads") + 1] == "1"
    assert f"fps={PROXY_FPS},scale=-2:{PROXY_HEIGHT}" in command
    assert command[command.index("-crf") + 1] == str(PROXY_CRF)
    assert "-an" in command, "the proxy carries no audio — audio.wav is the audio artifact"


# --- the audio artifact, for real ---------------------------------------------------------


@needs_ffmpeg
def test_extracted_audio_is_16k_mono_16bit(tmp_path: Path) -> None:
    """Stage 1 and the VAD both assume this. Checking here is where the fix is obvious."""
    out = extract_audio(FIXTURE, tmp_path / "audio.wav")
    with wave.open(str(out), "rb") as handle:
        assert (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) == (
            TARGET_SAMPLE_RATE,
            1,
            2,
        )


@needs_ffmpeg
def test_audio_in_the_wrong_format_is_refused_at_stage_0(tmp_path: Path) -> None:
    """A 44.1 kHz stereo file reaching Stage 1 fails there with no mention of the VAD."""
    from hawedit.ingest import _assert_audio_format

    wrong = tmp_path / "wrong.wav"
    with wave.open(str(wrong), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 400)
    with pytest.raises(IngestError, match="16000 Hz mono"):
        _assert_audio_format(wrong)


@needs_ffmpeg
def test_probe_reports_the_fixtures_real_duration() -> None:
    assert probe_duration_ms(FIXTURE) == pytest.approx(4_162, abs=50)


# --- shot detection, and why it runs on the source ----------------------------------------


@needs_ffmpeg
@needs_media_stack
def test_shot_cuts_are_found_where_the_fixture_was_cut() -> None:
    """Ground truth comes from how the file was assembled, not from a previous run."""
    cuts = detect_shots(FIXTURE)
    assert len(cuts) == len(GROUND_TRUTH_CUTS_MS), f"expected 2 cuts, got {cuts}"
    for found, expected in zip(cuts, GROUND_TRUTH_CUTS_MS, strict=True):
        assert abs(found - expected) <= CUT_TOLERANCE_MS, f"cut at {found} ms, expected {expected}"


@needs_ffmpeg
@needs_media_stack
def test_detecting_on_the_proxy_is_coarser_than_stage_5s_tolerance(tmp_path: Path) -> None:
    """D-023, measured rather than argued.

    The proxy is 1 fps, so every event it can express lands on a whole second. §3 Stage 5
    matches a shot cut against a 400 ms window. Detecting on the proxy therefore produces cuts
    that are either wrong by more than the tolerance they are compared against, or right by
    rounding — and a pipeline whose correctness depends on rounding is not correct.
    """
    proxy = extract_proxy(FIXTURE, tmp_path / "proxy.mp4")
    proxy_cuts = detect_shots(proxy)
    source_cuts = detect_shots(FIXTURE)

    def worst_error(cuts: tuple[int, ...]) -> int:
        if not cuts:
            return 10**6  # found nothing at all — the worst outcome available
        return max(min(abs(c - truth) for c in cuts) for truth in GROUND_TRUTH_CUTS_MS)

    assert worst_error(source_cuts) <= CUT_TOLERANCE_MS
    assert worst_error(proxy_cuts) > CUT_TOLERANCE_MS, (
        f"proxy cuts {proxy_cuts} were as good as source cuts {source_cuts} on this fixture — "
        f"if that holds generally, D-023 needs revisiting"
    )


# --- VAD, with both controls --------------------------------------------------------------


@needs_ffmpeg
@needs_media_stack
def test_vad_finds_the_two_utterances_in_the_fixture(tmp_path: Path) -> None:
    """Positive control. The fixture is two sentences with a pause, so it is two segments."""
    audio = extract_audio(FIXTURE, tmp_path / "audio.wav")
    segments = detect_speech(audio)
    assert len(segments) == 2, f"expected the two utterances, got {segments}"
    assert segments[0].end_ms < segments[1].start_ms, "segments must not overlap"
    assert all(s.duration_s > 0.5 for s in segments)


@needs_media_stack
def test_vad_finds_no_speech_in_silence(tmp_path: Path) -> None:
    """Negative control. Without it, a VAD that returns everything would pass the test above."""
    silent = tmp_path / "silence.wav"
    with wave.open(str(silent), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(TARGET_SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * (TARGET_SAMPLE_RATE * 4))
    assert detect_speech(silent) == ()


@needs_ffmpeg
@needs_media_stack
def test_no_vad_segment_from_long_audio_exceeds_the_asr_ceiling(tmp_path: Path) -> None:
    """A minute of real speech, chunked. Every segment must be something Stage 1 can accept.

    The fixture is repeated to build the long file, so its natural pauses are repeated too and
    VAD has legitimate places to split — this does not isolate `max_speech_duration_s` as the
    cause of any particular boundary. What it does establish is the property Stage 1 depends
    on, on real audio of realistic length, rather than on a hand-built segment list.
    """
    audio = extract_audio(FIXTURE, tmp_path / "audio.wav")
    with wave.open(str(audio), "rb") as handle:
        params, frames = handle.getparams(), handle.readframes(handle.getnframes())
    long_audio = tmp_path / "long.wav"
    with wave.open(str(long_audio), "wb") as handle:
        handle.setparams(params)
        handle.writeframes(frames * 15)  # ~62 s, comfortably past the 40 s ceiling

    segments = detect_speech(long_audio)
    assert segments, "15 repetitions of speech must not come back as silence"
    assert max(s.duration_s for s in segments) <= MAX_SPEECH_DURATION_S
    assert_within_asr_ceiling(segments)  # must not raise


def test_an_over_ceiling_segment_is_refused_with_the_reason() -> None:
    """§3 Stage 1's 40 s is an interface limit, so this is a failure and not a slow path."""
    with pytest.raises(IngestError, match="ceiling"):
        assert_within_asr_ceiling((SpeechSegment(start_ms=0, end_ms=41_000),))


def test_a_segment_at_the_ceiling_is_accepted() -> None:
    assert_within_asr_ceiling((SpeechSegment(start_ms=0, end_ms=40_000),))


# --- the artifact ------------------------------------------------------------------------


@needs_ffmpeg
@needs_media_stack
def test_ingest_produces_every_stage_0_artifact(tmp_path: Path) -> None:
    result = ingest(FIXTURE, tmp_path / "work", media_id="fixture")
    assert Path(result.audio_path).exists()
    assert Path(result.proxy_path).exists()
    assert result.duration_ms == pytest.approx(4_162, abs=50)
    assert len(result.shot_cuts_ms) == 2
    assert len(result.speech) == 2


@needs_ffmpeg
@needs_media_stack
def test_diarization_is_none_and_never_an_empty_list(tmp_path: Path) -> None:
    """§1, fail visible not silent. An empty tuple would claim the audio has no speaker turns.

    Community-1 is a gated repo with no credentials here (`BLOCKED.md` #4). "Did not run" and
    "ran and found nothing" are different facts and must not serialize to the same JSON.
    """
    result = ingest(FIXTURE, tmp_path / "work", media_id="fixture")
    assert result.diarization is None
    assert result.to_dict()["diarization"] is None


def test_the_result_round_trips_through_json() -> None:
    import json

    original = IngestResult(
        media_id="m",
        source="s.mp4",
        audio_path="a.wav",
        proxy_path="p.mp4",
        duration_ms=4_162,
        shot_cuts_ms=(1_400, 2_800),
        speech=(SpeechSegment(start_ms=0, end_ms=1_790),),
    )
    assert IngestResult.from_dict(json.loads(original.to_json())) == original


def test_a_round_trip_does_not_turn_absent_diarization_into_an_empty_result() -> None:
    import json

    original = IngestResult(
        media_id="m",
        source="s.mp4",
        audio_path="a.wav",
        proxy_path="p.mp4",
        duration_ms=1,
        shot_cuts_ms=(),
        speech=(),
    )
    assert IngestResult.from_dict(json.loads(original.to_json())).diarization is None


def test_missing_ffmpeg_names_the_fix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("hawedit.ingest.find_ffmpeg", lambda: None)
    with pytest.raises(IngestError, match="fetch-ffmpeg.sh"):
        ingest(FIXTURE, tmp_path / "work")


# --- the CI-only failure: present is not usable ---------------------------------------------


def test_the_media_stack_check_asks_whether_it_works_not_whether_it_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug CI caught and every local run missed.

    PySceneDetect declares OpenCV as an *optional* extra, so `import scenedetect` succeeds on
    an install that cannot detect a single cut. A guard built on `find_spec` answers "is the
    module present", which is a different question from "does it work" — and the gap only
    appears when something calls `detect()`, which on a clean runner was 22 red tests.

    Same shape as §4.3.2's warning about libass and what `encoder_available` found for NVENC: a
    component can be present and unusable, and only trying it tells you which.
    """
    import builtins

    real_import = builtins.__import__

    def without_opencv(name: str, *args: object, **kwargs: object) -> object:
        if name == "scenedetect" or name.startswith("scenedetect."):
            raise ImportError("OpenCV could not be found, try installing opencv-python")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", without_opencv)
    assert media_stack_available() is False


def test_the_stack_this_machine_has_is_reported_available() -> None:
    """The positive control. An always-False check would pass the test above trivially."""
    assert media_stack_available() is True


def test_opencv_is_a_declared_dependency_not_an_accident() -> None:
    """It was installed locally and undeclared, which is why only CI found it."""
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    media = pyproject["project"]["optional-dependencies"]["media"]
    assert any("opencv" in dep for dep in media), (
        f"scenedetect's backend is not declared; a clean install cannot detect shots: {media}"
    )
