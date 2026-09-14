"""M3.1 — §4.3 RTL caption rendering, and Kurdish invariant #4.

§0 calls this failure mode #3: "FFmpeg's default shaping engine breaks Arabic-script text.
You will not catch it in code review — you will catch it when a client sees the burned-in
captions."

§4.3's six requirements, and where each is tested:

1. `shaping=complex` explicitly, never `auto` — `test_the_filter_always_sets_shaping_complex`
2. libass built with HarfBuzz **and** FriBidi — `assert_rtl_stack`, which follows the
   blueprint in checking both `-buildconf` and the linked libraries, because "a package that
   accepts the option may still lack the backing library"
3. `ass`/`subtitles`, never `drawtext` — `test_the_filter_never_uses_drawtext`
4. font covers the full Kurdish set — `assert_font_covers_kurdish`, run against the real
   Noto Naskh Arabic shipped in `assets/fonts`
5. line breaks inserted from the word alignment, never `wrap_unicode` —
   `test_wrap_style_disables_automatic_wrapping`
6. golden-file render test — the comparison is implemented and tested; generating the
   reference needs a verified libass build (`BLOCKED.md` #5)
"""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Final

import cv2
import pytest

from hawedit.captions import (
    DEFAULT_BOTTOM_CAPTION_BAND,
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINE_WIDTH_PX,
    DEFAULT_PLATE_COLOUR,
    DEFAULT_PLATE_PADDING,
    DEFAULT_TOP_CAPTION_BAND,
    DEFAULT_TOP_MARGIN_V,
    GOLDEN_CAPTION_TEXT,
    KURDISH_REQUIRED_GLYPHS,
    MIN_LEGIBILITY_CONTRAST_RATIO,
    POPUP_MAX_CHARS,
    POPUP_MAX_WIDTH_PX,
    REPORT_THEME,
    VIRAL_FONT_SIZE,
    VIRAL_THEME,
    CaptionsOutsideClip,
    CaptionStyle,
    CaptionTheme,
    CaptionVerificationError,
    EmphasisCategory,
    FontCoverageError,
    GoldenReferenceMissing,
    MissingRtlStack,
    assert_ass_fonts_cover_kurdish,
    assert_captions_within_clip,
    assert_font_covers_kurdish,
    assert_fonts_dir_covers_kurdish,
    assert_rtl_stack,
    build_ass,
    chunk_caption_events,
    classify_kurdish_emphasis,
    compare_golden_render,
    compute_rtl_word_positions,
    contrast_ratio,
    decode_to_rgb,
    emphasis_index,
    event_needs_plate,
    find_ffmpeg,
    intersects_caption_band,
    measure_rendered_caption_width,
    parse_ass_colour,
    parse_dialogue_times,
    relative_luminance,
    render_caption_png,
    should_use_top_caption_placement,
    subtitle_filter,
    verify_caption_geometry,
    verify_caption_glyphs,
    verify_caption_integrity,
    verify_caption_text,
    wrap_caption_lines,
    wrap_title_lines,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoNaskhArabic-Regular.ttf"


FULL_BUILDCONF = """
  configuration:
    --prefix=/usr
    --enable-gpl
    --enable-libass
    --enable-libfribidi
    --enable-libharfbuzz
    --enable-libx264
"""


LDD_OUTPUT = """
    libass.so.9 => /usr/lib/libass.so.9
    libharfbuzz.so.0 => /usr/lib/libharfbuzz.so.0
    libfribidi.so.0 => /usr/lib/libfribidi.so.0
"""


def words(*specs: tuple[str, int, int]) -> tuple[Word, ...]:
    return tuple(Word(w=w, start_ms=s, end_ms=e, conf=0.95) for w, s, e in specs)


A_SENTENCE = Sentence(
    words=words(("ئەمە", 0, 400), ("زۆر", 400, 800), ("باشە.", 800, 1400)), complete=True
)


# --- §4.3.2 the RTL stack, verified at deploy time -------------------------------------


def _render_clip_source() -> str:
    """`render_clip`'s body, for the two guards whose claim is *where the call is*.

    Both are wiring, and wiring is what pass #18 found unheld twice — D-105's lesson, and the
    reason `assert_font_covers_kurdish` sat in the module with no caller at all.
    """
    render_py = FONT.resolve().parents[2] / "src" / "hawedit" / "render.py"
    source = render_py.read_text(encoding="utf-8")
    body = source[source.index("def render_clip(") :]
    following = body.find("\ndef ")  # render_clip is currently the last function in the module
    return body if following == -1 else body[:following]


def _render_caption_png_source() -> str:
    """`render_caption_png`'s body, for the claim that it burns production's own filter."""
    captions_py = FONT.resolve().parents[2] / "src" / "hawedit" / "captions.py"
    source = captions_py.read_text(encoding="utf-8")
    body = source[source.index("def render_caption_png(") :]
    following = body.find("\ndef ")
    return body if following == -1 else body[:following]


def test_the_golden_render_burns_productions_own_filter_string() -> None:
    """§4.3.6 compares pixels, and those pixels have to come from the filter production burns.

    `render_caption_png` spelled out its own `ass=…:shaping=…:fontsdir=…` until D-164 —
    identical to `subtitle_filter`'s output character for character, and nothing required it to
    stay so. A fourth element added to the burn would have gone unrendered by the only test that
    looks at pixels, which is §4.3.6's whole point ("the option flag is not" the safeguard).

    Wiring, so the claim is where the call is — D-105's lesson, and the same shape as
    `test_the_burn_verifies_the_rtl_stack_it_shapes_with` above.
    """
    body = _render_caption_png_source()
    assert "subtitle_filter(" in body, (
        "the golden render no longer derives its filter from subtitle_filter, so §4.3.6 is "
        "comparing pixels rendered from a string production does not use"
    )
    # The control: deriving it and then rebuilding it inline beside the call would satisfy the
    # assertion above while changing nothing.
    assert 'f"ass=' not in body, (
        "render_caption_png builds an `ass=…` filter of its own again; production's string is "
        "the one whose pixels §4.3.6 must compare"
    )


def test_rendering_the_wrong_way_refuses_rather_than_rendering_the_right_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control's own control, and the price of deriving the filter.

    `render_caption_png` now reaches `shaping=simple` by replacing production's
    `shaping=complex`. If production ever stopped emitting that substring, the replacement would
    quietly no-op: `test_simple_shaping_fails_the_golden_test` would render the **right** way,
    find it equal to the reference, and fail — reading as a shaping regression when the truth is
    a broken test. It refuses instead, naming the string it could not find.
    """
    import hawedit.captions as captions

    monkeypatch.setattr(captions, "subtitle_filter", lambda ass, fonts: "ass=x:fontsdir=y")
    with pytest.raises(ValueError, match="carries no"):
        captions.render_caption_png(
            Path("ffmpeg-never-runs"),
            tmp_path / "captions.ass",
            tmp_path,
            tmp_path / "out.png",
            shaping="simple",
        )


def test_a_complete_build_passes() -> None:
    report = assert_rtl_stack(FULL_BUILDCONF, LDD_OUTPUT)
    assert report.libass and report.harfbuzz and report.fribidi


def test_a_build_without_libass_is_refused() -> None:
    with pytest.raises(MissingRtlStack, match="libass"):
        assert_rtl_stack("  configuration:\n    --enable-gpl\n", "")


def test_a_build_without_harfbuzz_is_refused() -> None:
    """§4.3: shaping=complex "Requires libass to be built with HarfBuzz." Accepting the
    option is not the same as having the library."""
    buildconf = "  configuration:\n    --enable-libass\n    --enable-libfribidi\n"
    with pytest.raises(MissingRtlStack, match="HarfBuzz"):
        assert_rtl_stack(buildconf, "")


def test_a_build_without_fribidi_is_refused() -> None:
    buildconf = "  configuration:\n    --enable-libass\n    --enable-libharfbuzz\n"
    with pytest.raises(MissingRtlStack, match="FriBidi"):
        assert_rtl_stack(buildconf, "")


def test_an_explicit_disable_beats_an_enable_for_the_same_library() -> None:
    """Found SURVIVED by adversarial pass #18 (D-133): the `disabled` precedence in `find()`
    could be deleted with the whole suite green.

    Every other case reaches `None` by absence — `--disable-libass` alone leaves libass out of
    `enabled` too, so removing the precedence changes nothing there. It matters only when both
    flags are present, which is how a build script appending `--disable-libass` to an inherited
    `--enable-libass` base actually looks. ffmpeg takes the last flag; so does this.

    A linked `libass.so` must not rescue it either: an explicitly disabled library is a
    statement about the build, and the .so on the box may be a different ffmpeg's.
    """
    both = "  configuration:\n    --enable-libass\n    --disable-libass\n"
    with pytest.raises(MissingRtlStack, match="libass"):
        assert_rtl_stack(both + "    --enable-libharfbuzz\n    --enable-libfribidi\n", "")
    with pytest.raises(MissingRtlStack, match="libass"):
        assert_rtl_stack(both, LDD_OUTPUT)
    # The control: without the --disable- the very same configure line is accepted, so this is
    # measuring the precedence and not merely that some string is refused.
    report = assert_rtl_stack("  configuration:\n    --enable-libass\n", LDD_OUTPUT)
    assert report.libass is True


def test_the_burn_verifies_the_rtl_stack_it_shapes_with() -> None:
    """Also SURVIVED pass #18: `assert_rtl_stack` could be deleted from `render_clip` and no
    test noticed — while the comment beside it says "Checked here, not only in the golden test".

    The claim is about where the call is, so that is what is asserted. Same shape as
    `test_the_burn_verifies_the_font_directory_it_was_handed`, one guard over.
    """
    body = _render_clip_source()
    assert "assert_rtl_stack(" in body, (
        "render_clip no longer verifies the shaping stack; §4.3.2's failure is invisible until "
        "a client sees the burned-in captions, and the golden test only covers this host"
    )


def test_linked_libraries_can_supply_what_buildconf_omits() -> None:
    """The blueprint checks both `-buildconf` and `ldd` precisely because a distro build can
    link HarfBuzz into libass without an ffmpeg configure flag naming it."""
    buildconf = "  configuration:\n    --enable-libass\n"
    report = assert_rtl_stack(buildconf, LDD_OUTPUT)
    assert report.harfbuzz_source == "linked libraries"


def test_the_failure_message_names_what_is_missing() -> None:
    with pytest.raises(MissingRtlStack) as exc:
        assert_rtl_stack("  configuration:\n    --enable-libass\n", "")
    message = str(exc.value)
    assert "HarfBuzz" in message and "FriBidi" in message


# --- §4.3.4 font coverage ---------------------------------------------------------------


def test_the_required_glyph_set_is_the_one_section_4_3_lists() -> None:
    assert set("ڕڵۆێچژپگە") <= KURDISH_REQUIRED_GLYPHS


def test_the_required_set_includes_the_collision_pair_measurement_found() -> None:
    """D-013: `ھ` U+06BE appears in real Kurdish. A font missing it renders boxes."""
    assert "ھ" in KURDISH_REQUIRED_GLYPHS
    assert "ه" in KURDISH_REQUIRED_GLYPHS


def test_the_shipped_font_covers_the_kurdish_set() -> None:
    """Real assertion against the real font this project ships."""
    assert_font_covers_kurdish(FONT)


def test_a_font_missing_glyphs_is_refused() -> None:
    """An Arabic font has no Egyptian hieroglyph, so this asks for one it cannot have —
    and the message must name the codepoint, since a box in a caption gives no clue."""
    with pytest.raises(FontCoverageError, match="U\\+13000"):
        assert_font_covers_kurdish(FONT, required=frozenset("ڕ𓀀"))


def test_a_missing_font_file_is_refused() -> None:
    with pytest.raises(FileNotFoundError):
        assert_font_covers_kurdish(Path("/nonexistent/font.ttf"))


# --- §4.3.1 and §4.3.3 the filter string ------------------------------------------------


def test_the_filter_always_sets_shaping_complex() -> None:
    """§4.3.1: "Set shaping=complex explicitly. Never rely on auto." """
    assert "shaping=complex" in subtitle_filter(Path("/w/captions.ass"), Path("/w/fonts"))


def test_the_filter_never_uses_drawtext() -> None:
    """§4.3.3: the ASS path is the supported route for captions."""
    rendered = subtitle_filter(Path("/w/captions.ass"), Path("/w/fonts"))
    assert rendered.startswith("ass=")
    assert "drawtext" not in rendered


def test_the_filter_references_the_font_directory() -> None:
    """§4.3.4: "do not rely on fontconfig resolution on the render host." """
    assert "fontsdir=" in subtitle_filter(Path("/w/captions.ass"), Path("/w/fonts"))


def test_filter_paths_are_escaped() -> None:
    """An unescaped colon in a path silently truncates the filtergraph argument.

    Two backslashes, because ffmpeg unescapes a filter option twice — once splitting the
    filtergraph, once parsing the filter's own arguments. One backslash survives the first
    pass and is eaten by the second, leaving the `:` it was protecting as a separator again.
    """
    rendered = subtitle_filter(Path("/w/od:d/captions.ass"), Path("/w/fonts"))
    assert r"od\\:d" in rendered


def test_a_windows_path_is_escaped_for_both_unescaping_passes() -> None:
    """hawapc01 is Windows, and `C:\\Users\\…` carries both metacharacters at once.

    Escaped wrong this fails loudly — but only because `fontsdir` follows the ass path and
    ffmpeg then sees an option name it does not know. Put a path last and the same mistake
    truncates in silence into `shaping=auto`, which §4.3 says is invisible until a client
    sees the captions. `Path` keeps the string verbatim on POSIX, so this pins the same
    bytes on the CI runner as on the render box.
    """
    rendered = subtitle_filter(Path(r"C:\Users\w\captions.ass"), Path(r"C:\Users\w\fonts"))
    assert rendered == (
        r"ass=C\\:/Users/w/captions.ass:shaping=complex:fontsdir=C\\:/Users/w/fonts"
    )


# --- §4.3.5 our own line breaks ---------------------------------------------------------


def test_line_breaks_come_from_the_word_alignment() -> None:
    line_words = words(("یەک", 0, 100), ("دوو", 100, 200), ("سێ", 200, 300), ("چوار", 300, 400))
    lines = wrap_caption_lines(line_words, max_chars=8)
    assert len(lines) > 1
    assert all(len(" ".join(w.w for w in line)) <= 8 for line in lines)


def test_a_single_short_line_is_not_split() -> None:
    assert len(wrap_caption_lines(words(("ئەمە", 0, 100)), max_chars=40)) == 1


def test_a_word_longer_than_the_limit_still_gets_its_own_line() -> None:
    """Never drop a word to satisfy a width — a missing word is worse than a long line."""
    long_word = "ئەمەیەکێکیزۆردرێژە"
    lines = wrap_caption_lines(words((long_word, 0, 100), ("باشە", 100, 200)), max_chars=5)
    assert any(line[0].w == long_word for line in lines)
    assert sum(len(line) for line in lines) == 2


def test_wrapping_preserves_word_order_and_loses_nothing() -> None:
    line_words = words(*[(f"w{i}", i * 100, i * 100 + 100) for i in range(12)])
    lines = wrap_caption_lines(line_words, max_chars=10)
    assert [w.w for line in lines for w in line] == [w.w for w in line_words]


# --- the ASS file -------------------------------------------------------------------------


def test_wrap_style_disables_automatic_wrapping() -> None:
    """§4.3.5: automatic wrapping on RTL text produces bad break points regardless, and
    `wrap_unicode` is off by default for native ASS anyway. WrapStyle 2 = breaks only at \\N."""
    assert "WrapStyle: 2" in build_ass((A_SENTENCE,), font_name="Noto Naskh Arabic")


def test_the_ass_declares_the_font_it_needs() -> None:
    ass = build_ass((A_SENTENCE,), font_name="Noto Naskh Arabic")
    assert "Noto Naskh Arabic" in ass


def test_the_ass_has_the_required_sections() -> None:
    ass = build_ass((A_SENTENCE,))
    for section in ("[Script Info]", "[V4+ Styles]", "[Events]"):
        assert section in ass


def test_dialogue_timings_come_from_the_sentence() -> None:
    ass = build_ass((A_SENTENCE,))
    assert "0:00:00.00" in ass
    assert "0:00:01.40" in ass


def test_the_raw_kurdish_text_reaches_the_dialogue_line() -> None:
    """Captions show what was said — the raw surface forms, not the normalized index text."""
    assert "ئەمە زۆر باشە." in build_ass((A_SENTENCE,))


def test_our_line_breaks_appear_as_hard_ass_breaks() -> None:
    ass = build_ass((A_SENTENCE,), max_chars_per_line=8)
    assert "\\N" in ass


def test_word_highlight_style_emits_karaoke_timings_from_the_alignment() -> None:
    """§5's `caption_style: word_highlight`, driven by §4.2's word timings."""
    ass = build_ass((A_SENTENCE,), style=CaptionStyle.WORD_HIGHLIGHT)
    assert "{\\kf40}" in ass, "400 ms word -> 40 centiseconds"


def test_the_plain_style_emits_no_karaoke_tags() -> None:
    assert "\\kf" not in build_ass((A_SENTENCE,), style=CaptionStyle.LINE)


def test_an_incomplete_sentence_is_never_captioned() -> None:
    """Invariant #2 again: a fragment is rejected, never rendered."""
    fragment = Sentence(words=words(("بەڵام", 0, 300)), complete=False)
    with pytest.raises(ValueError, match="complete"):
        build_ass((fragment,))


def test_no_sentences_is_refused() -> None:
    with pytest.raises(ValueError, match="no sentences"):
        build_ass(())


# --- §4.3 bounds: six refusals in this module that no test held --------------------------------
#
# Measured by neutralising each in a shadow copy of src/hawedit and running this file with
# tests/test_delivery.py, tests/test_render.py and tests/test_review_findings.py — the callers
# that turned out to hold guards elsewhere. These six reddened nothing in any of them.


def test_a_sentence_starting_before_the_clip_is_refused() -> None:
    """It "would need a negative timestamp, which means it is speech from outside this clip".

    `build_ass` is handed sentences and a `clip_in_ms` to subtract. Nothing else reconciles the
    two, so without this the cue is emitted with a negative start and libass draws it from the
    first frame — a caption for words the clip does not contain, presented as if it did.
    """
    with pytest.raises(CaptionsOutsideClip, match="starts before the clip"):
        build_ass((A_SENTENCE,), clip_in_ms=A_SENTENCE.start_ms + 1)


def test_a_sentence_running_past_the_end_of_the_clip_is_refused() -> None:
    """The other end of the same reconciliation, and the one with no negative number to give it
    away: the cue is well-formed and simply outlives the video."""
    duration = A_SENTENCE.end_ms - A_SENTENCE.start_ms
    with pytest.raises(CaptionsOutsideClip, match="runs past the end of the clip"):
        build_ass((A_SENTENCE,), clip_in_ms=A_SENTENCE.start_ms, clip_duration_ms=duration - 1)
    # The control: exactly filling the clip is allowed, so the boundary is `>` and not `>=`.
    build_ass((A_SENTENCE,), clip_in_ms=A_SENTENCE.start_ms, clip_duration_ms=duration)


def test_a_caption_file_with_no_dialogue_lines_is_refused() -> None:
    """Kurdish invariant #4 is that the burn happens; a file libass reads as empty draws
    nothing, and the clip ships silently uncaptioned."""
    with pytest.raises(CaptionsOutsideClip, match="no Dialogue lines"):
        assert_captions_within_clip("[Script Info]\n[Events]\n", clip_duration_ms=5_000)


def test_a_non_positive_wrap_width_is_refused() -> None:
    """`max_chars` is the line-break width §4.3.5 says to compute ourselves. At zero every word
    is longer than the limit, so each takes its own line and the wrap becomes one word per line
    rather than an error anyone would see."""
    for width in (0, -1):
        with pytest.raises(ValueError, match="max_chars must be positive"):
            wrap_caption_lines(A_SENTENCE.words, max_chars=width)


def test_a_missing_font_file_is_refused_by_name(tmp_path: Path) -> None:
    """The coverage check reads the font to decide whether Kurdish renders. Absent, `TTFont`
    raises about a file handle rather than about the font, and the message a build produces is
    what tells an operator which of the two failed."""
    with pytest.raises(FileNotFoundError, match="no font at"):
        assert_font_covers_kurdish(tmp_path / "absent.ttf")


def test_a_missing_candidate_render_is_an_assertion_not_a_comparison(tmp_path: Path) -> None:
    """§4.3.6's golden test compares two files. The reference has its own refusal one line up;
    this is the other operand, and without it the comparison reads a file that is not there."""
    reference = tmp_path / "golden.png"
    reference.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    with pytest.raises(AssertionError, match="no candidate render"):
        compare_golden_render(reference, tmp_path / "absent.png")


def test_braces_in_text_are_escaped_so_they_are_not_read_as_override_tags() -> None:
    tricky = Sentence(words=words(("{\\b1}", 0, 200)), complete=True)
    ass = build_ass((tricky,))
    assert "{\\b1}" not in ass.split("[Events]")[1]


# --- §4.3.6 the golden render -------------------------------------------------------------


def test_an_identical_render_matches_the_reference(tmp_path: Path) -> None:
    reference = tmp_path / "ref.png"
    candidate = tmp_path / "out.png"
    reference.write_bytes(b"\x89PNG\r\n\x1a\n-pixels-")
    candidate.write_bytes(b"\x89PNG\r\n\x1a\n-pixels-")
    compare_golden_render(reference, candidate)


def test_a_differing_render_fails_the_golden_test(tmp_path: Path) -> None:
    """§4.3.6: "Shaping regressions arrive silently through ffmpeg or libass updates and are
    invisible in code review. This is the real safeguard — the option flag is not." """
    reference = tmp_path / "ref.png"
    candidate = tmp_path / "out.png"
    reference.write_bytes(b"\x89PNG\r\n\x1a\n-pixels-")
    candidate.write_bytes(b"\x89PNG\r\n\x1a\n-DIFFERENT-")
    with pytest.raises(AssertionError, match="differs"):
        compare_golden_render(reference, candidate)


def test_a_missing_reference_says_how_to_generate_it(tmp_path: Path) -> None:
    """Silently passing when the reference is absent would make the safeguard decorative."""
    candidate = tmp_path / "out.png"
    candidate.write_bytes(b"x")
    with pytest.raises(GoldenReferenceMissing, match="HarfBuzz"):
        compare_golden_render(tmp_path / "missing.png", candidate)


# --- §4.3.6 the golden render, against a real ffmpeg -------------------------------------


GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN = GOLDEN_DIR / "kurdish-caption.png"
GOLDEN_VIRAL_KARAOKE = GOLDEN_DIR / "kurdish-viral-karaoke.png"
GOLDEN_HOOK_CARD = GOLDEN_DIR / "kurdish-hook-card.png"
GOLDEN_CAPTION_FIXTURE = GOLDEN_DIR / "kurdish-caption-fixture.png"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"

# Task T1.8: Pinned SHA256 digests for all committed reference goldens (anti-cheat).
# Altering a golden file without an explicit, reviewed change fails this check.
GOLDEN_DIGESTS: Final[dict[str, str]] = {
    "kurdish-caption.png": ("e3d3f3e5d22df202e978b327e7cf73deee7d4c601319898e5ef79e5877fd1f90"),
    "kurdish-viral-karaoke.png": (
        "0f9e8e457aff772a89ba8f3d78b9e3c14f859ad12d176a5a25b95107289b567d"
    ),
    "kurdish-hook-card.png": ("12d1a92949a85a2706f56853914065bf15b29dfbdbb8843957164fd2f9e385b2"),
    "kurdish-caption-fixture.png": (
        "78a822e529d662ce39252467fddd8a1c4e46fe56687a3d206455ba94697bb343"
    ),
}


FONTS_DIR = FONT.parent


def _golden_sentence() -> Sentence:
    """The fixed line the reference was rendered from — see GOLDEN_CAPTION_TEXT."""
    return Sentence(
        words=words(
            ("ڕۆژنامەوانی", 0, 600),
            ("کوردی", 600, 1000),
            ("لە", 1000, 1200),
            ("هەولێر.", 1200, 1800),
        ),
        complete=True,
    )


def test_the_golden_reference_is_committed() -> None:
    """Always on. If the reference is deleted, the suite says so rather than quietly
    losing §4.3.6's only real safeguard."""
    assert GOLDEN.exists(), f"golden reference missing at {GOLDEN}"
    assert GOLDEN.stat().st_size > 1000


def test_the_golden_sentence_matches_the_text_the_reference_was_rendered_from() -> None:
    """A reference rendered from different text silently tests nothing."""
    assert _golden_sentence().text == GOLDEN_CAPTION_TEXT


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_the_render_matches_the_golden_reference(tmp_path: Path) -> None:
    """§4.3.6's real safeguard: render Kurdish and compare to the committed reference."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    assert_rtl_stack(
        __import__("subprocess")
        .run([str(ffmpeg), "-hide_banner", "-buildconf"], capture_output=True, text=True)
        .stdout,
        "",
    )
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(build_ass((_golden_sentence(),)), encoding="utf-8")
    rendered = render_caption_png(ffmpeg, ass_path, FONTS_DIR, tmp_path / "out.png")
    compare_golden_render(GOLDEN, rendered, ffmpeg=ffmpeg)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_the_comparison_runs_on_pixels_and_not_on_the_encoded_file(tmp_path: Path) -> None:
    """`decode_to_rgb` exists because "PNG encoders differ between ffmpeg and zlib versions",
    and nothing pinned that the comparison actually uses it.

    Adversarial pass 26 found the existing coverage was accidental: forcing the comparison onto
    file bytes reddens `test_the_render_matches_the_golden_reference` **here**, but only because
    this machine's encoder happens to disagree with the one the reference was made on — measured
    2026-08-10, 20,830 bytes against 21,847 for **pixel-identical** output. On a machine whose
    encoder agreed, that regression would pass unnoticed and the golden test would be one
    ffmpeg upgrade away from crying wolf.

    The two files are the reference re-encoded at compression levels 9 and 1 — the same picture
    in different bytes **by construction**, so the difference comes from the levels rather than
    from which encoder produced the committed file. Comparing a repack against `GOLDEN` itself
    would reintroduce the same luck: measured here, even a default re-encode already differs
    from the committed bytes, so the control would never fire on this machine.
    """
    import subprocess

    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None

    def repack(level: str, name: str) -> Path:
        out = tmp_path / name
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(GOLDEN),
                "-compression_level",
                level,
                "-y",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out

    tight, loose = repack("9", "tight.png"), repack("1", "loose.png")

    # The controls, in both directions: the bytes must really differ and the pixels must really
    # not. Without the first this would pass on two identical files; without the second it would
    # be asserting that the comparison ignores a difference that is real.
    assert tight.read_bytes() != loose.read_bytes(), (
        "the two compression levels produced identical bytes, so this test cannot tell the two "
        "comparison modes apart"
    )
    assert decode_to_rgb(ffmpeg, tight) == decode_to_rgb(ffmpeg, loose)

    compare_golden_render(tight, loose, ffmpeg=ffmpeg)  # decoded: same picture, must pass

    with pytest.raises(AssertionError, match="differs"):
        compare_golden_render(tight, loose)  # bytes: differ, which is why ffmpeg is passed


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_simple_shaping_fails_the_golden_test(tmp_path: Path) -> None:
    """The negative control, and the whole justification for §4.3.

    If `shaping=simple` produced the same pixels, the golden test would be measuring
    nothing and `shaping=complex` would be cargo cult. It does not: simple breaks the
    joining forms of لە and the initial هـ of هەولێر.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(build_ass((_golden_sentence(),)), encoding="utf-8")
    broken = render_caption_png(
        ffmpeg, ass_path, FONTS_DIR, tmp_path / "simple.png", shaping="simple"
    )
    with pytest.raises(AssertionError, match="differs"):
        compare_golden_render(GOLDEN, broken, ffmpeg=ffmpeg)


def test_golden_files_match_their_pinned_digests() -> None:
    """Every reference golden must exist and match its pinned sha256.

    A golden test is only as strong as its reference. Silent edits to reference images
    to make buggy renders pass is a textbook anti-cheat failure (§4.3.6, AGENTS.md).
    """
    assert GOLDEN_DIR.exists()
    committed = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(GOLDEN_DIR.glob("*.png"))
    }
    assert committed == GOLDEN_DIGESTS, (
        f"committed goldens and pinned digests mismatch: "
        f"diff={set(committed.items()) ^ set(GOLDEN_DIGESTS.items())}"
    )


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_the_render_matches_viral_karaoke_golden(tmp_path: Path) -> None:
    """§4.3.6: VIRAL_THEME animated word highlight karaoke render matches committed golden."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "karaoke.ass"
    ass_path.write_text(
        build_ass(
            (_golden_sentence(),),
            theme=VIRAL_THEME,
            style=CaptionStyle.WORD_HIGHLIGHT,
            font_size=VIRAL_FONT_SIZE,
            clip_in_ms=0,
            clip_duration_ms=2000,
        ),
        encoding="utf-8",
    )
    rendered = render_caption_png(ffmpeg, ass_path, FONTS_DIR, tmp_path / "rendered_karaoke.png")
    compare_golden_render(GOLDEN_VIRAL_KARAOKE, rendered, ffmpeg=ffmpeg)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_simple_shaping_fails_viral_karaoke_golden(tmp_path: Path) -> None:
    """Negative control: simple shaping must fail the viral karaoke golden comparison."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "karaoke.ass"
    ass_path.write_text(
        build_ass(
            (_golden_sentence(),),
            theme=VIRAL_THEME,
            style=CaptionStyle.WORD_HIGHLIGHT,
            font_size=VIRAL_FONT_SIZE,
            clip_in_ms=0,
            clip_duration_ms=2000,
        ),
        encoding="utf-8",
    )
    broken = render_caption_png(
        ffmpeg, ass_path, FONTS_DIR, tmp_path / "broken_karaoke.png", shaping="simple"
    )
    with pytest.raises(AssertionError, match="differs"):
        compare_golden_render(GOLDEN_VIRAL_KARAOKE, broken, ffmpeg=ffmpeg)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_the_render_matches_hook_card_golden(tmp_path: Path) -> None:
    """§4.3.6: Hook card opening frame matches committed golden."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "hook.ass"
    ass_path.write_text(
        build_ass(
            (_golden_sentence(),),
            theme=VIRAL_THEME,
            style=CaptionStyle.WORD_HIGHLIGHT,
            font_size=VIRAL_FONT_SIZE,
            title_ckb="ڕۆژنامەوانی لە هەولێر",
            clip_in_ms=0,
            clip_duration_ms=2000,
        ),
        encoding="utf-8",
    )
    rendered = render_caption_png(ffmpeg, ass_path, FONTS_DIR, tmp_path / "rendered_hook.png")
    compare_golden_render(GOLDEN_HOOK_CARD, rendered, ffmpeg=ffmpeg)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_simple_shaping_fails_hook_card_golden(tmp_path: Path) -> None:
    """Negative control: simple shaping must fail the hook card golden comparison."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "hook.ass"
    ass_path.write_text(
        build_ass(
            (_golden_sentence(),),
            theme=VIRAL_THEME,
            style=CaptionStyle.WORD_HIGHLIGHT,
            font_size=VIRAL_FONT_SIZE,
            title_ckb="ڕۆژنامەوانی لە هەولێر",
            clip_in_ms=0,
            clip_duration_ms=2000,
        ),
        encoding="utf-8",
    )
    broken = render_caption_png(
        ffmpeg, ass_path, FONTS_DIR, tmp_path / "broken_hook.png", shaping="simple"
    )
    with pytest.raises(AssertionError, match="differs"):
        compare_golden_render(GOLDEN_HOOK_CARD, broken, ffmpeg=ffmpeg)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_the_render_matches_caption_over_fixture_video_golden(tmp_path: Path) -> None:
    """§4.3.6: Caption reframed and burned over real fixture video matches committed golden."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    assert FIXTURE.exists(), f"fixture video missing at {FIXTURE}"
    ass_path = tmp_path / "fixture.ass"
    ass_path.write_text(
        build_ass(
            (_golden_sentence(),),
            theme=VIRAL_THEME,
            style=CaptionStyle.WORD_HIGHLIGHT,
            font_size=VIRAL_FONT_SIZE,
            clip_in_ms=0,
            clip_duration_ms=2000,
        ),
        encoding="utf-8",
    )
    rendered = render_caption_png(
        ffmpeg,
        ass_path,
        FONTS_DIR,
        tmp_path / "rendered_fixture.png",
        source_video=FIXTURE,
        timestamp_s=0.500,
    )
    compare_golden_render(GOLDEN_CAPTION_FIXTURE, rendered, ffmpeg=ffmpeg)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_simple_shaping_fails_caption_over_fixture_video_golden(tmp_path: Path) -> None:
    """Negative control: simple shaping must fail the caption-over-video golden comparison."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "fixture.ass"
    ass_path.write_text(
        build_ass(
            (_golden_sentence(),),
            theme=VIRAL_THEME,
            style=CaptionStyle.WORD_HIGHLIGHT,
            font_size=VIRAL_FONT_SIZE,
            clip_in_ms=0,
            clip_duration_ms=2000,
        ),
        encoding="utf-8",
    )
    broken = render_caption_png(
        ffmpeg,
        ass_path,
        FONTS_DIR,
        tmp_path / "broken_fixture.png",
        source_video=FIXTURE,
        timestamp_s=0.500,
        shaping="simple",
    )
    with pytest.raises(AssertionError, match="differs"):
        compare_golden_render(GOLDEN_CAPTION_FIXTURE, broken, ffmpeg=ffmpeg)


