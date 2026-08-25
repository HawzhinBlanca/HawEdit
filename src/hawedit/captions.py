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
* Every used ASS font family is bound to one font inside the supplied directory, and that
  exact font's Kurdish coverage is asserted rather than assumed (§4.3.4).
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

from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.transcripts import Word

__all__ = [
    "DEFAULT_MAX_CHARS_PER_LINE",
    "GOLDEN_CAPTION_TEXT",
    "KURDISH_REQUIRED_GLYPHS",
    "POPUP_MAX_CHARS",
    "POPUP_MAX_GAP_MS",
    "POPUP_MAX_MS",
    "POPUP_MAX_WORDS",
    "REPORT_THEME",
    "VIRAL_FONT_SIZE",
    "VIRAL_THEME",
    "CaptionStyle",
    "CaptionTheme",
    "CaptionsOutsideClip",
    "FontCoverageError",
    "GoldenReferenceMissing",
    "MissingRtlStack",
    "RtlStackReport",
    "assert_ass_fonts_cover_kurdish",
    "assert_captions_within_clip",
    "assert_font_covers_kurdish",
    "assert_fonts_dir_covers_kurdish",
    "assert_rtl_stack",
    "build_ass",
    "chunk_caption_events",
    "compare_golden_render",
    "decode_to_rgb",
    "find_ffmpeg",
    "parse_dialogue_times",
    "render_caption_png",
    "subtitle_filter",
    "wrap_caption_lines",
]

# §4.3.4's list, the two heh forms, and the two letters §4.1 normalizes Arabic `ك`/`ي`
# into. A font can contain Arabic kaf/yeh and still lack Kurdish `ک` U+06A9 / `ی` U+06CC;
# measured, libass then split `کوردی` across fallback fonts (D-163).
KURDISH_REQUIRED_GLYPHS: Final[frozenset[str]] = frozenset("ڕڵۆێچژپگە" + "هھ" + "کی")

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


# One popup holds a breath, not a paragraph. A vertical crop shows ~22 Kurdish characters at
# the sizes §4.3 renders, and a caption that outlives its own words is a wall of text the
# viewer reads ahead of the audio — the failure that made every earlier run of this pipeline
# unusable for social delivery even though every timestamp in it was correct.
POPUP_MAX_WORDS: Final = 3
POPUP_MAX_CHARS: Final = 22
POPUP_MAX_MS: Final = 2_000
# A pause inside one popup leaves it on screen with nothing being said. Break there instead:
# the alignment already knows where the speaker stopped.
POPUP_MAX_GAP_MS: Final = 400

# Below this, two consecutive popups are held together rather than blinked apart. Measured
# against the real 25 fps fixture: a 3-frame hole reads as a flicker, not as a beat.
_POPUP_HOLD_MS: Final = 600


@dataclass(frozen=True, slots=True)
class CaptionTheme:
    """The V4+ style row's visual fields, which are chosen together and only together.

    Separated from `font_name`/`font_size` because those two were already parameters and a
    value with two sources is a value nobody can predict.

    **`primary` and `secondary` are not "the colour" and "the other colour".** ASS karaoke
    starts text in `secondary` and switches it to `primary` as each ``\\kf`` span elapses,
    for a highlight that follows the voice, `primary` is the *spoken* colour. The reporting
    default below has them the other way round — white primary, yellow secondary — which
    renders unspoken words yellow and spoken words white: a highlight that runs ahead of the
    speaker. Correct for a subtitle track being proofread, wrong for anything shipped.
    """

    primary: str = "&H00FFFFFF"
    secondary: str = "&H0000FFFF"
    outline_colour: str = "&H00000000"
    back_colour: str = "&H80000000"
    bold: bool = False
    outline: float = 3.0
    shadow: float = 1.0
    margin_l: int = 60
    margin_r: int = 60
    margin_v: int = 140

    def style_row(self, name: str, font_name: str, font_size: int) -> str:
        """One `Style:` line. `%g` keeps `3.0` as `3` so existing goldens still match."""
        return (
            f"Style: {name},{font_name},{font_size},{self.primary},{self.secondary},"
            f"{self.outline_colour},{self.back_colour},{int(self.bold)},0,0,0,100,100,0,0,1,"
            f"{self.outline:g},{self.shadow:g},2,{self.margin_l},{self.margin_r},"
            f"{self.margin_v},1"
        )


