"""§3 Stage 6 — render, on a real encoder producing a real vertical clip with real captions.

    Reframing, captions, encode. Caption requirements in §4.3 are not optional.

M2.4's deliverable is "one rendered clip", and the only way to know a clip rendered is to
decode it back. So these tests run ffmpeg, produce an MP4, probe its dimensions and duration,
and extract frames to check that Kurdish text is actually on them.

That last check is the one that matters. A burn-in has many silent failure modes — the wrong
filter order, a font directory that resolves to nothing, an ASS file libass parses but finds
nothing to draw in — and every one of them produces a valid, playable, caption-free clip.
Comparing a captioned render against an uncaptioned render of the same frames turns all of
them into a test failure: if the pixels are identical, nothing was drawn.

The refusals get as much attention as the happy path, because Stage 6 is the last gate before
a client sees the output. A clip that has not cleared QC, a boundary that violates Kurdish
invariant #2, an encoder that is not on this machine — each must stop here rather than
producing something plausible.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from hawedit.boundary import BoundaryInputs, fuse_boundary
from hawedit.brand import BrandKit, BrandKitError, ProgressBarConfig
from hawedit.captions import build_ass, ffprobe_for, find_ffmpeg
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Provenance, Qc
from hawedit.ingest import probe_duration_ms
from hawedit.render import (
    DELIVERY_AUDIO_RATE,
    DELIVERY_COLOR_ARGS,
    DELIVERY_LUFS,
    ENCODER_PROBE_SIZE,
    FACE_COMPOSITION_LINE,
    MAX_VERTICAL_ZOOM,
    MIN_SHOT_MS,
    NVENC_MIN_FRAME,
    SPEECH_CHAIN_FILTERS,
    TARGET_FACE_HEIGHT_SHARE,
    VERTICAL_HEIGHT,
    VERTICAL_WIDTH,
    Encoder,
    LoudnessStats,
    Reframe,
    RenderError,
    _publish_render,
    assert_encoded_span,
    audio_filter,
    blurred_fill_filter,
    crop_filter,
    cut_points_ms,
    decide_wide_shot_layout,
    deliverable_video_args,
    eased_push_schedule,
    encoder_available,
    frame_duration_ms,
    frame_rate,
    measure_audio_loudness,
    punch_in_schedule,
    quality_args,
    render_clip,
    shot_spans,
    two_person_split_filter,
    vertical_crop_size,
    vertical_framing,
)
from hawedit.sentences import Sentence
from hawedit.silence import SilencePlan
from hawedit.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
FONTS = ROOT / "assets" / "fonts"

# The fixture is 640x360 — see tests/test_ingest.py for how it is built.
SOURCE_WIDTH, SOURCE_HEIGHT = 640, 360

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

CAPTION_TEXT = "ڕۆژنامەوانی کوردی"


def _sentence() -> Sentence:
    """One caption line whose word timings sit inside the clip's own window."""
    return Sentence(
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=800, conf=0.95),
            Word(w="کوردی", start_ms=800, end_ms=1_600, conf=0.95),
        ),
        complete=True,
    )


def _clip(*, qc: Qc | None = None, complete: bool = True) -> Clip:
    boundary = fuse_boundary(
        BoundaryInputs(anchor_in_ms=500, anchor_out_ms=2_500, sentence_complete=complete)
    )
    return Clip(
        clip_id="m2-4",
        media_id="kurdish-speech-3cuts",
        media_sha256=FIXTURE_SHA256,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb=CAPTION_TEXT,
            norm_ckb=CAPTION_TEXT,
            en_aux=None,
            words=(),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
        ),
        editorial=Editorial(
            hook_score=0.8,
            self_contained=True,
            meaning_fidelity=0.9,
            misleading_edit_risk=0.05,
            cultural_landing=0.7,
            narrative_role="payoff",
            judge="gemini-2.5-pro",
        ),
        output=Output(
            title_ckb=CAPTION_TEXT,
            description_ckb=CAPTION_TEXT,
            crop_target="9:16",
            caption_style="word_highlight",
            durations=(30,),
        ),
        qc=(
            qc
            if qc is not None
            else Qc(
                auto_pass=True,
                flags=(),
                human_reviewed=True,
                reviewed_by="Hawa",
                reviewed_at="2026-09-02T19:00:00Z",
                reviewed_sha256="0" * 64,
            )
        ),
        provenance=Provenance.current(),
    )


def _write_ass(tmp_path: Path) -> Path:
    path = tmp_path / "captions.ass"
    path.write_text(build_ass((_sentence(),)), encoding="utf-8")
    return path