# --- §4.3.5 our own line breaks, on the decoded pixels -------------------------------------
#
# The adversarial pass of 2026-08-08 found that "line breaks are ours" was asserted three ways —
# `wrap_caption_lines` unit-tested on word tuples, `\N` present in the ASS, and `WrapStyle: 2`
# present in the header — and never once rendered. The golden reference is 28 characters against
# a 32-character limit, so it is a single line and cannot exercise wrapping at all.
#
# Every row and band count below is measured, in `evidence/rtl-shaping-wrapping.md`.


def _ink_bands(raw: bytes, width: int = 1080, height: int = 1920) -> list[tuple[int, int]]:
    """Contiguous runs of rows containing ink — one band per rendered caption line."""
    rows = [y for y in range(height) if any(raw[(y * width + x) * 3] > 40 for x in range(width))]
    bands: list[tuple[int, int]] = []
    for y in rows:
        if bands and y == bands[-1][1] + 1:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


def _two_line_sentence() -> Sentence:
    """A real Sorani sentence of 50 characters — past the 32-character limit, so it wraps."""
    return Sentence(
        words=words(
            ("ڕۆژنامەوانی", 0, 500),
            ("کوردی", 500, 900),
            ("لە", 900, 1100),
            ("هەولێر", 1100, 1600),
            ("باسی", 1600, 1900),
            ("گرنگی", 1900, 2300),
            ("زمان", 2300, 2700),
            ("دەکات.", 2700, 3200),
        ),
        complete=True,
    )


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_our_line_break_is_the_break_that_renders(tmp_path: Path) -> None:
    """The claim, on the artifact: two lines out, because we put a break in.

    Measured on this fixture: bands at rows 1667-1707 and 1728-1765. Asserting the *count*
    rather than the exact rows so a font-metric change does not fail a render that is still
    two correctly broken lines.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    sentence = _two_line_sentence()
    assert len(wrap_caption_lines(sentence.words, max_chars=DEFAULT_MAX_CHARS_PER_LINE)) == 2

    ass_path = tmp_path / "two.ass"
    ass_path.write_text(build_ass((sentence,)), encoding="utf-8")
    assert "\\N" in ass_path.read_text(encoding="utf-8")
    rendered = render_caption_png(ffmpeg, ass_path, FONTS_DIR, tmp_path / "two.png")
    assert len(_ink_bands(decode_to_rgb(ffmpeg, rendered))) == 2


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_without_our_break_the_same_text_renders_as_one_line(tmp_path: Path) -> None:
    """The negative control. Two bands mean nothing unless one band is reachable.

    The same 50 characters fit on a single line at this size, so the second band exists only
    because `wrap_caption_lines` put it there — not because the text ran out of room.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "one.ass"
    ass_path.write_text(build_ass((_two_line_sentence(),)).replace("\\N", " "), encoding="utf-8")
    rendered = render_caption_png(ffmpeg, ass_path, FONTS_DIR, tmp_path / "one.png")
    assert len(_ink_bands(decode_to_rgb(ffmpeg, rendered))) == 1


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_wrap_style_2_really_stops_libass_wrapping(tmp_path: Path) -> None:
    """What `test_wrap_style_disables_automatic_wrapping` asserts as a string, measured.

    That test checks the header says `WrapStyle: 2`; nothing checked the setting does anything.
    It does, and only for a line wider than the play area — which is why production output
    cannot demonstrate it: our own 32-character limit breaks lines long before libass would.
    Twelve words on one line, 960 px of play area:

        WrapStyle 2  ->  1 band,  x-span 0..1079   (kept on one line, clipped at the frame)
        WrapStyle 0  ->  3 bands, x-span 262..818  (libass broke it where it chose)
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    wide = build_ass((_two_line_sentence(),)).replace("\\N", " ")
    assert "WrapStyle: 2" in wide

    kept = tmp_path / "ws2.ass"
    kept.write_text(
        wide + "Dialogue: 0,0:00:00.00,0:00:03.20,Kurdish,,0,0,0,," + "x " * 40 + "\n",
        encoding="utf-8",
    )
    broken = tmp_path / "ws0.ass"
    broken.write_text(
        kept.read_text(encoding="utf-8").replace("WrapStyle: 2", "WrapStyle: 0"), encoding="utf-8"
    )

    two = _ink_bands(
        decode_to_rgb(ffmpeg, render_caption_png(ffmpeg, kept, FONTS_DIR, tmp_path / "a.png"))
    )
    zero = _ink_bands(
        decode_to_rgb(ffmpeg, render_caption_png(ffmpeg, broken, FONTS_DIR, tmp_path / "b.png"))
    )
    assert len(zero) > len(two), (
        f"WrapStyle 0 produced {len(zero)} bands and WrapStyle 2 produced {len(two)}: the setting "
        f"is doing nothing, so the header assertion is measuring a string and not a behaviour."
    )


# --- §4.3.4, D-133: the set, and the check that had no production caller -------------------


def _font_without(tmp_path: Path, codepoint: int) -> Path:
    """The real shipped Noto, subset to drop exactly one codepoint.

    A hand-made font would prove nothing about a plausible one. This keeps every other glyph,
    every layout feature and the family name, so libass resolves it by the same name the ASS
    asks for — the only difference is the one character.
    """
    from fontTools import subset
    from fontTools.ttLib import TTFont

    fonts_dir = tmp_path / f"fonts-without-{codepoint:04X}"
    fonts_dir.mkdir()
    victim = TTFont(FONT)
    subsetter = subset.Subsetter(
        subset.Options(layout_features="*", name_IDs="*", glyph_names=True)
    )
    subsetter.populate(unicodes={cp for cp in TTFont(FONT).getBestCmap() if cp != codepoint})
    subsetter.subset(victim)
    out = fonts_dir / FONT.name
    victim.save(out)
    return out


def test_the_required_set_contains_every_letter_the_normalizer_emits_as_kurdish() -> None:
    """§4.1's normalizer converts Arabic `ك`/`ي` **into** `ک` U+06A9 / `ی` U+06CC — it calls
    them "the Farsi forms Kurdish uses" — so every normalized transcript is written in them.
    A font requirement that omits them certifies a font that cannot draw Kurdish text.

    Derived from what `normalize_sorani` actually returns, not from a list of the alphabet.
    """
    from hawedit.normalize import normalize_sorani

    emitted = {
        char
        for char in normalize_sorani(GOLDEN_CAPTION_TEXT + " كوردي")
        if unicodedata.category(char).startswith("L")
    }
    kurdish_specific = {char for char in emitted if ord(char) > 0x0660}
    missing = sorted(kurdish_specific - KURDISH_REQUIRED_GLYPHS)
    assert not missing, (
        "the normalizer produces "
        + " ".join(f"{c} U+{ord(c):04X}" for c in missing)
        + " and no font is required to have them"
    )


def test_the_golden_sentences_own_letters_are_all_required() -> None:
    """The control for the test above, from the other direction: this project's own §4.3.6
    reference line is Kurdish text, so every Kurdish-specific letter in it must be required.
    A set that satisfies the normalizer by accident but not the shipped caption is not enough.
    """
    letters = {
        char
        for char in GOLDEN_CAPTION_TEXT
        if unicodedata.category(char).startswith("L") and ord(char) > 0x0660
    }
    assert letters <= KURDISH_REQUIRED_GLYPHS, sorted(letters - KURDISH_REQUIRED_GLYPHS)


def test_a_font_with_the_arabic_kaf_but_not_the_kurdish_one_is_refused(tmp_path: Path) -> None:
    """The measured defect. Before D-133 this font *passed*: the required set had no U+06A9,
    so a font keeping Arabic kaf U+0643 and dropping the Kurdish keheh was certified.
    """
    maimed = _font_without(tmp_path, 0x06A9)
    from fontTools.ttLib import TTFont

    cmap = TTFont(maimed).getBestCmap()
    assert 0x0643 in cmap, "this font is supposed to keep the Arabic kaf"
    assert 0x06A9 not in cmap, "the subset did not drop the Kurdish keheh"

    with pytest.raises(FontCoverageError, match=r"U\+06A9"):
        assert_font_covers_kurdish(maimed)


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_the_refused_font_really_does_break_the_render(tmp_path: Path) -> None:
    """Asserted on the decoded pixels, because "missing glyph" is a claim about the artifact.

    §4.3.4 says missing glyphs render as boxes. Measured, it is worse: libass falls back to
    another font for that one character, so `کوردی` comes apart into a detached `ک` at a
    different size and `وردی` — a word the viewer reads as two. The frame gains ink rather
    than losing it, which is why "the caption looks present" is no evidence at all.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(build_ass((_golden_sentence(),)), encoding="utf-8")

    maimed = _font_without(tmp_path, 0x06A9)
    broken = render_caption_png(ffmpeg, ass_path, maimed.parent, tmp_path / "broken.png")
    good = render_caption_png(ffmpeg, ass_path, FONTS_DIR, tmp_path / "good.png")

    broken_pixels = decode_to_rgb(ffmpeg, broken)
    good_pixels = decode_to_rgb(ffmpeg, good)
    assert len(broken_pixels) == len(good_pixels)
    # Both frames must actually contain a caption: two black frames compare equal and would
    # make every assertion here vacuous. This is the trap the first measurement fell into.
    assert sum(1 for b in good_pixels if b > 32) > 4_000, "the reference frame rendered nothing"
    assert sum(1 for b in broken_pixels if b > 32) > 4_000, "the broken frame rendered nothing"
    assert broken_pixels != good_pixels, (
        "a font with no Kurdish keheh rendered the golden line identically, so the coverage "
        "requirement would be measuring nothing"
    )