# What §4.3 has always emitted. Kept as the default so every existing caller, golden render
# and delivery sidecar is byte-identical to before this theme existed.
REPORT_THEME: Final = CaptionTheme()

# Built for a phone held in one hand. Three things differ from `REPORT_THEME` and each is a
# defect fixed rather than a taste applied:
#
# `primary`/`secondary` are swapped, so the sweep runs *with* the voice instead of ahead of it.
# `margin_v` is 360 rather than 140: Reels, Shorts and TikTok all draw their own caption bar
# and action rail over roughly the bottom 300 px of a 1920-tall frame, so a 140 px margin puts
# Kurdish text underneath the platform's own UI on every one of them.
# `outline`/`shadow`/`bold` are heavier because burned-in text is composited over live video,
# not over a neutral card, and a 3 px outline disappears against a bright background.
# 64 pt is a reading size for a 1080-wide report frame. A reel is watched at arm's length on
# a phone, often muted, and the caption is the only channel the words arrive on.
#
# The number is an em, and Naskh sets a small face inside it, so this is not the height of the
# text. Measured by rendering a real 17-character popup and taking the ink bounding box:
# 64 pt -> 38 px tall, 74 -> 43, 84 -> 49, 96 -> 56, 108 -> 63, 120 -> 70. A burned-in social
# caption wants 60-90 px on a 1920-tall frame, so 74 was less than half the size it looked.
# 108 lands in that band while leaving the widest popup (22 characters, ~620 px) comfortably
# inside the 920 px the left and right margins leave for it.
VIRAL_FONT_SIZE: Final = 108

VIRAL_THEME: Final = CaptionTheme(
    primary="&H0000E5FF",
    secondary="&H00FFFFFF",
    bold=True,
    outline=4.0,
    shadow=2.0,
    margin_l=80,
    margin_r=80,
    margin_v=360,
)


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
    # Parse configure FLAGS, not substrings. `--disable-libass` contains "libass", so a
    # substring search certifies a build that explicitly turned the library off — which is
    # the one failure this check exists to catch. Reported by audit finding #4.
    enabled = set(re.findall(r"--enable-([a-z0-9_+-]+)", buildconf.lower()))
    disabled = set(re.findall(r"--disable-([a-z0-9_+-]+)", buildconf.lower()))
    # A linked shared object is real evidence; match the library file name, not free text.
    linked = set(re.findall(r"\blib([a-z0-9_+-]+?)\.so", linked_libraries.lower()))

    def find(name: str) -> str | None:
        if name in disabled:
            return None  # an explicit --disable- always wins
        if name in enabled:
            return "buildconf"
        if name in linked:
            return "linked libraries"
        return None

    libass_source = find("libass")
    harfbuzz_source = find("libharfbuzz") or find("harfbuzz")
    fribidi_source = find("libfribidi") or find("fribidi")

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

    from fontTools.ttLib import TTFont, TTLibError  # imported lazily: only rendering needs it

    try:
        with TTFont(font_path, lazy=True) as font:
            cmap = font.getBestCmap()
    except (OSError, TypeError, ValueError, TTLibError) as exc:
        raise FontCoverageError(f"cannot inspect font {font_path.name}: {exc}") from exc
    if cmap is None:
        raise FontCoverageError(f"{font_path.name} has no usable Unicode character map")
    missing = sorted(char for char in required if ord(char) not in cmap)
    if missing:
        raise FontCoverageError(
            f"{font_path.name} has no glyph for {' '.join(missing)} "
            f"(U+{' U+'.join(f'{ord(c):04X}' for c in missing)}). These render as boxes in "
            f"burned-in captions — §4.3.4."
        )