def _probe(path: Path, entries: str) -> str:
    ffprobe = find_ffmpeg()
    assert ffprobe is not None
    return subprocess.run(
        [
            str(ffprobe_for(ffprobe)),
            "-v",
            "error",
            "-show_entries",
            entries,
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _frame(video: Path, at_s: float, out: Path) -> Path:
    binary = find_ffmpeg()
    assert binary is not None
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{at_s:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-y",
            str(out),
        ],
        check=True,
    )
    return out


# --- the crop, as arithmetic --------------------------------------------------------------


def test_the_crop_reaches_the_vertical_target() -> None:
    assert crop_filter(1920, 1080).endswith(f"scale={VERTICAL_WIDTH}:{VERTICAL_HEIGHT}")


def test_the_crop_is_taken_at_source_resolution_before_scaling() -> None:
    """Cropping after a scale throws away detail before deciding what to keep."""
    chain = crop_filter(1920, 1080)
    assert chain.index("crop=") < chain.index("scale="), chain
    assert "crop=606:1080" in chain, chain  # 1080 * 9/16, rounded to even


def test_the_crop_is_centred_when_nothing_is_tracking_a_speaker() -> None:
    assert "crop=606:1080:657:0" in crop_filter(1920, 1080)


def test_a_focus_point_moves_the_crop() -> None:
    """The seam §3 Stage 6's speaker tracking plugs into, tested before it exists."""
    left = crop_filter(1920, 1080, focus_x=400)
    assert "crop=606:1080:97:0" in left, left


def test_a_focus_point_at_the_frame_edge_is_clamped_not_refused() -> None:
    """A face near the edge is a real face. Sliding the crop keeps it; raising drops the clip."""
    assert "crop=606:1080:0:0" in crop_filter(1920, 1080, focus_x=0)
    assert "crop=606:1080:1314:0" in crop_filter(1920, 1080, focus_x=1920)


def test_crop_dimensions_are_even_for_yuv420p() -> None:
    """Odd dimensions are an encoder error, not a rounding difference."""
    for width, height in ((1919, 1079), (641, 361), (1280, 720)):
        crop = crop_filter(width, height).split(",")[0]
        w, h = (int(v) for v in crop.removeprefix("crop=").split(":")[:2])
        assert w % 2 == 0 and h % 2 == 0, f"{width}x{height} -> {crop}"


def test_a_degenerate_source_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        crop_filter(0, 1080)


# --- the refusals -------------------------------------------------------------------------


def test_a_clip_that_has_not_cleared_qc_is_never_encoded(tmp_path: Path) -> None:
    """§2 puts a human QC gate before output, always. Stage 6 is where "always" is tested."""
    clip = _clip(qc=Qc(auto_pass=False, flags=("low_confidence",), human_reviewed=False))
    with pytest.raises(ValueError, match="QC"):
        render_clip(
            clip,
            FIXTURE,
            _write_ass(tmp_path),
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )
    assert not (tmp_path / "out.mp4").exists(), "a refused clip must leave no artifact"


def test_an_automatic_pass_without_human_review_is_never_encoded(tmp_path: Path) -> None:
    clip = _clip(qc=Qc(auto_pass=True, flags=(), human_reviewed=False))
    with pytest.raises(ValueError, match="human QC"):
        render_clip(
            clip,
            FIXTURE,
            _write_ass(tmp_path),
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )
    assert not (tmp_path / "out.mp4").exists()


def test_an_existing_render_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retry or colliding worker must not replace an artifact a client may already use."""
    output = tmp_path / "out.mp4"
    original = b"the first worker's verified artifact"
    output.write_bytes(original)

    def ffmpeg_must_not_run() -> None:
        pytest.fail("an existing publication target should be refused before probing ffmpeg")

    monkeypatch.setattr("hawedit.render.find_ffmpeg", ffmpeg_must_not_run)
    with pytest.raises(RenderError, match="refusing to overwrite"):
        render_clip(
            _clip(),
            FIXTURE,
            _write_ass(tmp_path),
            FONTS,
            output,
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )
    assert output.read_bytes() == original


def test_atomic_publication_preserves_the_worker_that_won_the_name(tmp_path: Path) -> None:
    """The final race is settled by the filesystem, not by a check-then-overwrite sequence."""
    staging = tmp_path / ".clip.staging.mp4"
    output = tmp_path / "clip.mp4"
    staging.write_bytes(b"second worker")
    output.write_bytes(b"first worker")

    with pytest.raises(RenderError, match="another job published"):
        _publish_render(staging, output)

    assert output.read_bytes() == b"first worker"
    assert staging.read_bytes() == b"second worker"


@needs_ffmpeg
def test_an_interrupted_encode_leaves_no_partial_or_final_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffmpeg may create bytes before failing; those bytes must never occupy the final name."""
    real_run = subprocess.run
    output = tmp_path / "interrupted.mp4"

    def interrupt_the_real_encode(args: object, **kwargs: object) -> object:
        command = list(args) if isinstance(args, list | tuple) else []
        destination = Path(str(command[-1])) if command else Path()
        if destination.parent == tmp_path and destination.name.startswith(".interrupted."):
            destination.write_bytes(b"plausible but incomplete mp4 bytes")
            return subprocess.CompletedProcess(
                command, returncode=1, stdout=b"", stderr=b"simulated interruption"
            )
        return real_run(args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr("hawedit.render.subprocess.run", interrupt_the_real_encode)
    with pytest.raises(RenderError, match="simulated interruption"):
        render_clip(
            _clip(),
            FIXTURE,
            _write_ass(tmp_path),
            FONTS,
            output,
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )

    assert not output.exists()
    assert not tuple(tmp_path.glob(".interrupted.*.mp4")), "private staging file leaked"


def test_an_incomplete_sentence_cannot_even_reach_a_clip() -> None:
    """Kurdish invariant #2, at the earliest point it can be enforced.

    `fuse_boundary` refuses outright, so there is no path from a candidate whose sentence did
    not close to a `Clip` at all — the render gate never sees one because one cannot be built.
    """
    from hawedit.boundary import IncompleteSentence

    with pytest.raises(IncompleteSentence):
        _clip(complete=False)


def test_a_hand_built_incomplete_boundary_is_still_refused_at_the_render(tmp_path: Path) -> None:
    """The second line of defence, which is the one that matters for deserialized input.

    `Boundary` is deliberately not self-validating (see its docstring): a boundary arriving as
    JSON from another stage must be *checkable on arrival*, which a type that cannot represent
    a violation would make impossible. So the invariant is asserted again here, and this test
    constructs the violation directly rather than through `fuse_boundary`.
    """
    from dataclasses import replace

    from hawedit.boundary import BoundaryInvariantViolated

    clip = _clip()
    smuggled = replace(clip, boundary=replace(clip.boundary, sentence_complete=False))
    with pytest.raises(BoundaryInvariantViolated):
        render_clip(
            smuggled,
            FIXTURE,
            _write_ass(tmp_path),
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )
    assert not (tmp_path / "out.mp4").exists(), "a refused clip must leave no artifact"


def test_the_encoder_probe_is_not_smaller_than_nvenc_will_accept() -> None:
    """A probe below NVENC's minimum frame calls a working encoder unavailable.

    This is the guard on a real defect. `encoder_available` probed at 64x64, and NVENC refuses
    anything under roughly `NVENC_MIN_FRAME` with "Frame Dimension less than the minimum
    supported value" — so on hawapc01, the one machine §6 says to use NVENC on, the function
    written *because* a capability listing cannot be trusted returned a confident wrong answer,
    and `render_clip` would have refused NVENC exactly where it is required. Needs no ffmpeg:
    it is arithmetic about the probe's own geometry, so it holds on a runner with no GPU too.
    """
    assert ENCODER_PROBE_SIZE[0] >= NVENC_MIN_FRAME[0]
    assert ENCODER_PROBE_SIZE[1] >= NVENC_MIN_FRAME[1]


@needs_ffmpeg
def test_encoder_availability_is_decided_by_a_real_encode_not_by_the_listing() -> None:
    """§4.3.2's lesson applied to encoders, in whichever direction this machine sits.

    `ffmpeg -encoders` lists what was compiled in. A container with no NVIDIA driver lists
    `h264_nvenc` and cannot encode one frame with it; hawapc01 lists it and can. Neither
    answer is safe to hardcode, and this test used to hardcode the pessimistic one — it
    asserted NVENC was *unavailable*, which is wrong on the box §6 names, so it was written to
    go red the moment the project reached its own hardware.

    The property, both ways: what `encoder_available` reports equals whether a real encode at
    Stage 6's output size writes bytes. The encode below is spelled out separately on purpose
    — sharing the helper would make this test agree with the bug it exists to catch, and the
    bug it did catch was a probe at the wrong size.
    """
    binary = find_ffmpeg()
    assert binary is not None
    listing = subprocess.run(
        [str(binary), "-hide_banner", "-loglevel", "error", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    for encoder in (Encoder.X264, Encoder.NVENC):
        listed = any(line.split()[1:2] == [encoder.value] for line in listing.splitlines())
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "probe.mp4"
            subprocess.run(
                [
                    str(binary),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black:s={VERTICAL_WIDTH}x{VERTICAL_HEIGHT}:d=0.1",
                    "-frames:v",
                    "1",
                    "-c:v",
                    encoder.value,
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    str(out),
                ],
                capture_output=True,
                check=False,
            )
            really_encodes = out.exists() and out.stat().st_size > 0
        assert encoder_available(encoder, binary) == really_encodes, (
            f"{encoder.value} is listed={listed} and really encodes={really_encodes}, but "
            f"encoder_available says {encoder_available(encoder, binary)}. Availability must "
            f"come from encoding, not from the listing — in both directions."
        )


@needs_ffmpeg
def test_an_unavailable_encoder_raises_instead_of_falling_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§6 puts NVENC on hawapc01. Getting x264 instead would measure the wrong encoder.

    The refusal is what is under test, not the graphics card. Deciding by what this machine
    happens to have made the test run only on hardware that could not do the thing — and on
    hawapc01 it stopped running altogether, which is a skip on the exact box the rule is for.
    So availability is answered directly and the refusal is exercised everywhere.
    """
    monkeypatch.setattr("hawedit.render.encoder_available", lambda *_: False)
    with pytest.raises(RenderError, match="nvenc"):
        render_clip(
            _clip(),
            FIXTURE,
            _write_ass(tmp_path),
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
            encoder=Encoder.NVENC,
        )


@needs_ffmpeg
def test_the_encoder_this_machine_does_have_is_reported_available() -> None:
    """The positive control. Without it, an always-False probe would pass every test above."""
    binary = find_ffmpeg()
    assert binary is not None
    assert encoder_available(Encoder.X264, binary)


@needs_ffmpeg
def test_a_missing_subtitle_file_is_refused(tmp_path: Path) -> None:
    """§4.3: captions are not optional, so rendering without them is not a degraded mode."""
    with pytest.raises(RenderError, match="not optional"):
        render_clip(
            _clip(),
            FIXTURE,
            tmp_path / "absent.ass",
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )


def test_no_ffmpeg_names_the_fix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("hawedit.render.find_ffmpeg", lambda: None)
    (tmp_path / "captions.ass").write_text("", encoding="utf-8")
    with pytest.raises(RenderError, match="hawedit-ffmpeg-setup"):
        render_clip(
            _clip(),
            FIXTURE,
            tmp_path / "captions.ass",
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )


# --- M2.4: one rendered clip, decoded back -------------------------------------------------


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One real clip. Rendered once and probed by several tests — encoding is not cheap."""
    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")
    work = tmp_path_factory.mktemp("m2-4")
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    result = render_clip(
        _clip(), FIXTURE, ass, FONTS, work / "clip.mp4", SOURCE_WIDTH, SOURCE_HEIGHT
    )
    assert result.captions_burned_in
    return Path(result.path)


@needs_ffmpeg
def test_the_rendered_clip_is_vertical(rendered: Path) -> None:
    dimensions = _probe(rendered, "stream=width,height").split()
    assert dimensions == [str(VERTICAL_WIDTH), str(VERTICAL_HEIGHT)], dimensions


@needs_ffmpeg
def test_the_rendered_clip_spans_the_fused_boundary(rendered: Path) -> None:
    """The clip is cut to `final_in`..`final_out`, not to the anchors it was grown from."""
    clip = _clip()
    expected_s = (clip.out_ms - clip.in_ms) / 1000
    assert float(_probe(rendered, "format=duration")) == pytest.approx(expected_s, abs=0.15)


@needs_ffmpeg
def test_the_render_result_does_not_claim_to_have_tracked_a_speaker(tmp_path: Path) -> None:
    """§3 Stage 6 reframes from diarization plus face detection. Neither runs (`BLOCKED` #4).

    A centre crop labelled "reframed" looks right in every artifact and is wrong on every
    two-shot, and nothing downstream could tell the difference.
    """
    ass = _write_ass(tmp_path)
    result = render_clip(
        _clip(), FIXTURE, ass, FONTS, tmp_path / "clip.mp4", SOURCE_WIDTH, SOURCE_HEIGHT
    )
    assert result.reframe is Reframe.STATIC_CENTRE
    assert result.reframe.value == "static_centre", (
        "the value that travels with the artifact must name the static crop — a consumer "
        "reading this field is asking whether the speaker was tracked"
    )


@needs_ffmpeg
def test_kurdish_captions_are_actually_burned_into_the_pixels(
    rendered: Path, tmp_path: Path
) -> None:
    """The check every other assertion here depends on.

    A wrong filter order, an unresolvable font directory, an ASS file with nothing drawable —
    each produces a valid, playable, caption-free clip that passes a dimensions-and-duration
    test. The only proof is the same frames rendered without the subtitle filter: if the
    pixels match, libass drew nothing.
    """
    binary = find_ffmpeg()
    assert binary is not None
    clip = _clip()
    bare = tmp_path / "bare.mp4"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{clip.in_ms / 1000:.3f}",
            "-t",
            f"{(clip.out_ms - clip.in_ms) / 1000:.3f}",
            "-i",
            str(FIXTURE),
            "-vf",
            crop_filter(SOURCE_WIDTH, SOURCE_HEIGHT),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-y",
            str(bare),
        ],
        check=True,
    )
    with_captions = _frame(rendered, 0.5, tmp_path / "with.rgb").read_bytes()
    without = _frame(bare, 0.5, tmp_path / "without.rgb").read_bytes()

    assert len(with_captions) == len(without) == VERTICAL_WIDTH * VERTICAL_HEIGHT * 3
    differing = sum(1 for a, b in zip(with_captions, without, strict=True) if a != b)
    assert differing > 1_000, (
        f"only {differing} bytes differ between the captioned and uncaptioned renders — "
        f"libass drew nothing, and the clip would ship without captions (§4.3)"
    )


@needs_ffmpeg
def test_the_burned_in_captions_are_shaped(rendered: Path, tmp_path: Path) -> None:
    """§4.3.1/§4.3.2, at the burn-in rather than at the golden frame.

    `shaping=simple` renders Arabic-script letters in isolated forms — visibly broken text
    that still looks like text to anything counting non-black pixels. Rendering the same
    captions the wrong way and requiring the pixels to differ is what makes the burn-in a
    check on shaping and not merely on ink.
    """
    from hawedit.captions import _escape_filter_path

    binary = find_ffmpeg()
    assert binary is not None
    clip = _clip()
    ass = _write_ass(tmp_path)
    broken = tmp_path / "simple.mp4"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{clip.in_ms / 1000:.3f}",
            "-t",
            f"{(clip.out_ms - clip.in_ms) / 1000:.3f}",
            "-i",
            str(FIXTURE),
            "-vf",
            f"{crop_filter(SOURCE_WIDTH, SOURCE_HEIGHT)},"
            f"ass={_escape_filter_path(ass)}:shaping=simple:fontsdir={_escape_filter_path(FONTS)}",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-y",
            str(broken),
        ],
        check=True,
    )
    complex_frame = _frame(rendered, 0.5, tmp_path / "complex.rgb").read_bytes()
    simple_frame = _frame(broken, 0.5, tmp_path / "simple.rgb").read_bytes()
    differing = sum(1 for a, b in zip(complex_frame, simple_frame, strict=True) if a != b)
    assert differing > 500, (
        f"complex and simple shaping produced near-identical pixels ({differing} bytes differ). "
        f"Either the shaping option is not reaching libass, or libass has no HarfBuzz — §4.3.2 "
        f"says a build can accept the option and still lack the library."
    )


@needs_ffmpeg
def test_the_evidence_clip_is_committed() -> None:
    """M2.4's deliverable is an artifact, so the artifact is in the repository."""
    clip = ROOT / "evidence" / "m2-4-rendered-clip.mp4"
    assert clip.exists(), f"M2.4's rendered clip is not committed at {clip}"
    assert clip.stat().st_size > 1_000


