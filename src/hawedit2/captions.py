"""§4.3 RTL caption rendering — Kurdish invariant #4.

§0 lists this as failure mode #3, with the sharpest warning in the blueprint: "FFmpeg's
default shaping engine breaks Arabic-script text. You will not catch it in code review — you
will catch it when a client sees the burned-in captions."

Everything here follows from that. The option flag is necessary and **not sufficient**:

* `shaping=complex` is always emitted, never left to `auto` (§4.3.1).
* The stack is verified at deploy time from **two** sources — `ffmpeg -buildconf` and the
  linked libraries — because §4.3.2 warns that "a package that accepts the option may still
  lack the backing library", and a distro can link HarfBuzz into libass without an ffmpeg
  configure flag naming it.
* Captions go through `ass`/`subtitles`, never `drawtext` (§4.3.3).
* The font is referenced by directory, not resolved through fontconfig on the render host,
  and its Kurdish coverage is asserted rather than assumed (§4.3.4).
* Line breaks are ours, computed from the word alignment, and `WrapStyle: 2` turns libass's
  own wrapping off entirely (§4.3.5). Automatic wrapping on RTL text produces bad break
  points regardless of engine.
* The golden-file comparison exists because §4.3.6 says so plainly: "Shaping regressions
  arrive silently through ffmpeg or libass updates and are invisible in code review. This is
  the real safeguard — the option flag is not."

Caption text is the **raw** surface forms. Normalized text is for the index (invariant #3);
a viewer must see what was said, spelled as the speaker's transcript spells it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from hawedit2.sentences import Sentence
from hawedit2.transcripts import Word

__all__ = [
    "DEFAULT_MAX_CHARS_PER_LINE",
    "GOLDEN_CAPTION_TEXT",
    "KURDISH_REQUIRED_GLYPHS",
    "CaptionStyle",
    "FontCoverageError",
    "GoldenReferenceMissing",
    "MissingRtlStack",
    "RtlStackReport",
    "assert_font_covers_kurdish",
    "assert_rtl_stack",
    "build_ass",
    "compare_golden_render",
    "decode_to_rgb",
    "find_ffmpeg",
    "render_caption_png",
    "subtitle_filter",
    "wrap_caption_lines",
]

# §4.3.4's list, plus the two heh forms. `ھ` U+06BE is not in §4.3's list but appears in
# ordinary Kurdish words — measured at 204 entries in the real lexicon (D-013) — and a font
# missing it renders boxes in words like دھۆک.
KURDISH_REQUIRED_GLYPHS: Final[frozenset[str]] = frozenset("ڕڵۆێچژپگە" + "هھ")

# Caption line width. Long RTL lines are hard to read on a vertical crop; this is a
# reporting default, adjustable per output format.
DEFAULT_MAX_CHARS_PER_LINE: Final = 32

_ASS_OVERRIDE = re.compile(r"[{}]")

# The fixed Kurdish line §4.3.6's golden render uses. Chosen to exercise the joining
# behaviour that `shaping=simple` gets wrong — `لە` and the initial form of `هەولێر` — plus
# ڕ ۆ ژ ە ی from §4.3.4's required set.
GOLDEN_CAPTION_TEXT: Final = "ڕۆژنامەوانی کوردی لە هەولێر."


class MissingRtlStack(RuntimeError):
    """Raised when the render host cannot shape Arabic script correctly."""


class FontCoverageError(RuntimeError):
    """Raised when a font lacks glyphs Kurdish captions need."""


class GoldenReferenceMissing(RuntimeError):
    """Raised when the golden reference render is absent — the safeguard is not optional."""


class CaptionStyle(Enum):
    """§5's `output.caption_style`."""

    LINE = "line"
    WORD_HIGHLIGHT = "word_highlight"


@dataclass(frozen=True, slots=True)
class RtlStackReport:
    """What the deploy-time check found, and where."""

    libass: bool
    harfbuzz: bool
    fribidi: bool
    harfbuzz_source: str | None = None
    fribidi_source: str | None = None


def assert_rtl_stack(buildconf: str, linked_libraries: str = "") -> RtlStackReport:
    """Verify ffmpeg can shape Arabic script, from build flags and linked libraries.

    Mirrors the two commands in §4.3.2 and the Appendix: `ffmpeg -hide_banner -buildconf`
    and `ldd $(which ffmpeg)`. Either source satisfies HarfBuzz and FriBidi, because a
    distro build can link them through libass without naming them in its configure line —
    but libass itself must appear in the build configuration.

    Raises:
        MissingRtlStack: any of libass, HarfBuzz or FriBidi is absent. The message names
            which, because "the RTL stack is broken" is not actionable at 2am.
    """
    haystack_build = buildconf.lower()
    haystack_linked = linked_libraries.lower()

    def find(*needles: str) -> str | None:
        if any(needle in haystack_build for needle in needles):
            return "buildconf"
        if any(needle in haystack_linked for needle in needles):
            return "linked libraries"
        return None

    libass_source = find("libass")
    harfbuzz_source = find("harfbuzz")
    fribidi_source = find("fribidi")

    missing: list[str] = []
    if libass_source is None:
        missing.append("libass (the ass/subtitles filters are the supported caption route)")
    if harfbuzz_source is None:
        missing.append("HarfBuzz (shaping=complex requires libass built with it)")
    if fribidi_source is None:
        missing.append("FriBidi (bidirectional reordering of Arabic script)")

    if missing:
        raise MissingRtlStack(
            "this ffmpeg cannot render Kurdish captions correctly — missing: "
            + "; ".join(missing)
            + ". §4.3: a build that accepts shaping=complex may still lack the backing "
            "library, and the failure is invisible until a client sees the burned-in text."
        )

    return RtlStackReport(
        libass=True,
        harfbuzz=True,
        fribidi=True,
        harfbuzz_source=harfbuzz_source,
        fribidi_source=fribidi_source,
    )