def assert_fonts_dir_covers_kurdish(
    fonts_dir: Path,
    required: frozenset[str] = KURDISH_REQUIRED_GLYPHS,
) -> Path:
    """Return one font libass can use for every required glyph, or fail before encoding."""
    try:
        candidates = sorted(
            path
            for path in fonts_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"}
        )
    except OSError as exc:
        raise FontCoverageError(f"cannot inspect fonts directory {fonts_dir}: {exc}") from exc
    if not candidates:
        raise FontCoverageError(
            f"{fonts_dir} holds no font file; §4.3.4 forbids host font fallback"
        )

    failures: list[str] = []
    for candidate in candidates:
        try:
            assert_font_covers_kurdish(candidate, required=required)
        except (FontCoverageError, OSError) as exc:
            failures.append(f"{candidate.name}: {exc}")
        else:
            return candidate
    detail = failures[0] if failures else "no readable candidate"
    raise FontCoverageError(f"no font in {fonts_dir} covers Kurdish; closest failure: {detail}")


_INLINE_FONT_OVERRIDE = re.compile(r"\{[^}]*\\fn", re.IGNORECASE)


def _ass_format(line: str, *, section: str, required: frozenset[str]) -> tuple[str, ...]:
    fields = tuple(part.strip().casefold() for part in line.split(":", 1)[1].split(","))
    if not fields or any(not field for field in fields):
        raise FontCoverageError(f"ASS {section} Format has an empty field")
    missing = sorted(required - set(fields))
    if missing:
        raise FontCoverageError(
            f"ASS {section} Format has no {', '.join(name.title() for name in missing)} field"
        )
    if len(fields) != len(set(fields)):
        raise FontCoverageError(f"ASS {section} Format has duplicate fields")
    return fields


def _ass_record(line: str, fields: tuple[str, ...], *, kind: str) -> dict[str, str]:
    values = tuple(part.strip() for part in line.split(":", 1)[1].split(",", len(fields) - 1))
    if len(values) != len(fields):
        raise FontCoverageError(
            f"ASS {kind} has {len(values)} field(s), but its Format declares {len(fields)}"
        )
    return dict(zip(fields, values, strict=True))


def _used_ass_font_families(ass_text: str) -> tuple[str, ...]:
    """Return the declared family for every style used by a Dialogue event."""
    section = ""
    style_fields: tuple[str, ...] | None = None
    event_fields: tuple[str, ...] | None = None
    styles: dict[str, tuple[str, str]] = {}
    used_styles: list[tuple[str, str]] = []

    for raw_line in ass_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.casefold()
            continue
        folded = line.casefold()
        if section == "[v4+ styles]":
            if folded.startswith("format:"):
                if style_fields is not None:
                    raise FontCoverageError("ASS has more than one V4+ Styles Format declaration")
                style_fields = _ass_format(
                    line, section="style", required=frozenset({"name", "fontname"})
                )
            elif folded.startswith("style:"):
                if style_fields is None:
                    raise FontCoverageError("ASS Style appears before its V4+ Styles Format")
                record = _ass_record(line, style_fields, kind="Style")
                style_name = record["name"]
                family = record["fontname"]
                if not style_name or not family:
                    raise FontCoverageError("ASS Style name and Fontname must be non-empty")
                key = style_name.casefold()
                if key in styles:
                    raise FontCoverageError(f"ASS defines style {style_name!r} more than once")
                styles[key] = (style_name, family)
        elif section == "[events]":
            if folded.startswith("format:"):
                if event_fields is not None:
                    raise FontCoverageError("ASS has more than one Events Format declaration")
                event_fields = _ass_format(
                    line, section="event", required=frozenset({"style", "text"})
                )
                if event_fields[-1] != "text":
                    raise FontCoverageError(
                        "ASS Events Format must put Text last so commas in captions are unambiguous"
                    )
            elif folded.startswith("dialogue:"):
                if event_fields is None:
                    raise FontCoverageError("ASS Dialogue appears before its Events Format")
                record = _ass_record(line, event_fields, kind="Dialogue")
                if _INLINE_FONT_OVERRIDE.search(record["text"]):
                    raise FontCoverageError(
                        "ASS Dialogue contains an inline \\fn family override; the burn cannot "
                        "prove which directory font libass will select"
                    )
                style_name = record["style"]
                if not style_name:
                    raise FontCoverageError("ASS Dialogue style must be non-empty")
                used_styles.append((style_name.casefold(), style_name))

    if style_fields is None or not styles:
        raise FontCoverageError("ASS has no usable V4+ Styles table")
    if event_fields is None or not used_styles:
        raise FontCoverageError("ASS has no usable Dialogue event")

    families: list[str] = []
    for key, original in used_styles:
        try:
            _declared_name, family = styles[key]
        except KeyError as exc:
            raise FontCoverageError(f"ASS Dialogue uses undefined style {original!r}") from exc
        if family not in families:
            families.append(family)
    return tuple(families)


