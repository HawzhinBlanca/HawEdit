"""§3 Stage 6 — render. Reframe, burn in captions, encode.

    Reframing, captions, encode. Caption requirements in §4.3 are not optional. Vertical
    reframing tracks the active speaker from diarization plus face detection.

Three things this module refuses to do, each because the alternative fails silently:

**It will not render a clip that has not cleared the gate.** `Clip.assert_renderable()` runs
first, every time. §2 puts a human QC gate before output *always*, and Kurdish invariant #2
forbids rendering a boundary whose sentence is incomplete. A render function that takes an
`in_ms`/`out_ms` pair and trusts them is how a clip that was rejected reaches a client.

**It names what drove the crop.** Static centre, continuous face tracking and future
speaker tracking are distinct artifact values. The current dynamic path follows a smoothed,
continuous dominant face; it does not claim active-speaker association while diarization remains
gated (`BLOCKED.md` #4). A centre crop that called itself reframing would be wrong on a two-shot.

**It will not silently fall back to a software encoder.** §6 puts NVENC on hawapc01. Asking
for NVENC on a machine without it and getting x264 anyway means a throughput measurement that
is quietly about the wrong encoder — the same class of mistake §3 Stage 1 warns about with
published RTF figures. Ask for what is not there and it raises.

**It never encodes into the client-visible path.** ffmpeg writes a private sibling, that file
is measured, and only then is it linked into place with write-once semantics. An interrupted
encode leaves no plausible partial MP4, and a concurrent worker cannot replace the artifact
that won the name first.

The burn-in goes through `captions.subtitle_filter`, which hard-codes `shaping=complex` and an
explicit `fontsdir`. §4.3.1 is emphatic that `auto` must not be relied on and §4.3.4 that
fontconfig must not be trusted to find the font, and the golden render (§4.3.6) proves the
difference is real on this build rather than theoretical.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

from hawedit.brand import BrandKit, logo_overlay_coordinates, progress_bar_filter
from hawedit.captions import (
    FontCoverageError,
    assert_ass_fonts_cover_kurdish,
    assert_captions_within_clip,
    assert_rtl_stack,
    find_ffmpeg,
    subtitle_filter,
)
from hawedit.clip import Clip
from hawedit.ingest import IngestError, probe_duration_ms, probe_stream
from hawedit.silence import SilencePlan, silence_trim_filter
from hawedit.transcripts import Word

__all__ = [
    "DEFAULT_PUSH_STEP_MS",
    "DEFAULT_PUSH_ZOOM",
    "DELIVERY_AUDIO_RATE",
    "DELIVERY_COLOR_ARGS",
    "DELIVERY_LUFS",
    "DELIVERY_TRUE_PEAK_DB",
    "ENCODER_PROBE_SIZE",
    "NVENC_MIN_FRAME",
    "SPEECH_CHAIN_FILTERS",
    "VERTICAL_HEIGHT",
    "VERTICAL_WIDTH",
    "Encoder",
    "LoudnessStats",
    "Reframe",
    "RenderError",
    "RenderResult",
    "assert_encoded_span",
    "audio_filter",
    "blurred_fill_filter",
    "crop_filter",
    "decide_wide_shot_layout",
    "deliverable_video_args",
    "eased_push_schedule",
    "encoder_available",
    "frame_duration_ms",
    "frame_rate",
    "linked_libraries",
    "measure_audio_loudness",
    "quality_args",
    "render_clip",
    "shot_spans",
    "two_person_split_filter",
    "vertical_crop_size",
]

# §4.3's caption geometry is built for 1080x1920, and `render_caption_png` defaults to it.
# Keeping one vertical target means the ASS PlayResX/PlayResY match the frame and libass is
# never scaling text — scaled text is the failure the golden render would otherwise measure.
VERTICAL_WIDTH: Final = 1080
VERTICAL_HEIGHT: Final = 1920

# NVENC's smallest accepted H.264 frame, measured on hawapc01's RTX 3090 Ti with ffmpeg
# 8.1.1: 64x64 and 128x128 write zero bytes with "Frame Dimension less than the minimum
# supported value"; 145x49 encodes. Recorded as a constant so `encoder_available`'s probe
# geometry has something to be checked against — the value itself is NVIDIA's, not ours.
NVENC_MIN_FRAME: Final = (145, 49)

# What `encoder_available` encodes when it asks whether an encoder works. Stage 6's own output
# size, because that is the frame the encoder will really be handed, and because anything
# smaller can fail for reasons that say nothing about availability. See `encoder_available`.
ENCODER_PROBE_SIZE: Final = (VERTICAL_WIDTH, VERTICAL_HEIGHT)

# Broadcast delivery targets Rec.709 color tags to ensure standard sRGB/Rec.709 display
# consistency across modern mobile devices and video platforms (Task T2.10). Both container
# tags and bitstream SPS VUI parameters are populated so decoder probes read bt709.
DELIVERY_COLOR_ARGS: Final[tuple[str, ...]] = (
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-colorspace",
    "bt709",
    "-bsf:v",
    "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
)


class RenderError(RuntimeError):
    """Raised when Stage 6 cannot produce a clip it would be honest to ship."""


# Every platform this pipeline delivers to normalises playback to roughly -14 LUFS, and a
# podcast master sits ten decibels below that. Uploading unnormalised means either the viewer
# reaches for the volume or the platform's own limiter does the job less carefully than this
# does. -1 dBTP of headroom leaves room for the lossy re-encode on the other side to overshoot
# without clipping.
DELIVERY_LUFS: Final = -14.0
DELIVERY_TRUE_PEAK_DB: Final = -1.0

# 48 kHz stereo is what every target re-encodes to. Handing them 44.1 kHz buys one extra
# resample for nothing.
DELIVERY_AUDIO_RATE: Final = 48_000
DELIVERY_AUDIO_BITRATE: Final = "192k"

# Task T3.2 / D-264: Native speech conditioning chain for pro Kurdish social reels.
# Order: Highpass rumble cut (80 Hz) -> Adaptive FFT denoiser (-25 dB) ->
# Sibilance de-esser (6 kHz) -> Presence EQ (+1.5 dB @ 3 kHz).
SPEECH_CHAIN_FILTERS: Final = (
    "highpass=f=80:p=2,"
    "afftdn=nf=-25:tn=1,"
    "deesser=i=0.4:m=0.5:f=0.5:s=o,"
    "equalizer=f=3000:t=q:w=1.5:g=1.5"
)


def quality_args(encoder: Encoder, crf: int) -> list[str]:
    """The flags that actually make `encoder` hold a constant quality.

    **`-crf` is silently ignored by NVENC**, and that is not a style preference — measured on
    hawapc01 with ffmpeg 8.1.1, `-crf 18` and `-crf 30` into `h264_nvenc` produce byte-for-byte
    identical output (976,781 bytes for the same 3 s 1080x1920 source). So every render on the
    machine §6 designates for NVENC ignored the quality argument it was given and encoded at
    the driver's default rate-control instead. `-rc vbr -cq N -b:v 0` responds: the same two
    values give 5,412,913 and 1,763,082 bytes.

    This is `encoder_available`'s lesson a second time — the encoder accepting an option is not
    the encoder honouring it — and the reason both numbers above are in this docstring rather
    than in a commit message.
    """
    if encoder is Encoder.NVENC:
        # -b:v 0 is required: without it NVENC caps the constant-quality result at a default
        # bitrate ceiling and the cq value stops mattering again at the top of the range.
        return ["-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    return ["-crf", str(crf)]


def deliverable_video_args(
    encoder: Encoder,
    crf: int = 20,
    fps: float = 25.0,
    *,
    deliverable: bool = True,
) -> list[str]:
    """The encoder flags for broadcast delivery vs working renders (Task T2.10).

    Deliverable profile targets 8–12 Mbps vertical output at 1080x1920:
    - NVENC: -preset p6 -profile:v high -bf 3 -spatial-aq 1 -temporal-aq 1
      -rc vbr -cq <crf> -b:v 0 -g <2*fps>
    - libx264: -preset slow -profile:v high -bf 3 -crf <crf> -g <2*fps>

    Working renders keep -cq 27 / -crf 27 via quality_args.
    """
    if not deliverable:
        return quality_args(encoder, crf)

    gop = str(max(1, round(2 * fps)))
    if encoder is Encoder.NVENC:
        return [
            "-preset",
            "p6",
            "-profile:v",
            "high",
            "-bf",
            "3",
            "-spatial-aq",
            "1",
            "-temporal-aq",
            "1",
            "-rc",
            "vbr",
            "-cq",
            str(crf),
            "-b:v",
            "0",
            "-g",
            gop,
        ]
    return [
        "-preset",
        "slow",
        "-profile:v",
        "high",
        "-bf",
        "3",
        "-crf",
        str(crf),
        "-g",
        gop,
    ]


@dataclass(frozen=True, slots=True)
class LoudnessStats:
    """EBU R128 loudness statistics from FFmpeg loudnorm filter output."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float
    output_i: float | None = None
    output_tp: float | None = None
    output_lra: float | None = None
    output_thresh: float | None = None
    normalization_type: str = "linear"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_i": self.input_i,
            "input_tp": self.input_tp,
            "input_lra": self.input_lra,
            "input_thresh": self.input_thresh,
            "target_offset": self.target_offset,
            "output_i": self.output_i,
            "output_tp": self.output_tp,
            "output_lra": self.output_lra,
            "output_thresh": self.output_thresh,
            "normalization_type": self.normalization_type,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LoudnessStats:
        return LoudnessStats(
            input_i=float(data["input_i"]),
            input_tp=float(data["input_tp"]),
            input_lra=float(data["input_lra"]),
            input_thresh=float(data["input_thresh"]),
            target_offset=float(data["target_offset"]),
            output_i=float(data["output_i"]) if data.get("output_i") is not None else None,
            output_tp=float(data["output_tp"]) if data.get("output_tp") is not None else None,
            output_lra=float(data["output_lra"]) if data.get("output_lra") is not None else None,
            output_thresh=float(data["output_thresh"])
            if data.get("output_thresh") is not None
            else None,
            normalization_type=str(data.get("normalization_type", "linear")),
        )