def assert_font_covers_kurdish(
    font_path: Path,
    required: frozenset[str] = KURDISH_REQUIRED_GLYPHS,
) -> None:
    """Verify a font has a glyph for every character Kurdish captions need.

    §4.3.4: "Missing glyphs render as boxes." A box in a burned-in caption cannot be fixed
    after delivery, so this runs at build time rather than being trusted.

    Raises:
        FileNotFoundError: no font at `font_path`.
        FontCoverageError: one or more required characters have no glyph.
    """
    if not font_path.exists():
        raise FileNotFoundError(f"no font at {font_path}")

    from fontTools.ttLib import TTFont  # imported lazily: only the render path needs it

    cmap = TTFont(font_path).getBestCmap()
    missing = sorted(char for char in required if ord(char) not in cmap)
    if missing:
        raise FontCoverageError(
            f"{font_path.name} has no glyph for {' '.join(missing)} "
            f"(U+{' U+'.join(f'{ord(c):04X}' for c in missing)}). These render as boxes in "
            f"burned-in captions — §4.3.4."
        )


def _escape_filter_path(path: Path) -> str:
    """Escape a path for an ffmpeg filtergraph argument.

    An unescaped `:` silently truncates the argument and the filter then renders with
    default options — including `shaping=auto`, which is the exact failure §4.3 is about.
    """
    escaped = str(path).replace("\\", "\\\\")
    for character in (":", "'", "[", "]", ","):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def subtitle_filter(ass_path: Path, fonts_dir: Path) -> str:
    """The ffmpeg filter string for burning in Kurdish captions.

    Always `ass=…:shaping=complex:fontsdir=…` — never `drawtext` (§4.3.3), and never
    relying on `shaping=auto` (§4.3.1) or on fontconfig resolving the font (§4.3.4).
    """
    return (
        f"ass={_escape_filter_path(ass_path)}"
        f":shaping=complex"
        f":fontsdir={_escape_filter_path(fonts_dir)}"
    )