def _font_family_names(font_path: Path) -> frozenset[str]:
    from fontTools.ttLib import TTFont, TTLibError

    try:
        with TTFont(font_path, lazy=True) as font:
            names = {
                record.toUnicode().strip()
                for record in font["name"].names
                if record.nameID in {1, 16} and record.toUnicode().strip()
            }
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, TTLibError) as exc:
        raise FontCoverageError(
            f"cannot read font family names from {font_path.name}: {exc}"
        ) from exc
    if not names:
        raise FontCoverageError(f"{font_path.name} has no family name in name-table ID 1 or 16")
    return frozenset(names)


def assert_ass_fonts_cover_kurdish(
    ass_text: str,
    fonts_dir: Path,
    required: frozenset[str] = KURDISH_REQUIRED_GLYPHS,
) -> tuple[Path, ...]:
    """Bind each used ASS family to one directory font and verify that exact font's glyphs.

    This is intentionally stricter than imitating fontconfig fallback. More than one file claiming
    the same family is ambiguous without reproducing libass's weight/style selection, and an inline
    `\\fn` can switch families inside one event; both are refused before a client can see fallback.
    """
    families = _used_ass_font_families(ass_text)
    try:
        candidates = sorted(
            path
            for path in fonts_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"}
        )
    except OSError as exc:
        raise FontCoverageError(f"cannot inspect fonts directory {fonts_dir}: {exc}") from exc
    if not candidates:
        raise FontCoverageError(
            f"{fonts_dir} holds no font file; §4.3.4 forbids host font fallback"
        )

    by_family: dict[str, list[Path]] = {}
    unreadable: list[str] = []
    for candidate in candidates:
        try:
            names = _font_family_names(candidate)
        except FontCoverageError as exc:
            unreadable.append(str(exc))
            continue
        for name in names:
            by_family.setdefault(name.casefold(), []).append(candidate)

    resolved: list[Path] = []
    for family in families:
        matches = by_family.get(family.casefold(), [])
        if not matches:
            detail = f"; unreadable candidate: {unreadable[0]}" if unreadable else ""
            raise FontCoverageError(
                f"no font in {fonts_dir} declares ASS family {family!r}{detail}; refusing host "
                "font fallback"
            )
        if len(matches) != 1:
            match_names = ", ".join(path.name for path in matches)
            raise FontCoverageError(
                f"ASS family {family!r} is declared by multiple directory fonts ({match_names}); "
                "libass style selection would be ambiguous"
            )
        match = matches[0]
        try:
            assert_font_covers_kurdish(match, required=required)
        except (FontCoverageError, OSError) as exc:
            raise FontCoverageError(
                f"ASS family {family!r} resolves to {match.name}, but that font fails Kurdish "
                f"coverage: {exc}"
            ) from exc
        if match not in resolved:
            resolved.append(match)
    return tuple(resolved)


def _escape_filter_path(path: Path) -> str:
    """Escape a path for an ffmpeg filtergraph argument.

    An unescaped `:` silently truncates the argument and the filter then renders with
    default options — including `shaping=auto`, which is the exact failure §4.3 is about.

    **Two backslashes, not one.** ffmpeg unescapes a filter option twice: once when it splits
    the filtergraph description into filters and their arguments, and again when the filter
    parses its own options. A single backslash survives the first pass and is consumed by the
    second, so the `:` it was protecting reappears as a separator. The old single-escape form
    was therefore wrong on every platform; it only ever *showed* on one, because a POSIX path
    rarely contains any of these characters and the substitutions simply never fired.

    Windows separators become `/`, which ffmpeg accepts everywhere. A Windows path carries
    two metacharacters at once — the drive `:` and `\\` as the separator — and escaping
    backslashes through two passes is a second problem that not having them removes.

    Measured on hawapc01 against the real binary, all three forms on the same font directory:
    `C\\:\\\\Users\\\\…` and `C\\:/Users/…` both die with "No option name near"; `C\\\\:/Users/…`
    renders. `tests/test_captions.py` pins the survivor.
    """
    escaped = str(path).replace("\\", "/")
    for character in (":", "'", "[", "]", ","):
        escaped = escaped.replace(character, f"\\\\{character}")
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