# =========================================================================================
# §8.3 — "assert final_in <= anchor_in and final_out >= anchor_out on every SHIPPED clip"
#
# The invariant was asserted on the plan: `assert_renderable()` runs, the numbers are checked,
# ffmpeg is invoked, and `RenderResult.duration_ms` reports what was *asked for*. The file was
# never measured. Requesting 0..8000 ms of a 4162 ms fixture: ffmpeg exits 0, writes 4180 ms,
# and the result claims 8000. The shipped clip ends 3.8 s before its own `final_out` — which is
# mid-sentence, the one thing Kurdish invariant #2 exists to prevent — with every check green.
# =========================================================================================


@needs_ffmpeg
def test_a_clip_running_past_the_end_of_the_media_is_refused(tmp_path: Path) -> None:
    """Measured: the encode succeeds and silently truncates, so the numbers must be checked
    against the source before an encoder is ever started."""
    clip = _clip()
    over = replace(clip, out_ms=8_000, boundary=replace(clip.boundary, final_out_ms=8_000))
    output = tmp_path / "over.mp4"
    with pytest.raises(RenderError, match="4162"):
        render_clip(
            clip=over,
            source=FIXTURE,
            ass_path=_write_ass(tmp_path),
            output=output,
            source_width=SOURCE_WIDTH,
            source_height=SOURCE_HEIGHT,
            fonts_dir=FONTS,
        )
    assert not output.exists(), "a refused clip still wrote a file"


@needs_ffmpeg
def test_the_burn_refuses_a_fonts_directory_without_kurdish_coverage(tmp_path: Path) -> None:
    fonts = tmp_path / "empty-fonts"
    fonts.mkdir()
    output = tmp_path / "missing-font.mp4"
    with pytest.raises(RenderError, match="no font file"):
        render_clip(
            clip=_clip(),
            source=FIXTURE,
            ass_path=_write_ass(tmp_path),
            fonts_dir=fonts,
            output=output,
            source_width=SOURCE_WIDTH,
            source_height=SOURCE_HEIGHT,
        )
    assert not output.exists()


@needs_ffmpeg
def test_the_result_reports_the_duration_of_the_file_not_of_the_request(tmp_path: Path) -> None:
    """A number carries its provenance: `measured_duration_ms` comes from the artifact."""
    clip = _clip()
    output = tmp_path / "ok.mp4"
    result = render_clip(
        clip=clip,
        source=FIXTURE,
        ass_path=_write_ass(tmp_path),
        output=output,
        source_width=SOURCE_WIDTH,
        source_height=SOURCE_HEIGHT,
        fonts_dir=FONTS,
    )
    assert result.requested_duration_ms == clip.out_ms - clip.in_ms
    assert result.measured_duration_ms == probe_duration_ms(output, find_ffmpeg())
    assert abs(result.measured_duration_ms - result.requested_duration_ms) <= 40


def test_a_file_shorter_than_the_request_is_refused() -> None:
    """The net under the pre-flight check, as a unit.

    Truncation by a short source is now impossible, but it is not the only way an encode can
    come up short, and this is the check that would catch the others.
    """
    with pytest.raises(RenderError, match="shorter"):
        assert_encoded_span(measured_ms=4_180, requested_ms=8_000, frame_ms=40)


def test_a_file_one_frame_long_is_container_rounding_not_a_failure() -> None:
    """Measured on the real fixture: correct cuts came back exact except one, which was +40 ms
    — exactly one frame at 25 fps. Rejecting that would fail honest renders."""
    assert_encoded_span(measured_ms=2_040, requested_ms=2_000, frame_ms=40)


def test_a_file_more_than_one_frame_long_is_refused() -> None:
    with pytest.raises(RenderError, match="longer"):
        assert_encoded_span(measured_ms=100_000, requested_ms=2_000, frame_ms=40)


def test_a_file_one_frame_short_is_tolerated_and_two_frames_is_not() -> None:
    assert_encoded_span(measured_ms=1_960, requested_ms=2_000, frame_ms=40)
    with pytest.raises(RenderError, match="shorter"):
        assert_encoded_span(measured_ms=1_919, requested_ms=2_000, frame_ms=40)


def test_frame_duration_comes_from_the_file_rather_than_an_assumed_rate() -> None:
    """25 fps is the fixture's rate, not a constant. A 30 fps source has a different frame."""
    assert frame_duration_ms(FIXTURE, find_ffmpeg()) == 40


def test_dynamic_crop_interpolates_between_focus_points_instead_of_stepping() -> None:
    """A step between samples is the shimmer; a ramp between them is a pan.

    This asserted the stepped form — a snap at the midpoint between neighbouring samples —
    until a real 2 fps face track showed what that means on screen: the crop jumping twice a
    second for the whole clip. The behaviour changed deliberately, so the assertion does too.
    """
    chain = crop_filter(
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        focus_points=((100, 50), (1_100, 600)),
        clip_in_ms=100,
    )
    # Clamped left edge at the first point, right edge at the second, ramped between them
    # across the whole 1.0 s the two samples span.
    assert "if(lt(t\\,1.000)\\,(0+(438)*(t-0.000)/1.000)\\,438)" in chain
    # The old midpoint snap must be gone, not merely outnumbered.
    assert "\\,0.500)\\," not in chain


def test_dynamic_crop_holds_still_between_equal_keyframes() -> None:
    """`stabilize` encodes a hold as two equal neighbours; the filter must not drift over it."""
    chain = crop_filter(
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        focus_points=((0, 200), (4_000, 200), (4_400, 500)),
    )
    # 640x360 crops to 202 wide, so a face centred at 200 puts the crop's left edge at 99.
    # A flat span is emitted as the bare position, never as a ramp with a zero numerator.
    assert "if(lt(t\\,4.000)\\,99\\," in chain
    assert "(99+(0)*" not in chain


def test_dynamic_crop_holds_the_opening_position_before_the_first_keyframe() -> None:
    """A clip whose track starts late must not extrapolate backwards off the front."""
    chain = crop_filter(
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        focus_points=((2_000, 100), (3_000, 500)),
    )
    assert chain.startswith("crop=202:360:if(lt(t\\,2.000)\\,0\\,if(lt(t\\,3.000)\\,")


@needs_ffmpeg
def test_real_render_accepts_a_time_varying_face_track(tmp_path: Path) -> None:
    clip = _clip()
    output = tmp_path / "tracked.mp4"
    result = render_clip(
        clip=clip,
        source=FIXTURE,
        ass_path=_write_ass(tmp_path),
        output=output,
        source_width=SOURCE_WIDTH,
        source_height=SOURCE_HEIGHT,
        fonts_dir=FONTS,
        focus_points=((clip.in_ms, 50), (clip.out_ms - 1, 600)),
    )
    assert result.reframe is Reframe.FACE_TRACKED
    assert output.exists() and output.stat().st_size > 1_000


@needs_ffmpeg
def test_real_render_preserves_validated_speaker_tracking_provenance(tmp_path: Path) -> None:
    clip = _clip()
    output = tmp_path / "speaker-tracked.mp4"
    result = render_clip(
        clip=clip,
        source=FIXTURE,
        ass_path=_write_ass(tmp_path),
        output=output,
        source_width=SOURCE_WIDTH,
        source_height=SOURCE_HEIGHT,
        fonts_dir=FONTS,
        focus_points=((clip.in_ms, 50), (clip.out_ms - 1, 600)),
        reframe=Reframe.SPEAKER_TRACKED,
    )
    assert result.reframe is Reframe.SPEAKER_TRACKED
    assert output.exists() and output.stat().st_size > 1_000


def test_render_refuses_a_reframe_label_that_contradicts_its_points(tmp_path: Path) -> None:
    def attempt(
        output: Path,
        reframe: Reframe,
        focus_points: tuple[tuple[int, int], ...] = (),
    ) -> None:
        render_clip(
            clip=_clip(),
            source=FIXTURE,
            ass_path=tmp_path / "unused.ass",
            fonts_dir=FONTS,
            output=output,
            source_width=SOURCE_WIDTH,
            source_height=SOURCE_HEIGHT,
            focus_points=focus_points,
            reframe=reframe,
        )

    with pytest.raises(ValueError, match="dynamic reframe mode needs focus points"):
        attempt(
            tmp_path / "speaker-without-points.mp4",
            Reframe.SPEAKER_TRACKED,
        )
    with pytest.raises(ValueError, match="dynamic reframe mode needs focus points"):
        attempt(
            tmp_path / "face-without-points.mp4",
            Reframe.FACE_TRACKED,
        )
    with pytest.raises(ValueError, match="static reframe mode cannot carry focus points"):
        attempt(
            tmp_path / "static-with-points.mp4",
            Reframe.STATIC_CENTRE,
            ((500, 100),),
        )


def test_the_burn_refuses_an_ass_whose_stamps_fall_outside_the_clip(tmp_path: Path) -> None:
    """`assert_captions_within_clip`'s LOGIC was tested; its wiring into `render_clip` was not.

    Measured 2026-08-09: feeding the guard a synthetic always-valid ASS instead of the file on
    disk — the import still used, so ruff stays clean — left the full suite at 0 failures.
    Deleting the call outright is "caught" only because ruff reports an unused import and the
    nested-gate tests then fail on a red lint, which is a linter noticing, not a test. Under the
    import-preserving mutation an ASS carrying source-absolute stamps ships a valid, playable,
    caption-free MP4 with `captions_burned_in=True` — Kurdish invariant #4. D-097.

    This asserts the wiring: a file the guard should reject must be rejected *through the render
    path*, on whatever file arrives.
    """
    from hawedit.captions import CaptionsOutsideClip

    clip = _clip()
    duration_ms = clip.out_ms - clip.in_ms
    # Source-absolute stamps: a minute into the episode, entirely outside the cut stream where
    # t=0 is the start of the clip. libass would draw nothing.
    absolute = tmp_path / "source-absolute.ass"
    absolute.write_text(
        "[Script Info]\nWrapStyle: 2\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:01:00.00,0:01:01.60,Default,,0,0,0,,ڕۆژنامەوانی\n",
        encoding="utf-8",
    )
    assert duration_ms < 60_000, "the fixture clip must end before the planted stamp begins"

    with pytest.raises(CaptionsOutsideClip):
        render_clip(
            clip,
            FIXTURE,
            absolute,
            FONTS,
            tmp_path / "out.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
        )
    assert not (tmp_path / "out.mp4").exists(), "refused, but an MP4 was written anyway"

    # The control: the ordinary ASS this suite builds must still render, or this test would pass
    # for a `render_clip` that refused every caption file it was handed.
    rendered = render_clip(
        clip,
        FIXTURE,
        _write_ass(tmp_path),
        FONTS,
        tmp_path / "ok.mp4",
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
    )
    assert Path(rendered.path).exists()
    assert rendered.captions_burned_in


