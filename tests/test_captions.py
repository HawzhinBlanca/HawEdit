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

from pathlib import Path

import pytest

from hawedit.captions import (
    DEFAULT_MAX_CHARS_PER_LINE,
    GOLDEN_CAPTION_TEXT,
    KURDISH_REQUIRED_GLYPHS,
    CaptionStyle,
    FontCoverageError,
    GoldenReferenceMissing,
    MissingRtlStack,
    assert_font_covers_kurdish,
    assert_rtl_stack,
    build_ass,
    compare_golden_render,
    decode_to_rgb,
    find_ffmpeg,
    render_caption_png,
    subtitle_filter,
    wrap_caption_lines,
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

GOLDEN = Path(__file__).resolve().parent / "golden" / "kurdish-caption.png"
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