def chunk_caption_events(
    words: Sequence[Word],
    *,
    max_words: int = POPUP_MAX_WORDS,
    max_chars: int = POPUP_MAX_CHARS,
    max_ms: int = POPUP_MAX_MS,
    max_gap_ms: int = POPUP_MAX_GAP_MS,
) -> tuple[tuple[Word, ...], ...]:
    """Split one sentence into popup-sized groups, each of which is its own caption event.

    `wrap_caption_lines` answers "where does this sentence break across lines"; this answers
    "where does it break across *time*". They are different questions and conflating them is
    what put a seven-line, fifteen-second block on screen: the sentence was one event, so the
    whole paragraph appeared at its first word and stayed until its last.

    A group closes on whichever comes first — word count, rendered width, elapsed span, or a
    pause. The pause rule is the one that cannot be replaced by a shorter limit: a group that
    straddles a silence sits on screen saying nothing.

    Raises:
        ValueError: any limit is non-positive, or `words` is empty.
    """
    if not words:
        raise ValueError("no words to chunk into caption events")
    if max_words < 1:
        raise ValueError("max_words must be positive")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if max_ms < 1:
        raise ValueError("max_ms must be positive")
    if max_gap_ms < 0:
        raise ValueError("max_gap_ms must be non-negative")

    chunks: list[tuple[Word, ...]] = []
    current: list[Word] = []
    width = 0
    for word in words:
        addition = len(word.w) + (1 if current else 0)
        # A single word wider than `max_chars` still gets its own event: dropping it would
        # caption speech that was never said, and splitting Arabic script mid-word breaks
        # shaping (§4.3.5's reasoning, applied to time instead of line width).
        closes = bool(current) and (
            len(current) >= max_words
            or width + addition > max_chars
            or word.end_ms - current[0].start_ms > max_ms
            or word.start_ms - current[-1].end_ms > max_gap_ms
        )
        if closes:
            chunks.append(tuple(current))
            current, width = [word], len(word.w)
        else:
            current.append(word)
            width += addition
    chunks.append(tuple(current))
    return tuple(chunks)


class CaptionsOutsideClip(ValueError):
    """The caption file's timeline is not the clip's timeline.

    §3 Stage 6 burns subtitles into a stream ffmpeg has already cut, so t=0 is the start of
    the clip and never the start of the source. A caption scheduled in source time lands past
    the end of a clip taken from the middle of an episode, libass draws nothing, and the
    result is a valid, playable, entirely caption-free MP4 — Kurdish invariant #4 absent with
    no error anywhere.
    """


_DIALOGUE_TIME = re.compile(
    r"^Dialogue:\s*\d+,(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2}),", re.MULTILINE
)


def parse_dialogue_times(ass_text: str) -> tuple[tuple[int, int], ...]:
    """Every Dialogue line's `(start_ms, end_ms)`, as the file actually carries them.

    ASS stores centiseconds, so the values read back truncated to 10 ms. That is a property of
    the format rather than a rounding choice here, and it is visible in the result instead of
    being smoothed over.
    """
    return tuple(
        (_parse_ass_time(start), _parse_ass_time(end))
        for start, end in _DIALOGUE_TIME.findall(ass_text)
    )


def _parse_ass_time(stamp: str) -> int:
    hours, minutes, rest = stamp.split(":")
    seconds, centiseconds = rest.split(".")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(centiseconds) * 10