# --- D-147: the guard was tested, its wiring was not -----------------------------------------


def test_render_refuses_when_the_written_file_is_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`assert_encoded_span` is unit-tested; that it is *called with the measurement* was not.

    Found by adversarial pass #8: replacing the call site with
    `assert_encoded_span(duration_ms, duration_ms, …)` — the guard comparing the request against
    itself — left the whole suite green. The guard is only ever reached through `render_clip`, and
    truncation by a short source is prevented upstream, so no test drove it.

    The probe is replaced rather than the encode, because what is under test here is the wiring:
    the guard's own arithmetic is covered by the unit tests above with real measured numbers.
    D-147.
    """
    clip = _clip()
    requested = clip.out_ms - clip.in_ms
    real = probe_duration_ms

    def short_for_the_output(path: Path, ffmpeg: Path | None = None) -> int:
        # The pre-flight check probes the SOURCE with this same helper, and it is wired and
        # tested — a blanket patch trips that refusal instead of the one under test.
        return real(path, ffmpeg) if path == FIXTURE else requested - 200

    monkeypatch.setattr("hawedit.render.probe_duration_ms", short_for_the_output)

    with pytest.raises(RenderError, match="shorter than"):
        render_clip(
            clip=clip,
            source=FIXTURE,
            ass_path=_write_ass(tmp_path),
            output=tmp_path / "short.mp4",
            source_width=SOURCE_WIDTH,
            source_height=SOURCE_HEIGHT,
            fonts_dir=FONTS,
        )


def test_render_accepts_a_file_that_measures_what_was_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. A wiring that refused every render would satisfy the test above."""
    clip = _clip()
    requested = clip.out_ms - clip.in_ms
    real = probe_duration_ms

    def exact_for_the_output(path: Path, ffmpeg: Path | None = None) -> int:
        return real(path, ffmpeg) if path == FIXTURE else requested

    monkeypatch.setattr("hawedit.render.probe_duration_ms", exact_for_the_output)

    result = render_clip(
        clip=clip,
        source=FIXTURE,
        ass_path=_write_ass(tmp_path),
        output=tmp_path / "exact.mp4",
        source_width=SOURCE_WIDTH,
        source_height=SOURCE_HEIGHT,
        fonts_dir=FONTS,
    )
    assert result.measured_duration_ms == requested


@needs_ffmpeg
def test_one_frame_is_read_from_the_source_not_assumed_to_be_forty_ms(tmp_path: Path) -> None:
    """`frame_duration_ms`'s docstring: "Not a constant … a 30 fps source is 33 ms."

    Every fixture here is 25 fps, where the constant 40 is *correct*, so replacing the function
    body with `return 40` left the suite green — the same fixture-satisfies-the-rule blindness as
    D-086, D-088 and D-101. A 30 fps source is generated here so the two answers differ.
    """
    thirty = tmp_path / "thirty.mp4"
    subprocess.run(
        [
            str(find_ffmpeg()),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:r=30:d=1",
            "-c:v",
            "libx264",
            "-y",
            str(thirty),
        ],
        check=True,
        capture_output=True,
    )

    assert frame_rate(thirty, find_ffmpeg()) == pytest.approx(30.0)
    assert frame_duration_ms(thirty, find_ffmpeg()) == 33, (
        "one frame of a 30 fps source is 33 ms; 40 would make the shipped-clip tolerance too "
        "loose by a fifth of a frame, and too loose is the direction that ships a truncated clip"
    )
    assert frame_duration_ms(FIXTURE, find_ffmpeg()) == 40, "the 25 fps fixture is still 40 ms"


# --- what adversarial pass #12 found unprotected (D-125) --------------------------------

# M3.5's defect was `build_ass` writing source-absolute timestamps into a stream ffmpeg had
# already cut. Every mechanism of the fix is held (8/8), but measured: removing the
# `- clip_in_ms` shift leaves **every test in this file and in test_pipeline.py green**. The
# proof lives in `test_caption_timing.py`, on a hand-built ffmpeg invocation — and the ASS this
# file hands `render_clip` is already clip-relative (`_sentence()` is 0..1600 in clip time),
# which is legitimate for a renderer test and means the *composition* never reaches the product's
# own renderer. That is the shape M3.5 came from: proven where the offset is chosen, exercised
# where the offset is too small to matter.
#
# 2000 ms is not an arbitrary offset: `_sentence()` is 1600 ms long, so an unshifted caption
# lands entirely outside a clip that starts at 2000 and `assert_captions_within_clip` can refuse
# it. At the 500 ms this file's clip uses, the same mistake still overlaps and draws.
SOURCE_TIME_SENTENCE_IN_MS = 2_000
SOURCE_TIME_SENTENCE_OUT_MS = 3_600


def _mid_media_clip() -> Clip:
    """A clip taken from the middle of the fixture, spanning one spoken sentence."""
    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=SOURCE_TIME_SENTENCE_IN_MS,
            anchor_out_ms=SOURCE_TIME_SENTENCE_OUT_MS,
            sentence_complete=True,
        )
    )
    return replace(
        _clip(), in_ms=boundary.final_in_ms, out_ms=boundary.final_out_ms, boundary=boundary
    )


def _source_time_sentence() -> Sentence:
    """The same line, timed on the *source* clock — which is what §4.2 produces."""
    return Sentence(
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=SOURCE_TIME_SENTENCE_IN_MS, end_ms=2_800, conf=0.95),
            Word(w="کوردی", start_ms=2_800, end_ms=SOURCE_TIME_SENTENCE_OUT_MS, conf=0.95),
        ),
        complete=True,
    )


@needs_ffmpeg
def test_the_composed_path_burns_captions_into_a_clip_from_mid_media(tmp_path: Path) -> None:
    """`build_ass(clip_in_ms=clip.in_ms)` then the real `render_clip`, decoded.

    The whole composition, through the function the product calls, at an offset where getting it
    wrong is visible. Asserted on pixels against an uncaptioned render of the same span, because
    a caption-free clip is valid, playable and passes every dimension-and-duration check.
    """
    binary = find_ffmpeg()
    assert binary is not None
    clip = _mid_media_clip()
    duration_ms = clip.out_ms - clip.in_ms

    ass = tmp_path / "captions.ass"
    ass.write_text(
        build_ass((_source_time_sentence(),), clip_in_ms=clip.in_ms, clip_duration_ms=duration_ms),
        encoding="utf-8",
    )
    captioned = render_clip(
        clip, FIXTURE, ass, FONTS, tmp_path / "captioned.mp4", SOURCE_WIDTH, SOURCE_HEIGHT
    )
    assert captioned.captions_burned_in

    bare = tmp_path / "bare.mp4"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{clip.in_ms / 1000:.3f}",
            "-t",
            f"{duration_ms / 1000:.3f}",
            "-i",
            str(FIXTURE),
            "-vf",
            crop_filter(SOURCE_WIDTH, SOURCE_HEIGHT),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-y",
            str(bare),
        ],
        check=True,
    )
    with_captions = _frame(Path(captioned.path), 0.5, tmp_path / "with.rgb").read_bytes()
    without = _frame(bare, 0.5, tmp_path / "without.rgb").read_bytes()
    assert len(with_captions) == len(without) == VERTICAL_WIDTH * VERTICAL_HEIGHT * 3
    differing = sum(1 for a, b in zip(with_captions, without, strict=True) if a != b)
    assert differing > 1_000, (
        f"only {differing} bytes differ between the captioned and uncaptioned renders of a clip "
        f"cut from {clip.in_ms} ms — libass drew nothing and the clip would ship bare (§4.3)"
    )


@needs_ffmpeg
def test_an_unshifted_caption_file_is_refused_at_the_burn(tmp_path: Path) -> None:
    """The control, and the defect itself through the product's renderer.

    `build_ass` without the clip's offset writes the sentence at 2000..3600 while the clip's own
    window is 0..1600, so nothing is drawable and `render_clip` must refuse rather than encode a
    caption-free MP4. Without this the test above passes for a renderer that silently ships one.
    """
    clip = _mid_media_clip()
    ass = tmp_path / "unshifted.ass"
    ass.write_text(build_ass((_source_time_sentence(),)), encoding="utf-8")
    from hawedit.captions import CaptionsOutsideClip

    with pytest.raises(CaptionsOutsideClip):
        render_clip(clip, FIXTURE, ass, FONTS, tmp_path / "never.mp4", SOURCE_WIDTH, SOURCE_HEIGHT)


# =========================================================================================
# The three refusals a guard-revert sweep over this module found UNHELD: every `raise` here
# deleted one at a time against a green baseline, whole suite each time. `delivery.py` came
# back 12/12 held; these are render.py's, and the first one is the last check standing between
# a failed encode and a client. D-194.
# =========================================================================================


@needs_ffmpeg
def test_a_failed_encode_is_refused_with_ffmpegs_own_words(tmp_path: Path) -> None:
    """Deleting this left the suite green, and the fall-through is not harmless: the next line
    probes `output` for its duration, so a failed encode became whatever `probe_duration_ms`
    says about a file that may not be there.

    The failure is real rather than mocked: an unknown output suffix reaches ffmpeg's muxer
    selection and is refused there. An already-existing path is no longer suitable for this test,
    because the hardened renderer correctly rejects overwrite before launching ffmpeg.
    """
    output = tmp_path / "clip.hawedit-unknown-container"

    with pytest.raises(RenderError, match="encode failed") as refused:
        render_clip(
            clip=_clip(),
            source=FIXTURE,
            ass_path=_write_ass(tmp_path),
            output=output,
            source_width=SOURCE_WIDTH,
            source_height=SOURCE_HEIGHT,
            fonts_dir=FONTS,
        )

    # The control: the refusal must carry ffmpeg's own diagnosis. A generic "encode failed"
    # would satisfy the match above while telling an operator nothing, and the reason this
    # message exists at all is that ffmpeg is the only thing that knows why it stopped.
    assert "output format" in str(refused.value), refused.value


