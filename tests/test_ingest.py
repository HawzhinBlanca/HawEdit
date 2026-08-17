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

import hashlib
import json
import os
import subprocess
import threading
import wave
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.diarization import Segment
from hawedit.ingest import (
    LOUDNORM_FILTER,
    MAX_SPEECH_DURATION_S,
    OMNIASR_CEILING_S,
    PROXY_CRF,
    PROXY_FPS,
    PROXY_HEIGHT,
    TARGET_SAMPLE_RATE,
    DiarizationInvalidOutput,
    Diarizer,
    IngestError,
    IngestResult,
    SpeechSegment,
    assert_within_asr_ceiling,
    attach_diarization,
    detect_shots,
    detect_speech,
    extract_audio,
    extract_proxy,
    ingest,
    media_stack_available,
    probe_duration_ms,
    probe_stream,
)

ROOT = Path(__file__).resolve().parents[1]


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

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


def _blueprint_stage_0_settings() -> dict[str, str]:
    """Every Stage 0 setting §3 states, read out of the frozen blueprint.

    The blueprint gives two ffmpeg commands and the VAD line verbatim, so these are not
    approximations — unlike `ContentDetector, threshold ~27` and the visual `~1 fps`, which are
    written with a tilde and are deliberately **not** bound here: pinning an approximate figure
    as exact would invent precision the document declined to give.

    This test previously asserted `== 16_000`, `== "loudnorm=…"` and `== (1, 720, 28)` — literals
    typed beside the constants, with `BLUEPRINT.md` named in the function title and never opened.
    Adversarial pass 28 also found it covered **four of the six** Stage 0 constants: neither
    `MAX_SPEECH_DURATION_S` nor `OMNIASR_CEILING_S` appeared, and the first could go 38 → 30 with
    the whole suite green, because the only test touching it asserts a *margin*
    (`CEILING - MAX >= 2.0`) that 30 satisfies. D-173.

    Non-vacuity: every one of the six must be found, and a missing match fails here rather than
    quietly asserting nothing.
    """
    import re
    from pathlib import Path as _Path

    blueprint = (_Path(__file__).resolve().parents[1] / "BLUEPRINT.md").read_text(encoding="utf-8")
    patterns = {
        "sample_rate": r"-ar (\d+)",
        "loudnorm": r"-af (loudnorm=[^\s\\]+)",
        "proxy_fps": r"-vf \"fps=(\d+),scale=-2:\d+\"",
        "proxy_height": r"-vf \"fps=\d+,scale=-2:(\d+)\"",
        "proxy_crf": r"-crf (\d+)",
        "max_speech_duration_s": r"max_speech_duration_s=(\d+)",
        "omniasr_ceiling_s": r"OmniASR's (\d+) s ceiling",
    }
    found: dict[str, str] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, blueprint)
        assert match is not None, f"§3 Stage 0 no longer states {name}; the scan is broken"
        found[name] = match.group(1)
    return found


def test_the_stage_0_constants_are_the_blueprints() -> None:
    """Derived from the frozen document, and covering every constant it states."""
    stated = _blueprint_stage_0_settings()
    assert int(stated["sample_rate"]) == TARGET_SAMPLE_RATE, stated
    assert stated["loudnorm"] == LOUDNORM_FILTER, stated
    assert int(stated["proxy_fps"]) == PROXY_FPS, stated
    assert int(stated["proxy_height"]) == PROXY_HEIGHT, stated
    assert int(stated["proxy_crf"]) == PROXY_CRF, stated
    assert float(stated["max_speech_duration_s"]) == MAX_SPEECH_DURATION_S, stated
    assert float(stated["omniasr_ceiling_s"]) == OMNIASR_CEILING_S, stated


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
    """Capture ffmpeg argv without running it — but still leave the output file behind.

    A real ffmpeg writes its destination, and `_extract_once` now refuses an extraction that
    produced nothing (D-132). A fake that writes nothing is not standing in for ffmpeg, it is
    standing in for the failure that refusal exists to name.
    """
    seen: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        seen.append(command)
        Path(command[-1]).write_bytes(b"\x00" * 64)
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
    assert result.source_sha256 == FIXTURE_SHA256