def assert_captions_within_clip(ass_text: str, clip_duration_ms: int) -> None:
    """Refuse a caption file that has nothing to draw inside `[0, clip_duration_ms]`.

    This runs at the burn, on whatever file arrives, because a fix applied only where the file
    is *written* is not a fix — the same lesson as D-038. `build_ass` now applies the clip
    offset; this catches a hand-written file, a file from an older run, and a future caller
    that forgets, which is the failure that actually shipped.

    Partial overlap is enough: something is on screen, so this is not the silent case.

    Raises:
        CaptionsOutsideClip: no Dialogue line, or none intersecting the clip.
    """
    events = parse_dialogue_times(ass_text)
    if not events:
        raise CaptionsOutsideClip(
            "the caption file has no Dialogue lines: libass would draw nothing and the clip "
            "would ship without captions (Kurdish invariant #4)"
        )
    if not any(start < clip_duration_ms and end > 0 for start, end in events):
        first, last = events[0], events[-1]
        raise CaptionsOutsideClip(
            f"the caption file spans {first[0]}..{last[1]} ms and the clip is "
            f"0..{clip_duration_ms} ms, so libass has nothing to draw. Subtitles are burned "
            f"into a stream that was "
            f"already cut, where t=0 is the start of the clip — source-absolute timestamps "
            f"produce a valid, playable, caption-free MP4."
        )


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