def test_render_clip_raises_on_subprocess_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subprocess timeout raises RenderError naming the deadline, and never hangs indefinitely."""
    clip = _clip()
    ass = _write_ass(tmp_path)
    output = tmp_path / "timeout.mp4"
    real_run = subprocess.run

    def _timed_out(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        if "-ss" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60.0)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _timed_out)

    with pytest.raises(RenderError, match="encode timed out after"):
        render_clip(
            clip=clip,
            source=FIXTURE,
            ass_path=ass,
            output=output,
            source_width=SOURCE_WIDTH,
            source_height=SOURCE_HEIGHT,
            fonts_dir=FONTS,
        )


def test_a_source_too_small_to_crop_is_refused(tmp_path: Path) -> None:
    """A crop of zero width is not a narrow clip, it is an ffmpeg error at encode time or a
    frame of nothing. Measured: 1x1000, 1000x1 and 2x2 all reduce to a zero dimension once the
    even-number rounding yuv420p needs is applied."""
    for width, height in ((1, 1000), (1000, 1), (2, 2)):
        with pytest.raises(ValueError, match="cannot be cropped"):
            crop_filter(width, height)

    # The control: the real fixture's own dimensions must still produce a filter, so this
    # measures the degenerate case and not a `crop_filter` that refuses everything. It earned
    # its place immediately — the first version passed the target size positionally, where the
    # signature takes `focus_x` and `focus_points`, and every refusal above still fired.
    assert crop_filter(SOURCE_WIDTH, SOURCE_HEIGHT).startswith("crop=")


def test_a_frame_rate_of_zero_is_refused_rather_than_divided_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`0/0` is what ffprobe reports for a stream whose rate it cannot determine, and the guard
    that turns it into a named refusal was held by nothing. Without it the ratio is evaluated
    and the caller gets `ZeroDivisionError` from inside a rate probe — `frame_duration_ms`
    divides by the result, so the traceback would point one function further away still.

    ffprobe's answer is supplied rather than hunted for, the way the symlink tests supply the
    kernel's: what is scarce is a file that provokes it, not the refusal under test.
    """
    monkeypatch.setattr("hawedit.render.probe_stream", lambda *_a, **_k: "0/0")
    with pytest.raises(RenderError, match="could not read a frame rate"):
        frame_rate(FIXTURE)

    # The control: a rate ffprobe *can* report is returned as the exact ratio, not rounded —
    # 30000/1001 is 29.97002997…, and `delivery.ms_to_timecode` refuses the non-integer rate on
    # purpose, which it can only do if it is told the truth.
    monkeypatch.setattr("hawedit.render.probe_stream", lambda *_a, **_k: "30000/1001")
    assert frame_rate(FIXTURE) == 30000 / 1001


def test_nvenc_gets_a_quality_flag_it_actually_honours() -> None:
    """`-crf` is accepted and ignored by NVENC, which made it a no-op on the §6 host.

    Measured on hawapc01 with ffmpeg 8.1.1: `-crf 18` and `-crf 30` into `h264_nvenc` both
    wrote 976,781 bytes for the same 3 s 1080x1920 source. `-rc vbr -cq N -b:v 0` wrote
    5,412,913 and 1,763,082 for the same pair.
    """
    assert quality_args(Encoder.NVENC, 20) == ["-rc", "vbr", "-cq", "20", "-b:v", "0"]
    assert "-crf" not in quality_args(Encoder.NVENC, 20)
    # Without -b:v 0 the constant-quality result is capped by a default bitrate ceiling and
    # the cq value stops mattering again at the top of the range.
    assert "-b:v" in quality_args(Encoder.NVENC, 20)


def test_x264_keeps_crf_which_is_the_flag_it_honours() -> None:
    assert quality_args(Encoder.X264, 20) == ["-crf", "20"]


def test_delivery_color_args_target_rec709() -> None:
    """Standard Rec.709 tags ensure color consistency across modern mobile/web targets."""
    assert DELIVERY_COLOR_ARGS == (
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-bsf:v",
        "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
    )


def test_deliverable_video_args_nvenc_matches_pro_grade_profile() -> None:
    """Task T2.10: NVENC profile with high preset, B-frames, AQ, CQ and GOP."""
    args = deliverable_video_args(Encoder.NVENC, crf=20, fps=25.0, deliverable=True)
    expected = [
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
        "20",
        "-b:v",
        "0",
        "-g",
        "50",
    ]
    assert args == expected


def test_deliverable_video_args_x264_matches_pro_grade_profile() -> None:
    """Task T2.10: libx264 deliverable profile carries slow preset, B-frames, CRF and GOP."""
    args = deliverable_video_args(Encoder.X264, crf=20, fps=30.0, deliverable=True)
    expected = [
        "-preset",
        "slow",
        "-profile:v",
        "high",
        "-bf",
        "3",
        "-crf",
        "20",
        "-g",
        "60",
    ]
    assert args == expected


def test_deliverable_video_args_working_render_preserves_crf() -> None:
    """Working renders (deliverable=False) preserve base quality arguments."""
    assert deliverable_video_args(Encoder.NVENC, 27, deliverable=False) == quality_args(
        Encoder.NVENC, 27
    )
    assert deliverable_video_args(Encoder.X264, 27, deliverable=False) == quality_args(
        Encoder.X264, 27
    )


def test_crop_filter_lanczos_and_unsharp_flags() -> None:
    """Task T2.10: Lanczos scaling and light unsharp filtering in crop filter chain."""
    plain = crop_filter(1920, 1080)
    assert ":flags=lanczos" not in plain
    assert "unsharp=" not in plain

    enhanced = crop_filter(1920, 1080, lanczos=True, unsharp=True)
    assert ":flags=lanczos" in enhanced
    assert ",unsharp=5:5:0.5:5:5:0.0" in enhanced

    punch_in_enhanced = crop_filter(
        2560, 1440, punch_ins=((1000, 1.15),), lanczos=True, unsharp=True
    )
    assert ":flags=lanczos" in punch_in_enhanced
    assert ",unsharp=5:5:0.5:5:5:0.0" in punch_in_enhanced


@needs_ffmpeg
def test_deliverable_render_carries_rec709_color_tags(tmp_path: Path) -> None:
    """Delivered clip carries bt709 color primaries, transfer and space."""
    work = tmp_path / "deliverable_render"
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    out = work / "clip.mp4"
    result = render_clip(
        _clip(),
        FIXTURE,
        ass,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        deliverable=True,
    )
    assert Path(result.path).exists()
    primaries = _probe(Path(result.path), "stream=color_primaries").strip()
    trc = _probe(Path(result.path), "stream=color_transfer").strip()
    space = _probe(Path(result.path), "stream=color_space").strip()
    assert primaries == "bt709"
    assert trc == "bt709"
    assert space == "bt709"


def test_delivery_audio_is_normalised_to_the_platform_target() -> None:
    """A podcast master sits ~10 LU under what every target normalises playback to."""
    chain = audio_filter()
    assert "loudnorm=I=-14:TP=-1:LRA=11" in chain
    assert f"aresample={DELIVERY_AUDIO_RATE}" in chain
    assert DELIVERY_AUDIO_RATE == 48_000