def test_the_directory_check_accepts_the_directory_the_product_ships(tmp_path: Path) -> None:
    """The positive control. A check that refuses everything would pass every test below."""
    assert assert_fonts_dir_covers_kurdish(FONTS_DIR) == FONT


def test_a_fonts_directory_with_no_font_at_all_is_refused(tmp_path: Path) -> None:
    """§4.3.4 forbids relying on fontconfig resolution. An empty `fontsdir` is exactly that:
    libass draws Kurdish in whatever the render host happens to have."""
    empty = tmp_path / "fonts"
    empty.mkdir()
    with pytest.raises(FontCoverageError, match="no font file"):
        assert_fonts_dir_covers_kurdish(empty)


def test_a_fonts_directory_whose_only_font_cannot_draw_kurdish_is_refused(
    tmp_path: Path,
) -> None:
    maimed = _font_without(tmp_path, 0x06A9)
    with pytest.raises(FontCoverageError, match=r"closest failure: .*U\+06A9"):
        assert_fonts_dir_covers_kurdish(maimed.parent)


def test_one_covering_font_beside_a_broken_one_is_accepted(tmp_path: Path) -> None:
    """The control for the test above. libass searches the directory, so a second font that
    cannot draw Kurdish is not by itself a failure — refusing here would make the guard fire
    on any host that keeps more than one font in the directory.
    """
    maimed = _font_without(tmp_path, 0x06A9)
    shipped_copy = maimed.parent / "ZZ-covering.ttf"
    shipped_copy.write_bytes(FONT.read_bytes())
    assert assert_fonts_dir_covers_kurdish(maimed.parent) == shipped_copy