def _parse_loudnorm_stats(stderr_text: str, default_norm_type: str = "linear") -> LoudnessStats:
    """Extract and parse the loudnorm JSON block from FFmpeg stderr."""
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr_text)
    if not match:
        raise RenderError(
            f"failed to parse loudnorm JSON from FFmpeg output:\n{stderr_text[-1000:]}"
        )
    try:
        data = json.loads(match.group(0))
        return LoudnessStats(
            input_i=float(data["input_i"]),
            input_tp=float(data["input_tp"]),
            input_lra=float(data["input_lra"]),
            input_thresh=float(data["input_thresh"]),
            target_offset=float(data["target_offset"]),
            output_i=float(data["output_i"]) if "output_i" in data else None,
            output_tp=float(data["output_tp"]) if "output_tp" in data else None,
            output_lra=float(data["output_lra"]) if "output_lra" in data else None,
            output_thresh=float(data["output_thresh"]) if "output_thresh" in data else None,
            normalization_type=str(data.get("normalization_type", default_norm_type)),
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RenderError(f"invalid loudnorm JSON statistics: {exc}") from exc


def measure_audio_loudness(
    source: Path,
    in_ms: int,
    duration_ms: int,
    binary: Path | None = None,
    speech_chain: bool = False,
    retained_intervals_ms: Sequence[tuple[int, int]] = (),
) -> LoudnessStats:
    """Pass 1 of two-pass EBU R128 loudness measurement (Task T3.1 / T3.2).

    Executes FFmpeg with loudnorm print_format=json into null muxer to measure
    integrated loudness, true peak, loudness range, input threshold, and target offset.
    If `speech_chain=True`, conditioning filters (highpass, afftdn, deesser, EQ)
    are applied so measurement reflects the final conditioned signal.
    If `retained_intervals_ms` has multiple segments, dead air is excised before measurement.
    """
    if binary is None:
        binary = find_ffmpeg()
    if not source.exists():
        raise RenderError(f"cannot measure loudness: source file {source} does not exist")
    if duration_ms <= 0:
        raise RenderError(f"cannot measure loudness: invalid duration {duration_ms}ms")

    af_chain = (
        f"{SPEECH_CHAIN_FILTERS},"
        f"loudnorm=I={DELIVERY_LUFS:g}:TP={DELIVERY_TRUE_PEAK_DB:g}:LRA=11:print_format=json"
        if speech_chain
        else f"loudnorm=I={DELIVERY_LUFS:g}:TP={DELIVERY_TRUE_PEAK_DB:g}:LRA=11:print_format=json"
    )

    if len(retained_intervals_ms) > 1:
        atrim_parts: list[str] = []
        concat_in: list[str] = []
        for idx, (s_ms, e_ms) in enumerate(retained_intervals_ms):
            s_sec = s_ms / 1000.0
            e_sec = e_ms / 1000.0
            atrim_parts.append(
                f"[0:a]atrim=start={s_sec:.3f}:end={e_sec:.3f},asetpts=PTS-STARTPTS[a{idx}]"
            )
            concat_in.append(f"[a{idx}]")
        atrim_graph = (
            f"{';'.join(atrim_parts)};"
            f"{''.join(concat_in)}concat=n={len(retained_intervals_ms)}:v=0:a=1[a_tightened];"
            f"[a_tightened]{af_chain}"
        )
        audio_stream_args = ["-filter_complex", atrim_graph]
    else:
        audio_stream_args = ["-af", af_chain]

    cmd = [
        str(binary),
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostats",
        "-ss",
        f"{in_ms / 1000:.3f}",
        "-t",
        f"{duration_ms / 1000:.3f}",
        "-i",
        str(source),
        "-vn",
        "-sn",
        "-dn",
        *audio_stream_args,
        "-f",
        "null",
        "-",
    ]
    timeout_s = max(30.0, (duration_ms / 1000.0) * 5.0)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"loudness measurement timed out after {timeout_s:.1f}s for {source}"
        ) from exc

    if proc.returncode != 0:
        raise RenderError(
            f"loudness measurement failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace')[-800:]}"
        )

    stderr_text = proc.stderr.decode("utf-8", "replace")
    return _parse_loudnorm_stats(stderr_text, default_norm_type="dynamic")


def audio_filter(
    measured: LoudnessStats | None = None,
    linear: bool = False,
    speech_chain: bool = False,
) -> str:
    """EBU R128 normalisation to the delivery target, with optional speech conditioning.

    If `speech_chain=True`, prepends highpass, afftdn denoiser, de-esser, and presence EQ.
    If `measured` is provided and `linear=True`, applies two-pass linear normalisation
    with static gain scaling and True Peak ceiling, eliminating dynamic volume pumping.
    If `measured` is None, falls back to single-pass dynamic normalisation for working renders.
    """
    prefix = f"{SPEECH_CHAIN_FILTERS}," if speech_chain else ""
    if measured is not None and linear:
        return (
            f"{prefix}"
            f"loudnorm=I={DELIVERY_LUFS:g}:TP={DELIVERY_TRUE_PEAK_DB:g}:LRA=11:"
            f"measured_I={measured.input_i:.2f}:measured_TP={measured.input_tp:.2f}:"
            f"measured_LRA={measured.input_lra:.2f}:measured_thresh={measured.input_thresh:.2f}:"
            f"offset={measured.target_offset:.2f}:linear=true:print_format=json,"
            f"aresample={DELIVERY_AUDIO_RATE}"
        )
    return (
        f"{prefix}"
        f"loudnorm=I={DELIVERY_LUFS:g}:TP={DELIVERY_TRUE_PEAK_DB:g}:LRA=11,"
        f"aresample={DELIVERY_AUDIO_RATE}"
    )


def _publish_render(staging: Path, output: Path) -> None:
    """Atomically publish one verified render without replacing a competing artifact."""
    try:
        # Same-directory hard-link publication is atomic and refuses EEXIST on both POSIX
        # and Windows. os.replace would be atomic but would silently overwrite the winner.
        os.link(staging, output)
    except FileExistsError as exc:
        raise RenderError(
            f"refusing to overwrite render artifact {output}; another job published it"
        ) from exc
    except OSError as exc:
        raise RenderError(f"could not atomically publish render artifact {output}: {exc}") from exc