def wrap_caption_lines(
    words: Sequence[Word],
    max_chars: int = DEFAULT_MAX_CHARS_PER_LINE,
) -> tuple[tuple[Word, ...], ...]:
    """Break a caption into lines at word boundaries from the alignment.

    §4.3.5: "Insert line breaks yourself from the word alignment." A word longer than
    `max_chars` gets its own line rather than being dropped or split — a missing word in a
    caption is worse than a long line, and splitting Arabic-script mid-word breaks shaping.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")

    lines: list[tuple[Word, ...]] = []
    current: list[Word] = []
    width = 0
    for word in words:
        addition = len(word.w) + (1 if current else 0)
        if current and width + addition > max_chars:
            lines.append(tuple(current))
            current, width = [word], len(word.w)
        else:
            current.append(word)
            width += addition
    if current:
        lines.append(tuple(current))
    return tuple(lines)


def _ass_time(milliseconds: int) -> str:
    """ASS timestamps are H:MM:SS.cc — centiseconds, not milliseconds."""
    centiseconds = milliseconds // 10
    seconds, centiseconds = divmod(centiseconds, 100)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _escape_ass_text(text: str) -> str:
    """Neutralise ASS override braces so transcript text is never read as markup."""
    return _ASS_OVERRIDE.sub("", text)


def build_ass(
    sentences: Sequence[Sentence],
    font_name: str = "Noto Naskh Arabic",
    font_size: int = 64,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    style: CaptionStyle = CaptionStyle.LINE,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
) -> str:
    """Generate an ASS subtitle file for a clip's sentences.

    `WrapStyle: 2` disables libass's own wrapping entirely: breaks happen only where this
    module puts a `\\N`, computed from the word alignment (§4.3.5).

    `WORD_HIGHLIGHT` emits karaoke (`\\kf`) durations straight from §4.2's word timings —
    which is the whole reason forced alignment is a hard requirement rather than a nicety.

    Text is the **raw** surface forms: a viewer sees what was said, not the index's
    normalized form.

    Raises:
        ValueError: no sentences, or a sentence that never closed (invariant #2 — a
            fragment is rejected, never rendered).
    """
    if not sentences:
        raise ValueError("no sentences to caption")
    for sentence in sentences:
        if not sentence.complete:
            raise ValueError(
                f"sentence at {sentence.start_ms} ms is not complete — reject, never render "
                f"(Kurdish invariant #2). Captioning a fragment ships a broken clip."
            )

    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            # 2 = no automatic wrapping; line breaks only where we put \N (§4.3.5).
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Kurdish,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,"
            "&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,140,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )

    events: list[str] = []
    for sentence in sentences:
        lines = wrap_caption_lines(sentence.words, max_chars=max_chars_per_line)
        if style is CaptionStyle.WORD_HIGHLIGHT:
            rendered_lines = [
                "".join(
                    f"{{\\kf{max(1, (word.end_ms - word.start_ms) // 10)}}}"
                    f"{_escape_ass_text(word.w)} "
                    for word in line
                ).strip()
                for line in lines
            ]
        else:
            rendered_lines = [" ".join(_escape_ass_text(word.w) for word in line) for line in lines]
        text = "\\N".join(rendered_lines)
        events.append(
            f"Dialogue: 0,{_ass_time(sentence.start_ms)},{_ass_time(sentence.end_ms)},"
            f"Kurdish,,0,0,0,,{text}"
        )

    return header + "\n" + "\n".join(events) + "\n"


def find_ffmpeg() -> Path | None:
    """Locate an ffmpeg binary: `HAWEDIT2_FFMPEG`, then `.ffmpeg/`, then `PATH`.

    Returns `None` rather than raising — the caller decides whether a missing ffmpeg is a
    skipped render test or a failed deploy check.
    """
    from os import environ
    from shutil import which

    configured = environ.get("HAWEDIT2_FFMPEG")
    if configured and Path(configured).exists():
        return Path(configured)
    # Where scripts/fetch-ffmpeg.sh puts it, so the readiness report and the gate agree
    # without anyone having to remember an environment variable.
    vendored = Path(__file__).resolve().parents[2] / ".ffmpeg" / "ffmpeg"
    if vendored.exists():
        return vendored
    located = which("ffmpeg")
    return Path(located) if located else None


def render_caption_png(
    ffmpeg: Path,
    ass_path: Path,
    fonts_dir: Path,
    output: Path,
    width: int = 1080,
    height: int = 1920,
    shaping: str = "complex",
) -> Path:
    """Burn one caption frame onto a black background — the §4.3.6 golden render.

    `width`/`height` must match the ASS `PlayResX`/`PlayResY`, or libass scales the text and
    the comparison measures the scaling rather than the shaping.

    `shaping` is a parameter only so a test can render the **wrong** way and prove the right
    way differs. Production always goes through `subtitle_filter`, which hard-codes `complex`.
    """
    import subprocess

    filter_string = (
        f"ass={_escape_filter_path(ass_path)}"
        f":shaping={shaping}"
        f":fontsdir={_escape_filter_path(fonts_dir)}"
    )
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:d=1",
            "-vf",
            filter_string,
            "-frames:v",
            "1",
            "-y",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    return output


def decode_to_rgb(ffmpeg: Path, image: Path) -> bytes:
    """Decode an image to raw RGB24 pixels.

    The golden comparison runs on pixels, not on file bytes: PNG encoders differ between
    ffmpeg and zlib versions, so a byte comparison would fail on an encoder upgrade that
    changed nothing a viewer can see — and a golden test that cries wolf gets disabled.
    """
    import subprocess

    result = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(image),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return result.stdout


def compare_golden_render(reference: Path, candidate: Path, ffmpeg: Path | None = None) -> None:
    """§4.3.6's golden-file test: compare a rendered Kurdish caption to a fixed reference.

    §4.3.6 is explicit that this — not the option flag — is the real safeguard: "Shaping
    regressions arrive silently through ffmpeg or libass updates and are invisible in code
    review."

    When `ffmpeg` is supplied the comparison runs on decoded pixels rather than file bytes,
    so a PNG-encoder change cannot fail a render that looks identical.

    Raises:
        GoldenReferenceMissing: the reference is absent. Passing silently would make the
            safeguard decorative, which is the failure mode §4.3.6 is guarding against.
        AssertionError: the render differs from the reference.
    """
    if not reference.exists():
        raise GoldenReferenceMissing(
            f"no golden reference at {reference}. Generate it on a build whose libass is "
            f"verified to have HarfBuzz and FriBidi (assert_rtl_stack) — a reference "
            f"produced by a broken build enshrines the bug it is meant to catch."
        )
    if not candidate.exists():
        raise AssertionError(f"no candidate render at {candidate}")

    if ffmpeg is not None:
        reference_bytes = decode_to_rgb(ffmpeg, reference)
        candidate_bytes = decode_to_rgb(ffmpeg, candidate)
    else:
        reference_bytes = reference.read_bytes()
        candidate_bytes = candidate.read_bytes()
    if reference_bytes != candidate_bytes:
        raise AssertionError(
            f"rendered caption differs from the golden reference "
            f"({len(candidate_bytes)} bytes vs {len(reference_bytes)}). Either the shaping "
            f"stack changed or the caption did. §4.3.6: shaping regressions are invisible in "
            f"code review — investigate before regenerating the reference."
        )
