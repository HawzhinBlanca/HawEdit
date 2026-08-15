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

import unicodedata
from pathlib import Path

import pytest

from hawedit.captions import (
    DEFAULT_MAX_CHARS_PER_LINE,
    GOLDEN_CAPTION_TEXT,
    KURDISH_REQUIRED_GLYPHS,
    CaptionsOutsideClip,
    CaptionStyle,
    FontCoverageError,
    GoldenReferenceMissing,
    MissingRtlStack,
    assert_ass_fonts_cover_kurdish,
    assert_captions_within_clip,
    assert_font_covers_kurdish,
    assert_fonts_dir_covers_kurdish,
    assert_rtl_stack,
    build_ass,
    compare_golden_render,
    decode_to_rgb,
    find_ffmpeg,
    parse_dialogue_times,
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
