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
from pathlib import Path
from typing import Final

from hawedit.captions import (
    assert_captions_within_clip,
    assert_rtl_stack,
    find_ffmpeg,
    subtitle_filter,
)
from hawedit.clip import Clip
from hawedit.ingest import IngestError, probe_duration_ms, probe_stream

__all__ = [
    "ENCODER_PROBE_SIZE",
    "NVENC_MIN_FRAME",
    "VERTICAL_HEIGHT",
    "VERTICAL_WIDTH",
    "Encoder",
    "Reframe",
    "RenderError",
    "RenderResult",
    "assert_encoded_span",
    "crop_filter",
    "encoder_available",
    "frame_duration_ms",
    "frame_rate",
    "linked_libraries",
    "render_clip",
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


def crop_filter(
    source_width: int,
    source_height: int,
    focus_x: int | None = None,
    focus_points: Sequence[tuple[int, int]] = (),
    clip_in_ms: int = 0,
    target_width: int = VERTICAL_WIDTH,
    target_height: int = VERTICAL_HEIGHT,
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

    if focus_points:
        ordered = sorted(focus_points)
        positions = [
            max(0, min(center - crop_w // 2, source_width - crop_w)) for _, center in ordered
        ]
        expression = str(positions[-1])
        for index in range(len(positions) - 2, -1, -1):
            boundary_s = ((ordered[index][0] + ordered[index + 1][0]) / 2 - clip_in_ms) / 1000
            expression = (
                f"if(lt(t\\,{max(0.0, boundary_s):.3f})\\,{positions[index]}\\,{expression})"
            )
        x: int | str = expression
    elif focus_x is None:
        x = (source_width - crop_w) // 2
    else:
        # Clamp rather than raise: a face detector reporting a centre near the frame edge is
        # correct about the face and merely asking for a crop that does not fit. Sliding it
        # into frame keeps the subject; refusing would drop the clip.
        x = max(0, min(focus_x - crop_w // 2, source_width - crop_w))
    y = (source_height - crop_h) // 2

    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={target_width}:{target_height}"


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

    # The final name is a write-once publication target, never ffmpeg's working file. Checking
    # before the expensive probes/encode gives deterministic reruns, while the atomic link at
    # publication time closes the race with another worker that passes this same preflight.
    if os.path.lexists(output):
        raise RenderError(
            f"refusing to overwrite render artifact {output}; choose a new clip/run id"
        )

    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise RenderError("no ffmpeg available — run scripts/fetch-ffmpeg.sh or set HAWEDIT_FFMPEG")

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

    duration_ms = clip.out_ms - clip.in_ms
    # Subtitles are burned into a stream ffmpeg has already cut, so t=0 is the start of the
    # clip. A file carrying source-absolute stamps draws nothing and ships a caption-free MP4;
    # checked here on whatever file arrives, not only where `build_ass` writes one.
    assert_captions_within_clip(ass_path.read_text(encoding="utf-8"), duration_ms)
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
                "-c:v",
                encoder.value,
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-y",
                str(staging),
            ],
            capture_output=True,
            check=False,
        )
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
        # Named for what it is. §3 Stage 6's speaker tracking needs diarization, which does
        # not run (`BLOCKED.md` #4), so no clip this function produces may claim it.
        reframe=Reframe.FACE_TRACKED if focus_points else Reframe.STATIC_CENTRE,
        encoder=encoder,
        captions_burned_in=True,
        ffmpeg_version=version,
    )