class Reframe(Enum):
    """How the vertical crop was chosen. The name travels with the artifact.

    `FACE_TRACKED` is the current dynamic path. `SPEAKER_TRACKED` is what §3 Stage 6 ultimately
    specifies and still needs diarization (`BLOCKED.md` #4) plus face association. It exists so
    that the day it lands,
    every clip rendered before it is distinguishable from every clip rendered after, without
    anyone having to remember which was which.
    """

    STATIC_CENTRE = "static_centre"
    FACE_TRACKED = "face_tracked"
    SPEAKER_TRACKED = "speaker_tracked"
    BLURRED_FILL = "blurred_fill"
    TWO_PERSON_SPLIT = "two_person_split"


class Encoder(Enum):
    """§6: NVENC on hawapc01, x264 everywhere else. Never silently substituted."""

    X264 = "libx264"
    NVENC = "h264_nvenc"


@lru_cache(maxsize=8)
def encoder_available(encoder: Encoder, ffmpeg: Path) -> bool:
    """Can this ffmpeg actually encode with `encoder`? Attempted, not looked up.

    `-encoders` is a list of what was *compiled in*, which is not the same question. The
    static build used here lists `h264_nvenc` and cannot encode a single frame with it,
    because NVENC is loaded at runtime and there is no NVIDIA driver — measured, not assumed.
    Trusting the listing would let `render_clip` accept an NVENC request on this machine and
    fail deep inside the real encode, or worse, produce a truncated file.

    This is §4.3.2's lesson applied to encoders: "a build accepting the option may still lack
    the backing library". The only answer worth having comes from trying it, so this encodes
    one frame to a real file and checks that bytes came out. Cached — the answer cannot change
    within a process, and the probe costs an ffmpeg launch.

    **The probe encodes at the size Stage 6 actually outputs, and that is not a detail.** It
    used to use 64x64, and on hawapc01 — the machine §6 says to use NVENC on — that reported
    `h264_nvenc` unavailable while NVENC worked perfectly: NVENC refuses a frame below roughly
    `NVENC_MIN_FRAME` with "Frame Dimension less than the minimum supported value", and the
    probe was under it. Measured on this box: 64x64 and 128x128 write **0 bytes**, 145x49 and
    1080x1920 both encode. So the one function written because a capability listing cannot be
    trusted was itself returning a confident wrong answer, and `render_clip` would have refused
    NVENC exactly where §6 requires it. The question is "can this encoder encode what Stage 6
    will hand it", so the probe asks that question at that size.
    """
    with tempfile.TemporaryDirectory() as work:
        probe = Path(work) / "probe.mp4"
        result = subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={ENCODER_PROBE_SIZE[0]}x{ENCODER_PROBE_SIZE[1]}:d=0.1",
                "-frames:v",
                "1",
                "-c:v",
                encoder.value,
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(probe),
            ],
            capture_output=True,
            check=False,
            timeout=30.0,
        )
        # ffmpeg can exit 0 having written nothing when the encoder fails to initialise, so
        # the exit code alone is not the answer either.
        return result.returncode == 0 and probe.exists() and probe.stat().st_size > 0


