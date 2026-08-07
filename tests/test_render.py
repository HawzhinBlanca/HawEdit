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

import subprocess
from pathlib import Path

import pytest

from hawedit2.boundary import BoundaryInputs, fuse_boundary
from hawedit2.captions import build_ass, find_ffmpeg
from hawedit2.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Qc
from hawedit2.render import (
    VERTICAL_HEIGHT,
    VERTICAL_WIDTH,
    Encoder,
    Reframe,
    RenderError,
    crop_filter,
    encoder_available,
    render_clip,
)
from hawedit2.sentences import Sentence
from hawedit2.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FONTS = ROOT / "assets" / "fonts"

# The fixture is 640x360 — see tests/test_ingest.py for how it is built.
SOURCE_WIDTH, SOURCE_HEIGHT = 640, 360

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT2_FFMPEG")

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
        qc=qc if qc is not None else Qc(auto_pass=True, flags=(), human_reviewed=True),
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
            str(ffprobe.with_name("ffprobe")),
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


def test_an_incomplete_sentence_cannot_even_reach_a_clip() -> None:
    """Kurdish invariant #2, at the earliest point it can be enforced.

    `fuse_boundary` refuses outright, so there is no path from a candidate whose sentence did
    not close to a `Clip` at all — the render gate never sees one because one cannot be built.
    """
    from hawedit2.boundary import IncompleteSentence

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

    from hawedit2.boundary import BoundaryInvariantViolated

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


@needs_ffmpeg
def test_a_listed_but_unusable_encoder_is_not_reported_as_available() -> None:
    """§4.3.2's lesson, applied to encoders — measured on this exact build.

    `ffmpeg -encoders` lists what was compiled in. The static build fetched by
    `scripts/fetch-ffmpeg.sh` lists `h264_nvenc` and cannot encode one frame with it: NVENC is
    loaded at runtime and there is no NVIDIA driver here. Reading the listing would have this
    machine claim an encoder §6 puts on hawapc01, and the failure would surface deep inside a
    real encode. So the probe encodes a frame and checks bytes came out.
    """
    binary = find_ffmpeg()
    assert binary is not None
    listing = subprocess.run(
        [str(binary), "-hide_banner", "-loglevel", "error", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    listed = any(line.split()[1:2] == [Encoder.NVENC.value] for line in listing.splitlines())
    if not listed:
        pytest.skip("this build does not compile in NVENC — nothing to distinguish")
    assert not encoder_available(Encoder.NVENC, binary), (
        "h264_nvenc is listed and reported available, but no NVIDIA driver is present. If this "
        "machine really has a working GPU, this test has outlived the environment it documents."
    )


@needs_ffmpeg
def test_an_unusable_encoder_raises_instead_of_falling_back(tmp_path: Path) -> None:
    """§6 puts NVENC on hawapc01. Getting x264 instead would measure the wrong encoder."""
    binary = find_ffmpeg()
    assert binary is not None
    if encoder_available(Encoder.NVENC, binary):
        pytest.skip("this ffmpeg can genuinely encode with NVENC — nothing to refuse")
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
    monkeypatch.setattr("hawedit2.render.find_ffmpeg", lambda: None)
    (tmp_path / "captions.ass").write_text("", encoding="utf-8")
    with pytest.raises(RenderError, match="fetch-ffmpeg.sh"):
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
        pytest.skip("no ffmpeg — set HAWEDIT2_FFMPEG")
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
    from hawedit2.captions import _escape_filter_path

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