@needs_ffmpeg
@needs_media_stack
def test_ingest_refuses_source_bytes_changed_during_stage_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit import ingest as ingest_module

    source = tmp_path / "mutable.mp4"
    source.write_bytes(FIXTURE.read_bytes())

    def mutate_after_measurement(_source: Path) -> tuple[int, ...]:
        with source.open("ab") as stream:
            stream.write(b"changed-during-stage-zero")
        return ()

    monkeypatch.setattr(ingest_module, "detect_shots", mutate_after_measurement)
    with pytest.raises(IngestError, match="source changed"):
        ingest(source, tmp_path / "work", media_id="mutable")


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
        source_sha256="a" * 64,
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
        source_sha256="a" * 64,
    )
    assert IngestResult.from_dict(json.loads(original.to_json())).diarization is None


def _base_ingest_result(duration_ms: int = 4_162) -> IngestResult:
    return IngestResult(
        media_id="m",
        source="s.mp4",
        audio_path="a.wav",
        proxy_path="p.mp4",
        duration_ms=duration_ms,
        shot_cuts_ms=(1_400, 2_800),
        speech=(SpeechSegment(start_ms=0, end_ms=1_790),),
        source_sha256="a" * 64,
    )


def test_diarization_attachment_records_a_sorted_exclusive_result() -> None:
    class Producer:
        def diarize(self, audio: Path) -> tuple[Segment, ...]:
            assert audio == Path("a.wav")
            return (Segment(2_000, 4_000, "SPEAKER_01"), Segment(0, 1_800, "SPEAKER_00"))

    result = attach_diarization(_base_ingest_result(), Producer())
    assert isinstance(Producer(), Diarizer)
    assert result.diarization == (
        Segment(0, 1_800, "SPEAKER_00"),
        Segment(2_000, 4_000, "SPEAKER_01"),
    )
    assert result.to_dict()["diarization"] == [
        {"start_ms": 0, "end_ms": 1_800, "speaker": "SPEAKER_00"},
        {"start_ms": 2_000, "end_ms": 4_000, "speaker": "SPEAKER_01"},
    ]


@pytest.mark.parametrize(
    ("turns", "message"),
    [
        ((Segment(0, 2_000, "A"), Segment(1_000, 3_000, "B")), "overlap"),
        ((Segment(0, 4_163, "A"),), "media duration"),
        ((object(),), "Segment"),
    ],
)
def test_diarization_attachment_refuses_untrusted_invalid_output(
    turns: tuple[object, ...], message: str
) -> None:
    class Producer:
        def diarize(self, audio: Path) -> tuple[object, ...]:
            return turns

    with pytest.raises(DiarizationInvalidOutput, match=message):
        attach_diarization(_base_ingest_result(), Producer())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [
        {"start_ms": False, "end_ms": 10, "speaker": "A"},
        {"start_ms": 0, "end_ms": True, "speaker": "A"},
        {"start_ms": 0, "end_ms": 10, "speaker": []},
    ],
)
def test_ingest_json_refuses_coercible_diarization_fields(bad: dict[str, object]) -> None:
    payload = _base_ingest_result().to_dict()
    payload["diarization"] = [bad]
    with pytest.raises((TypeError, ValueError)):
        IngestResult.from_dict(payload)


def test_ingest_json_refuses_noncanonical_or_overlapping_turns() -> None:
    payload = _base_ingest_result().to_dict()
    payload["diarization"] = [
        {"start_ms": 2_000, "end_ms": 3_000, "speaker": "B"},
        {"start_ms": 0, "end_ms": 1_000, "speaker": "A"},
    ]
    with pytest.raises(ValueError, match="canonical order"):
        IngestResult.from_dict(payload)

    payload["diarization"] = [
        {"start_ms": 0, "end_ms": 2_000, "speaker": "A"},
        {"start_ms": 1_000, "end_ms": 3_000, "speaker": "B"},
    ]
    with pytest.raises(ValueError, match="overlap"):
        IngestResult.from_dict(payload)


