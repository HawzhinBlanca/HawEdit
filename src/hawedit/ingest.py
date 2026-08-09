"""§3 Stage 0 — ingest. CPU only, never blocks a GPU.

    ffmpeg -i "$SRC" -vn -ac 1 -ar 16000 -af loudnorm=I=-23:TP=-2:LRA=7 \\
           -c:a pcm_s16le "$WORK/audio.wav"
    ffmpeg -i "$SRC" -vf "fps=1,scale=-2:720" -c:v libx264 -crf 28 -an "$WORK/proxy.mp4"

Three things §3 Stage 0 is specific about, all of which are load-bearing:

**Single-threaded ffmpeg processes.** "Spawn many *single-threaded* ffmpeg processes rather
than one with `-threads 64` — the 3990X is Zen 2, modest single-thread speed and enormous
parallelism." So every invocation here passes `-threads 1`, and parallelism belongs at the
level above: many files at once, not many threads per file. A test asserts the flag, because
it is the kind of thing that gets "optimised" away by someone who has not read §6.

**VAD at 38 s, under a 40 s ceiling.** `max_speech_duration_s=38` exists because OmniASR's
interface limit is 40 s (§3 Stage 1). A segment over that ceiling is not a slow path, it is
an ASR failure — so `assert_within_asr_ceiling` refuses one rather than passing it downstream
to fail later with a less obvious message.

**Shot detection runs on the source, not the proxy.** The proxy is `fps=1`, which quantises
every event to a full second — and §3 Stage 5 matches shot cuts against a **400 ms** window.
Detecting on the proxy would feed boundary fusion cuts coarser than the tolerance they are
compared against, so every cut would either miss or match by accident. See D-023.

Diarization is deliberately **absent rather than faked**: Community-1 is a gated repo
(`BLOCKED.md` #4), and `IngestResult.diarization` is `None` when it has not run. A
zero-speaker result would read as "one speaker throughout", which is a claim about the audio.
"""

from __future__ import annotations

import json
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.diarization import Segment

__all__ = [
    "CONTENT_DETECTOR_THRESHOLD",
    "LOUDNORM_FILTER",
    "MAX_SPEECH_DURATION_S",
    "OMNIASR_CEILING_S",
    "PROXY_CRF",
    "PROXY_FPS",
    "PROXY_HEIGHT",
    "TARGET_SAMPLE_RATE",
    "IngestResult",
    "SpeechSegment",
    "assert_within_asr_ceiling",
    "detect_shots",
    "detect_speech",
    "extract_audio",
    "extract_proxy",
    "ingest",
    "media_stack_available",
    "probe_duration_ms",
    "probe_stream",
]

# §3 Stage 0's literal parameters.
TARGET_SAMPLE_RATE: Final = 16_000
LOUDNORM_FILTER: Final = "loudnorm=I=-23:TP=-2:LRA=7"
PROXY_FPS: Final = 1
PROXY_HEIGHT: Final = 720
PROXY_CRF: Final = 28
CONTENT_DETECTOR_THRESHOLD: Final = 27.0
MAX_SPEECH_DURATION_S: Final = 38.0

# §3 Stage 1's interface limit. VAD's 38 s leaves the margin §3 Stage 0 describes.
OMNIASR_CEILING_S: Final = 40.0


class IngestError(RuntimeError):
    """Raised when Stage 0 cannot produce what later stages require."""


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    """One VAD speech region. Must stay under the ASR ceiling."""

    start_ms: int
    end_ms: int

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


def _run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise IngestError(
            f"{Path(command[0]).name} failed ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')[-600:]}"
        )
    return result


def _ffmpeg(ffmpeg: Path | None) -> Path:
    resolved = ffmpeg or find_ffmpeg()
    if resolved is None:
        raise IngestError(
            "no ffmpeg available — run scripts/fetch-ffmpeg.sh or set HAWEDIT_FFMPEG."
        )
    return resolved


def probe_stream(
    source: Path,
    entries: str,
    ffmpeg: Path | None = None,
    video_only: bool = False,
    separator: str = "x",
) -> str:
    """Ask ffprobe for `entries` about `source`, as one stripped string.

    One resolver and one argv for every probe in the system. Three call sites had grown their
    own — with three different behaviours when ffprobe failed, including one that let a raw
    `CalledProcessError` escape into the pipeline runner.
    """
    binary = _ffmpeg(ffmpeg)
    ffprobe = ffprobe_for(binary)
    if not ffprobe.exists():
        raise IngestError(f"no ffprobe beside {binary}")
    result = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            *(("-select_streams", "v:0") if video_only else ()),
            "-show_entries",
            entries,
            "-of",
            f"csv=p=0:s={separator}" if video_only else "default=nw=1:nk=1",
            str(source),
        ]
    )
    return result.stdout.decode().strip()