def _font_with_family(directory: Path, family: str, filename: str = "covering.ttf") -> Path:
    """Copy the shipped font while changing only its authoritative family names."""
    from fontTools.ttLib import TTFont

    output = directory / filename
    font = TTFont(FONT)
    names = font["name"]
    names.removeNames(nameID=1)
    names.removeNames(nameID=16)
    names.setName(family, 1, 3, 1, 0x409)
    font.save(output)
    font.close()
    return output


def test_the_shipped_ass_family_binds_to_the_shipped_covering_font() -> None:
    ass = build_ass((_golden_sentence(),), font_name="Noto Naskh Arabic")
    assert assert_ass_fonts_cover_kurdish(ass, FONTS_DIR) == (FONT,)


def test_an_unrelated_covering_font_cannot_certify_the_requested_broken_family(
    tmp_path: Path,
) -> None:
    """The exact D-133 shortfall: directory coverage and selected-font coverage differ."""
    requested_but_broken = _font_without(tmp_path, 0x06A9)
    unrelated_covering = _font_with_family(
        requested_but_broken.parent, "Unrelated Covering Family", "ZZ-covering.ttf"
    )
    assert assert_fonts_dir_covers_kurdish(requested_but_broken.parent) == unrelated_covering

    ass = build_ass((_golden_sentence(),), font_name="Noto Naskh Arabic")
    with pytest.raises(FontCoverageError, match=r"Noto Naskh Arabic.*U\+06A9"):
        assert_ass_fonts_cover_kurdish(ass, requested_but_broken.parent)


def test_a_missing_ass_family_is_refused_instead_of_using_host_fallback(tmp_path: Path) -> None:
    _font_with_family(tmp_path, "Another Family")
    ass = build_ass((_golden_sentence(),), font_name="Missing Family")
    with pytest.raises(FontCoverageError, match="no font.*Missing Family"):
        assert_ass_fonts_cover_kurdish(ass, tmp_path)


def test_two_files_claiming_the_used_family_are_refused_as_ambiguous(tmp_path: Path) -> None:
    _font_with_family(tmp_path, "Noto Naskh Arabic", "first.ttf")
    _font_with_family(tmp_path, "Noto Naskh Arabic", "second.ttf")
    ass = build_ass((_golden_sentence(),), font_name="Noto Naskh Arabic")
    with pytest.raises(FontCoverageError, match="multiple directory fonts.*first.ttf.*second.ttf"):
        assert_ass_fonts_cover_kurdish(ass, tmp_path)


def test_an_undefined_dialogue_style_is_refused_before_font_resolution() -> None:
    ass = build_ass((_golden_sentence(),)).replace(",Kurdish,,0,0,0,,", ",Undefined,,0,0,0,,")
    with pytest.raises(FontCoverageError, match="undefined style.*Undefined"):
        assert_ass_fonts_cover_kurdish(ass, FONTS_DIR)


def test_a_malformed_style_format_is_refused() -> None:
    ass = build_ass((_golden_sentence(),)).replace(
        "Format: Name, Fontname, Fontsize", "Format: Name, Name, Fontsize"
    )
    with pytest.raises(FontCoverageError, match="style Format.*Fontname"):
        assert_ass_fonts_cover_kurdish(ass, FONTS_DIR)


def test_an_inline_font_family_override_is_refused() -> None:
    ass = build_ass((_golden_sentence(),)).replace(
        GOLDEN_CAPTION_TEXT, rf"{{\fnAnother Family}}{GOLDEN_CAPTION_TEXT}"
    )
    with pytest.raises(FontCoverageError, match=r"inline \\fn"):
        assert_ass_fonts_cover_kurdish(ass, FONTS_DIR)


def test_the_burn_verifies_the_font_directory_it_was_handed() -> None:
    """This is the whole point of D-133: `assert_font_covers_kurdish` had **no caller in
    `src/`**. It ran in one test against one hard-coded path while `render_clip` burned
    whatever font sat in the `fonts_dir` argument — and `pipeline._runtime_fonts_dir()`
    resolves to an installed location off a real deployment, which no test ever looks at.

    Asserted on the source, in the shape D-119's entry-point test uses: the call has to be
    in `render_clip`, not merely imported somewhere in the module.
    """
    assert "assert_ass_fonts_cover_kurdish(ass_text, fonts_dir)" in _render_clip_source(), (
        "render_clip does not bind the ASS family to a covering font in its fonts directory; "
        "§4.3.4's check would certify a font libass never selects"
    )


# --- D-167: what a break inside a surface form costs, in pixels ------------------------------


_TWO_WORDS = ("یەکەم", "دووەم")