def test_ingest_json_refuses_a_turn_past_the_media_clock() -> None:
    payload = _base_ingest_result().to_dict()
    payload["diarization"] = [
        {"start_ms": 0, "end_ms": 4_163, "speaker": "A"},
    ]
    with pytest.raises(ValueError, match="media duration"):
        IngestResult.from_dict(payload)


def test_missing_ffmpeg_names_the_fix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("hawedit.ingest.find_ffmpeg", lambda: None)
    with pytest.raises(IngestError, match="hawedit-ffmpeg-setup"):
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


# --- §1: Stage 0 is re-runnable (D-132) ---------------------------------------------------


def _provenance(dest: Path) -> Path:
    return dest.with_suffix(dest.suffix + ".provenance.json")


@needs_ffmpeg
def test_a_second_extraction_of_the_same_source_reuses_the_file_it_already_wrote(
    tmp_path: Path,
) -> None:
    """§1 calls the stages re-runnable. Measured on `ZAR38MinTest.mp4`, Stage 0 took 151.4 s
    and a second run into the same work directory spent **100.2 s of it** re-extracting audio
    and proxy already on disk — two thirds of the stage, redone.

    Asserted on the artifact: the file must be the same bytes AND the same inode-level mtime,
    because "identical output" is what a wasteful re-extraction also produces.
    """
    dest = tmp_path / "audio.wav"
    first = extract_audio(FIXTURE, dest).read_bytes()
    stamp = dest.stat().st_mtime_ns

    reused = extract_audio(FIXTURE, dest)

    assert reused.read_bytes() == first
    assert dest.stat().st_mtime_ns == stamp, "the file was rewritten, so nothing was reused"


@needs_ffmpeg
def test_a_changed_source_is_extracted_again_rather_than_served_from_the_old_output(
    tmp_path: Path,
) -> None:
    """The control. "Reuse whenever the destination exists" passes the test above and ships
    one video's audio for another's — the wrong output, which is worse than the slow one.

    **The source path is held constant and only the content changes**, which is the only way
    to bind the digest: `-i <source>` is part of the recorded command, so handing over a
    *differently named* file is caught by the command comparison and says nothing about
    whether the content was ever hashed. The first version of this test made that mistake and
    the mutation audit found it — the digest check survived being replaced by `True`.

    Same path, different bytes is also the case that actually happens: a re-export, a fixed
    audio track, a file swapped in place under a work directory that was not cleaned.
    """
    source = tmp_path / "source.mp4"
    source.write_bytes(FIXTURE.read_bytes())
    dest = tmp_path / "audio.wav"
    from_fixture = extract_audio(source, dest).read_bytes()
    recorded_first = json.loads(_provenance(dest).read_text(encoding="utf-8"))["source_sha256"]

    subprocess.run(  # a different recording, written over the same path
        [
            str(find_ffmpeg()),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=4",
            "-shortest",
            "-y",
            str(source),
        ],
        check=True,
    )
    from_replacement = extract_audio(source, dest).read_bytes()

    assert from_replacement != from_fixture, (
        "the replaced source's audio is byte-identical to the original's, so output extracted "
        "from a file that no longer exists was served for the one that does"
    )
    recorded_second = json.loads(_provenance(dest).read_text(encoding="utf-8"))["source_sha256"]
    assert recorded_second != recorded_first, "the digest did not follow the content"