@needs_ffmpeg
def test_a_real_encode_lands_on_the_loudness_target(tmp_path: Path) -> None:
    """The filter string is not the evidence; the measured loudness of the file is.

    ebur128 over the encoded artifact, not over the filter graph that was asked for.
    """
    binary = find_ffmpeg()
    assert binary is not None
    quiet = tmp_path / "quiet.wav"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=6:sample_rate=48000",
            "-af",
            "volume=-24dB",
            "-y",
            str(quiet),
        ],
        check=True,
    )
    loud = tmp_path / "loud.wav"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(quiet),
            "-af",
            audio_filter(),
            "-ar",
            str(DELIVERY_AUDIO_RATE),
            "-y",
            str(loud),
        ],
        check=True,
    )

    def integrated(path: Path) -> float:
        measured = subprocess.run(
            [
                str(binary),
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-af",
                "ebur128=framelog=quiet",
                "-f",
                "null",
                "-",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stderr
        tail = measured[measured.rindex("Integrated loudness") :]
        return float(tail.split("I:")[1].split("LUFS")[0].strip())

    assert integrated(quiet) < -20.0, "the input really is quiet"
    assert abs(integrated(loud) - DELIVERY_LUFS) <= 1.5, "single-pass loudnorm lands on target"


# --- reframe-composition T2: the crop is placed from the measured face box -------------------


def test_a_well_framed_source_is_not_zoomed() -> None:
    """Both of the owner's own sources, measured, and neither may be touched.

    ep10 at 1920x1080: 246 detections, face 28.5% of frame height, centred 33% down.
    ep29 at 2560x1440: 163 detections, face 16.2%, centred 31% down.

    The target was 0.22 for one commit, derived from ep10 alone, and ep29 disproved it — at 0.22
    its 810x1440 crop tightened to 598x1062, taking the upscale from 1.33x to 1.81x and cutting
    into the top of the subject's head. One source is not a distribution, so the floor sits below
    the *lower* of the two. D-258.
    """
    ep10_w, ep10_h = vertical_crop_size(1920, 1080)
    assert vertical_framing(1080, ep10_w, ep10_h, 360, 308) == (ep10_w, ep10_h, 0)
    ep29_w, ep29_h = vertical_crop_size(2560, 1440)
    assert vertical_framing(1440, ep29_w, ep29_h, 443, 234) == (ep29_w, ep29_h, 0), (
        "ep29 is well composed at 1440p and tightening it would spend the sharpness that "
        "resolution bought"
    )


def test_a_small_face_is_tightened_to_the_composition_line() -> None:
    """The other measured source: a face 11.6% of frame height, centred 45% down.

    309 detections across 60 samples of a 1920x1080 wide shot. Tightening is capped at
    MAX_VERTICAL_ZOOM because every bit of it is upscale on a source already carried 1.78x to
    reach 1920 tall.
    """
    base_w, base_h = vertical_crop_size(1920, 1080)
    crop_w, crop_h, y = vertical_framing(1080, base_w, base_h, face_center_y=481, face_height=125)

    assert (crop_w, crop_h) == (466, 832), "the wide shot was not tightened toward the target"
    assert abs(125 / crop_h - TARGET_FACE_HEIGHT_SHARE) < 0.01, "it did not reach the floor"
    assert abs(crop_w / crop_h - 9 / 16) < 0.01, "the aspect ratio must survive the zoom"
    assert y == 481 - int(FACE_COMPOSITION_LINE * crop_h), "the face is not on the line"
    # The point of the exercise: less dead wall above the subject than the full-height crop.
    assert 0 < y <= 1080 - crop_h, "nothing was trimmed from the top, or the crop left the frame"


def test_tightening_stops_at_the_cap_however_small_the_face() -> None:
    """The cap is what stops a distant subject from being upscaled into mush.

    Tightening is never free — every bit of it comes straight out of sharpness on a source
    already carried 1.78x to reach 1920 tall — so a face small enough to demand more than
    MAX_VERTICAL_ZOOM gets the cap and stays under-sized rather than getting a soft frame.
    """
    base_w, base_h = vertical_crop_size(1920, 1080)
    crop_w, crop_h, _y = vertical_framing(1080, base_w, base_h, face_center_y=540, face_height=40)

    assert abs(1080 / crop_h - MAX_VERTICAL_ZOOM) < 0.02, f"the cap leaked: {1080 / crop_h:.2f}x"
    assert 40 / crop_h < TARGET_FACE_HEIGHT_SHARE, (
        "a face this small cannot reach the floor, and the cap is what says so"
    )


def test_an_unmeasured_focus_point_crops_as_it_always_did() -> None:
    """AC-6. 37 FocusPoint construction sites predate vertical framing, and every artifact ever
    rendered came from a crop centred vertically. None of them may move."""
    assert vertical_framing(1080, 607, 1080, None, None) == (607, 1080, 0)
    assert crop_filter(1920, 1080) == crop_filter(1920, 1080, face_center_y=None, face_height=None)


def test_a_zero_face_height_is_refused_rather_than_dividing() -> None:
    """A face of no height is not a measurement, and `share = 0 / crop_h` would zoom to the cap
    on a detector bug rather than saying the input was wrong."""
    with pytest.raises(ValueError, match="face height must be positive"):
        vertical_framing(1080, 607, 1080, face_center_y=500, face_height=0)


# --- pro-edit T5: the framing changes, and only on a sentence boundary -----------------------


def test_the_crop_changes_scale_at_least_once() -> None:
    """The delivered ep29 clip ran 34.65 s in one unbroken framing.

    `crop_filter` fixed `crop_w`/`crop_h` before building its filter string, so a scale change
    was not merely absent but structurally impossible. ffmpeg evaluates `w`/`h` once at
    configuration and only `x`/`y` per frame, so the size is changed by command — every one of
    crop's four options carries the `T` flag, verified on this build and on real footage before
    being designed around. D-259.
    """
    schedule = punch_in_schedule([0, 4_000, 9_000], 12_000)
    chain = crop_filter(2560, 1440, focus_x=1288, punch_ins=schedule)

    assert chain.startswith("sendcmd=c='"), chain
    assert "crop w" in chain and "crop h" in chain, "the size never changes"
    # Both directions: a punch-in that never returns is a zoom, not an edit.
    widths = re.findall(r"crop w (\d+)", chain)
    assert len(set(widths)) > 1, f"every commanded width is the same: {widths}"


def test_a_scale_change_lands_on_a_sentence_boundary() -> None:
    """A cut inside a word reads as a glitch rather than as a beat.

    Boundaries closer together than `MIN_SHOT_MS` are dropped rather than merged: holding a
    framing is the default and a change has to earn its place.
    """
    boundaries = [0, 500, 4_000, 4_200, 9_000, 30_000]
    schedule = punch_in_schedule(boundaries, 12_000)
    times = [at_ms for at_ms, _ in schedule]

    assert all(at_ms in boundaries for at_ms in times), f"{times} is not a subset of the starts"
    assert 0 not in times, "the opening framing is not a cut"
    assert 30_000 not in times, "a change past the end would never be seen"
    assert all(later - earlier >= MIN_SHOT_MS for earlier, later in pairwise(times)), (
        f"{times} changes framing faster than {MIN_SHOT_MS} ms"
    )
    assert times[0] >= MIN_SHOT_MS, "the opening framing must hold as long as any other"


def test_existing_single_framing_callers_are_unchanged() -> None:
    """The golden render is a pixel comparison and every artifact ever cut took this path.

    An empty schedule is the common case — a clip whose sentences are all shorter than the
    minimum shot — and it must produce the byte-identical filter string it always did.
    """
    plain = crop_filter(2560, 1440, focus_x=1288)

    assert crop_filter(2560, 1440, focus_x=1288, punch_ins=()) == plain
    assert "sendcmd" not in plain
    assert punch_in_schedule([0, 800, 1_600], 2_400) == (), (
        "a clip too sparse to cut must ask for no cuts, not for a strobe"
    )


def test_a_punch_in_recentres_itself_when_the_crop_tightens() -> None:
    """Baked-in pixel positions would drift the subject sideways on every punch-in.

    The non-punch path interpolates positions already clamped against a fixed crop width, which
    is correct while the width never changes and wrong the moment it does. The punch path
    expresses `x` in ffmpeg's own `out_w`, so the crop re-centres itself as it resizes.
    """
    chain = crop_filter(2560, 1440, focus_x=1288, punch_ins=punch_in_schedule([4_000], 12_000))

    assert "out_w" in chain and "in_w-out_w" in chain, chain
    assert "out_h" in chain and "in_h-out_h" in chain, chain


@pytest.mark.parametrize(
    ("duration", "zoom", "message"),
    [(0, 1.25, "duration must be positive"), (12_000, 0.8, "zoom must be at least 1.0")],
)
def test_a_schedule_that_cannot_mean_anything_is_refused(
    duration: int, zoom: float, message: str
) -> None:
    """A zoom below 1.0 widens, which is not a punch-in; a clip of no length has no boundaries."""
    with pytest.raises(ValueError, match=message):
        punch_in_schedule([4_000], duration, zoom=zoom)


# --- pro-edit: cuts land on breaths, not only on sentence starts -----------------------------


def test_a_cut_lands_on_a_pause_between_words() -> None:
    """Measured on the delivered ep29 clip: 34.65 s carrying two sentences, so cutting only on
    sentence starts allowed exactly one framing change in the whole clip.

    The same clip has five pauses of 120 ms or more, which MIN_SHOT_MS thins to three usable
    cuts. One change in 35 s is not an edit; three is a rhythm. A pause is also a better cut
    point than a sentence start, not merely a more frequent one — it is where the speaker
    themselves broke.
    """
    words = (
        Word(w="یەک", start_ms=0, end_ms=500, conf=0.9),
        Word(w="دوو", start_ms=700, end_ms=1_200, conf=0.9),
        Word(w="سێ", start_ms=1_250, end_ms=1_800, conf=0.9),
    )
    # The 200 ms gap qualifies; the 50 ms one does not.
    assert cut_points_ms(words, 0) == (700,)


def test_a_cut_is_timed_to_the_new_speech_not_the_silence() -> None:
    """The framing arrives with the next word rather than during the pause, so the change reads
    as motivated by what is being said."""
    words = (
        Word(w="یەک", start_ms=10_000, end_ms=10_400, conf=0.9),
        Word(w="دوو", start_ms=11_000, end_ms=11_500, conf=0.9),
    )
    assert cut_points_ms(words, 10_000) == (1_000,), "clip-relative, at the later word's start"


def test_speech_without_pauses_asks_for_no_cuts() -> None:
    """Continuous speech has nowhere to cut that is not inside a word, and the honest answer is
    the single framing the clip had before punch-ins existed."""
    words = tuple(
        Word(w="w", start_ms=index * 400, end_ms=index * 400 + 390, conf=0.9) for index in range(8)
    )
    assert cut_points_ms(words, 0) == ()
    assert punch_in_schedule(cut_points_ms(words, 0), 3_200) == ()


def test_a_punch_in_beside_a_real_camera_cut_is_dropped() -> None:
    """Measured on the 56 s multi-angle clip: the source changes camera at 0.57 s, 17.09 s and
    26.01 s, and a punch-in landed at 26.78 s — 0.77 s after an angle change.

    The camera cuts, then the crop jumps scale before the eye has settled. Two changes that close
    read as a glitch rather than as rhythm, and the source cut *is already* the framing change,
    so the punch-in on top of it is redundant as well as jarring.
    """
    breaths = [11_030, 20_820, 26_780, 34_230, 39_670]
    source_cuts = [566, 17_086, 26_006]

    without = [at_ms for at_ms, _ in punch_in_schedule(breaths, 56_572)]
    with_guard = [at_ms for at_ms, _ in punch_in_schedule(breaths, 56_572, avoid_ms=source_cuts)]

    assert 26_780 in without, "the fixture no longer reproduces the double-cut"
    assert 26_780 not in with_guard, "the punch-in beside the camera cut survived"
    assert set(without) - set(with_guard) == {26_780}, "it dropped more than the offender"


def test_the_guard_is_symmetric_around_a_camera_cut() -> None:
    """A punch-in shortly *before* an angle change is the same defect arriving in the other
    order, so the guard looks both ways."""
    just_before = [9_000]
    just_after = [11_000]
    camera_cut = [10_000]

    assert punch_in_schedule(just_before, 30_000, avoid_ms=camera_cut) == ()
    assert punch_in_schedule(just_after, 30_000, avoid_ms=camera_cut) == ()
    # Far enough away and it survives, or the guard would suppress everything.
    assert punch_in_schedule([20_000], 30_000, avoid_ms=camera_cut) != ()


def test_a_source_that_never_cuts_keeps_every_punch_in() -> None:
    """The control. A single-camera source has no angle changes to avoid, and suppressing
    punch-ins there would leave exactly the flat clip they exist to fix."""
    breaths = [4_000, 9_000, 14_000]

    assert punch_in_schedule(breaths, 20_000, avoid_ms=()) == punch_in_schedule(breaths, 20_000)


def test_a_punch_in_keeps_the_face_on_the_composition_line() -> None:
    """Task T2.4: dynamic punch-in zooms must keep the face anchored on
    FACE_COMPOSITION_LINE (0.38 of out_h) rather than dropping it to centre (0.50 of out_h).
    """
    filter_expr = crop_filter(
        source_width=1920,
        source_height=1080,
        focus_x=960,
        face_center_y=420,
        punch_ins=((5000, 1.15),),
    )
    assert f"420-{FACE_COMPOSITION_LINE}*out_h" in filter_expr
    assert "-out_h/2" not in filter_expr.split(":")[3]

    filter_expr_no_face = crop_filter(
        source_width=1920,
        source_height=1080,
        focus_x=960,
        face_center_y=None,
        punch_ins=((5000, 1.15),),
    )
    assert "out_h/2" in filter_expr_no_face


def test_audio_filter_linear_formatting() -> None:
    """Task T3.1: audio_filter formats measured two-pass parameters with linear=true."""
    stats = LoudnessStats(
        input_i=-21.5,
        input_tp=-14.2,
        input_lra=6.3,
        input_thresh=-32.1,
        target_offset=1.2,
    )
    chain = audio_filter(measured=stats, linear=True)
    assert "measured_I=-21.50" in chain
    assert "measured_TP=-14.20" in chain
    assert "measured_LRA=6.30" in chain
    assert "measured_thresh=-32.10" in chain
    assert "offset=1.20" in chain
    assert "linear=true" in chain
    assert "print_format=json" in chain
    assert f"aresample={DELIVERY_AUDIO_RATE}" in chain


def test_audio_filter_default_preserves_dynamic_chain() -> None:
    """The default audio_filter keeps dynamic loudnorm for fast working renders."""
    chain = audio_filter()
    assert "measured_I" not in chain
    assert "linear=true" not in chain
    assert "print_format=json" not in chain
    assert "loudnorm=" in chain


def test_loudness_stats_dict_roundtrip() -> None:
    """LoudnessStats serializes losslessly to and from dict."""
    stats = LoudnessStats(
        input_i=-21.05,
        input_tp=-18.06,
        input_lra=2.3,
        input_thresh=-31.05,
        target_offset=0.03,
        output_i=-14.02,
        output_tp=-1.5,
        output_lra=2.1,
        output_thresh=-24.02,
        normalization_type="linear",
    )
    d = stats.to_dict()
    restored = LoudnessStats.from_dict(d)
    assert restored == stats


@needs_ffmpeg
def test_measure_audio_loudness_parses_json_stats(tmp_path: Path) -> None:
    """Task T3.1 / AC-1: Pass 1 loudnorm analysis parses valid statistics from audio."""
    binary = find_ffmpeg()
    assert binary is not None
    audio_file = tmp_path / "test_audio.wav"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=3:sample_rate=48000",
            "-y",
            str(audio_file),
        ],
        check=True,
    )
    stats = measure_audio_loudness(audio_file, in_ms=0, duration_ms=2000, binary=binary)
    assert isinstance(stats, LoudnessStats)
    assert stats.input_i < 0.0
    assert stats.input_tp < 0.0
    assert stats.input_lra >= 0.0
    assert stats.input_thresh < 0.0


