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

import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Final

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
from hawedit.transcripts import Word

__all__ = [
    "DELIVERY_AUDIO_RATE",
    "DELIVERY_LUFS",
    "DELIVERY_TRUE_PEAK_DB",
    "ENCODER_PROBE_SIZE",
    "NVENC_MIN_FRAME",
    "VERTICAL_HEIGHT",
    "VERTICAL_WIDTH",
    "Encoder",
    "Reframe",
    "RenderError",
    "RenderResult",
    "assert_encoded_span",
    "audio_filter",
    "crop_filter",
    "encoder_available",
    "frame_duration_ms",
    "frame_rate",
    "linked_libraries",
    "quality_args",
    "render_clip",
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


def audio_filter() -> str:
    """Single-pass EBU R128 normalisation to the delivery target.

    Single pass rather than the two-pass measure-then-apply: the second pass buys accuracy
    this does not need (a fraction of a LU on a speech clip) at the cost of decoding the audio
    twice, and the clip is already cut to length before it gets here.
    """
    return (
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


def vertical_framing(
    source_height: int,
    crop_w: int,
    crop_h: int,
    face_center_y: int | None,
    face_height: int | None,
) -> tuple[int, int, int]:
    """The crop rectangle after composing for the face: `(crop_w, crop_h, y)`.

    Returns the input untouched, with `y` at the centre, whenever nothing was measured or the
    face already fills at least `TARGET_FACE_HEIGHT_SHARE` of the crop. That is the common case
    on a well-shot source and it must cost nothing: for any 16:9 source `crop_h` is the full
    height, so the crop is the whole frame and there is no vertical decision to make.

    When the face is smaller than the target the crop tightens toward it — both dimensions, so
    the 9:16 aspect is preserved — and slides so the face centre lands on
    `FACE_COMPOSITION_LINE`. Tightening is bounded by `MAX_VERTICAL_ZOOM` because every bit of it
    is upscale on a source that has none to spare.
    """
    if face_height is not None and face_height <= 0:
        raise ValueError(f"a measured face height must be positive, got {face_height}")

    zoom = 1.0
    if face_height is not None and crop_h > 0:
        share = face_height / crop_h
        if share < TARGET_FACE_HEIGHT_SHARE:
            zoom = min(TARGET_FACE_HEIGHT_SHARE / share, MAX_VERTICAL_ZOOM)
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
) -> str:
    """The ffmpeg filter chain that takes a landscape frame to a vertical one.

    Crops to the target aspect ratio at the source's own resolution first and scales after, so
    the crop is expressed in source pixels and no detail is thrown away before it is chosen.

    Args:
        focus_x: horizontal centre of the crop, in source pixels. `None` centres it. This is
            the seam the speaker-tracking path plugs into: §3 Stage 6 derives it from
            diarization plus face detection, and until that exists every caller passes `None`
            and gets a crop that is honestly labelled `Reframe.STATIC_CENTRE`.

    Raises:
        ValueError: the source is smaller than the crop it would need.
    """
    crop_w, crop_h = vertical_crop_size(source_width, source_height, target_width, target_height)
    # Before the horizontal expression is built, because every clamp in it is against `crop_w`
    # and a tightened crop has a different one.
    crop_w, crop_h, y = vertical_framing(source_height, crop_w, crop_h, face_center_y, face_height)

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

    if not punch_ins:
        return f"crop={crop_w}:{crop_h}:{x}:{y},scale={target_width}:{target_height}"

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
        f"scale={target_width}:{target_height}"
    )


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
    clip.assert_renderable()

    effective_reframe = (
        (Reframe.FACE_TRACKED if focus_points else Reframe.STATIC_CENTRE)
        if reframe is None
        else reframe
    )
    if not isinstance(effective_reframe, Reframe):
        raise TypeError("reframe must be a Reframe value")
    if effective_reframe is Reframe.STATIC_CENTRE and focus_points:
        raise ValueError("static reframe mode cannot carry focus points")
    if effective_reframe is not Reframe.STATIC_CENTRE and not focus_points:
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
        [str(binary), "-hide_banner", "-version"], capture_output=True, text=True, check=False
    ).stdout.splitlines()[0]
    buildconf = subprocess.run(
        [str(binary), "-hide_banner", "-buildconf"], capture_output=True, text=True, check=False
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
    filters = ",".join(
        [
            crop_filter(
                source_width,
                source_height,
                focus_x,
                focus_points=focus_points,
                face_center_y=face_center_y,
                face_height=face_height,
                punch_ins=punch_ins,
                clip_in_ms=clip.in_ms,
            ),
            subtitle_filter(ass_path, fonts_dir),
        ]
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

    timeout_s = max(60.0, (duration_ms / 1000.0) * 10.0)
    try:
        try:
            result = subprocess.run(
                [
                    str(binary),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-threads",
                    "1",  # §6: parallelism across clips, not inside one encode
                    "-ss",
                    f"{clip.in_ms / 1000:.3f}",
                    "-t",
                    f"{duration_ms / 1000:.3f}",
                    "-i",
                    str(source),
                    "-vf",
                    filters,
                    "-af",
                    audio_filter(),
                    "-c:v",
                    encoder.value,
                    *quality_args(encoder, crf),
                    "-pix_fmt",
                    "yuv420p",
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
                    f"{duration_ms / 1000:.3f}",
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

        # Measure before publication. A short/broken file is never visible under the delivery
        # name, even briefly.
        measured_ms = probe_duration_ms(staging, binary)
        assert_encoded_span(measured_ms, duration_ms, frame_duration_ms(staging, binary))

        _publish_render(staging, output)
    finally:
        staging.unlink(missing_ok=True)

    return RenderResult(
        clip_id=clip.clip_id,
        path=str(output),
        width=VERTICAL_WIDTH,
        height=VERTICAL_HEIGHT,
        requested_duration_ms=duration_ms,
        measured_duration_ms=measured_ms,
        # The explicit mode was validated against the crop evidence before any encode work,
        # so the artifact cannot claim speaker/face tracking without time-varying points.
        reframe=effective_reframe,
        encoder=encoder,
        captions_burned_in=True,
        ffmpeg_version=version,
    )