@needs_ffmpeg
def test_changing_the_extraction_settings_re_extracts_instead_of_keeping_the_old_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache keyed on the input alone answers a *different question* with the old answer.

    §6's `-ar 16000` is the setting Stage 1 depends on, so it is the one moved here: extract
    at 8 kHz first, then at the real rate, and require the header on disk to follow.
    """
    dest = tmp_path / "audio.wav"
    monkeypatch.setattr("hawedit.ingest.TARGET_SAMPLE_RATE", 8_000)
    monkeypatch.setattr("hawedit.ingest._assert_audio_format", lambda _p: None)
    extract_audio(FIXTURE, dest)
    with wave.open(str(dest), "rb") as handle:
        assert handle.getframerate() == 8_000

    monkeypatch.undo()
    extract_audio(FIXTURE, dest)

    with wave.open(str(dest), "rb") as handle:
        assert handle.getframerate() == TARGET_SAMPLE_RATE, (
            "the sample rate changed and the 8 kHz output was reused; Stage 1 would decode "
            "audio the VAD's frame maths cannot describe"
        )


@needs_ffmpeg
def test_an_output_truncated_by_a_killed_run_is_not_reused(tmp_path: Path) -> None:
    """A run interrupted mid-write leaves a plausible-looking file. §1's re-runnability is
    worth nothing if resuming trusts it — the recorded size is what catches it.
    """
    dest = tmp_path / "audio.wav"
    whole = extract_audio(FIXTURE, dest).read_bytes()
    dest.write_bytes(whole[: len(whole) // 3])

    assert extract_audio(FIXTURE, dest).read_bytes() == whole, (
        "a third of a wav file was accepted as the extracted audio"
    )


@needs_ffmpeg
def test_an_output_with_no_provenance_beside_it_is_extracted_again(tmp_path: Path) -> None:
    """Every work directory written before D-132 is in exactly this state, as is one whose
    sidecar was cleaned up. Absent evidence is not evidence of a match.
    """
    dest = tmp_path / "audio.wav"
    extract_audio(FIXTURE, dest)
    _provenance(dest).unlink()
    stamp = dest.stat().st_mtime_ns

    extract_audio(FIXTURE, dest)

    assert dest.stat().st_mtime_ns != stamp, "an unexplained file was taken on trust"


@needs_ffmpeg
def test_unreadable_provenance_falls_back_to_extracting(tmp_path: Path) -> None:
    """The failure mode of every sidecar: half-written JSON. Falling back costs 70 s; trusting
    a `.get()` on a partially parsed dict costs correctness.
    """
    dest = tmp_path / "audio.wav"
    extract_audio(FIXTURE, dest)
    _provenance(dest).write_text('{"source_sha256": "ab', encoding="utf-8")
    stamp = dest.stat().st_mtime_ns

    extract_audio(FIXTURE, dest)

    assert dest.stat().st_mtime_ns != stamp
    assert json.loads(_provenance(dest).read_text(encoding="utf-8"))["output_bytes"] > 0


@needs_ffmpeg
def test_reused_audio_is_still_checked_against_the_format_stage_1_assumes(
    tmp_path: Path,
) -> None:
    """`_assert_audio_format` runs on every call, reused or not: the format is a property of
    the file that arrives at Stage 1, not of the run that happened to write it. Without this
    the guard is skipped exactly when the file has been sitting on disk long enough to change.
    """
    dest = tmp_path / "audio.wav"
    extract_audio(FIXTURE, dest)
    with wave.open(str(dest), "wb") as handle:  # same path, wrong format, provenance intact
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 4_000)
    size = dest.stat().st_size
    recorded = json.loads(_provenance(dest).read_text(encoding="utf-8"))
    recorded["output_bytes"] = size
    _provenance(dest).write_text(json.dumps(recorded), encoding="utf-8")

    with pytest.raises(IngestError, match="16000 Hz mono"):
        extract_audio(FIXTURE, dest)


def test_an_extraction_that_produced_no_file_is_named_not_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffmpeg exiting 0 without writing is the shape `curl --fail` exists for (D-121). It used
    to surface as a bare FileNotFoundError from the sidecar's own stat(), pointing at
    provenance bookkeeping instead of at the pass that wrote nothing.
    """
    monkeypatch.setattr(
        "hawedit.ingest._run",
        lambda command: subprocess.CompletedProcess(command, 0, b"", b""),
    )
    with pytest.raises(IngestError, match="produced no audio.wav"):
        extract_audio(FIXTURE, tmp_path / "audio.wav", ffmpeg=Path("/bin/ffmpeg"))
    assert not _provenance(tmp_path / "audio.wav").exists(), (
        "a failed extraction left a provenance record a later run could match"
    )


