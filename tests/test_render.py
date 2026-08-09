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
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from hawedit.boundary import BoundaryInputs, fuse_boundary
from hawedit.captions import build_ass, ffprobe_for, find_ffmpeg
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Qc
from hawedit.ingest import probe_duration_ms
from hawedit.render import (
    ENCODER_PROBE_SIZE,
    NVENC_MIN_FRAME,
    VERTICAL_HEIGHT,
    VERTICAL_WIDTH,
    Encoder,
    Reframe,
    RenderError,
    _publish_render,
    assert_encoded_span,
    crop_filter,
    encoder_available,
    frame_duration_ms,
    frame_rate,
    render_clip,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
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


def test_dynamic_crop_tracks_focus_points_over_the_clip_timeline() -> None:
    chain = crop_filter(
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        focus_points=((100, 50), (1_100, 600)),
        clip_in_ms=100,
    )
    assert "if(lt(t\\,0.500)" in chain
    assert "\\,0\\," in chain
    assert "\\,438)" in chain


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