def probe_duration_ms(source: Path, ffmpeg: Path | None = None) -> int:
    """Media duration in milliseconds, via ffprobe beside the ffmpeg binary."""
    return round(float(probe_stream(source, "format=duration", ffmpeg)) * 1000)


def extract_audio(source: Path, dest: Path, ffmpeg: Path | None = None) -> Path:
    """§3 Stage 0's audio pass: 16 kHz mono PCM, loudness-normalised.

    `-threads 1` is deliberate (§3 Stage 0 / §6): parallelism belongs across files, not
    inside one ffmpeg on a Zen 2 chip with modest single-thread speed.
    """
    binary = _ffmpeg(ffmpeg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "1",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-af",
            LOUDNORM_FILTER,
            "-c:a",
            "pcm_s16le",
            "-y",
            str(dest),
        ]
    )
    _assert_audio_format(dest)
    return dest


def _assert_audio_format(wav_path: Path) -> None:
    """Stage 1 assumes 16 kHz mono 16-bit. Check it here, where the fix is obvious."""
    with wave.open(str(wav_path), "rb") as handle:
        rate, channels, width = handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
    if (rate, channels, width) != (TARGET_SAMPLE_RATE, 1, 2):
        raise IngestError(
            f"{wav_path.name} is {rate} Hz / {channels}ch / {width * 8}-bit; Stage 1 and the "
            f"VAD both assume {TARGET_SAMPLE_RATE} Hz mono 16-bit."
        )


def extract_proxy(source: Path, dest: Path, ffmpeg: Path | None = None) -> Path:
    """§3 Stage 0's video proxy: 1 fps, 720p, CRF 28, no audio.

    One frame per second is right for keyframe and visual work and **wrong for shot
    detection** — see `detect_shots`.
    """
    binary = _ffmpeg(ffmpeg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "1",
            "-i",
            str(source),
            "-vf",
            f"fps={PROXY_FPS},scale=-2:{PROXY_HEIGHT}",
            "-c:v",
            "libx264",
            "-crf",
            str(PROXY_CRF),
            "-an",
            "-y",
            str(dest),
        ]
    )
    return dest


def media_stack_available() -> bool:
    """Can this install actually detect shots and speech — not merely import the modules?

    `importlib.util.find_spec("scenedetect")` returns a spec for an install that cannot detect
    a single cut, because PySceneDetect declares OpenCV as an *optional* extra. A guard built
    on that answers "is the module present", which is a different question from "does it work",
    and the gap is invisible until something calls `detect()`.

    That is the same mistake §4.3.2 warns about for libass and `encoder_available` found for
    NVENC: a component can be present and unusable. So this imports the whole chain the way
    Stage 0 uses it, and answers the question that was actually asked.
    """
    try:
        import numpy  # noqa: F401
        import scenedetect  # noqa: F401
        import silero_vad  # noqa: F401
        import torch  # noqa: F401
        from scenedetect import ContentDetector, detect  # noqa: F401
    except ImportError:
        return False
    return True


def detect_shots(source: Path, threshold: float = CONTENT_DETECTOR_THRESHOLD) -> tuple[int, ...]:
    """Shot-cut times in milliseconds, via PySceneDetect's ContentDetector.

    Runs on **the source**, never the 1 fps proxy. §3 Stage 5 matches a cut against a 400 ms
    window; a proxy quantises every cut to a whole second, so proxy-derived cuts would be
    coarser than the tolerance they are compared against (D-023).
    """
    from scenedetect import ContentDetector, detect

    scenes = detect(str(source), ContentDetector(threshold=threshold))
    # Each scene's start is a cut, except the first — that is the file beginning, not a cut.
    return tuple(round(start.get_seconds() * 1000) for start, _ in scenes[1:])