@needs_ffmpeg
def test_loudnorm_runs_linear_with_measured_inputs(tmp_path: Path) -> None:
    """Task T3.1 / AC-3: deliverable render executes two-pass linear loudnorm."""
    work = tmp_path / "deliverable_loudnorm"
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    out = work / "clip.mp4"
    result = render_clip(
        _clip(),
        FIXTURE,
        ass,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        deliverable=True,
    )
    assert result.loudness_pass1 is not None
    assert result.loudness_pass1.input_i < 0.0
    assert result.loudness_pass2 is not None
    assert result.loudness_pass2.normalization_type == "linear"
    assert result.loudness_pass2.output_tp is not None
    assert result.loudness_pass2.output_tp <= -1.0 + 1e-3
    assert result.loudness_pass2.output_i is not None


def test_contract_records_two_pass_loudness() -> None:
    """Task T3.1 / AC-5: Output contract serializes and restores two-pass loudness dict."""
    loudness_record = {
        "pass1": {
            "input_i": -20.5,
            "input_tp": -12.1,
            "input_lra": 3.4,
            "input_thresh": -30.5,
            "target_offset": 0.5,
            "normalization_type": "dynamic",
        },
        "pass2": {
            "input_i": -20.5,
            "input_tp": -12.1,
            "input_lra": 3.4,
            "input_thresh": -30.5,
            "target_offset": 0.5,
            "output_i": -14.01,
            "output_tp": -1.5,
            "output_lra": 3.2,
            "output_thresh": -24.01,
            "normalization_type": "linear",
        },
    }
    out = Output(
        title_ckb="سەردێڕ",
        description_ckb="ڕوونکردنەوە",
        crop_target="static_centre",
        caption_style="classic",
        durations=(15, 30),
        loudness=loudness_record,
    )
    d = out.to_dict()
    assert "loudness" in d
    assert d["loudness"] == loudness_record
    restored = Output.from_dict(d)
    assert restored.loudness == loudness_record


def test_audio_filter_speech_chain_formatting() -> None:
    """Task T3.2 / AC-1: audio_filter prepends speech conditioning chain when enabled."""
    chain_with_speech = audio_filter(speech_chain=True)
    assert chain_with_speech.startswith(SPEECH_CHAIN_FILTERS)
    assert "highpass=f=80:p=2" in chain_with_speech
    assert "afftdn=nf=-25:tn=1" in chain_with_speech
    assert "deesser=i=0.4:m=0.5:f=0.5:s=o" in chain_with_speech
    assert "equalizer=f=3000:t=q:w=1.5:g=1.5" in chain_with_speech
    assert "loudnorm=" in chain_with_speech
    assert f"aresample={DELIVERY_AUDIO_RATE}" in chain_with_speech

    # Normal working render filter does not include speech chain
    chain_plain = audio_filter(speech_chain=False)
    assert "highpass" not in chain_plain
    assert "afftdn" not in chain_plain
    assert "deesser" not in chain_plain
    assert "equalizer" not in chain_plain


@needs_ffmpeg
def test_deliverable_render_incorporates_speech_chain(tmp_path: Path) -> None:
    """Task T3.2 / AC-4: deliverable render executes speech chain + loudnorm without error."""
    work = tmp_path / "deliverable_speech_chain"
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    out = work / "clip_speech.mp4"
    result = render_clip(
        _clip(),
        FIXTURE,
        ass,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        deliverable=True,
    )
    assert Path(result.path).exists()
    assert result.loudness_pass1 is not None
    assert result.loudness_pass2 is not None
    assert result.loudness_pass2.output_i is not None
    assert abs(result.loudness_pass2.output_i - (-14.0)) <= 6.0


def test_blurred_fill_filter_generates_valid_filter_chain() -> None:
    filt = blurred_fill_filter(1920, 1080)
    assert "split=2[fg][bg]" in filt
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in filt
    assert "crop=1080:1920" in filt
    assert "boxblur=20:2" in filt
    assert "eq=brightness=-0.15" in filt
    assert "scale=1080:-2" in filt
    assert "overlay=(W-w)/2:(H-h)/2" in filt

    # Deliverable flags
    filt_deliverable = blurred_fill_filter(1920, 1080, lanczos=True, unsharp=True)
    assert ":flags=lanczos" in filt_deliverable
    assert ",unsharp=5:5:0.5:5:5:0.0" in filt_deliverable

    # Non-positive dimensions rejected
    with pytest.raises(ValueError, match="must be positive"):
        blurred_fill_filter(0, 1080)
    with pytest.raises(ValueError, match="must be positive"):
        blurred_fill_filter(1920, -1)


def test_decide_wide_shot_layout_selects_correct_strategy() -> None:
    # 1. Close-up / medium shot: face height share >= 0.18
    mode, zoom = decide_wide_shot_layout(0.22, face_sharpness=100.0)
    assert mode == "crop"
    assert zoom == 1.0

    # 2. Wide shot with high sharpness: face height share 0.08, sharpness 120.0 (floor = 60.0)
    mode, zoom = decide_wide_shot_layout(
        0.08,
        face_sharpness=120.0,
        closeup_sharpness_median=100.0,
    )
    assert mode == "zoom"
    assert zoom == 1.875

    # 3. Wide shot with low sharpness: face height share 0.08, sharpness 35.0 (< floor 60.0)
    mode, zoom = decide_wide_shot_layout(
        0.08,
        face_sharpness=35.0,
        closeup_sharpness_median=100.0,
    )
    assert mode == "blurred_fill"
    assert zoom == 1.0

    # 4. Invalid input
    with pytest.raises(ValueError, match="must be positive"):
        decide_wide_shot_layout(-0.05, 50.0)


@needs_ffmpeg
def test_render_clip_supports_blurred_fill_layout(tmp_path: Path) -> None:
    work = tmp_path / "blurred_fill_render"
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    out = work / "clip_blurred_fill.mp4"

    result = render_clip(
        _clip(),
        FIXTURE,
        ass,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        reframe=Reframe.BLURRED_FILL,
    )
    assert Path(result.path).is_file()
    assert result.reframe is Reframe.BLURRED_FILL
    assert result.width == VERTICAL_WIDTH
    assert result.height == VERTICAL_HEIGHT

    # Refuse focus points when BLURRED_FILL is requested (it is not a crop-based reframe)
    with pytest.raises(ValueError, match="blurred_fill reframe mode cannot carry focus points"):
        render_clip(
            _clip(),
            FIXTURE,
            ass,
            FONTS,
            work / "refused.mp4",
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
            reframe=Reframe.BLURRED_FILL,
            focus_points=((0, 320),),
        )


def test_shot_spans_partitions_clip_into_contiguous_intervals() -> None:
    # 1. Standard pauses: 3200, 7100 in a 10s clip
    spans = shot_spans([3200, 7100], 10_000)
    assert spans == ((0, 3200), (3200, 7100), (7100, 10_000))

    # 2. Contiguity holds across all adjacent spans
    for earlier, later in pairwise(spans):
        assert earlier[1] == later[0]

    # 3. Boundaries closer than min_shot_ms (3000 ms) are dropped
    spans_thinned = shot_spans([1500, 3500, 8000], 10_000)
    # 1500 is < 3000 from 0, so dropped; 3500 is >= 3000, so kept; 8000 - 3500 = 4500, so kept
    assert spans_thinned == ((0, 3500), (3500, 8000), (8000, 10_000))

    # 4. Pause within guard_ms (1500 ms) of a source cut is discarded
    spans_guarded = shot_spans(
        boundaries_ms=[2000, 5200],
        clip_duration_ms=10_000,
        source_cuts_ms=[5000],
    )
    # 5200 dropped due to guard around 5000; 5000 kept as source cut
    assert (0, 5000) in spans_guarded or any(s[0] == 5000 for s in spans_guarded)

    # 5. Non-positive duration raises ValueError
    with pytest.raises(ValueError, match="must be positive"):
        shot_spans([], 0)


def test_eased_push_schedule_generates_smoothstep_progression() -> None:
    spans = ((0, 2000), (2000, 5000))
    schedule = eased_push_schedule(spans, push_zoom=1.08, step_ms=100)

    # First shot: 0 to 2000 ms
    shot1_frames = [f for f in schedule if f[0] < 2000 or (f[0] == 2000 and f[1] == 1.08)]
    assert shot1_frames[0] == (0, 1.0)

    # Midpoint of shot 1 at 1000 ms: smoothstep(0.5) = 0.5 -> 1.0 + 0.08 * 0.5 = 1.04
    midpoint_frame = next(f for f in shot1_frames if f[0] == 1000)
    assert midpoint_frame == (1000, 1.04)

    # Second shot starts back at 1.0 (hard cut) and grows to 1.08 at 5000 ms
    shot2_frames = [f for f in schedule if f[0] >= 2000]
    assert shot2_frames[0] == (2000, 1.0)
    assert shot2_frames[-1] == (5000, 1.08)

    # Monotonicity of shot 2
    for f1, f2 in pairwise(shot2_frames):
        assert f2[1] >= f1[1]

    # Error conditions
    with pytest.raises(ValueError, match="must be at least 1.0"):
        eased_push_schedule(spans, push_zoom=0.9)
    with pytest.raises(ValueError, match="step_ms must be positive"):
        eased_push_schedule(spans, step_ms=0)