def _two_word_sentence() -> Sentence:
    return Sentence(
        words=(
            Word(w=_TWO_WORDS[0], start_ms=0, end_ms=400, conf=0.9),
            Word(w=_TWO_WORDS[1], start_ms=400, end_ms=900, conf=0.9),
        ),
        complete=True,
    )


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_a_break_inside_a_caption_line_drops_everything_after_it(tmp_path: Path) -> None:
    """Why `Word` refuses a surface form that is not one line (D-167).

    An ASS `Dialogue:` event is **one line**. Nothing in `[Events]` that does not start with a
    recognised keyword is rendered, so a break inside the text does not wrap the caption — it
    ends it, and libass draws the head with no error anywhere.

    The measurement is an **identity**, not a difference: the frame burned from the broken file
    is byte-for-byte the frame burned from a file whose text was *truncated at the break*. A
    difference against the intact render would prove only that two files differ, which two
    renders of anything do; identity against the truncated one proves the tail never arrived.
    The intact comparison is here to stop that identity being vacuous — it would also hold if
    this machine rendered nothing at all.

    `Word` now makes the broken state unconstructible, so the file is production's own output
    with the one character changed: this is the exact text libass received before the guard.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    intact_ass = build_ass((_two_word_sentence(),))
    joined = f"{_TWO_WORDS[0]} {_TWO_WORDS[1]}"
    assert intact_ass.count(joined) == 1, "the two words are not on one Dialogue line as assumed"

    def burn(ass_text: str, name: str) -> bytes:
        path = tmp_path / f"{name}.ass"
        path.write_text(ass_text, encoding="utf-8")
        png = render_caption_png(ffmpeg, path, FONTS_DIR, tmp_path / f"{name}.png")
        return decode_to_rgb(ffmpeg, png)

    broken_ass = intact_ass.replace(joined, f"{_TWO_WORDS[0]}\n{_TWO_WORDS[1]}")
    truncated_ass = intact_ass.replace(joined, _TWO_WORDS[0])

    broken = burn(broken_ass, "broken")
    truncated = burn(truncated_ass, "truncated")
    intact = burn(intact_ass, "intact")

    assert broken == truncated, (
        "the text after the break reached the pixels, so this render does not demonstrate the "
        "defect D-167's guard exists for — re-measure before relaxing the guard"
    )
    assert broken != intact, (
        f"the intact and truncated renders are identical, so the comparison above measures "
        f"nothing: {_TWO_WORDS[1]!r} is not being drawn even when whole (missing font?)"
    )
    assert parse_dialogue_times(broken_ass) == parse_dialogue_times(intact_ass), (
        "the cue-time readback disagrees with the intact file, which would have made this "
        "detectable without looking at pixels — it did not, which is why the guard is upstream"
    )


def test_the_required_set_contains_kurdish_letters_the_normalizer_produces() -> None:
    from hawedit.normalize import normalize_sorani

    emitted = {
        character
        for character in normalize_sorani(GOLDEN_CAPTION_TEXT + " كوردي")
        if unicodedata.category(character).startswith("L") and ord(character) > 0x0660
    }
    assert emitted <= KURDISH_REQUIRED_GLYPHS, sorted(emitted - KURDISH_REQUIRED_GLYPHS)


def test_the_required_set_explicitly_includes_kurdish_keheh_and_yeh() -> None:
    assert {"ک", "ی"} <= KURDISH_REQUIRED_GLYPHS


def test_the_shipped_fonts_directory_has_a_covering_font() -> None:
    assert assert_fonts_dir_covers_kurdish(FONT.parent) == FONT


def test_an_empty_or_noncovering_fonts_directory_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FontCoverageError, match="no font file"):
        assert_fonts_dir_covers_kurdish(empty)

    only_naskh = tmp_path / "only-naskh"
    only_naskh.mkdir()
    (only_naskh / FONT.name).write_bytes(FONT.read_bytes())
    with pytest.raises(FontCoverageError, match=r"U\+1F600"):
        assert_fonts_dir_covers_kurdish(only_naskh, required=frozenset({"😀"}))


def _popup_sentence() -> Sentence:
    spoken = words(
        ("یەک", 0, 400),
        ("دوو", 400, 800),
        ("سێ", 800, 1_200),
        ("چوار", 1_200, 1_600),
        ("پێنج", 1_600, 2_000),
        ("شەش.", 2_000, 2_400),
    )
    return Sentence(words=spoken, complete=True)


def test_popup_chunks_close_on_the_word_count() -> None:
    chunks = chunk_caption_events(_popup_sentence().words, max_words=3, max_chars=99, max_ms=99_999)
    assert [len(chunk) for chunk in chunks] == [3, 3]


def test_popup_chunks_close_on_a_pause_even_when_nothing_else_is_full() -> None:
    """A group that straddles a silence sits on screen with nothing being said.

    No shorter word or character limit replaces this rule: the pause can fall anywhere.
    """
    spoken = words(("یەک", 0, 300), ("دوو", 300, 600), ("سێ", 3_000, 3_300))
    chunks = chunk_caption_events(spoken, max_words=9, max_chars=99, max_ms=99_999, max_gap_ms=400)
    assert [[word.w for word in chunk] for chunk in chunks] == [["یەک", "دوو"], ["سێ"]]


def test_popup_chunks_close_on_elapsed_time() -> None:
    spoken = words(("یەک", 0, 1_500), ("دوو", 1_500, 3_000))
    chunks = chunk_caption_events(spoken, max_words=9, max_chars=99, max_ms=2_000, max_gap_ms=9_999)
    assert [len(chunk) for chunk in chunks] == [1, 1]


def test_a_word_wider_than_the_limit_gets_its_own_event_rather_than_being_dropped() -> None:
    spoken = words(("کورت", 0, 200), ("درێژترین‌وشەی‌ئەم‌ڕستەیە", 200, 900))
    chunks = chunk_caption_events(spoken, max_words=9, max_chars=6, max_ms=9_999, max_gap_ms=9_999)
    assert [word.w for chunk in chunks for word in chunk] == [
        "کورت",
        "درێژترین‌وشەی‌ئەم‌ڕستەیە",
    ]


def test_chunking_refuses_input_it_cannot_split() -> None:
    with pytest.raises(ValueError, match="no words"):
        chunk_caption_events(())
    for limit in ("max_words", "max_chars", "max_ms"):
        with pytest.raises(ValueError, match="must be positive"):
            chunk_caption_events(_popup_sentence().words, **{limit: 0})
    with pytest.raises(ValueError, match="must be non-negative"):
        chunk_caption_events(_popup_sentence().words, max_gap_ms=-1)


def test_popup_events_never_put_a_paragraph_on_screen() -> None:
    """One event per sentence is a wall of text; one per popup is a caption.

    A 2.4 s sentence is mild — the real 38-minute source produced a single 15.8 s event
    holding seven wrapped lines, which is the whole of the visible defect.
    """
    ass = build_ass(
        (_popup_sentence(),),
        style=CaptionStyle.WORD_HIGHLIGHT,
        max_words_per_event=3,
        max_chars_per_line=22,
    )
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 2
    assert all("\\N" not in line for line in events), "a popup must never wrap"


def test_popup_events_hold_across_a_short_hole_and_stop_at_the_sentence() -> None:
    ass = build_ass((_popup_sentence(),), style=CaptionStyle.WORD_HIGHLIGHT, max_words_per_event=3)
    spans = parse_dialogue_times(ass)
    # The first popup is held open until the second begins: no blink between them.
    assert spans[0][1] == spans[1][0]
    # The last popup ends on its own last word, never past the sentence.
    assert spans[-1][1] == _popup_sentence().end_ms


def test_the_default_theme_is_byte_identical_to_what_shipped_before_it_existed() -> None:
    """`REPORT_THEME` is a refactor, not a change. Every existing caller must be unaffected."""
    assert REPORT_THEME.style_row("Kurdish", "Noto Naskh Arabic", 64) == (
        "Style: Kurdish,Noto Naskh Arabic,64,&H00FFFFFF,&H0000FFFF,&H00000000,"
        "&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,140,1"
    )


def test_the_viral_theme_sweeps_with_the_voice_rather_than_ahead_of_it() -> None:
    """ASS karaoke fills from `secondary` to `primary`, so `primary` is the *spoken* colour.

    The reporting default has white primary and yellow secondary, which renders unspoken
    words yellow and spoken words white — a highlight that leads the speaker.
    """
    assert VIRAL_THEME.primary == "&H0000E5FF", "spoken text is gold"
    assert VIRAL_THEME.secondary == "&H00FFFFFF", "unspoken text is white"
    assert (VIRAL_THEME.primary, VIRAL_THEME.secondary) == (
        REPORT_THEME.secondary.replace("&H0000FFFF", "&H0000E5FF"),
        REPORT_THEME.primary,
    )


def test_the_viral_theme_clears_the_platform_caption_bar() -> None:
    """140 px of a 1920-tall frame puts Kurdish text under the Reels/Shorts/TikTok UI."""
    assert REPORT_THEME.margin_v == 140
    assert VIRAL_THEME.margin_v == 360
    assert VIRAL_THEME.bold and VIRAL_THEME.outline > REPORT_THEME.outline


def test_a_theme_reaches_the_rendered_style_row() -> None:
    ass = build_ass((_popup_sentence(),), font_size=74, theme=VIRAL_THEME)
    assert VIRAL_THEME.style_row("Kurdish", "Noto Naskh Arabic", 74) in ass
    assert ",140,1" not in ass


def test_a_custom_theme_round_trips_every_field() -> None:
    theme = CaptionTheme(
        primary="&H00112233",
        secondary="&H00445566",
        outline_colour="&H00778899",
        back_colour="&H00AABBCC",
        bold=True,
        outline=2.5,
        shadow=0.5,
        margin_l=1,
        margin_r=2,
        margin_v=3,
    )
    assert theme.style_row("K", "F", 10) == (
        "Style: K,F,10,&H00112233,&H00445566,&H00778899,&H00AABBCC,1,0,0,0,100,100,0,0,1,"
        "2.5,0.5,2,1,2,3,1"
    )


def test_the_viral_font_size_is_set_from_measured_ink_not_from_the_point_number() -> None:
    """A point size is an em, and Naskh sets a small face inside it.

    Rendered a real 17-character Kurdish popup at each size and took the ink bounding box:
    64 pt gave 38 px of height, 74 -> 43, 84 -> 49, 96 -> 56, 108 -> 63, 120 -> 70. A burned-in
    social caption wants 60-90 px on a 1920-tall frame, so the 74 this shipped with was under
    half the height it appeared to promise.
    """
    assert VIRAL_FONT_SIZE == 108

    # The widest popup the chunker can emit must still fit between the margins. At 108 pt
    # Kurdish measures about 28 px per character, and the theme leaves 1080 - 80 - 80 = 920.
    assert 1080 - VIRAL_THEME.margin_l - VIRAL_THEME.margin_r > POPUP_MAX_CHARS * 28


# --- pro-edit T2: the judge's own title becomes the hook card --------------------------------


def _a_hook_sentence() -> Sentence:
    return Sentence(
        words=(
            Word(w="ماڵێک", start_ms=0, end_ms=500, conf=0.9),
            Word(w="دانیشتوون.", start_ms=500, end_ms=1_200, conf=0.9),
        ),
        complete=True,
    )


def test_the_hook_card_uses_the_judges_own_title() -> None:
    """Stage 4 writes `title_ckb` for every verdict and the render discarded it.

    Measured on the ep29 delivery: the judge wrote a real Kurdish title and the burned clip
    opened on speech with nothing on screen but karaoke. A social clip is scrolled past in its
    first second. D-259.
    """
    title = "ئایا توێکاری حەرامە؟"
    ass = build_ass(
        (_a_hook_sentence(),),
        style=CaptionStyle.WORD_HIGHLIGHT,
        max_words_per_event=3,
        title_ckb=title,
    )

    assert "Style: Hook," in ass, "the card needs its own style or it inherits the caption band"
    hook_events = [line for line in ass.splitlines() if line.startswith("Dialogue: 1,")]
    assert len(hook_events) == 1, f"expected exactly one hook event, got {len(hook_events)}"
    assert title.split()[0] in hook_events[0], "the judge's words are not on the card"
    # Layer 1, above the karaoke, and overlapping it in time by design.
    assert hook_events[0].startswith("Dialogue: 1,0:00:00.00,")
    # The card sits at the top; the captions keep the bottom band they were tuned for.
    hook_style = next(line for line in ass.splitlines() if line.startswith("Style: Hook,"))
    assert ",8," in hook_style, "the card must not land in the caption band"


def test_a_clip_without_a_title_renders_unchanged() -> None:
    """Every clip rendered before the hook card existed, and the golden among them.

    A title is optional because Stage 4 can be skipped entirely — `--verdict`, a blocked judge,
    a run that stops at Stage 5. None of those may gain a style row or an event.
    """
    without = build_ass((_a_hook_sentence(),), style=CaptionStyle.WORD_HIGHLIGHT)
    assert "Style: Hook," not in without
    assert "Dialogue: 1," not in without
    assert build_ass((_a_hook_sentence(),), style=CaptionStyle.WORD_HIGHLIGHT, title_ckb="") == (
        without
    ), "an empty title must be the same as no title, not an empty card"


def test_a_long_title_wraps_rather_than_running_off_the_frame() -> None:
    """`wrap_title_lines` exists because a title is prose, not aligned words.

    `wrap_caption_lines` wraps `Word`s and carries their timings; sharing it would mean inventing
    timestamps to satisfy a signature.
    """
    lines = wrap_title_lines("یەک دوو سێ چوار پێنج شەش حەوت هەشت نۆ دە", max_chars=12)

    assert len(lines) > 1, "a title longer than the line budget must wrap"
    assert all(len(line) <= 12 for line in lines), lines
    assert " ".join(lines).split() == "یەک دوو سێ چوار پێنج شەش حەوت هەشت نۆ دە".split(), (
        "wrapping must not lose or reorder a word"
    )


# --- pro-edit T3: the key word carries the accent, as a style change only ---------------------


def test_the_longest_word_carries_the_emphasis() -> None:
    """A proxy for the carrying word that needs no model, and ties go to the earliest so a
    re-render never moves the accent."""
    words = (
        Word(w="لە", start_ms=0, end_ms=200, conf=0.9),
        Word(w="کاتژمێردا", start_ms=200, end_ms=900, conf=0.9),
        Word(w="بکە", start_ms=900, end_ms=1_200, conf=0.9),
    )
    assert emphasis_index(words) == 1, "the longest word did not carry it"

    tie = (
        Word(w="یەک", start_ms=0, end_ms=300, conf=0.9),
        Word(w="دوو", start_ms=300, end_ms=600, conf=0.9),
    )
    assert emphasis_index(tie) == 0, "a tie must resolve to the earliest, not drift"


def test_a_single_word_event_is_not_emphasised() -> None:
    """Accenting the only word on screen accents nothing; it just makes the caption bigger."""
    assert emphasis_index((Word(w="تەنیا", start_ms=0, end_ms=400, conf=0.9),)) is None
    assert emphasis_index(()) is None


def test_emphasis_never_alters_the_caption_text() -> None:
    """Kurdish invariant #1 governs the transcript, and a caption that edits a word to look
    better is editing the transcript. The accent is an override *around* the word.
    """
    sentence = Sentence(
        words=(
            Word(w="لە", start_ms=0, end_ms=200, conf=0.9),
            Word(w="کاتژمێردا", start_ms=200, end_ms=900, conf=0.9),
        ),
        complete=True,
    )
    ass = build_ass((sentence,), style=CaptionStyle.WORD_HIGHLIGHT, max_words_per_event=3)

    assert "\\fscx118" in ass, "no accent was applied"
    assert "\\fscx100" in ass, "the accent was never closed, so it runs to the end of the event"
    # Every surface form still appears, unmodified, in reading order.
    for word in sentence.words:
        assert word.w in ass, f"{word.w!r} was altered by the accent"


def test_the_hook_card_is_drawn_on_a_plate() -> None:
    """Measured on the first edited clip: the card rendered white over a light shirt and a lit
    face, readable only because of its outline. A plate makes it readable on *any* footage.
    """
    ass = build_ass(
        (
            Sentence(
                words=(Word(w="ماڵێک", start_ms=0, end_ms=500, conf=0.9),),
                complete=True,
            ),
        ),
        style=CaptionStyle.WORD_HIGHLIGHT,
        max_words_per_event=3,
        title_ckb="سەردێڕ",
    )
    hook_style = next(line for line in ass.splitlines() if line.startswith("Style: Hook,"))
    fields = hook_style.split(",")

    # Index 15: field 0 is the "Style: Name" prefix, so BorderStyle sits one later than
    # the Format line reads.
    assert fields[15] == "3", f"BorderStyle is {fields[15]}, so the card has no plate"
    kurdish = next(line for line in ass.splitlines() if line.startswith("Style: Kurdish,"))
    assert kurdish.split(",")[15] == "1", "the caption band must keep outline-and-shadow"


def test_measure_rendered_caption_width_measures_ink_and_caches() -> None:
    """Task T2.9: measure_rendered_caption_width measures positive ink extent and caches."""
    assert measure_rendered_caption_width("") == 0
    assert measure_rendered_caption_width("   ") == 0

    text = "ڕۆژنامەوانی کوردی"
    width1 = measure_rendered_caption_width(text)
    assert width1 > 100

    width2 = measure_rendered_caption_width(text)
    assert width1 == width2


def test_wrap_caption_lines_respects_max_width_px() -> None:
    """AC-1: wrap_caption_lines breaks lines before ink width exceeds max_width_px."""
    line_words = words(
        ("ڕۆژنامەوانییە", 0, 100),
        ("بەپێزەکانی", 100, 200),
        ("ئەمڕۆمان", 200, 300),
        ("لێرەیە", 300, 400),
    )
    # Without max_width_px and high max_chars, it's 1 line
    single = wrap_caption_lines(line_words, max_chars=100)
    assert len(single) == 1

    # With max_width_px=500, it breaks into multiple lines
    wrapped = wrap_caption_lines(line_words, max_chars=100, max_width_px=500)
    assert len(wrapped) > 1

    # Preserves every word in reading order
    assert [w.w for line in wrapped for w in line] == [w.w for w in line_words]


def test_chunk_caption_events_respects_max_width_px() -> None:
    """AC-2: chunk_caption_events closes events before ink width exceeds max_width_px."""
    assert POPUP_MAX_WIDTH_PX == 700
    line_words = words(
        ("ڕۆژنامەوانییە", 0, 100),
        ("بەپێزەکانی", 100, 200),
        ("ئەمڕۆمان", 200, 300),
        ("لێرەیە", 300, 400),
    )
    # With max_width_px=400, chunks close before exceeding 400 px
    chunks = chunk_caption_events(line_words, max_words=10, max_chars=100, max_width_px=400)
    assert len(chunks) > 1
    assert [w.w for chunk in chunks for w in chunk] == [w.w for w in line_words]


def test_oversized_word_gets_own_line_under_width_limit() -> None:
    """AC-3: A single oversized word gets its own line/chunk rather than being dropped or split."""
    long_word = "پێشکەشکردنەکەیان"
    line_words = words((long_word, 0, 100), ("باشە", 100, 200))
    # Set limit smaller than the long word's rendered width
    lines = wrap_caption_lines(line_words, max_chars=100, max_width_px=150)
    assert len(lines) == 2
    assert lines[0][0].w == long_word
    assert lines[1][0].w == "باشە"

    chunks = chunk_caption_events(line_words, max_words=10, max_chars=100, max_width_px=150)
    assert len(chunks) == 2
    assert chunks[0][0].w == long_word
    assert chunks[1][0].w == "باشە"


def test_shaped_line_breaking_validates_positive_width() -> None:
    """Non-positive max_width_px must be rejected with ValueError."""
    line_words = words(("ئەمە", 0, 100))
    with pytest.raises(ValueError, match="max_width_px must be positive"):
        wrap_caption_lines(line_words, max_width_px=0)
    with pytest.raises(ValueError, match="max_width_px must be positive"):
        chunk_caption_events(line_words, max_width_px=0)


def test_shaped_width_breaking_prevents_margin_overflow(tmp_path: Path) -> None:
    """AC-4: Pixel test proving long-ligature Kurdish line no longer overflows margins."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg not available for pixel test")

    # A line with wide Kurdish ligatures that overflows margins if not broken
    text_words = words(
        ("ڕۆژنامەوانییە", 0, 100),
        ("بەپێزەکانی", 100, 200),
        ("ئەمڕۆمان", 200, 300),
        ("لێرەیە", 300, 400),
    )
    # Wrapped lines under shaped width
    lines = wrap_caption_lines(text_words, max_chars=100, max_width_px=DEFAULT_MAX_LINE_WIDTH_PX)
    assert len(lines) >= 2, "must be wrapped into multiple lines"

    # Build ASS with wrapped lines
    ass_text = build_ass(
        (Sentence(words=text_words, complete=True),),
        font_name="Noto Naskh Arabic",
        font_size=VIRAL_FONT_SIZE,
        theme=VIRAL_THEME,
        max_line_width_px=DEFAULT_MAX_LINE_WIDTH_PX,
    )
    ass_path = tmp_path / "shaped.ass"
    ass_path.write_text(ass_text, encoding="utf-8")

    png_path = tmp_path / "shaped.png"
    render_caption_png(ffmpeg, ass_path, FONTS_DIR, png_path, width=1080, height=1920)

    img = cv2.imread(str(png_path), cv2.IMREAD_GRAYSCALE)
    assert img is not None, "rendered PNG must be readable"
    pts = cv2.findNonZero(img)
    assert pts is not None, "rendered caption must produce ink pixels"

    x, y, w, h = cv2.boundingRect(pts)
    left_margin = VIRAL_THEME.margin_l
    right_margin = 1080 - VIRAL_THEME.margin_r

    # Ink must be strictly contained within horizontal margins
    assert x >= left_margin - 5, f"ink spills into left margin: x={x} < margin_l={left_margin}"
    assert x + w <= right_margin + 5, (
        f"ink spills into right margin: right_edge={x + w} > right_margin={right_margin}"
    )