def detect_speech(
    wav_path: Path, max_speech_duration_s: float = MAX_SPEECH_DURATION_S
) -> tuple[SpeechSegment, ...]:
    """Silero VAD speech regions (§3 Stage 0).

    Reads the WAV with the standard library rather than torchaudio: Stage 0 has already
    guaranteed 16 kHz mono PCM, so the extra dependency would buy nothing.
    """
    import numpy as np
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    with wave.open(str(wav_path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    audio = torch.from_numpy(np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0)

    stamps = get_speech_timestamps(
        audio,
        load_silero_vad(onnx=True),
        sampling_rate=TARGET_SAMPLE_RATE,
        max_speech_duration_s=max_speech_duration_s,
    )
    return tuple(
        SpeechSegment(
            start_ms=round(s["start"] / TARGET_SAMPLE_RATE * 1000),
            end_ms=round(s["end"] / TARGET_SAMPLE_RATE * 1000),
        )
        for s in stamps
    )


def assert_within_asr_ceiling(
    segments: tuple[SpeechSegment, ...], ceiling_s: float = OMNIASR_CEILING_S
) -> None:
    """Refuse a VAD segment longer than OmniASR can accept.

    §3 Stage 1: 40 s is an interface limit, so an over-length segment is an ASR failure
    rather than a slow path. Catching it here names the cause; catching it in Stage 1 gives
    a decode error with nothing pointing back at the VAD settings.
    """
    over = [s for s in segments if s.duration_s > ceiling_s]
    if over:
        worst = max(over, key=lambda s: s.duration_s)
        raise IngestError(
            f"{len(over)} VAD segment(s) exceed OmniASR's {ceiling_s:.0f} s ceiling "
            f"(worst: {worst.duration_s:.1f} s at {worst.start_ms} ms). §3 Stage 0 sets "
            f"max_speech_duration_s={MAX_SPEECH_DURATION_S:.0f} for this margin."
        )


def _clip_speech_to_media(
    segments: tuple[SpeechSegment, ...], duration_ms: int
) -> tuple[SpeechSegment, ...]:
    """Intersect VAD output with the video media clock.

    Audio decoders and VAD padding may expose samples a few milliseconds past the duration
    ffprobe reports for the video. Those samples have no corresponding frame and therefore
    cannot become canonical words, evidence timestamps, or clip boundaries in a video
    repurposing system. Regions wholly outside the media clock are omitted; overlapping regions
    retain exactly their in-range portion.
    """
    if duration_ms <= 0:
        raise IngestError(f"media duration must be positive, got {duration_ms} ms")

    clipped: list[SpeechSegment] = []
    for segment in segments:
        if segment.end_ms <= segment.start_ms:
            raise IngestError(
                f"VAD emitted an invalid speech region {segment.start_ms}..{segment.end_ms} ms"
            )
        start_ms = max(0, segment.start_ms)
        end_ms = min(duration_ms, segment.end_ms)
        if end_ms > start_ms:
            clipped.append(SpeechSegment(start_ms=start_ms, end_ms=end_ms))
    return tuple(clipped)


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Everything Stage 0 produces, as JSON-serialisable data (§1)."""

    media_id: str
    source: str
    audio_path: str
    proxy_path: str
    duration_ms: int
    shot_cuts_ms: tuple[int, ...]
    speech: tuple[SpeechSegment, ...]
    # `None` means diarization did not run — never an empty tuple, which would assert that
    # the audio contains no speaker turns (BLOCKED.md #4).
    diarization: tuple[Segment, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "source": self.source,
            "audio_path": self.audio_path,
            "proxy_path": self.proxy_path,
            "duration_ms": self.duration_ms,
            "shot_cuts_ms": list(self.shot_cuts_ms),
            "speech": [{"start_ms": s.start_ms, "end_ms": s.end_ms} for s in self.speech],
            "diarization": (
                None
                if self.diarization is None
                else [
                    {"start_ms": d.start_ms, "end_ms": d.end_ms, "speaker": d.speaker}
                    for d in self.diarization
                ]
            ),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IngestResult:
        raw_diarization = data.get("diarization")
        return IngestResult(
            media_id=data["media_id"],
            source=data["source"],
            audio_path=data["audio_path"],
            proxy_path=data["proxy_path"],
            duration_ms=data["duration_ms"],
            shot_cuts_ms=tuple(data["shot_cuts_ms"]),
            speech=tuple(SpeechSegment(**s) for s in data["speech"]),
            diarization=(
                None if raw_diarization is None else tuple(Segment(**d) for d in raw_diarization)
            ),
        )


def ingest(
    source: Path,
    work_dir: Path,
    media_id: str | None = None,
    ffmpeg: Path | None = None,
) -> IngestResult:
    """Run §3 Stage 0 over one media file.

    Produces the 16 kHz mono audio Stage 1 consumes, the 1 fps proxy the visual stages
    consume, shot cuts from the source, and VAD speech regions verified against OmniASR's
    ceiling.

    Diarization is not run here — Community-1 is gated (`BLOCKED.md` #4) — and its absence is
    recorded as `None` rather than as an empty result.

    Raises:
        IngestError: ffmpeg is unavailable, a pass failed, the audio is the wrong format, or
            a VAD segment exceeds the ASR ceiling.
    """
    binary = _ffmpeg(ffmpeg)
    work_dir.mkdir(parents=True, exist_ok=True)
    identifier = media_id or source.stem

    audio = extract_audio(source, work_dir / "audio.wav", ffmpeg=binary)
    proxy = extract_proxy(source, work_dir / "proxy.mp4", ffmpeg=binary)
    duration_ms = probe_duration_ms(source, ffmpeg=binary)
    speech = _clip_speech_to_media(detect_speech(audio), duration_ms)
    assert_within_asr_ceiling(speech)

    return IngestResult(
        media_id=identifier,
        source=str(source),
        audio_path=str(audio),
        proxy_path=str(proxy),
        duration_ms=duration_ms,
        shot_cuts_ms=detect_shots(source),
        speech=speech,
        diarization=None,
    )