@needs_ffmpeg
def test_render_clip_supports_eased_push_in_schedule(tmp_path: Path) -> None:
    work = tmp_path / "eased_push_render"
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    out = work / "clip_eased_push.mp4"

    clip = _clip()
    duration = clip.out_ms - clip.in_ms
    spans = shot_spans([duration // 2], duration)
    schedule = eased_push_schedule(spans, push_zoom=1.08, step_ms=100)

    result = render_clip(
        clip,
        FIXTURE,
        ass,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        punch_ins=schedule,
    )
    assert Path(result.path).is_file()
    assert result.width == VERTICAL_WIDTH
    assert result.height == VERTICAL_HEIGHT


@needs_ffmpeg
def test_render_clip_supports_silence_plan(tmp_path: Path) -> None:
    work = tmp_path / "silence_render"
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "captions.ass"
    ass.write_text(build_ass((_sentence(),)), encoding="utf-8")
    out = work / "clip_silence.mp4"

    clip = _clip()
    duration = clip.out_ms - clip.in_ms
    # Excise a 500 ms pause: retained is [0, 800] and [1300, duration]
    plan = SilencePlan(
        clip_in_ms=clip.in_ms,
        clip_out_ms=clip.out_ms,
        threshold_ms=400,
        target_gap_ms=100,
        retained_intervals_ms=((0, 800), (1300, duration)),
        removed_intervals_ms=((800, 1300),),
        total_removed_ms=500,
    )

    result = render_clip(
        clip,
        FIXTURE,
        ass,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        silence_plan=plan,
    )
    assert Path(result.path).is_file()
    assert result.requested_duration_ms == duration - 500
    assert abs(result.measured_duration_ms - (duration - 500)) <= 50


@needs_ffmpeg
def test_two_renders_of_one_edit_agree(tmp_path: Path) -> None:
    """T1.7 (Reproducibility Proof, §7.8).

    Re-render the same edit twice from identical inputs:
    - ASS byte-identical
    - contract identical minus timestamps
    - video PSNR >= 45 dB (or inf) between the two
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None

    ass_path1 = tmp_path / "captions1.ass"
    ass_path2 = tmp_path / "captions2.ass"
    text1 = build_ass((_sentence(),), play_res_x=1080, play_res_y=1920)
    text2 = build_ass((_sentence(),), play_res_x=1080, play_res_y=1920)
    ass_path1.write_text(text1, encoding="utf-8")
    ass_path2.write_text(text2, encoding="utf-8")
    assert ass_path1.read_bytes() == ass_path2.read_bytes(), "ASS files must be byte-identical"

    clip1 = _clip()
    clip2 = _clip()
    dict1 = clip1.to_dict()
    dict2 = clip2.to_dict()
    assert dict1 == dict2, "Contract structures must be identical"

    out1 = tmp_path / "render1.mp4"
    out2 = tmp_path / "render2.mp4"

    encoder = Encoder.NVENC if encoder_available(Encoder.NVENC, ffmpeg) else Encoder.X264

    res1 = render_clip(
        clip1,
        FIXTURE,
        ass_path1,
        FONTS,
        out1,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        encoder=encoder,
        focus_points=((clip1.in_ms, SOURCE_WIDTH // 2), (clip1.out_ms, SOURCE_WIDTH // 2)),
        reframe=Reframe.FACE_TRACKED,
        ffmpeg=ffmpeg,
        crf=20,
        deliverable=True,
    )
    res2 = render_clip(
        clip2,
        FIXTURE,
        ass_path2,
        FONTS,
        out2,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        encoder=encoder,
        focus_points=((clip2.in_ms, SOURCE_WIDTH // 2), (clip2.out_ms, SOURCE_WIDTH // 2)),
        reframe=Reframe.FACE_TRACKED,
        ffmpeg=ffmpeg,
        crf=20,
        deliverable=True,
    )

    assert Path(res1.path).is_file()
    assert Path(res2.path).is_file()
    assert res1.measured_duration_ms == res2.measured_duration_ms

    proc = subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-i",
            str(out1),
            "-i",
            str(out2),
            "-lavfi",
            "psnr",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"average:([\d.]+|inf)", proc.stderr)
    assert match is not None, f"PSNR could not be parsed: {proc.stderr}"
    val_str = match.group(1)
    if val_str != "inf":
        psnr_val = float(val_str)
        assert psnr_val >= 45.0, f"PSNR {psnr_val} dB is below 45.0 dB reproducibility threshold"


def test_two_person_split_filter_syntax() -> None:
    filt = two_person_split_filter(
        2560,
        1440,
        top_crop=(100, 0, 1620, 1440),
        bottom_crop=(800, 0, 1620, 1440),
        target_width=1080,
        target_height=1920,
    )
    assert "split=2[top_src][bot_src]" in filt
    assert "[top_src]crop=1620:1440:100:0,scale=1080:960[top_p]" in filt
    assert "[bot_src]crop=1620:1440:800:0,scale=1080:960[bot_p]" in filt
    assert "[top_p][bot_p]vstack=inputs=2" in filt


def test_two_person_split_filter_options() -> None:
    filt = two_person_split_filter(
        2560,
        1440,
        top_crop=(100, 0, 1620, 1440),
        bottom_crop=(800, 0, 1620, 1440),
        lanczos=True,
        unsharp=True,
    )
    assert ":flags=lanczos,unsharp=5:5:0.5:5:5:0.0[top_p]" in filt
    assert ":flags=lanczos,unsharp=5:5:0.5:5:5:0.0[bot_p]" in filt


def test_two_person_split_filter_validations() -> None:
    # Non-positive source or target
    with pytest.raises(ValueError, match="source dimensions must be positive"):
        two_person_split_filter(0, 1440, (0, 0, 100, 100), (0, 0, 100, 100))
    with pytest.raises(ValueError, match="target dimensions must be positive"):
        two_person_split_filter(2560, 1440, (0, 0, 100, 100), (0, 0, 100, 100), target_width=0)
    with pytest.raises(ValueError, match="target_height must be even"):
        two_person_split_filter(2560, 1440, (0, 0, 100, 100), (0, 0, 100, 100), target_height=1921)

    # Crop exceeds source
    with pytest.raises(ValueError, match="top crop box .* exceeds source dimensions"):
        two_person_split_filter(2560, 1440, (2000, 0, 1620, 1440), (0, 0, 1620, 1440))
    with pytest.raises(ValueError, match="bottom crop box .* exceeds source dimensions"):
        two_person_split_filter(2560, 1440, (0, 0, 1620, 1440), (0, 100, 1620, 1440))

    # Negative coordinates / dimensions
    with pytest.raises(ValueError, match="crop coordinates must be non-negative"):
        two_person_split_filter(2560, 1440, (-10, 0, 1620, 1440), (0, 0, 1620, 1440))
    with pytest.raises(ValueError, match="crop dimensions must be positive"):
        two_person_split_filter(2560, 1440, (0, 0, 0, 1440), (0, 0, 1620, 1440))


def test_render_clip_two_person_split_contract(tmp_path: Path) -> None:
    clip = _clip()
    ass_path = _write_ass(tmp_path)
    out = tmp_path / "out.mp4"
    split_crops = ((0, 0, 405, 360), (100, 0, 405, 360))

    # TWO_PERSON_SPLIT with focus_points is refused
    with pytest.raises(ValueError, match="two_person_split reframe mode cannot carry focus points"):
        render_clip(
            clip,
            FIXTURE,
            ass_path,
            FONTS,
            out,
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
            reframe=Reframe.TWO_PERSON_SPLIT,
            focus_points=((clip.in_ms, 320),),
            split_crops=split_crops,
        )

    # TWO_PERSON_SPLIT without split_crops is refused
    with pytest.raises(ValueError, match="two_person_split reframe mode requires split_crops"):
        render_clip(
            clip,
            FIXTURE,
            ass_path,
            FONTS,
            out,
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
            reframe=Reframe.TWO_PERSON_SPLIT,
            split_crops=None,
        )

    # non-TWO_PERSON_SPLIT with split_crops is refused
    with pytest.raises(
        ValueError, match="split_crops can only be passed when reframe is TWO_PERSON_SPLIT"
    ):
        render_clip(
            clip,
            FIXTURE,
            ass_path,
            FONTS,
            out,
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
            reframe=Reframe.STATIC_CENTRE,
            split_crops=split_crops,
        )


@needs_ffmpeg
def test_render_clip_two_person_split_exec(tmp_path: Path) -> None:
    clip = _clip()
    ass_path = _write_ass(tmp_path)
    out = tmp_path / "split_out.mp4"
    # Source is 640x360. 360 * 1.125 = 405. 0+405 <= 640 and 200+405 = 605 <= 640.
    split_crops = ((0, 0, 405, 360), (200, 0, 405, 360))

    result = render_clip(
        clip,
        FIXTURE,
        ass_path,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        reframe=Reframe.TWO_PERSON_SPLIT,
        split_crops=split_crops,
    )
    assert Path(result.path).is_file()
    assert _probe(out, "stream=width") == "1080"
    assert _probe(out, "stream=height") == "1920"


def test_render_clip_refuses_missing_logo_file(tmp_path: Path) -> None:
    clip = _clip()
    ass_path = _write_ass(tmp_path)
    out = tmp_path / "brand_out.mp4"
    kit = BrandKit(logo_path=tmp_path / "nonexistent_logo.png")
    with pytest.raises(BrandKitError, match="brand logo file not found"):
        render_clip(
            clip,
            FIXTURE,
            ass_path,
            FONTS,
            out,
            SOURCE_WIDTH,
            SOURCE_HEIGHT,
            brand_kit=kit,
        )


@needs_ffmpeg
def test_render_clip_with_progress_bar_exec(tmp_path: Path) -> None:
    clip = _clip()
    ass_path = _write_ass(tmp_path)
    out = tmp_path / "pb_out.mp4"
    kit = BrandKit(progress_bar=ProgressBarConfig(enabled=True, color="#00FF00", height_px=8))

    result = render_clip(
        clip,
        FIXTURE,
        ass_path,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        brand_kit=kit,
    )
    assert Path(result.path).is_file()
    assert result.brand_kit == kit
    assert _probe(out, "stream=width") == "1080"
    assert _probe(out, "stream=height") == "1920"


@needs_ffmpeg
def test_render_clip_with_logo_and_progress_bar_exec(tmp_path: Path) -> None:
    clip = _clip()
    ass_path = _write_ass(tmp_path)
    out = tmp_path / "logo_pb_out.mp4"
    logo_path = ROOT / "tests" / "golden" / "kurdish-hook-card.png"
    assert logo_path.is_file()
    kit = BrandKit(
        logo_path=logo_path,
        logo_position="top_right",
        logo_width=120,
        logo_opacity=0.8,
        progress_bar=ProgressBarConfig(enabled=True, color="#E50914", height_px=6),
    )

    result = render_clip(
        clip,
        FIXTURE,
        ass_path,
        FONTS,
        out,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        brand_kit=kit,
    )
    assert Path(result.path).is_file()
    assert result.brand_kit == kit
    assert _probe(out, "stream=width") == "1080"
    assert _probe(out, "stream=height") == "1920"