def test_intersects_caption_band_detects_overlap_and_clearance() -> None:
    assert DEFAULT_BOTTOM_CAPTION_BAND == (1300, 1650)
    assert DEFAULT_TOP_CAPTION_BAND == (200, 520)
    assert intersects_caption_band(1400, 1500) is True
    assert intersects_caption_band(1200, 1350) is True  # crosses top boundary
    assert intersects_caption_band(1600, 1700) is True  # crosses bottom boundary
    assert intersects_caption_band(500, 900) is False  # completely above
    assert intersects_caption_band(1700, 1850) is False  # completely below


def test_should_use_top_caption_placement_evaluates_time_and_space() -> None:
    # Event: 1000..3000 ms
    # Temporal mismatch: face at 500..800 ms in bottom band
    assert (
        should_use_top_caption_placement(1000, 3000, face_intervals=((500, 800, 1350, 1550),))
        is False
    )

    # Spatial mismatch: face at 1500..2500 ms in upper third (Y=600..900)
    assert (
        should_use_top_caption_placement(1000, 3000, face_intervals=((1500, 2500, 600, 900),))
        is False
    )

    # Temporal + spatial match: face at 2000..2500 ms in bottom band (Y=1350..1550)
    assert (
        should_use_top_caption_placement(1000, 3000, face_intervals=((2000, 2500, 1350, 1550),))
        is True
    )


def test_build_ass_emits_kurdish_top_for_overlapping_events() -> None:
    s1 = Sentence(words=words(("خوارەوە", 0, 1000)), complete=True)
    s2 = Sentence(words=words(("سەروو", 1000, 2000)), complete=True)

    # Only s1 overlaps with a face in the bottom band
    face_intervals = ((0, 1000, 1350, 1550),)

    ass_text = build_ass(
        (s1, s2),
        font_name="Noto Naskh Arabic",
        font_size=VIRAL_FONT_SIZE,
        theme=VIRAL_THEME,
        face_intervals=face_intervals,
    )

    # KurdishTop style must be declared with alignment 8 and margin_v 240
    assert "Style: KurdishTop,Noto Naskh Arabic" in ass_text
    assert f",8,{VIRAL_THEME.margin_l},{VIRAL_THEME.margin_r},{DEFAULT_TOP_MARGIN_V},1" in ass_text

    dialogue_lines = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    # First dialogue line should use KurdishTop to avoid face overlap
    assert ",KurdishTop," in dialogue_lines[0]
    # Second dialogue line should retain default Kurdish bottom style
    assert ",Kurdish," in dialogue_lines[1]