def linked_libraries(ffmpeg: Path) -> str:
    """What this ffmpeg binary is dynamically linked against, via `ldd`.

    §4.3.2's warning is that a build accepting `shaping=complex` may lack the backing library,
    and `assert_rtl_stack` takes two evidence sources for exactly that reason: ffmpeg's own
    `--enable-libharfbuzz` governs *drawtext*, not whether the separately built, dynamically
    linked `libass.so` was itself compiled with HarfBuzz. The render path passed `""` for the
    second source, so the distro-build case the parameter exists for was dead code and Kurdish
    invariant #4 rested on a flag string. Found by the independent review of 2026-08-07.

    Returns the empty string rather than raising when `ldd` is absent or the binary is static —
    both are normal (the pinned build here *is* static), and a crash would take down every
    render. An empty result simply means this source contributes no evidence, which is what
    `assert_rtl_stack` already handles.
    """
    try:
        result = subprocess.run(
            ["ldd", str(ffmpeg)], capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


# Measured 2026-08-27 with the OpenCV frontal and profile cascades, 60 samples per source,
# 20 s apart, on two 1920x1080 Kurdish podcast sources:
#
#   ep10-0zC2bd03stw   1920x1080   246 detections   centre 33% down   face height 28.5%
#   ep29-VbX8UWwl1c4   2560x1440   163 detections   centre 31% down   face height 16.2%
#   01-MmQ9XPggSig     1920x1080   309 detections   centre 45% down   face height 11.6%
#
# The first two are the owner's own channel and both are well composed on the rule-of-thirds
# line; the third is a wide shot from a different channel. So the target is a floor that every
# well-shot source clears untouched, not an ideal every frame is dragged to — and it is set
# below **16.2%**, not below 28.5%.
#
# It was 0.22 for one commit, derived from ep10 alone, and ep29 disproved it. Measured: at 0.22
# ep29's 810x1440 crop tightens to 598x1062, so the upscale to 1080 wide goes from 1.33x to
# 1.81x — throwing away exactly the sharpness 1440p bought — and the crop cuts into the top of
# the subject's head. One source is not a distribution. D-258.
TARGET_FACE_HEIGHT_SHARE: Final = 0.15
# Where the face centre sits in the crop. Standard upper-third framing for a talking head, and
# close to the 33% the well-shot source measures on its own.
FACE_COMPOSITION_LINE: Final = 0.38
# The cap, and the honest part. Tightening is never free: a 1920x1080 source is already upscaled
# 1.78x to reach 1920 tall, so every bit of zoom comes straight out of sharpness. The 11.6% wide
# shot reaches 15% at 1.29x, taking its upscale to 2.30x — better framed and visibly softer, and
# a source shot that wide is better fixed at the camera than here. The cap bounds how far that
# trade can ever go.
MAX_VERTICAL_ZOOM: Final = 1.5

# How much tighter a punch-in sits than the base framing. Small on purpose: a punch-in is a change
# of emphasis, not a different shot, and past about a third it reads as a zoom effect rather than
# as an edit.
PUNCH_IN_ZOOM: Final = 1.25
# The floor on how often the framing may change. Measured against the delivered ep29 clip: 34.65 s
# in one unbroken framing. A social edit cuts far more often than that, but a change every second
# is a strobe, so each framing holds at least this long and every change lands on a sentence
# boundary — a cut mid-word reads as a glitch, not as a beat. D-259.
MIN_SHOT_MS: Final = 3_000
# The shortest gap between words that counts as a place to cut. A breath, not a sentence end.
#
# Measured on the delivered ep29 clip: 34.65 s carrying **two** sentences, so cutting only on
# sentence starts allowed exactly **one** framing change in the whole clip. The same clip has
# five pauses of 120 ms or more, which `MIN_SHOT_MS` then thins to three usable cuts. One change
# in 35 s is not an edit; three is a rhythm.
#
# A pause between words is also a *better* cut point than a sentence start, not merely a more
# frequent one: it is where the speaker themselves broke, which is where a human editor cuts.
# The rule that matters — never cut inside a word — is satisfied either way.
CUT_PAUSE_MS: Final = 120
# How far a punch-in must stay from a cut the *source* already made.
#
# Measured on the 56 s multi-angle clip: the source changes camera at 0.57 s, 17.09 s and
# 26.01 s, and a punch-in landed at **26.78 s** — 0.77 s after an angle change. The camera cuts,
# then the crop jumps scale before the eye has settled. Two changes that close read as a glitch
# rather than as rhythm, and the source cut *is already* the framing change, so the punch-in on
# top of it is redundant as well as jarring.
#
# Symmetric, because a punch-in shortly *before* an angle change is the same defect arriving in
# the other order.
SHOT_CUT_GUARD_MS: Final = 1_500


def cut_points_ms(words: Sequence[Word], clip_in_ms: int) -> tuple[int, ...]:
    """Clip-relative instants where a framing change may land, from the word alignment.

    Every gap of at least `CUT_PAUSE_MS` between consecutive words, timed at the *later* word's
    start so the new framing arrives with the new speech rather than during the silence.

    Empty when the speech has no pauses that long, which leaves `punch_in_schedule` with nothing
    to keep and the clip with the single framing it had before punch-ins existed.
    """
    points: list[int] = []
    for earlier, later in pairwise(words):
        if later.start_ms - earlier.end_ms >= CUT_PAUSE_MS:
            points.append(later.start_ms - clip_in_ms)
    return tuple(points)


def punch_in_schedule(
    boundaries_ms: Sequence[int],
    clip_duration_ms: int,
    *,
    min_shot_ms: int = MIN_SHOT_MS,
    zoom: float = PUNCH_IN_ZOOM,
    avoid_ms: Sequence[int] = (),
    guard_ms: int = SHOT_CUT_GUARD_MS,
) -> tuple[tuple[int, float], ...]:
    """Alternating wide/tight framings, one per kept boundary, clip-relative.

    `boundaries_ms` are instants measured from the clip's own zero where a framing may change —
    breaths between words, from `cut_points_ms`. Boundaries closer together than `min_shot_ms`
    are dropped rather than merged: holding a framing is the default and a change has to earn its
    place.

    `avoid_ms` are instants the *source* already cuts at. A punch-in within `guard_ms` of one is
    dropped: the angle change is the framing change, and a second one 0.77 s later — measured —
    reads as a glitch rather than as rhythm.

    Returns `()` when nothing survives, which is the honest answer for a clip too short or too
    sparse to cut, and which leaves `crop_filter` on exactly the path it took before punch-ins
    existed.

    Raises:
        ValueError: a non-positive duration, or a zoom that would widen instead of tighten.
    """
    if clip_duration_ms <= 0:
        raise ValueError(f"clip duration must be positive, got {clip_duration_ms}")
    if zoom < 1.0:
        raise ValueError(f"a punch-in tightens, so zoom must be at least 1.0, got {zoom}")

    kept: list[int] = []
    for at_ms in sorted(boundaries_ms):
        # A change at the first frame is the opening framing rather than a cut, and one at or
        # past the end would never be seen.
        if at_ms <= 0 or at_ms >= clip_duration_ms:
            continue
        if any(abs(at_ms - cut_ms) < guard_ms for cut_ms in avoid_ms):
            # The source already changes the picture here; adding to it is a double-cut.
            continue
        previous = kept[-1] if kept else 0
        if at_ms - previous < min_shot_ms:
            continue
        kept.append(at_ms)
    if not kept:
        return ()
    # The clip opens wide; every kept boundary flips it.
    return tuple((at_ms, zoom if index % 2 == 0 else 1.0) for index, at_ms in enumerate(kept))


DEFAULT_PUSH_ZOOM: Final = 1.08
DEFAULT_PUSH_STEP_MS: Final = 100


def shot_spans(
    boundaries_ms: Sequence[int],
    clip_duration_ms: int,
    *,
    source_cuts_ms: Sequence[int] = (),
    min_shot_ms: int = MIN_SHOT_MS,
    guard_ms: int = SHOT_CUT_GUARD_MS,
) -> tuple[tuple[int, int], ...]:
    """Partition clip duration into contiguous shot intervals [start_ms, end_ms] (Task T2.6).

    Uses pause boundaries and source cuts to determine motivated shot cuts.
    Boundaries closer together than min_shot_ms are dropped, and pause boundaries within
    guard_ms of a source cut are discarded.

    Returns:
        tuple of (start_ms, end_ms) contiguous intervals spanning 0 to clip_duration_ms.
    """
    if clip_duration_ms <= 0:
        raise ValueError(f"clip duration must be positive, got {clip_duration_ms}")

    # Collect source cuts strictly within the clip interior
    valid_source_cuts = [
        cut_ms for cut_ms in sorted(source_cuts_ms) if 0 < cut_ms < clip_duration_ms
    ]

    # Filter pause boundaries avoiding source cuts
    valid_boundaries = [
        b_ms
        for b_ms in sorted(boundaries_ms)
        if 0 < b_ms < clip_duration_ms
        and not any(abs(b_ms - cut_ms) < guard_ms for cut_ms in valid_source_cuts)
    ]

    # Combine all candidate cut points
    all_candidates = sorted(set(valid_source_cuts + valid_boundaries))

    kept_points: list[int] = [0]
    for pt in all_candidates:
        if pt - kept_points[-1] >= min_shot_ms and clip_duration_ms - pt >= 1_000:
            kept_points.append(pt)

    kept_points.append(clip_duration_ms)

    spans: list[tuple[int, int]] = []
    for start, end in pairwise(kept_points):
        if end > start:
            spans.append((start, end))

    return tuple(spans)


def eased_push_schedule(
    shot_spans: Sequence[tuple[int, int]],
    *,
    push_zoom: float = DEFAULT_PUSH_ZOOM,
    step_ms: int = DEFAULT_PUSH_STEP_MS,
    base_zoom: float = 1.0,
) -> tuple[tuple[int, float], ...]:
    """Generate discrete keyframes implementing continuous eased push-ins per shot (Task T2.6).

    Within each shot interval [start_ms, end_ms], smoothly interpolates the zoom factor
    from base_zoom to base_zoom * push_zoom using cubic smoothstep easing (S(p) = 3p^2 - 2p^3).
    At shot boundaries, the zoom factor resets to base_zoom, producing an instantaneous hard cut.

    Returns:
        tuple of (at_ms, factor) keyframes directly consumable by crop_filter.
    """
    if push_zoom < 1.0:
        raise ValueError(f"push_zoom must be at least 1.0, got {push_zoom}")
    if step_ms <= 0:
        raise ValueError(f"step_ms must be positive, got {step_ms}")

    keyframes: list[tuple[int, float]] = []

    for start_ms, end_ms in shot_spans:
        duration = end_ms - start_ms
        if duration <= 0:
            continue

        num_steps = max(1, duration // step_ms)
        for i in range(num_steps + 1):
            t_ms = min(end_ms, start_ms + i * step_ms)
            p = (t_ms - start_ms) / duration
            # Cubic smoothstep easing: 3*p^2 - 2*p^3
            ease = 3.0 * (p**2) - 2.0 * (p**3)
            factor = base_zoom * (1.0 + (push_zoom - 1.0) * ease)
            keyframes.append((t_ms, round(factor, 4)))

    # Deduplicate consecutive identical timestamps if any, keeping latest
    deduped: list[tuple[int, float]] = []
    for at_ms, factor in keyframes:
        if deduped and deduped[-1][0] == at_ms:
            deduped[-1] = (at_ms, factor)
        else:
            deduped.append((at_ms, factor))

    return tuple(deduped)


def vertical_framing(
    source_height: int,
    crop_w: int,
    crop_h: int,
    face_center_y: int | None,
    face_height: int | None,
    *,
    target_face_height_share: float = TARGET_FACE_HEIGHT_SHARE,
    max_vertical_zoom: float = MAX_VERTICAL_ZOOM,
) -> tuple[int, int, int]:
    """The crop rectangle after composing for the face: `(crop_w, crop_h, y)`.

    Returns the input untouched, with `y` at the centre, whenever nothing was measured or the
    face already fills at least `target_face_height_share` of the crop. That is the common case
    on a well-shot source and it must cost nothing: for any 16:9 source `crop_h` is the full
    height, so the crop is the whole frame and there is no vertical decision to make.

    When the face is smaller than the target the crop tightens toward it — both dimensions, so
    the 9:16 aspect is preserved — and slides so the face centre lands on
    `FACE_COMPOSITION_LINE`. Tightening is bounded by `max_vertical_zoom` because every bit of it
    is upscale on a source that has none to spare.
    """
    if face_height is not None and face_height <= 0:
        raise ValueError(f"a measured face height must be positive, got {face_height}")

    zoom = 1.0
    if face_height is not None and crop_h > 0:
        share = face_height / crop_h
        if share < target_face_height_share:
            zoom = min(target_face_height_share / share, max_vertical_zoom)
    if zoom > 1.0:
        # Even dimensions: an odd crop is a yuv420p encode failure, not a framing choice.
        crop_w = max(2, int(crop_w / zoom) // 2 * 2)
        crop_h = max(2, int(crop_h / zoom) // 2 * 2)

    if face_center_y is None:
        return crop_w, crop_h, (source_height - crop_h) // 2
    # Clamp rather than raise, for the reason the horizontal path clamps: a detector reporting a
    # face near the frame edge is correct about the face and merely asking for a crop that does
    # not fit. Sliding it into frame keeps the subject.
    y = max(0, min(face_center_y - int(FACE_COMPOSITION_LINE * crop_h), source_height - crop_h))
    return crop_w, crop_h, y


def vertical_crop_size(
    source_width: int,
    source_height: int,
    target_width: int = VERTICAL_WIDTH,
    target_height: int = VERTICAL_HEIGHT,
) -> tuple[int, int]:
    """The source-pixel rectangle a vertical crop takes, before scaling.

    Extracted from `crop_filter` because the reframe stabilizer needs the same number: a
    dead zone is only meaningful as a fraction of what the viewer can actually see, and a
    second copy of this arithmetic would be a second answer to that question.

    Raises:
        ValueError: the source is not positive, or is smaller than the crop it would need.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"source dimensions must be positive, got {source_width}x{source_height}")

    aspect = target_width / target_height
    crop_w = min(source_width, int(source_height * aspect))
    crop_h = min(source_height, int(source_width / aspect))
    # Even dimensions: yuv420p chroma is subsampled by two, and an odd crop is an encoder error
    # rather than a rounding difference.
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2
    if crop_w < 2 or crop_h < 2:
        raise ValueError(f"{source_width}x{source_height} cannot be cropped to {aspect:.3f}")
    return crop_w, crop_h


def _interpolated(points: Sequence[tuple[float, int]], fallback: int) -> str:
    """A piecewise-linear ffmpeg expression over `(seconds, value)` pairs.

    Extracted so the punch-in path can interpolate the *raw* face centres. The non-punch path
    interpolates positions that were already clamped against a fixed crop width — correct while
    the width never changes, and wrong the moment it does, because a position computed for the
    opening width drifts the subject sideways once the crop tightens.
    """
    if not points:
        return str(fallback)
    ordered = sorted(points)
    expression = str(ordered[-1][1])
    for index in range(len(ordered) - 2, -1, -1):
        start_s, here = ordered[index]
        end_s, there = ordered[index + 1]
        span = end_s - start_s
        segment = (
            str(here)
            if span <= 0 or here == there
            else f"({here}+({there - here})*(t-{start_s:.3f})/{span:.3f})"
        )
        expression = f"if(lt(t\\,{end_s:.3f})\\,{segment}\\,{expression})"
    if ordered[0][0] > 0:
        expression = f"if(lt(t\\,{ordered[0][0]:.3f})\\,{ordered[0][1]}\\,{expression})"
    return expression


def crop_filter(
    source_width: int,
    source_height: int,
    focus_x: int | None = None,
    focus_points: Sequence[tuple[int, int]] = (),
    clip_in_ms: int = 0,
    target_width: int = VERTICAL_WIDTH,
    target_height: int = VERTICAL_HEIGHT,
    *,
    face_center_y: int | None = None,
    face_height: int | None = None,
    punch_ins: Sequence[tuple[int, float]] = (),
    lanczos: bool = False,
    unsharp: bool = False,
    target_face_height_share: float = TARGET_FACE_HEIGHT_SHARE,
    max_vertical_zoom: float = MAX_VERTICAL_ZOOM,
) -> str:
    """The ffmpeg filter chain that takes a landscape frame to a vertical one.

    Crops to the target aspect ratio at the source's own resolution first and scales after, so
    the crop is expressed in source pixels and no detail is thrown away before it is chosen.

    Args:
        focus_x: horizontal centre of the crop, in source pixels. `None` centres it. This is
            the seam the speaker-tracking path plugs into: §3 Stage 6 derives it from
            diarization plus face detection, and until that exists every caller passes `None`
            and gets a crop that is honestly labelled `Reframe.STATIC_CENTRE`.
        lanczos: use high-quality Lanczos scaling instead of default bicubic (Task T2.10).
        unsharp: apply light luma unsharp sharpening post-scaling (Task T2.10).
        target_face_height_share: target face proportion for vertical framing composition.
        max_vertical_zoom: maximum upscale zoom allowed when tightening crop.

    Raises:
        ValueError: the source is smaller than the crop it would need.
    """
    crop_w, crop_h = vertical_crop_size(source_width, source_height, target_width, target_height)
    # Before the horizontal expression is built, because every clamp in it is against `crop_w`
    # and a tightened crop has a different one.
    crop_w, crop_h, y = vertical_framing(
        source_height,
        crop_w,
        crop_h,
        face_center_y,
        face_height,
        target_face_height_share=target_face_height_share,
        max_vertical_zoom=max_vertical_zoom,
    )

    if focus_points:
        ordered = sorted(focus_points)
        positions = [
            max(0, min(center - crop_w // 2, source_width - crop_w)) for _, center in ordered
        ]
        times = [(at_ms - clip_in_ms) / 1000 for at_ms, _ in ordered]
        # Interpolated, not stepped. A straight line between neighbouring keyframes is a pan;
        # a step between them is a glitch. `reframe.stabilize` supplies equal-valued neighbours
        # for the holds, so this sits still wherever the camera is meant to sit still.
        x: int | str = _interpolated(
            list(zip(times, positions, strict=True)),
            (source_width - crop_w) // 2,
        )
    elif focus_x is None:
        x = (source_width - crop_w) // 2
    else:
        # Clamp rather than raise: a face detector reporting a centre near the frame edge is
        # correct about the face and merely asking for a crop that does not fit. Sliding it
        # into frame keeps the subject; refusing would drop the clip.
        x = max(0, min(focus_x - crop_w // 2, source_width - crop_w))

    scale_flags = ":flags=lanczos" if lanczos else ""
    unsharp_filter = ",unsharp=5:5:0.5:5:5:0.0" if unsharp else ""

    if not punch_ins:
        scale_part = f"scale={target_width}:{target_height}{scale_flags}{unsharp_filter}"
        return f"crop={crop_w}:{crop_h}:{x}:{y},{scale_part}"

    # A punch-in changes the crop *size*, and ffmpeg evaluates `w`/`h` once at configuration —
    # only `x`/`y` are per-frame. So the size changes by command rather than by expression: all
    # four of crop's options carry the `T` flag, and that was proven on real footage before being
    # designed around, the way D-249 learned to with `-crf`.
    #
    # `x` and `y` are rewritten in terms of ffmpeg's own `out_w`/`out_h` so the crop re-centres
    # itself the instant its size changes.
    centre_x: int | str = (
        _interpolated(
            [((at_ms - clip_in_ms) / 1000, centre) for at_ms, centre in focus_points],
            source_width // 2,
        )
        if focus_points
        else (source_width // 2 if focus_x is None else focus_x)
    )
    x_expr = f"min(max({centre_x}-out_w/2\\,0)\\,in_w-out_w)"
    if face_center_y is not None:
        y_expr = f"min(max({face_center_y}-{FACE_COMPOSITION_LINE}*out_h\\,0)\\,in_h-out_h)"
    else:
        centre_y = source_height // 2
        y_expr = f"min(max({centre_y}-out_h/2\\,0)\\,in_h-out_h)"

    commands = ";".join(
        f"{at_ms / 1000:.3f} crop w {max(2, int(crop_w / factor)) // 2 * 2};"
        f"{at_ms / 1000:.3f} crop h {max(2, int(crop_h / factor)) // 2 * 2}"
        for at_ms, factor in punch_ins
    )
    return (
        f"sendcmd=c='{commands}',"
        f"crop={crop_w}:{crop_h}:{x_expr}:{y_expr},"
        f"scale={target_width}:{target_height}{scale_flags}{unsharp_filter}"
    )


def blurred_fill_filter(
    source_width: int,
    source_height: int,
    target_width: int = VERTICAL_WIDTH,
    target_height: int = VERTICAL_HEIGHT,
    *,
    blur_radius: int = 20,
    brightness: float = -0.15,
    lanczos: bool = False,
    unsharp: bool = False,
) -> str:
    """The ffmpeg filter chain placing a wide 16:9 shot over a blurred, darkened 9:16 background.

    Used when a shot's face share is too small for a close crop and zooming in would violate the
    sharpness floor (Task T2.2). The wide source is scaled sharp to target_width and centered,
    while the background is scaled to cover the canvas, blurred with boxblur, and darkened with eq.

    Args:
        source_width: original source video width.
        source_height: original source video height.
        target_width: output vertical width (default 1080).
        target_height: output vertical height (default 1920).
        blur_radius: boxblur luma radius for background (default 20).
        brightness: eq brightness adjustment for background (default -0.15).
        lanczos: use high-quality Lanczos scaling for foreground.
        unsharp: apply light sharpening to the sharp foreground.

    Raises:
        ValueError: source dimensions are non-positive.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"source dimensions must be positive, got {source_width}x{source_height}")

    scale_flags = ":flags=lanczos" if lanczos else ""
    unsharp_filter = ",unsharp=5:5:0.5:5:5:0.0" if unsharp else ""

    return (
        f"split=2[fg][bg];"
        f"[bg]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
        f"crop={target_width}:{target_height},"
        f"boxblur={blur_radius}:2,eq=brightness={brightness}[bg_blur];"
        f"[fg]scale={target_width}:-2{scale_flags}{unsharp_filter}[fg_sharp];"
        f"[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2"
    )


def two_person_split_filter(
    source_width: int,
    source_height: int,
    top_crop: tuple[int, int, int, int],
    bottom_crop: tuple[int, int, int, int],
    target_width: int = VERTICAL_WIDTH,
    target_height: int = VERTICAL_HEIGHT,
    *,
    lanczos: bool = False,
    unsharp: bool = False,
) -> str:
    """The ffmpeg filter chain placing two tracked speaker crops in a stacked 9:16 vertical split.

    Used when diarization indicates rapid conversational exchanges (Task T2.12).
    Top crop (9:8) scales to target_width x (target_height // 2) [1080x960].
    Bottom crop (9:8) scales to target_width x (target_height // 2) [1080x960].
    Stacked vertically with vstack=inputs=2 to form a 1080x1920 vertical canvas.

    Args:
        source_width: original source video width.
        source_height: original source video height.
        top_crop: (x, y, w, h) crop rectangle for top speaker pane.
        bottom_crop: (x, y, w, h) crop rectangle for bottom speaker pane.
        target_width: output vertical width (default 1080).
        target_height: output vertical height (default 1920).
        lanczos: use high-quality Lanczos scaling.
        unsharp: apply light sharpening.

    Raises:
        ValueError: dimensions non-positive or crop boxes out of bounds.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"source dimensions must be positive, got {source_width}x{source_height}")
    if target_width <= 0 or target_height <= 0:
        raise ValueError(f"target dimensions must be positive, got {target_width}x{target_height}")
    if target_height % 2 != 0:
        raise ValueError(f"target_height must be even, got {target_height}")

    pane_h = target_height // 2

    def _validate_crop(crop: tuple[int, int, int, int], name: str) -> None:
        x, y, w, h = crop
        if w <= 0 or h <= 0:
            raise ValueError(f"{name} crop dimensions must be positive, got {w}x{h}")
        if x < 0 or y < 0:
            raise ValueError(f"{name} crop coordinates must be non-negative, got ({x}, {y})")
        if x + w > source_width or y + h > source_height:
            raise ValueError(
                f"{name} crop box ({x}, {y}, {w}, {h}) exceeds source dimensions "
                f"{source_width}x{source_height}"
            )

    _validate_crop(top_crop, "top")
    _validate_crop(bottom_crop, "bottom")

    scale_flags = ":flags=lanczos" if lanczos else ""
    unsharp_filter = ",unsharp=5:5:0.5:5:5:0.0" if unsharp else ""

    tx, ty, tw, th = top_crop
    bx, by, bw, bh = bottom_crop

    return (
        f"split=2[top_src][bot_src];"
        f"[top_src]crop={tw}:{th}:{tx}:{ty},scale={target_width}:{pane_h}{scale_flags}{unsharp_filter}[top_p];"
        f"[bot_src]crop={bw}:{bh}:{bx}:{by},scale={target_width}:{pane_h}{scale_flags}{unsharp_filter}[bot_p];"
        f"[top_p][bot_p]vstack=inputs=2"
    )


def decide_wide_shot_layout(
    face_height_share: float,
    face_sharpness: float,
    *,
    closeup_sharpness_median: float | None = None,
    target_face_height_share: float = TARGET_FACE_HEIGHT_SHARE,
    max_wide_zoom: float = 2.5,
    default_sharpness_floor: float = 50.0,
) -> tuple[str, float]:
    """Decide wide-shot presentation: standard crop, deep zoom, or blurred-fill (Task T2.2).

    When face_height_share is below target_face_height_share (0.18), either:
    1. Zoom past MAX_VERTICAL_ZOOM (up to max_wide_zoom) if face sharpness is at or above
       the sharpness floor (0.6 * closeup_sharpness_median).
    2. Switch to blurred-fill layout if the face lacks sharpness to withstand deep digital zoom.

    Returns:
        (layout_mode, zoom_factor) where layout_mode is "crop", "zoom", or "blurred_fill".
    """
    if face_height_share <= 0:
        raise ValueError(f"face_height_share must be positive, got {face_height_share}")

    if face_height_share >= target_face_height_share:
        return "crop", 1.0

    floor = (
        closeup_sharpness_median * 0.6
        if closeup_sharpness_median is not None
        else default_sharpness_floor
    )
    if face_sharpness >= floor:
        zoom = min(target_face_height_share / face_height_share, max_wide_zoom)
        return "zoom", round(zoom, 3)

    return "blurred_fill", 1.0


@dataclass(frozen=True, slots=True)
class RenderResult:
    """One rendered clip, and the choices that produced it."""

    clip_id: str
    path: str
    width: int
    height: int
    # Two durations, because they are two different facts. `requested` is the clip's own span
    # — what §5 says this clip is. `measured` is probed from the file that was written. They
    # agreed silently for as long as nobody looked; §8.3 asks for the invariant "on every
    # shipped clip", and a shipped clip is a file, not a plan.
    requested_duration_ms: int
    measured_duration_ms: int
    reframe: Reframe
    encoder: Encoder
    captions_burned_in: bool
    ffmpeg_version: str
    loudness_pass1: LoudnessStats | None = None
    loudness_pass2: LoudnessStats | None = None
    brand_kit: BrandKit | None = None

    @property
    def duration_ms(self) -> int:
        """The duration of the artifact. Kept as a name because the file is the answer."""
        return self.measured_duration_ms


def frame_duration_ms(video: Path, ffmpeg: Path | None = None) -> int:
    """One frame of `video`, in milliseconds, from the file's own rate.

    Not a constant: the fixture here is 25 fps (40 ms), a 30 fps source is 33 ms. Assuming a
    rate would make the tolerance below either too tight for one source or too loose for
    another, and "too loose" is the direction that ships a truncated clip.
    """
    return round(1000 / frame_rate(video, ffmpeg))


def frame_rate(video: Path, ffmpeg: Path | None = None) -> float:
    """`video`'s frame rate, from `r_frame_rate`, kept as the exact ratio ffprobe reports.

    `30000/1001` is 29.97002997…, and rounding it to 30 here is the difference between an EDL
    that selects drop-frame numbering and one that drifts. `delivery.ms_to_timecode` can make
    that decision only if it is told the source's true rate.
    """
    try:
        rate = probe_stream(video, "stream=r_frame_rate", ffmpeg, video_only=True)
    except IngestError as exc:
        raise RenderError(str(exc)) from exc
    try:
        numerator, denominator = (int(part) for part in rate.split("/"))
        if numerator <= 0 or denominator <= 0:
            raise ValueError(rate)
    except ValueError as exc:
        # A video file whose frame rate cannot be read is not a file to guess about.
        raise RenderError(f"could not read a frame rate from {video}: {rate!r}") from exc
    return numerator / denominator


def assert_encoded_span(measured_ms: int, requested_ms: int, frame_ms: int) -> None:
    """Refuse an encode whose duration differs from the requested clip by over one frame.

    §8.3: "Boundary invariant: assert `final_in <= anchor_in` and `final_out >= anchor_out` on
    every shipped clip." A file short of `requested_ms` ends before the clip's own `final_out`,
    which is mid-sentence — exactly what Kurdish invariant #2 forbids — while every check on
    the numbers passed, because the numbers were never compared to the artifact.

    One frame of slack in each direction, measured rather than assumed: correct cuts of the
    real fixture came back exact except one, which was over by 40 ms — precisely one frame at
    25 fps. A longer file is also a defect: it can expose trailing source footage that has no
    corresponding transcript, captions, editorial review, or consent. One frame of container
    rounding in either direction is not.
    """
    if measured_ms < requested_ms - frame_ms:
        raise RenderError(
            f"the encoded file is {measured_ms} ms, shorter than the {requested_ms} ms clip it "
            f"claims to be (tolerance one frame, {frame_ms} ms). The clip ends before its own "
            f"final_out, which is mid-sentence — §8.3 asserts Kurdish invariant #2 on every "
            f"shipped clip, and the shipped clip is this file."
        )
    if measured_ms > requested_ms + frame_ms:
        raise RenderError(
            f"the encoded file is {measured_ms} ms, longer than the {requested_ms} ms clip it "
            f"claims to be (tolerance one frame, {frame_ms} ms). Trailing source footage "
            f"outside the reviewed clip must never be published."
        )


def render_clip(
    clip: Clip,
    source: Path,
    ass_path: Path,
    fonts_dir: Path,
    output: Path,
    source_width: int,
    source_height: int,
    encoder: Encoder = Encoder.X264,
    focus_x: int | None = None,
    focus_points: Sequence[tuple[int, int]] = (),
    ffmpeg: Path | None = None,
    crf: int = 20,
    reframe: Reframe | None = None,
    *,
    face_center_y: int | None = None,
    face_height: int | None = None,
    punch_ins: Sequence[tuple[int, float]] = (),
    fps: float | None = None,
    deliverable: bool = False,
    silence_plan: SilencePlan | None = None,
    split_crops: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None = None,
    brand_kit: BrandKit | None = None,
    music_bed_path: Path | None = None,
    music_ducking_volume: float = 0.25,
    for_review: bool = False,
) -> RenderResult:
    """Cut, reframe, burn in Kurdish captions and encode one clip.

    The clip's own gate runs first: `assert_renderable()` covers Kurdish invariant #2 and §2's
    QC-before-output rule, so a rejected clip cannot reach an encoder through this function.

    Raises:
        BoundaryInvariantViolated: Kurdish invariant #2 fails for this clip.
        ValueError: the clip has not cleared QC, or has no editorial/output block.
        MissingRtlStack: this ffmpeg cannot shape Arabic script (§4.3.2).
        RenderError: no ffmpeg, the requested encoder is absent, or the encode failed.
    """
    clip.assert_renderable(for_review=for_review)
    if brand_kit is not None:
        brand_kit.assert_valid()

    effective_reframe = (
        (Reframe.FACE_TRACKED if focus_points else Reframe.STATIC_CENTRE)
        if reframe is None
        else reframe
    )
    if not isinstance(effective_reframe, Reframe):
        raise TypeError("reframe must be a Reframe value")
    if effective_reframe is Reframe.STATIC_CENTRE and focus_points:
        raise ValueError("static reframe mode cannot carry focus points")
    if effective_reframe is Reframe.BLURRED_FILL and focus_points:
        raise ValueError("blurred_fill reframe mode cannot carry focus points")
    if effective_reframe is Reframe.TWO_PERSON_SPLIT and focus_points:
        raise ValueError("two_person_split reframe mode cannot carry focus points")
    if effective_reframe is Reframe.TWO_PERSON_SPLIT and not split_crops:
        raise ValueError("two_person_split reframe mode requires split_crops")
    if effective_reframe is not Reframe.TWO_PERSON_SPLIT and split_crops:
        raise ValueError("split_crops can only be passed when reframe is TWO_PERSON_SPLIT")
    if (
        effective_reframe
        not in (Reframe.STATIC_CENTRE, Reframe.BLURRED_FILL, Reframe.TWO_PERSON_SPLIT)
        and not focus_points
    ):
        raise ValueError("dynamic reframe mode needs focus points")

    # The final name is a write-once publication target, never ffmpeg's working file. Checking
    # before the expensive probes/encode gives deterministic reruns, while the atomic link at
    # publication time closes the race with another worker that passes this same preflight.
    if os.path.lexists(output):
        raise RenderError(
            f"refusing to overwrite render artifact {output}; choose a new clip/run id"
        )

    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise RenderError("no ffmpeg available — run hawedit-ffmpeg-setup or set HAWEDIT_FFMPEG")

    version = subprocess.run(
        [str(binary), "-hide_banner", "-version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    ).stdout.splitlines()[0]
    buildconf = subprocess.run(
        [str(binary), "-hide_banner", "-buildconf"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    ).stdout
    # §4.3.2: a build that accepts shaping=complex may still lack HarfBuzz, and the failure is
    # invisible until a client sees the captions. Checked here, not only in the golden test.
    assert_rtl_stack(buildconf, linked_libraries(binary))

    if not encoder_available(encoder, binary):
        raise RenderError(
            f"{binary} has no {encoder.value} encoder. §6 puts NVENC on hawapc01; falling back "
            f"to x264 here would make any throughput figure a measurement of the wrong encoder."
        )

    if not ass_path.exists():
        raise RenderError(f"no subtitle file at {ass_path} — §4.3 captions are not optional")
    try:
        ass_text = ass_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RenderError(f"cannot read subtitle file {ass_path}: {exc}") from exc

    duration_ms = clip.out_ms - clip.in_ms
    # Subtitles are burned into a stream ffmpeg has already cut, so t=0 is the start of the
    # clip. A file carrying source-absolute stamps draws nothing and ships a caption-free MP4;
    # checked here on whatever file arrives, not only where `build_ass` writes one.
    assert_captions_within_clip(ass_text, duration_ms)
    try:
        assert_ass_fonts_cover_kurdish(ass_text, fonts_dir)
    except FontCoverageError as exc:
        raise RenderError(str(exc)) from exc
    # Measured on the real fixture: asking for 0..8000 ms of a 4162 ms source makes ffmpeg
    # exit 0 and write 4180 ms. Nothing in the numbers is wrong — the clip is internally
    # consistent — so the only place to catch it is against the media itself, before encoding.
    source_ms = probe_duration_ms(source, binary)
    if clip.out_ms > source_ms:
        raise RenderError(
            f"clip {clip.clip_id} ends at {clip.out_ms} ms but {source.name} is {source_ms} ms. "
            f"ffmpeg would encode this successfully and truncate it, and the shipped clip would "
            f"end {clip.out_ms - source_ms} ms before its own final_out — mid-sentence, which "
            f"§8.3 asserts against on every shipped clip."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if effective_reframe is Reframe.BLURRED_FILL:
        video_filter = blurred_fill_filter(
            source_width,
            source_height,
            lanczos=deliverable,
            unsharp=deliverable,
        )
    elif effective_reframe is Reframe.TWO_PERSON_SPLIT:
        assert split_crops is not None
        video_filter = two_person_split_filter(
            source_width,
            source_height,
            split_crops[0],
            split_crops[1],
            lanczos=deliverable,
            unsharp=deliverable,
        )
    else:
        video_filter = crop_filter(
            source_width,
            source_height,
            focus_x,
            focus_points=focus_points,
            face_center_y=face_center_y,
            face_height=face_height,
            punch_ins=punch_ins,
            clip_in_ms=clip.in_ms,
            lanczos=deliverable,
            unsharp=deliverable,
        )

    # Keep the container suffix: ffmpeg infers its muxer from the path. NamedTemporaryFile is
    # closed before ffmpeg starts so Windows can replace its empty placeholder with the encode.
    with tempfile.NamedTemporaryFile(
        dir=output.parent,
        prefix=f".{output.stem}.",
        suffix=output.suffix,
        delete=False,
    ) as staging_file:
        staging = Path(staging_file.name)

    decode_threads = [] if deliverable else ["-threads", "1"]
    color_metadata = list(DELIVERY_COLOR_ARGS) if deliverable else []
    clip_fps = fps if fps is not None else frame_rate(source, binary)
    video_args = deliverable_video_args(encoder, crf, fps=clip_fps, deliverable=deliverable)

    effective_duration_ms = (
        (duration_ms - silence_plan.total_removed_ms)
        if (silence_plan is not None and silence_plan.total_removed_ms > 0)
        else duration_ms
    )

    loudness_p1: LoudnessStats | None = None
    loudness_p2: LoudnessStats | None = None
    if deliverable:
        loudness_p1 = measure_audio_loudness(
            source=source,
            in_ms=clip.in_ms,
            duration_ms=duration_ms,
            binary=binary,
            speech_chain=True,
            retained_intervals_ms=silence_plan.retained_intervals_ms if silence_plan else (),
        )
        af_chain = audio_filter(measured=loudness_p1, linear=True, speech_chain=True)
        loglevel_args = ["-loglevel", "info"]
    else:
        af_chain = audio_filter()
        loglevel_args = ["-loglevel", "error"]

    pb_f: str | None = None
    if brand_kit is not None and brand_kit.progress_bar.enabled:
        pb_f = progress_bar_filter(
            duration_s=effective_duration_ms / 1000.0,
            color=brand_kit.progress_bar.color,
            height_px=brand_kit.progress_bar.height_px,
            position=brand_kit.progress_bar.position,
            canvas_height=VERTICAL_HEIGHT,
        )

    sub_f = subtitle_filter(ass_path, fonts_dir)
    extra_inputs: list[str] = []

    if brand_kit is not None and brand_kit.logo_path is not None:
        extra_inputs.extend(["-i", str(brand_kit.logo_path)])
    if music_bed_path is not None:
        if not music_bed_path.is_file():
            raise FileNotFoundError(f"music bed file not found: {music_bed_path}")
        extra_inputs.extend(["-i", str(music_bed_path)])

    has_logo = brand_kit is not None and brand_kit.logo_path is not None
    has_silence = silence_plan is not None and silence_plan.total_removed_ms > 0
    has_music = music_bed_path is not None

    if has_logo or has_silence or has_music:
        if has_silence and silence_plan is not None:
            trim_prefix = f"{silence_trim_filter(silence_plan.retained_intervals_ms)};"
            v_in = "[v_tightened]"
            a_in = "[a_tightened]"
        else:
            trim_prefix = ""
            v_in = "[0:v]"
            a_in = "[0:a]"

        if effective_reframe in (Reframe.BLURRED_FILL, Reframe.TWO_PERSON_SPLIT):
            v_base = f"{v_in}{video_filter}[v_split];[v_split]{sub_f}[v_sub]"
        else:
            v_base = f"{v_in}{video_filter},{sub_f}[v_sub]"

        v_current = "[v_sub]"
        logo_steps = ""
        if has_logo and brand_kit is not None and brand_kit.logo_path is not None:
            logo_x, logo_y = logo_overlay_coordinates(
                brand_kit.logo_position, brand_kit.logo_margin
            )
            logo_prep = (
                f"[1:v]scale={brand_kit.logo_width}:-2,format=rgba,"
                f"colorchannelmixer=aa={brand_kit.logo_opacity:.2f}[logo];"
            )
            logo_overlay = (
                f"{v_current}[logo]overlay={logo_x}:{logo_y}:eof_action=repeat[v_branded];"
            )
            logo_steps = f"{logo_prep}{logo_overlay}"
            v_current = "[v_branded]"

        v_pb = f"{v_current}{pb_f}[v_out]" if pb_f is not None else f"{v_current}null[v_out]"

        if has_music:
            music_input_idx = 2 if has_logo else 1
            dur_s = effective_duration_ms / 1000.0
            sc_filter = "sidechaincompress=threshold=0.03:ratio=6:attack=80:release=400"
            mix_filter = "amix=inputs=2:weights=1.0 1.0:dropout_transition=2"
            a_chain = (
                f"[{music_input_idx}:a]aloop=loop=-1:size=2e+09,atrim=0:{dur_s:.3f},"
                f"asetpts=PTS-STARTPTS,volume={music_ducking_volume:.2f}[music_in];"
                f"{a_in}asplit=2[dia_mix][dia_sc];"
                f"[music_in][dia_sc]{sc_filter}[ducked_music];"
                f"[dia_mix][ducked_music]{mix_filter}[a_mixed];"
                f"[a_mixed]{af_chain}[a_out]"
            )
        else:
            a_chain = f"{a_in}{af_chain}[a_out]"

        full_complex = f"{trim_prefix}{v_base};{logo_steps}{v_pb};{a_chain}"
        stream_filter_args = [
            "-filter_complex",
            full_complex,
            "-map",
            "[v_out]",
            "-map",
            "[a_out]",
        ]
    else:
        v_filters = [video_filter, sub_f]
        if pb_f:
            v_filters.append(pb_f)
        stream_filter_args = [
            "-vf",
            ",".join(v_filters),
            "-af",
            af_chain,
        ]

    timeout_s = max(60.0, (duration_ms / 1000.0) * 10.0)
    try:
        try:
            result = subprocess.run(
                [
                    str(binary),
                    "-hide_banner",
                    *loglevel_args,
                    *decode_threads,
                    "-ss",
                    f"{clip.in_ms / 1000:.3f}",
                    "-t",
                    f"{duration_ms / 1000:.3f}",
                    "-i",
                    str(source),
                    *extra_inputs,
                    *stream_filter_args,
                    "-c:v",
                    encoder.value,
                    *video_args,
                    "-pix_fmt",
                    "yuv420p",
                    *color_metadata,
                    "-c:a",
                    "aac",
                    "-b:a",
                    DELIVERY_AUDIO_BITRATE,
                    "-ar",
                    str(DELIVERY_AUDIO_RATE),
                    "-ac",
                    "2",
                    # The moov atom belongs at the front of a file that will be streamed. Without
                    # this it is written last, and a player has to fetch the end of the file before
                    # it can start — which for a delivery artifact is the whole point of the format.
                    "-movflags",
                    "+faststart",
                    # A second, output-side duration. The input-side `-t` above bounds what is
                    # decoded; this bounds what is written. Without it the AAC encoder pads its
                    # final frame and the 48 kHz resample rounds up, and the container comes out
                    # 38 ms long on the real fixture — inside `assert_encoded_span`'s one-frame
                    # tolerance, but 38 ms of source that no one reviewed. With it the artifact is
                    # exactly the span §8.3 says it is: measured 4162 ms for a 4162 ms clip.
                    "-t",
                    f"{effective_duration_ms / 1000:.3f}",
                    "-y",
                    str(staging),
                ],
                capture_output=True,
                check=False,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"encode timed out after {timeout_s:.1f}s: ffmpeg did not finish in time"
            ) from exc
        if result.returncode != 0 or not staging.exists() or staging.stat().st_size == 0:
            raise RenderError(
                f"encode failed ({result.returncode}): "
                f"{result.stderr.decode('utf-8', 'replace')[-800:]}"
            )

        if deliverable and loudness_p1 is not None:
            stderr_text = result.stderr.decode("utf-8", "replace")
            try:
                loudness_p2 = _parse_loudnorm_stats(stderr_text, default_norm_type="linear")
            except RenderError:
                loudness_p2 = None

        # Measure before publication. A short/broken file is never visible under the delivery
        # name, even briefly.
        measured_ms = probe_duration_ms(staging, binary)
        assert_encoded_span(measured_ms, effective_duration_ms, frame_duration_ms(staging, binary))

        _publish_render(staging, output)
    finally:
        staging.unlink(missing_ok=True)

    return RenderResult(
        clip_id=clip.clip_id,
        path=str(output),
        width=VERTICAL_WIDTH,
        height=VERTICAL_HEIGHT,
        requested_duration_ms=effective_duration_ms,
        measured_duration_ms=measured_ms,
        # The explicit mode was validated against the crop evidence before any encode work,
        # so the artifact cannot claim speaker/face tracking without time-varying points.
        reframe=effective_reframe,
        encoder=encoder,
        captions_burned_in=True,
        ffmpeg_version=version,
        loudness_pass1=loudness_p1,
        loudness_pass2=loudness_p2,
        brand_kit=brand_kit,
    )