@needs_ffmpeg
def test_a_crashed_run_leaves_no_record_an_earlier_settings_run_could_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one case the size check alone cannot see: two settings alternating, one crashing.

    Extract at 16 kHz, then let an 8 kHz run die after leaving *exactly* the recorded byte
    count behind. The 16 kHz record still names the right command, the right source and the
    right size — and the file under it is now another run's wreckage. Removing the record
    before running is what stops the next 16 kHz call reusing it.
    """
    dest = tmp_path / "audio.wav"
    real = extract_audio(FIXTURE, dest).read_bytes()

    def dies_after_writing(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        Path(command[-1]).write_bytes(b"\x7f" * len(real))  # same size, wrong content
        raise IngestError("killed mid-encode")

    monkeypatch.setattr("hawedit.ingest.TARGET_SAMPLE_RATE", 8_000)
    monkeypatch.setattr("hawedit.ingest._run", dies_after_writing)
    monkeypatch.setattr("hawedit.ingest._assert_audio_format", lambda _p: None)
    with pytest.raises(IngestError, match="killed mid-encode"):
        extract_audio(FIXTURE, dest)
    assert dest.stat().st_size == len(real), "the collision this test exists for did not happen"
    monkeypatch.undo()

    assert extract_audio(FIXTURE, dest).read_bytes() == real, (
        "the crashed run's bytes were served under the earlier run's provenance"
    )


@needs_ffmpeg
def test_the_proxy_is_reused_on_the_same_terms_as_the_audio(tmp_path: Path) -> None:
    """One guard in `_extract_once`, not one per extractor — so the proxy's 30.3 s is covered
    by the same mechanism and cannot drift away from it.
    """
    dest = tmp_path / "proxy.mp4"
    first = extract_proxy(FIXTURE, dest).read_bytes()
    stamp = dest.stat().st_mtime_ns

    assert extract_proxy(FIXTURE, dest).read_bytes() == first
    assert dest.stat().st_mtime_ns == stamp, "the proxy was re-encoded"


# --- the two refusals in the probe path that no test held ------------------------------------
#
# Measured by neutralising each in a shadow copy of src/hawedit and running tests/test_ingest.py
# with tests/test_pipeline.py and tests/test_review_findings.py: both survived at that scope, so
# neither is held incidentally by a caller's file. `probe_stream` is the one argv every probe in
# the system goes through — the docstring says three call sites had grown their own, "including
# one that let a raw `CalledProcessError` escape into the pipeline runner". These two guards are
# what keeps that from happening again, and both are about the *identity* of the failure.


def _bin_pair(tmp_path: Path, *, with_ffprobe: bool) -> Path:
    """An ffmpeg path, optionally with the sibling `ffprobe_for` would resolve to.

    Named through `ffprobe_for` rather than spelled out, so the fixture cannot drift away from
    the resolver it is meant to exercise — `ffprobe_for` keeps the binary's suffix, which is
    the whole reason it exists. Nothing here is executed: the refusing case never reaches
    subprocess, and the control stubs it.
    """
    from hawedit.captions import ffprobe_for

    binary = tmp_path / "bin" / "ffmpeg.exe"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"")
    if with_ffprobe:
        ffprobe_for(binary).write_bytes(b"")
    return binary


def test_an_ffmpeg_with_no_ffprobe_beside_it_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without this line the missing binary reaches `subprocess.run`, which raises
    `FileNotFoundError` naming a path — an OSError crossing a stage boundary, which is the
    class of escape `probe_stream` was written to end. The refusal says which ffmpeg the
    ffprobe was expected beside, because that is the fact needed to fix it.
    """
    binary = _bin_pair(tmp_path, with_ffprobe=False)
    with pytest.raises(IngestError, match="no ffprobe beside"):
        probe_stream(FIXTURE, "format=duration", binary)

    # The control: the same call with the sibling present gets past this line. Without it the
    # test would pass just as well against a `probe_stream` that refused every input.
    def succeeds(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 0, b" 4.162\n", b"")

    monkeypatch.setattr("hawedit.ingest.subprocess.run", succeeds)
    assert probe_stream(FIXTURE, "format=duration", _bin_pair(tmp_path, with_ffprobe=True)) == (
        "4.162"
    )