def _karaoke(words: Sequence[Word], start_ms: int) -> str:
    """Karaoke spans for one run of words, tiling every gap so the sweep tracks the voice.

    Durations must tile the whole run, gaps included. Emitting only word durations makes the
    highlight run ahead by the length of every pause, so it drifts further from the speech
    with each silence. Reported by audit finding #7.
    """
    parts: list[str] = []
    cursor = start_ms
    for word in words:
        gap_cs = max(0, (word.start_ms - cursor) // 10)
        if gap_cs:
            # An empty karaoke span holds the highlight through the silence.
            parts.append(f"{{\\kf{gap_cs}}}")
        span_cs = max(1, (word.end_ms - word.start_ms) // 10)
        parts.append(f"{{\\kf{span_cs}}}{_escape_ass_text(word.w)} ")
        cursor = word.end_ms
    return "".join(parts).strip()


def build_ass(
    sentences: Sequence[Sentence],
    font_name: str = "Noto Naskh Arabic",
    font_size: int = 64,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    style: CaptionStyle = CaptionStyle.LINE,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    clip_in_ms: int = 0,
    clip_duration_ms: int | None = None,
    theme: CaptionTheme = REPORT_THEME,
    max_words_per_event: int | None = None,
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
    # The same sequence `pipeline.py` hands to `build_srt`, so the same refusal applies: an
    # overlapping or reversed pair burns two captions over each other, or none. D-165.
    assert_deliverable_order(sentences)
    for sentence in sentences:
        if not sentence.complete:
            raise ValueError(
                f"sentence at {sentence.start_ms} ms is not complete — reject, never render "
                f"(Kurdish invariant #2). Captioning a fragment ships a broken clip."
            )
        if sentence.start_ms < clip_in_ms:
            raise CaptionsOutsideClip(
                f"sentence at {sentence.start_ms} ms starts before the clip does "
                f"({clip_in_ms} ms): it would need a negative timestamp, which means it is "
                f"speech from outside this clip."
            )
        if clip_duration_ms is not None and sentence.end_ms - clip_in_ms > clip_duration_ms:
            raise CaptionsOutsideClip(
                f"sentence ending at {sentence.end_ms} ms runs past the end of the clip "
                f"({clip_in_ms + clip_duration_ms} ms) — a caption for speech this clip does "
                f"not contain."
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
            theme.style_row("Kurdish", font_name, font_size),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )

    def render(words: Sequence[Word]) -> str:
        if style is CaptionStyle.WORD_HIGHLIGHT:
            return _karaoke(words, words[0].start_ms)
        return " ".join(_escape_ass_text(word.w) for word in words)

    # The clip's timeline, not the source's. The kf spans are durations and are unaffected
    # — only the two absolute stamps below ever needed the offset, and for as long as they did
    # not have it, every clip cut from mid-episode shipped with no captions at all.
    def event(start_ms: int, end_ms: int, text: str) -> str:
        return (
            f"Dialogue: 0,{_ass_time(start_ms - clip_in_ms)},"
            f"{_ass_time(end_ms - clip_in_ms)},"
            f"Kurdish,,0,0,0,,{text}"
        )

    events: list[str] = []
    for sentence in sentences:
        if max_words_per_event is None:
            lines = wrap_caption_lines(sentence.words, max_chars=max_chars_per_line)
            events.append(
                event(
                    sentence.start_ms,
                    sentence.end_ms,
                    "\\N".join(render(line) for line in lines),
                )
            )
            continue
        # One event per popup. Each is short enough to fit one line, so no newline appears and
        # libass is never asked to lay a paragraph over live video.
        chunks = chunk_caption_events(
            sentence.words,
            max_words=max_words_per_event,
            max_chars=max_chars_per_line,
        )
        for index, chunk in enumerate(chunks):
            # Hold a popup until the next one starts when the hole between them is short: a
            # caption that vanishes for a fifth of a second reads as a glitch, not as a beat.
            # The last chunk ends on its own last word and never past the sentence, which is
            # what `clip_duration_ms` and `assert_captions_within_clip` are measured against.
            following = chunks[index + 1][0].start_ms if index + 1 < len(chunks) else None
            end_ms = chunk[-1].end_ms
            if following is not None and following - end_ms <= _POPUP_HOLD_MS:
                end_ms = following
            events.append(event(chunk[0].start_ms, end_ms, render(chunk)))

    return header + "\n" + "\n".join(events) + "\n"


def find_ffmpeg() -> Path | None:
    """Locate ffmpeg: explicit path, source generation, installed-user generation, then PATH.

    Returns `None` rather than raising — the caller decides whether a missing ffmpeg is a
    skipped render test or a failed deploy check.
    """
    from os import environ
    from shutil import which

    configured = environ.get("HAWEDIT_FFMPEG")
    if configured and Path(configured).is_file():
        return Path(configured)
    # Where scripts/fetch-ffmpeg.sh puts it, so the readiness report and the gate agree
    # without anyone having to remember an environment variable.
    vendored = Path(__file__).resolve().parents[2] / ".ffmpeg"
    for name in ("ffmpeg", "ffmpeg.exe"):
        if (vendored / name).is_file():
            return vendored / name
    # A wheel has no checkout-local scripts directory. hawedit-ffmpeg-setup installs into a
    # per-user cache and this shared resolver makes the next process discover it automatically.
    from hawedit.ffmpeg_setup import default_ffmpeg_dir

    installed = default_ffmpeg_dir()
    for name in ("ffmpeg", "ffmpeg.exe"):
        if (installed / name).is_file():
            return installed / name
    located = which("ffmpeg")
    return Path(located) if located else None


def ffprobe_for(ffmpeg: Path) -> Path:
    """The ffprobe that ships beside `ffmpeg`, keeping the binary's own suffix.

    `with_name("ffprobe")` is right on POSIX and wrong everywhere `ffmpeg` has an extension:
    `shutil.which` returns `ffmpeg.EXE` on Windows, whose sibling is `ffprobe.EXE`, and the
    bare name does not exist. Every caller took the same shortcut, so on hawapc01 — the box
    §6 names — Stage 0 ingest, the frame-rate probe and the pipeline's own duration check all
    failed identically at the first probe. One resolver, so the next caller cannot repeat it.
    """
    return ffmpeg.with_name("ffprobe" + ffmpeg.suffix)


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

    The filter comes **from** `subtitle_filter` rather than being rebuilt here. Both spellings
    were maintained side by side until D-164 — identical character for character, and nothing
    required them to stay so, which meant §4.3.6's pixel safeguard was comparing renders of a
    string production does not use. A fourth element added to the burn would have gone
    unrendered by the only test that looks at pixels.
    """
    import subprocess

    filter_string = subtitle_filter(ass_path, fonts_dir)
    if shaping != "complex":
        wrong = filter_string.replace("shaping=complex", f"shaping={shaping}", 1)
        if wrong == filter_string:
            raise ValueError(
                f"could not render with shaping={shaping!r}: {filter_string!r} carries no "
                f"`shaping=complex` to replace, so this would silently render the right way "
                f"and the negative control would be measuring nothing"
            )
        filter_string = wrong
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
