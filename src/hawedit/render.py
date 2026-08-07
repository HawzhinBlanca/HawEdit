"""§3 Stage 6 — render. Reframe, burn in captions, encode.

    Reframing, captions, encode. Caption requirements in §4.3 are not optional. Vertical
    reframing tracks the active speaker from diarization plus face detection.

Three things this module refuses to do, each because the alternative fails silently:

**It will not render a clip that has not cleared the gate.** `Clip.assert_renderable()` runs
first, every time. §2 puts a human QC gate before output *always*, and Kurdish invariant #2
forbids rendering a boundary whose sentence is incomplete. A render function that takes an
`in_ms`/`out_ms` pair and trusts them is how a clip that was rejected reaches a client.

**It will not call a centre crop "reframing".** §3 Stage 6's reframe tracks the active speaker
from diarization plus face detection, and neither is available (`BLOCKED.md` #4). So the crop
here is static, `Reframe.STATIC_CENTRE` says so by name, and `speaker_tracked` is a separate
value that this module cannot yet produce. A centre crop that called itself reframing would
look correct in every artifact and be wrong on every two-shot.

**It will not silently fall back to a software encoder.** §6 puts NVENC on hawapc01. Asking
for NVENC on a machine without it and getting x264 anyway means a throughput measurement that
is quietly about the wrong encoder — the same class of mistake §3 Stage 1 warns about with
published RTF figures. Ask for what is not there and it raises.

The burn-in goes through `captions.subtitle_filter`, which hard-codes `shaping=complex` and an
explicit `fontsdir`. §4.3.1 is emphatic that `auto` must not be relied on and §4.3.4 that
fontconfig must not be trusted to find the font, and the golden render (§4.3.6) proves the
difference is real on this build rather than theoretical.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Final

from hawedit.captions import assert_rtl_stack, find_ffmpeg, subtitle_filter
from hawedit.clip import Clip

__all__ = [
    "VERTICAL_HEIGHT",
    "VERTICAL_WIDTH",
    "Encoder",
    "Reframe",
    "RenderError",
    "RenderResult",
    "crop_filter",
    "encoder_available",
    "linked_libraries",
    "render_clip",
]

# §4.3's caption geometry is built for 1080x1920, and `render_caption_png` defaults to it.
# Keeping one vertical target means the ASS PlayResX/PlayResY match the frame and libass is
# never scaling text — scaled text is the failure the golden render would otherwise measure.
VERTICAL_WIDTH: Final = 1080
VERTICAL_HEIGHT: Final = 1920


class RenderError(RuntimeError):
    """Raised when Stage 6 cannot produce a clip it would be honest to ship."""


class Reframe(Enum):
    """How the vertical crop was chosen. The name travels with the artifact.

    `SPEAKER_TRACKED` is what §3 Stage 6 actually specifies and is not implemented — it needs
    diarization (`BLOCKED.md` #4) and face detection. It exists here so that the day it lands,
    every clip rendered before it is distinguishable from every clip rendered after, without
    anyone having to remember which was which.
    """

    STATIC_CENTRE = "static_centre"
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
    one 64x64 frame to a real file and checks that bytes came out. Cached — the answer cannot
    change within a process, and the probe costs an ffmpeg launch.
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
                "color=c=black:s=64x64:d=0.1",
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

    if focus_x is None:
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
    duration_ms: int
    reframe: Reframe
    encoder: Encoder
    captions_burned_in: bool
    ffmpeg_version: str


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
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = ",".join(
        [crop_filter(source_width, source_height, focus_x), subtitle_filter(ass_path, fonts_dir)]
    )

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
            str(output),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not output.exists():
        raise RenderError(
            f"encode failed ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')[-800:]}"
        )

    return RenderResult(
        clip_id=clip.clip_id,
        path=str(output),
        width=VERTICAL_WIDTH,
        height=VERTICAL_HEIGHT,
        duration_ms=duration_ms,
        # Named for what it is. §3 Stage 6's speaker tracking needs diarization, which does
        # not run (`BLOCKED.md` #4), so no clip this function produces may claim it.
        reframe=Reframe.STATIC_CENTRE,
        encoder=encoder,
        captions_burned_in=True,
        ffmpeg_version=version,
    )