def test_a_probe_that_exits_nonzero_is_refused_rather_than_read_as_an_empty_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_run` is the single subprocess call site for Stage 0, and this is its only check.

    Neutralised, `probe_stream` returns `result.stdout.decode().strip()` — for a failed
    ffprobe, the empty string. That is not an error anyone sees: `probe_duration_ms` turns it
    into `float("")`, a `ValueError` about string conversion several frames away from the
    binary that actually failed, with ffprobe's own explanation discarded. So the assertions
    are on the message, not just the type: the binary's name, its exit code, and the tail of
    its stderr are the three facts that make the refusal actionable.
    """
    binary = _bin_pair(tmp_path, with_ffprobe=True)
    reason = b"Invalid data found when processing input"

    def failed(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 3, b"", b"x" * 700 + reason)

    monkeypatch.setattr("hawedit.ingest.subprocess.run", failed)

    with pytest.raises(IngestError) as raised:
        probe_stream(FIXTURE, "format=duration", binary)
    message = str(raised.value)
    assert "ffprobe" in message, "the refusal does not say which binary failed"
    assert "(3)" in message, "the refusal does not carry the exit code"
    assert reason.decode() in message, "ffprobe's own explanation was dropped"
    assert "x" * 700 not in message, (
        "the stderr tail is not bounded — [-600:] must keep the end, which is where ffmpeg "
        "writes the line that says why, after however much banner precedes it"
    )

    # The caller that would otherwise raise ValueError from float(""), stated as a caller.
    with pytest.raises(IngestError):
        probe_duration_ms(FIXTURE, binary)


def test_vad_regions_are_intersected_with_the_video_media_clock() -> None:
    from hawedit.ingest import _clip_speech_to_media

    segments = (
        SpeechSegment(start_ms=-20, end_ms=100),
        SpeechSegment(start_ms=900, end_ms=1_020),
        SpeechSegment(start_ms=1_100, end_ms=1_200),
    )
    assert _clip_speech_to_media(segments, 1_000) == (
        SpeechSegment(start_ms=0, end_ms=100),
        SpeechSegment(start_ms=900, end_ms=1_000),
    )


def test_an_invalid_vad_region_is_refused_instead_of_hidden_by_clipping() -> None:
    from hawedit.ingest import _clip_speech_to_media

    with pytest.raises(IngestError, match="invalid speech region"):
        _clip_speech_to_media((SpeechSegment(start_ms=20, end_ms=20),), 1_000)


# --- the artifact ------------------------------------------------------------------------


@needs_ffmpeg
@needs_media_stack
def test_real_vad_cannot_publish_a_timestamp_after_the_fixture_ends(tmp_path: Path) -> None:
    """Silero reports this fixture's padded audio through 4180 ms; video ends at 4162 ms."""
    result = ingest(FIXTURE, tmp_path / "work", media_id="fixture")
    assert result.duration_ms == 4_162
    assert result.speech[-1].end_ms == result.duration_ms


def _fake_proxy_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        source = Path(command[command.index("-i") + 1])
        Path(command[-1]).write_bytes(b"proxy:" + source.read_bytes())
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr("hawedit.ingest._run", fake_run)
    return calls


def _sidecar(dest: Path) -> Path:
    return dest.with_suffix(dest.suffix + ".provenance.json")


def test_same_source_and_command_reuse_the_verified_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"one")
    dest = tmp_path / "proxy.mp4"
    calls = _fake_proxy_extractor(monkeypatch)

    extract_proxy(source, dest, Path("ffmpeg"))
    stamp = dest.stat().st_mtime_ns
    extract_proxy(source, dest, Path("ffmpeg"))

    assert len(calls) == 1
    assert dest.stat().st_mtime_ns == stamp
    assert json.loads(_sidecar(dest).read_text(encoding="utf-8"))["output_bytes"] > 0


def test_changed_bytes_at_the_same_source_path_are_extracted_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"one")
    dest = tmp_path / "proxy.mp4"
    calls = _fake_proxy_extractor(monkeypatch)
    extract_proxy(source, dest, Path("ffmpeg"))

    source.write_bytes(b"two")
    extract_proxy(source, dest, Path("ffmpeg"))

    assert len(calls) == 2
    assert dest.read_bytes() == b"proxy:two"


def test_changed_settings_and_truncated_outputs_are_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    dest = tmp_path / "proxy.mp4"
    calls = _fake_proxy_extractor(monkeypatch)
    extract_proxy(source, dest, Path("ffmpeg"))

    monkeypatch.setattr("hawedit.ingest.PROXY_CRF", 29)
    extract_proxy(source, dest, Path("ffmpeg"))
    dest.write_bytes(b"cut")
    extract_proxy(source, dest, Path("ffmpeg"))

    assert len(calls) == 3
    assert dest.read_bytes() == b"proxy:source"


def test_failed_rerun_preserves_the_last_good_artifact_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"good")
    dest = tmp_path / "proxy.mp4"
    _fake_proxy_extractor(monkeypatch)
    extract_proxy(source, dest, Path("ffmpeg"))
    before = dest.read_bytes(), _sidecar(dest).read_bytes()
    source.write_bytes(b"replacement")

    def fail(_command: list[str]) -> subprocess.CompletedProcess[bytes]:
        raise IngestError("encode interrupted")

    monkeypatch.setattr("hawedit.ingest._run", fail)
    with pytest.raises(IngestError, match="interrupted"):
        extract_proxy(source, dest, Path("ffmpeg"))

    assert (dest.read_bytes(), _sidecar(dest).read_bytes()) == before
    assert not tuple(tmp_path.glob(".proxy.*.mp4"))


def test_source_change_during_encode_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"before")
    dest = tmp_path / "proxy.mp4"

    def mutate(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        Path(command[-1]).write_bytes(b"mixed output")
        source.write_bytes(b"after")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr("hawedit.ingest._run", mutate)
    with pytest.raises(IngestError, match="source changed"):
        extract_proxy(source, dest, Path("ffmpeg"))
    assert not dest.exists()
    assert not _sidecar(dest).exists()


def test_success_without_output_is_a_domain_error_not_a_published_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        "hawedit.ingest._run",
        lambda command: subprocess.CompletedProcess(command, 0, b"", b""),
    )
    with pytest.raises(IngestError, match="produced no proxy.mp4"):
        extract_proxy(source, tmp_path / "proxy.mp4", Path("ffmpeg"))


@needs_ffmpeg
def test_reused_audio_is_still_checked_against_stage_1s_format(tmp_path: Path) -> None:
    dest = tmp_path / "audio.wav"
    extract_audio(FIXTURE, dest)
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\0\0" * 4_000)
    provenance = json.loads(_sidecar(dest).read_text(encoding="utf-8"))
    provenance["output_bytes"] = dest.stat().st_size
    _sidecar(dest).write_text(json.dumps(provenance), encoding="utf-8")

    with pytest.raises(IngestError, match="16000 Hz mono"):
        extract_audio(FIXTURE, dest)


def test_a_hardlinked_lock_is_refused_without_touching_its_victim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    victim = tmp_path / "victim"
    victim.write_bytes(b"KEEP")
    os.link(victim, tmp_path / "proxy.mp4.lock")
    calls = _fake_proxy_extractor(monkeypatch)

    with pytest.raises(IngestError, match="one regular private link"):
        extract_proxy(source, tmp_path / "proxy.mp4", Path("ffmpeg"))
    assert victim.read_bytes() == b"KEEP"
    assert calls == []


def test_concurrent_reruns_publish_once_then_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    dest = tmp_path / "proxy.mp4"
    calls = _fake_proxy_extractor(monkeypatch)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            extract_proxy(source, dest, Path("ffmpeg"))
        except BaseException as exc:  # asserted below; a thread must not hide its failure
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(calls) == 1
    assert dest.read_bytes() == b"proxy:source"