def test_face_aware_caption_placement_renders_ink_in_upper_band(tmp_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg binary not available")

    # Build ASS with an event placed at top
    s = Sentence(words=words(("سەرووی_شاشە", 0, 1000)), complete=True)
    ass_text = build_ass(
        (s,),
        font_name="Noto Naskh Arabic",
        font_size=VIRAL_FONT_SIZE,
        theme=VIRAL_THEME,
        face_intervals=((0, 1000, 1350, 1550),),
    )
    ass_path = tmp_path / "top.ass"
    ass_path.write_text(ass_text, encoding="utf-8")

    png_path = tmp_path / "top.png"
    render_caption_png(ffmpeg, ass_path, FONTS_DIR, png_path, width=1080, height=1920)

    img = cv2.imread(str(png_path), cv2.IMREAD_GRAYSCALE)
    assert img is not None
    pts = cv2.findNonZero(img)
    assert pts is not None

    x, y, w, h = cv2.boundingRect(pts)
    # Ink must be strictly in the upper region of the screen (Y < 600 px)
    assert y + h <= 600, f"Top placement ink spilt below Y=600: y+h={y + h}"
    # Bottom caption band (Y > 1200) must be 100% blank
    bottom_slice = img[1200:, :]
    assert cv2.countNonZero(bottom_slice) == 0, "Bottom caption band contained unexpected ink"


def test_parse_ass_colour_decodes_hex_to_rgb() -> None:
    assert DEFAULT_PLATE_COLOUR == "&H80000000"
    assert DEFAULT_PLATE_PADDING == 16.0
    assert MIN_LEGIBILITY_CONTRAST_RATIO == 4.5
    # ASS &HAABBGGRR
    assert parse_ass_colour("&H0000E5FF") == (255, 229, 0)  # Yellow
    assert parse_ass_colour("&H00FFFFFF") == (255, 255, 255)  # White
    assert parse_ass_colour("&H00000000") == (0, 0, 0)  # Black
    assert parse_ass_colour("&H80000000") == (0, 0, 0)  # 50% Black
    # 6-digit &HBBGGRR
    assert parse_ass_colour("&HFF0000") == (0, 0, 255)  # Blue


def test_relative_luminance_and_contrast_ratio_matches_wcag() -> None:
    lum_white = relative_luminance(255, 255, 255)
    lum_black = relative_luminance(0, 0, 0)
    assert lum_white == 1.0
    assert lum_black == 0.0

    # WCAG contrast between white and black is exactly 21:1
    cr_max = contrast_ratio(lum_white, lum_black)
    assert round(cr_max, 1) == 21.0

    # Contrast between white and light gray (lum ~ 0.58) is under 4.5:1 (illegible without plate)
    lum_light_gray = relative_luminance(200, 200, 200)
    cr_low = contrast_ratio(lum_white, lum_light_gray)
    assert cr_low < MIN_LEGIBILITY_CONTRAST_RATIO


def test_event_needs_plate_matches_temporal_overlap() -> None:
    intervals = ((1000, 2500), (4000, 5000))
    assert event_needs_plate(500, 900, intervals) is False
    assert event_needs_plate(1200, 2000, intervals) is True
    assert event_needs_plate(2400, 3000, intervals) is True
    assert event_needs_plate(2600, 3900, intervals) is False
    assert event_needs_plate(1000, 2000, None) is False


def test_build_ass_emits_kurdish_plate_style_for_plate_intervals() -> None:
    s1 = Sentence(words=words(("پلێت", 0, 1000)), complete=True)
    s2 = Sentence(words=words(("ئاسایی", 1000, 2000)), complete=True)

    plate_intervals = ((0, 1000),)
    ass_text = build_ass(
        (s1, s2),
        font_name="Noto Naskh Arabic",
        font_size=VIRAL_FONT_SIZE,
        theme=VIRAL_THEME,
        plate_intervals=plate_intervals,
    )

    assert "Style: KurdishPlate,Noto Naskh Arabic" in ass_text
    # border_style=3 and plate_colour &H80000000
    assert ",3,16,0," in ass_text

    dialogues = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    assert ",KurdishPlate," in dialogues[0]
    assert ",Kurdish," in dialogues[1]


def test_caption_plate_renders_dark_backing_on_white_background(tmp_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg binary not available")

    # Render a plate-backed caption over a pure white synthetic background
    s = Sentence(words=words(("تێکستی_پلێت", 0, 1000)), complete=True)
    ass_text = build_ass(
        (s,),
        font_name="Noto Naskh Arabic",
        font_size=VIRAL_FONT_SIZE,
        theme=VIRAL_THEME,
        plate_intervals=((0, 1000),),
    )
    ass_path = tmp_path / "plate.ass"
    ass_path.write_text(ass_text, encoding="utf-8")

    import subprocess

    vf = subtitle_filter(ass_path, FONTS_DIR)
    cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=white:s=1080x1920:d=1",
        "-vf",
        vf,
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    assert len(raw) == 1080 * 1920 * 3

    # Check that in the caption region (Y=1400..1600), pixels have been darkened by the plate
    import numpy as np

    arr = np.frombuffer(raw, dtype=np.uint8).reshape((1920, 1080, 3))
    caption_region = arr[1400:1600, 200:880]
    # On a pure white canvas without plate, all pixels are (255, 255, 255)
    # With plate, the backing box darkens the canvas to < 200
    darkened = np.sum((caption_region[:, :, 0] < 200) & (caption_region[:, :, 1] < 200))
    assert darkened > 5000, f"Expected darkened plate pixels behind text, got {darkened}"


def test_build_ass_with_speaker_metadata_and_turns() -> None:
    from hawedit.brand import SpeakerBio

    speaker_metadata = {
        "SPEAKER_00": SpeakerBio(name_ckb="د. ئاراس عومەر", title_ckb="پزیشکی پسپۆڕ"),
        "SPEAKER_01": SpeakerBio(name_ckb="هاوژین عەزیز"),
    }
    speaker_turns = (
        (0, 4_000, "SPEAKER_00"),
        (4_500, 7_000, "SPEAKER_01"),
        (7_500, 10_000, "SPEAKER_02"),  # Not in metadata
    )
    test_words = words(("سڵاو", 100, 500), ("هاوڕێیان", 600, 1200))
    sentence = Sentence(words=test_words, complete=True)

    ass_text = build_ass(
        sentences=[sentence],
        clip_in_ms=0,
        clip_duration_ms=12_000,
        speaker_turns=speaker_turns,
        speaker_metadata=speaker_metadata,
    )

    # Style row exists in header
    assert "Style: SpeakerTag," in ass_text

    # Events exist for SPEAKER_00 and SPEAKER_01, but NOT SPEAKER_02
    expected_spk0 = (
        "Dialogue: 2,0:00:00.00,0:00:03.50,SpeakerTag,,0,0,0,,"
        "{\\fad(250,250)}د. ئاراس عومەر\\N{\\fs28\\c&HCCCCCC&}پزیشکی پسپۆڕ"
    )
    expected_spk1 = (
        "Dialogue: 2,0:00:04.50,0:00:08.00,SpeakerTag,,0,0,0,,{\\fad(250,250)}هاوژین عەزیز"
    )
    assert expected_spk0 in ass_text
    assert expected_spk1 in ass_text
    assert "SPEAKER_02" not in ass_text


def test_compute_rtl_word_positions_strictly_right_to_left() -> None:
    """Words in a Kurdish phrase must have X positions strictly decreasing from right to left."""
    test_words = words(
        ("ڕۆژنامەوانی", 0, 800),
        ("کوردی", 800, 1700),
        ("لە", 1700, 2100),
        ("هەولێر", 2100, 3000),
    )
    positions = compute_rtl_word_positions(
        test_words,
        font_size=VIRAL_FONT_SIZE,
        canvas_width=1080,
    )
    assert len(positions) == 4
    x0, x1, x2, x3 = [pos[1] for pos in positions]
    assert x0 > x1 > x2 > x3, f"RTL invariant violated: X coords not decreasing: {positions}"
    assert 0 < x3 < 1080 and 0 < x0 < 1080, "Coordinates must fall inside canvas bounds"

    # Edge cases
    assert compute_rtl_word_positions([]) == []
    single = compute_rtl_word_positions([test_words[0]], canvas_width=1080)
    assert single == [(test_words[0], 540)]


def test_viral_popup_style_emits_bounce_tags_and_unbroken_text() -> None:
    """Viral popup captions emit dynamic scale bounce tags with unbroken Kurdish text."""
    test_words = words(("سڵاو", 100, 500), ("هاوڕێیان", 600, 1200))
    sentence = Sentence(words=test_words, complete=True)

    ass = build_ass((sentence,), style=CaptionStyle.VIRAL_POPUP, theme=VIRAL_THEME)

    assert r"{\t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)}" in ass
    assert "\\kf" not in ass, "Popups must not use \\kf tags which split HarfBuzz runs"
    assert "سڵاو هاوڕێیان" in ass, "Surface words must be joined cleanly without inline splits"


def test_rtl_word_highlight_emits_positioned_events_and_switches_styles() -> None:
    """RTL word highlight creates positioned words with active vs dim style alternation."""
    test_words = words(("سڵاو", 100, 500), ("هاوڕێیان", 500, 1200))
    sentence = Sentence(words=test_words, complete=True)

    ass = build_ass((sentence,), style=CaptionStyle.RTL_WORD_HIGHLIGHT, theme=VIRAL_THEME)

    assert "Style: KurdishDim," in ass, "Dim secondary style must be declared"
    assert "\\pos(" in ass, "Word positions must be explicitly positioned"

    # During first interval: word 0 is active (Kurdish) and word 1 is dim (KurdishDim)
    ev_w0_active = "Dialogue: 0,0:00:00.10,0:00:00.50,Kurdish,,0,0,0,,"
    ev_w1_dim = "Dialogue: 0,0:00:00.10,0:00:00.50,KurdishDim,,0,0,0,,"
    assert ev_w0_active in ass
    assert ev_w1_dim in ass

    # During second interval: word 1 is active and word 0 is dim
    ev_w0_dim = "Dialogue: 0,0:00:00.50,0:00:01.20,KurdishDim,,0,0,0,,"
    ev_w1_active = "Dialogue: 0,0:00:00.50,0:00:01.20,Kurdish,,0,0,0,,"
    assert ev_w0_dim in ass
    assert ev_w1_active in ass


def test_kurdish_two_word_chunk_preserves_source_rtl_order() -> None:
    """AC-9 / Item 12: Kurdish two-word phrases preserve source RTL order and position.

    Ensures that for a two-word Kurdish chunk ("کاک مەسعود", "برێمەر پۆڵ", "دەکەین دروست"):
    1. In RTL_WORD_HIGHLIGHT, the first word ("کاک") has a larger X coordinate than the
       second word ("مەسعود"), placing the first word on the screen's right side.
    2. In build_ass with RTL_WORD_HIGHLIGHT and VIRAL_POPUP, verify_caption_text passes
       with the exact expected reading order ["کاک", "مەسعود"].
    3. An inverted text ("مەسعود کاک") is strictly rejected by verify_caption_text.
    """
    phrase_words = words(("کاک", 100, 400), ("مەسعود", 400, 900))
    sentence = Sentence(words=phrase_words, complete=True)

    # 1. RTL positions: word 0 ("کاک") must be further right (higher X) than word 1 ("مەسعود")
    positions = compute_rtl_word_positions(phrase_words, canvas_width=1080)
    assert len(positions) == 2
    (w0, x0), (w1, x1) = positions
    assert w0.w == "کاک" and w1.w == "مەسعود"
    assert x0 > x1, f"Expected X(کاک) > X(مەسعود) for RTL reading, got {x0} <= {x1}"

    # 2. build_ass with VIRAL_POPUP emits exact reading order
    ass_popup = build_ass((sentence,), style=CaptionStyle.VIRAL_POPUP, theme=VIRAL_THEME)
    verify_caption_text(ass_popup, expected_text=["کاک", "مەسعود"])

    # 3. build_ass with RTL_WORD_HIGHLIGHT emits slices where both words appear in reading order
    ass_rtl = build_ass((sentence,), style=CaptionStyle.RTL_WORD_HIGHLIGHT, theme=VIRAL_THEME)
    verify_caption_text(ass_rtl, expected_text=["کاک", "مەسعود", "کاک", "مەسعود"])

    # 4. Inverted text is rejected
    with pytest.raises(CaptionVerificationError, match="wrong text"):
        verify_caption_text(ass_popup, expected_text=["مەسعود", "کاک"])


def test_classify_kurdish_emphasis_identifies_numbers() -> None:
    """Numbers in digits, Eastern Arabic numerals, and Kurdish words return NUMERIC."""
    for token in ("100", "2026", "١٠", "٥۰۰", "دوو", "سێ", "ملیۆن", "هەزار", "هەموو"):
        assert classify_kurdish_emphasis(token) is EmphasisCategory.NUMERIC, f"Failed for {token}"


def test_classify_kurdish_emphasis_identifies_entities() -> None:
    """Proper names, locations, and high-profile entities return ENTITY."""
    for token in ("کوردستان", "عێراق", "ئەمریکا", "پێشمەرگە", "بەغدا", "پۆڵ", "برێمەر"):
        assert classify_kurdish_emphasis(token) is EmphasisCategory.ENTITY, f"Failed for {token}"


def test_classify_kurdish_emphasis_identifies_action_alerts() -> None:
    """Negations, extreme claims, and crisis words return ACTION_ALERT."""
    for token in ("هەرگیز", "نەخێر", "مەترسی", "مەحاڵە", "کارەسات", "ڕاستەوخۆ"):
        assert classify_kurdish_emphasis(token) is EmphasisCategory.ACTION_ALERT, (
            f"Failed for {token}"
        )


def test_classify_kurdish_emphasis_defaults_to_neutral() -> None:
    """Common verbs, nouns, and function words return DEFAULT."""
    for token in ("سڵاو", "کتێب", "ڕۆژ", "باشە", "کە", "لە", "بە", ""):
        assert classify_kurdish_emphasis(token) is EmphasisCategory.DEFAULT, f"Failed for {token}"


def test_build_ass_keyword_emphasis_viral_popup() -> None:
    """Viral popup styles chunks according to keyword emphasis category."""
    # 1. Entity word chunk -> KurdishCyan
    ent_sentence = Sentence(words=words(("پێشمەرگە", 100, 500)), complete=True)
    ass_ent = build_ass((ent_sentence,), style=CaptionStyle.VIRAL_POPUP, theme=VIRAL_THEME)
    assert "Style: KurdishCyan," in ass_ent
    assert ",KurdishCyan,,0,0,0,," in ass_ent

    # 2. Number word chunk -> KurdishEmerald
    num_sentence = Sentence(words=words(("ملیۆن", 100, 500)), complete=True)
    ass_num = build_ass((num_sentence,), style=CaptionStyle.VIRAL_POPUP, theme=VIRAL_THEME)
    assert "Style: KurdishEmerald," in ass_num
    assert ",KurdishEmerald,,0,0,0,," in ass_num

    # 3. Action/Alert word chunk -> KurdishCoral
    alert_sentence = Sentence(words=words(("هەرگیز", 100, 500)), complete=True)
    ass_alert = build_ass((alert_sentence,), style=CaptionStyle.VIRAL_POPUP, theme=VIRAL_THEME)
    assert "Style: KurdishCoral," in ass_alert
    assert ",KurdishCoral,,0,0,0,," in ass_alert


def test_build_ass_keyword_emphasis_rtl_word_highlight() -> None:
    """RTL word highlight applies category style to active word dynamically."""
    test_words = words(("پێشمەرگە", 100, 500), ("هاتن", 500, 1000))
    sentence = Sentence(words=test_words, complete=True)

    ass = build_ass((sentence,), style=CaptionStyle.RTL_WORD_HIGHLIGHT, theme=VIRAL_THEME)

    # Word 0 (پێشمەرگە) is ENTITY -> active event uses KurdishCyan
    ev_w0_active = "Dialogue: 0,0:00:00.10,0:00:00.50,KurdishCyan,,0,0,0,,"
    # Word 1 (هاتن) is DEFAULT -> active event uses Kurdish
    ev_w1_active = "Dialogue: 0,0:00:00.50,0:00:01.00,Kurdish,,0,0,0,,"

    assert ev_w0_active in ass
    assert ev_w1_active in ass


def test_build_ass_disabled_keyword_emphasis_retains_standard_styles() -> None:
    """When keyword_emphasis=False, all active words use standard Kurdish style."""
    ent_sentence = Sentence(words=words(("پێشمەرگە", 100, 500)), complete=True)
    ass = build_ass(
        (ent_sentence,),
        style=CaptionStyle.VIRAL_POPUP,
        theme=VIRAL_THEME,
        keyword_emphasis=False,
    )
    assert "Style: KurdishCyan," not in ass
    assert ",Kurdish,,0,0,0,," in ass


def test_caption_verification_detects_wrong_text_and_broken_joining() -> None:
    """AC-06: Verification detects wrong text and broken cursive joining in Sorani."""
    style_fmt = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Kurdish,Noto Naskh Arabic,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,3.0,1.0,2,40,40,200,1\n"
    )
    valid_ass = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        f"{style_fmt}\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Kurdish,,0,0,0,,سڵاو لە هەمووان\n"
    )

    # 1. Valid Kurdish caption text passes
    verify_caption_text(valid_ass, expected_text=["سڵاو", "لە", "هەمووان"])

    # 2. Wrong text: expected words do not match dialogue text
    with pytest.raises(CaptionVerificationError, match="wrong text"):
        verify_caption_text(valid_ass, expected_text=["دەقی", "هەڵە", "جیاواز"])

    # 3. Broken joining: Arabic presentation form characters
    broken_presentation = valid_ass.replace("سڵاو", "\ufe8e\ufe8f")
    with pytest.raises(CaptionVerificationError, match="broken joining.*presentation form"):
        verify_caption_text(broken_presentation)

    # 4. Broken joining: disconnected letters separated by spaces
    broken_spaced = valid_ass.replace("سڵاو", "س ڵ ا و")
    with pytest.raises(CaptionVerificationError, match="broken joining.*disconnected letters"):
        verify_caption_text(broken_spaced)

    # 5. Broken joining: orphan tatweel at word boundary
    broken_tatweel = valid_ass.replace("سڵاو", "ـسڵاو")
    with pytest.raises(CaptionVerificationError, match="broken joining.*orphan tatweel"):
        verify_caption_text(broken_tatweel)


def test_caption_verification_rejects_missing_glyphs_and_unsafe_geometry() -> None:
    """AC-06: Verification rejects missing glyphs, unsafe placement, and illegible geometry."""
    style_fmt = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Kurdish,Noto Naskh Arabic,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,3.0,1.0,2,40,40,200,1\n"
    )
    base_ass = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        f"{style_fmt}\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Kurdish,,0,0,0,,دەقی ڕاستەقینە بۆ تاقیکردنەوە\n"
    )

    # 1. Valid geometry and glyphs pass
    verify_caption_geometry(base_ass)
    verify_caption_glyphs(base_ass)
    report = verify_caption_integrity(base_ass)
    assert report.text_ok and report.joining_ok and report.glyphs_ok and report.geometry_ok

    # 2. Missing glyphs: text contains unsupported / exotic non-Kurdish character
    unsupported_char_ass = base_ass.replace("دەقی", "دەقی\u0416")  # Cyrillic Zhe
    with pytest.raises(CaptionVerificationError, match="missing glyphs"):
        verify_caption_glyphs(unsupported_char_ass)

    # 3. Unsafe placement: coordinates outside frame (\pos out of screen)
    offscreen_ass = base_ass.replace("دەقی", r"{\pos(-150,2500)}دەقی")
    with pytest.raises(CaptionVerificationError, match="unsafe placement"):
        verify_caption_geometry(offscreen_ass)

    # 4. Unsafe placement: vertical margin too small (dangerously close to screen edge)
    unsafe_margin_ass = base_ass.replace("2,40,40,200,1", "2,40,40,15,1")
    with pytest.raises(CaptionVerificationError, match="unsafe placement.*margin"):
        verify_caption_geometry(unsafe_margin_ass)

    # 5. Illegible geometry: font size too small for mobile reading
    tiny_font_ass = base_ass.replace("Noto Naskh Arabic,48,", "Noto Naskh Arabic,14,")
    with pytest.raises(CaptionVerificationError, match="illegible.*geometry.*font size"):
        verify_caption_geometry(tiny_font_ass)

    # 6. Illegible geometry: line exceeds maximum character length without wrap
    long_kurdish = (
        "ئەمە دێڕێکی زۆر زۆر درێژە کە بەهیچ شێوەیەک "
        "جێگەی نابێتەوە لەسەر شاشەی مۆبایل و دەبێتە هۆی شێواندنی دەق"
    )
    long_line_ass = base_ass.replace("دەقی", long_kurdish)
    with pytest.raises(CaptionVerificationError, match="illegible.*geometry.*line exceeds"):
        verify_caption_geometry(long_line_ass)


def test_caption_chunks_preserve_source_word_order(tmp_path: Path) -> None:
    """Item B7: Captions in source order across Kurdish dialogue transcript (ep29).

    Asserts that:
    1. chunk_caption_events preserves the exact chronological word sequence of
       forced-alignment source tokens across multi-sentence dialogue.
    2. compute_rtl_word_positions enforces strictly decreasing X coordinates
       (X(w_0) > X(w_1) > ... > X(w_{k-1})) so that earlier words are always
       positioned to the right of later words in native RTL reading order.
    3. Critical two-word Kurdish phrases ("کاک مەسعود", "پۆڵ برێمەر", "دروست دەکەین")
       never suffer Left-to-Right run inversion on screen.
    4. verify_caption_text passes on correctly ordered dialogue and raises
       CaptionVerificationError on inverted word pairs.
    5. Golden pixel render of "کاک مەسعود" through FFmpeg/libass verifies that
       the horizontal pixel centroid of "کاک" is strictly greater than "مەسعود".
    """
    # 1. Ep29 dialogue sentence sequence
    ep29_sentences = (
        Sentence(
            words=words(
                ("ئەمڕۆ", 418, 841),
                ("لە", 841, 1103),
                ("پۆدکاستی", 1103, 1264),
                ("تایبەت", 1264, 1667),
                ("بە", 1667, 1748),
                ("خۆمان", 1748, 1788),
                ("قسە", 1788, 2150),
                ("دەکەین", 2150, 2654),
            ),
            complete=True,
        ),
        Sentence(
            words=words(
                ("کاتێک", 3000, 3400),
                ("پۆڵ", 3400, 3800),
                ("برێمەر", 3800, 4300),
                ("هاتە", 4300, 4700),
                ("کوردستان", 4700, 5400),
                ("کاک", 5400, 5800),
                ("مەسعود", 5800, 6400),
                ("قبوڵی", 6400, 6900),
                ("نەکرد", 6900, 7500),
            ),
            complete=True,
        ),
        Sentence(
            words=words(
                ("ئێمە", 8000, 8400),
                ("عێراقی", 8400, 8900),
                ("نوێ", 8900, 9300),
                ("دروست", 9300, 9800),
                ("دەکەین", 9800, 10300),
                ("بەڵام", 10300, 10700),
                ("بە", 10700, 11000),
                ("مەرج", 11000, 11600),
            ),
            complete=True,
        ),
    )

    # 2. Sequence order and geometric RTL monotonicity across all chunks
    for s in ep29_sentences:
        for max_w in (2, 3):
            chunks = chunk_caption_events(s.words, max_words=max_w)
            # Flattened words must match source words exactly
            flattened = [w for chunk in chunks for w in chunk]
            assert [w.w for w in flattened] == [w.w for w in s.words]
            assert [w.start_ms for w in flattened] == [w.start_ms for w in s.words]

            # For every chunk, verify strict RTL position ordering
            for chunk in chunks:
                if len(chunk) > 1:
                    positions = compute_rtl_word_positions(chunk, canvas_width=1080)
                    assert len(positions) == len(chunk)
                    for i in range(len(positions) - 1):
                        w_curr, x_curr = positions[i]
                        w_next, x_next = positions[i + 1]
                        assert x_curr > x_next, (
                            f"RTL inversion detected: word {w_curr.w!r} at X={x_curr} "
                            f"must be > word {w_next.w!r} at X={x_next}"
                        )

    # 3. Explicit check for the key two-word pairs from Zar #29
    kak_masud = words(("کاک", 5400, 5800), ("مەسعود", 5800, 6400))
    pos_km = compute_rtl_word_positions(kak_masud, canvas_width=1080)
    assert pos_km[0][1] > pos_km[1][1], "کاک must have higher X than مەسعود"

    paul_bremer = words(("پۆڵ", 3400, 3800), ("برێمەر", 3800, 4300))
    pos_pb = compute_rtl_word_positions(paul_bremer, canvas_width=1080)
    assert pos_pb[0][1] > pos_pb[1][1], "پۆڵ must have higher X than برێمەر"

    drust_dakeyn = words(("دروست", 9300, 9800), ("دەکەین", 9800, 10300))
    pos_dd = compute_rtl_word_positions(drust_dakeyn, canvas_width=1080)
    assert pos_dd[0][1] > pos_dd[1][1], "دروست must have higher X than دەکەین"

    # 4. verify_caption_text passes on valid order and refuses inversions
    all_source_tokens = [w.w for s in ep29_sentences for w in s.words]
    ass_viral = build_ass(ep29_sentences, style=CaptionStyle.VIRAL_POPUP, theme=VIRAL_THEME)
    verify_caption_text(ass_viral, expected_text=all_source_tokens)

    # Inverted tokens (e.g. replacing کاک مەسعود with مەسعود کاک) must fail
    inverted_tokens = list(all_source_tokens)
    idx_kak = inverted_tokens.index("کاک")
    inverted_tokens[idx_kak], inverted_tokens[idx_kak + 1] = (
        inverted_tokens[idx_kak + 1],
        inverted_tokens[idx_kak],
    )
    with pytest.raises(CaptionVerificationError, match="wrong text"):
        verify_caption_text(ass_viral, expected_text=inverted_tokens)

    # 5. Golden pixel render centroid verification
    ffmpeg = find_ffmpeg()
    if ffmpeg is not None:
        import cv2
        import numpy as np

        test_sentence = Sentence(
            words=words(("کاک", 0, 400), ("مەسعود", 400, 900)),
            complete=True,
        )
        ass_path = tmp_path / "caption_source_order.ass"
        ass_path.write_text(
            build_ass(
                (test_sentence,),
                style=CaptionStyle.VIRAL_POPUP,
                theme=VIRAL_THEME,
                fonts_dir=FONTS_DIR,
            ),
            encoding="utf-8",
        )
        out_png = tmp_path / "caption_source_order.png"
        render_caption_png(ffmpeg, ass_path, FONTS_DIR, out_png)
        assert out_png.is_file(), "Rendered caption PNG must exist"

        img = cv2.imread(str(out_png))
        assert img is not None, "Failed to load rendered caption PNG"
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = gray > 30
        assert np.any(mask), "Rendered caption must produce visible ink"

        _, x_coords = np.where(mask)
        # In a 1080-wide frame, centered text occupies X ~ 420..660
        # Right cluster (X > 570) is "کاک"; left cluster (X < 570) is "مەسعود"
        right_cluster = x_coords[x_coords > 570]
        left_cluster = x_coords[x_coords < 570]
        assert len(right_cluster) > 0 and len(left_cluster) > 0

        cx_kak = float(np.mean(right_cluster))
        cx_masud = float(np.mean(left_cluster))
        assert cx_kak > cx_masud, (
            f"Expected horizontal pixel centroid of 'کاک' ({cx_kak:.1f}) > "
            f"'مەسعود' ({cx_masud:.1f}) for native Kurdish RTL display"
        )
