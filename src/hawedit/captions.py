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
from dataclasses import dataclass, replace
from enum import Enum
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Final

from hawedit.brand import EndCardConfig, SpeakerBio
from hawedit.normalize import normalize_sorani
from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.transcripts import Word

__all__ = [
    "BROADCAST_THEME",
    "DEFAULT_BOTTOM_CAPTION_BAND",
    "DEFAULT_MAX_CHARS_PER_LINE",
    "DEFAULT_MAX_LINE_WIDTH_PX",
    "DEFAULT_PLATE_COLOUR",
    "DEFAULT_PLATE_PADDING",
    "DEFAULT_TOP_CAPTION_BAND",
    "DEFAULT_TOP_MARGIN_V",
    "END_CARD_FONT_SIZE",
    "END_CARD_THEME",
    "GOLDEN_CAPTION_TEXT",
    "KURDISH_REQUIRED_GLYPHS",
    "MIN_LEGIBILITY_CONTRAST_RATIO",
    "POPUP_MAX_CHARS",
    "POPUP_MAX_GAP_MS",
    "POPUP_MAX_MS",
    "POPUP_MAX_WIDTH_PX",
    "POPUP_MAX_WORDS",
    "REPORT_THEME",
    "SPEAKER_TAG_FONT_SIZE",
    "SPEAKER_TAG_MS",
    "SPEAKER_TAG_THEME",
    "VIRAL_FONT_SIZE",
    "VIRAL_THEME",
    "CaptionStyle",
    "CaptionTheme",
    "CaptionsOutsideClip",
    "EmphasisCategory",
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
    "classify_kurdish_emphasis",
    "compare_golden_render",
    "compute_rtl_word_positions",
    "contrast_ratio",
    "decode_to_rgb",
    "event_needs_plate",
    "find_ffmpeg",
    "intersects_caption_band",
    "measure_rendered_caption_width",
    "parse_ass_colour",
    "parse_dialogue_times",
    "relative_luminance",
    "render_caption_png",
    "should_use_top_caption_placement",
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
DEFAULT_MAX_LINE_WIDTH_PX: Final = 850

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
    VIRAL_POPUP = "viral_popup"
    RTL_WORD_HIGHLIGHT = "rtl_word_highlight"
    BROADCAST_STUDIO = "broadcast_studio"


# One popup holds a breath, not a paragraph. A vertical crop shows ~22 Kurdish characters at
# the sizes §4.3 renders, and a caption that outlives its own words is a wall of text the
# viewer reads ahead of the audio — the failure that made every earlier run of this pipeline
# unusable for social delivery even though every timestamp in it was correct.
POPUP_MAX_WORDS: Final = 3
POPUP_MAX_CHARS: Final = 22
POPUP_MAX_WIDTH_PX: Final = 700
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
    # 2 = bottom-centre, which is what every theme used before the hook card needed the top.
    alignment: int = 2
    # 1 = outline and shadow, which is what every theme used before the hook card. 3 draws an
    # opaque box behind the text instead, and then `outline` is the box's padding rather than a
    # stroke width. Measured on the first edited clip: the card rendered white over a light
    # shirt and a lit face, readable only because of its outline — a plate is what makes it
    # readable on *any* footage rather than on footage that happens to be dark.
    border_style: int = 1

    def style_row(
        self,
        name: str,
        font_name: str,
        font_size: int,
        *,
        alignment: int | None = None,
        margin_v: int | None = None,
        primary: str | None = None,
        secondary: str | None = None,
    ) -> str:
        """One `Style:` line. `%g` keeps `3.0` as `3` so existing goldens still match."""
        align = self.alignment if alignment is None else alignment
        mv = self.margin_v if margin_v is None else margin_v
        p = self.primary if primary is None else primary
        s = self.secondary if secondary is None else secondary
        return (
            f"Style: {name},{font_name},{font_size},{p},{s},"
            f"{self.outline_colour},{self.back_colour},{int(self.bold)},0,0,0,100,100,0,0,"
            f"{self.border_style},"
            f"{self.outline:g},{self.shadow:g},{align},{self.margin_l},"
            f"{self.margin_r},"
            f"{mv},1"
        )

    def plate_style_row(
        self,
        name: str,
        font_name: str,
        font_size: int,
        *,
        alignment: int | None = None,
        margin_v: int | None = None,
        plate_padding: float = 16.0,
        plate_colour: str = "&H80000000",
        primary: str | None = None,
        secondary: str | None = None,
    ) -> str:
        """One `Style:` line with border_style=3 (bounding plate behind text)."""
        align = self.alignment if alignment is None else alignment
        mv = self.margin_v if margin_v is None else margin_v
        p = self.primary if primary is None else primary
        s = self.secondary if secondary is None else secondary
        return (
            f"Style: {name},{font_name},{font_size},{p},{s},"
            f"{self.outline_colour},{plate_colour},{int(self.bold)},0,0,0,100,100,0,0,"
            f"3,{plate_padding:g},0,{align},{self.margin_l},{self.margin_r},{mv},1"
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

# The opening card. A social clip is scrolled past in the first second or it is not watched, and
# Stage 4 already writes a Kurdish title for every verdict — `title_ckb` — which the render threw
# away for as long as it existed. Measured on the ep29 delivery: the judge wrote a real title and
# the burned clip opened on speech with nothing on screen but karaoke. D-259.
HOOK_CARD_MS: Final = 1_800
HOOK_CARD_FONT_SIZE: Final = 84
# Top third rather than the caption band: the card and the first caption overlap in time, and two
# pieces of text in the same place is worse than none.
HOOK_CARD_THEME: Final = CaptionTheme(
    primary="&H00FFFFFF",
    secondary="&H00FFFFFF",
    bold=True,
    # With `border_style=3` this is the plate's padding, not a stroke width.
    outline=18.0,
    shadow=0.0,
    # 40% opaque black. ASS alpha runs the other way from intuition: 00 is opaque, FF invisible.
    back_colour="&H66000000",
    margin_l=60,
    margin_r=60,
    # Higher than the 220 the first edited clip used, which put the card across the subject's
    # forehead. A hook card belongs above the face, not on it.
    margin_v=120,
    alignment=8,
    border_style=3,
)

# Lower-third speaker introduction tag (Task T2.13, ADR D-268).
# Displayed during speaker turns from episode metadata + diarization mapping.
SPEAKER_TAG_MS: Final = 3_500
SPEAKER_TAG_FONT_SIZE: Final = 42
SPEAKER_TAG_THEME: Final = CaptionTheme(
    primary="&H00FFFFFF",
    secondary="&H00FFFFFF",
    bold=True,
    outline=12.0,
    shadow=0.0,
    # ~75% opaque dark plate for crisp readability on any video background
    back_colour="&H40000000",
    margin_l=60,
    margin_r=60,
    # Positioned at Y ≈ 1640 (PlayResY=1920, MarginV=280, Alignment=3),
    # comfortably above bottom subtitle band
    margin_v=280,
    alignment=3,
    border_style=3,
)

# 2-second outro end card with call-to-action (Task T2.13, ADR D-268).
END_CARD_FONT_SIZE: Final = 60
END_CARD_THEME: Final = CaptionTheme(
    primary="&H00FFFFFF",
    secondary="&H00FFFFFF",
    bold=True,
    outline=24.0,
    shadow=0.0,
    # 90% opaque dark backing card
    back_colour="&H1A000000",
    margin_l=80,
    margin_r=80,
    margin_v=0,
    # 5 = middle-centre alignment
    alignment=5,
    border_style=3,
)

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

BROADCAST_THEME: Final = CaptionTheme(
    primary="&H00FFFFFF",
    secondary="&H0000E5FF",
    outline_colour="&H00000000",
    back_colour="&H80000000",
    bold=True,
    outline=4.0,
    shadow=1.5,
    margin_l=80,
    margin_r=80,
    margin_v=440,
)

# Task T2.7: Face-aware caption placement band definitions.
# At 1080x1920 PlayRes, the bottom caption band occupies Y = 1300..1650.
# If a tracked face intersects this band, the caption dynamically moves to the top band
# (Y = 200..520, Alignment 8, MarginV 240) so the speaker's face is never obscured.
DEFAULT_BOTTOM_CAPTION_BAND: Final[tuple[int, int]] = (1300, 1650)
DEFAULT_TOP_CAPTION_BAND: Final[tuple[int, int]] = (200, 520)
DEFAULT_TOP_MARGIN_V: Final = 240


def intersects_caption_band(
    top_y: int,
    bottom_y: int,
    band: tuple[int, int] = DEFAULT_BOTTOM_CAPTION_BAND,
) -> bool:
    """Check whether a vertical interval [top_y, bottom_y] intersects a caption band."""
    band_top, band_bottom = band
    return bool(bottom_y >= band_top and top_y <= band_bottom)


def should_use_top_caption_placement(
    start_ms: int,
    end_ms: int,
    face_intervals: Sequence[tuple[int, int, int, int]] | None,
    band: tuple[int, int] = DEFAULT_BOTTOM_CAPTION_BAND,
) -> bool:
    """Determine whether an event at [start_ms, end_ms] intersects any face in the caption band."""
    if not face_intervals:
        return False
    for f_start, f_end, f_top, f_bottom in face_intervals:
        if f_start < end_ms and f_end > start_ms and intersects_caption_band(f_top, f_bottom, band):
            return True
    return False


# Task T2.8: Caption legibility and adaptive background plate definitions.
DEFAULT_PLATE_COLOUR: Final = "&H80000000"
DEFAULT_PLATE_PADDING: Final = 16.0
MIN_LEGIBILITY_CONTRAST_RATIO: Final = 4.5


def parse_ass_colour(colour: str) -> tuple[int, int, int]:
    """Parse an ASS colour string (&HAABBGGRR or &HBBGGRR) into (R, G, B) integers [0, 255]."""
    cleaned = colour.strip().lstrip("&H").lstrip("&h").rstrip("&")
    if len(cleaned) == 8:
        b = int(cleaned[2:4], 16)
        g = int(cleaned[4:6], 16)
        r = int(cleaned[6:8], 16)
    elif len(cleaned) == 6:
        b = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        r = int(cleaned[4:6], 16)
    else:
        return (255, 255, 255)
    return (r, g, b)


def relative_luminance(r: int, g: int, b: int) -> float:
    """Calculate standard WCAG 2.1 relative luminance L in [0.0, 1.0]."""

    def _channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(lum1: float, lum2: float) -> float:
    """Calculate standard WCAG 2.1 contrast ratio between two relative luminances."""
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def event_needs_plate(
    start_ms: int,
    end_ms: int,
    plate_intervals: Sequence[tuple[int, int]] | None,
) -> bool:
    """Check whether a caption event [start_ms, end_ms] intersects any plate interval."""
    if not plate_intervals:
        return False
    return any(p_start < end_ms and p_end > start_ms for p_start, p_end in plate_intervals)


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


def wrap_title_lines(title: str, max_chars: int = DEFAULT_MAX_CHARS_PER_LINE) -> list[str]:
    """Break a hook card's title on whitespace, greedily, at `max_chars`.

    Separate from `wrap_caption_lines` because that one wraps *aligned words* and carries their
    timings; a title has no timings, it is one string the judge wrote. Sharing it would mean
    inventing `Word`s with fake timestamps to satisfy a signature.
    """
    words = title.split()
    if not words:
        return []
    lines = [words[0]]
    for word in words[1:]:
        if len(lines[-1]) + 1 + len(word) <= max_chars:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


_WIDTH_CACHE: dict[tuple[str, str, int, int], int] = {}


def _default_fonts_dir() -> Path:
    import sys

    checkout = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    installed = Path(sys.prefix) / "share" / "hawedit" / "assets" / "fonts"
    return checkout if checkout.is_dir() else installed


def measure_rendered_caption_width(
    text: str,
    *,
    font_name: str = "Noto Naskh Arabic",
    font_size: int = VIRAL_FONT_SIZE,
    ffmpeg: Path | None = None,
    fonts_dir: Path | None = None,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
) -> int:
    """Measure the horizontal ink extent in pixels of rendered Kurdish text at PlayRes.

    Renders the candidate string through libass via FFmpeg with `shaping=complex` onto a
    blank background and measures the bounding width of non-zero pixels. Cached in-memory
    to make incremental line-breaking checks near instantaneous.
    """
    cleaned = text.strip()
    if not cleaned:
        return 0

    cache_key = (cleaned, font_name, font_size, canvas_width)
    cached = _WIDTH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        return int(len(cleaned) * font_size * 0.25)

    resolved_fonts = fonts_dir or _default_fonts_dir()

    import subprocess
    import tempfile

    escaped = _escape_ass_text(cleaned)
    ass_content = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {canvas_width}\n"
        f"PlayResY: {canvas_height}\n"
        "WrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,0,0,1,2.0,0.0,2,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{escaped}\n"
    )

    with tempfile.TemporaryDirectory() as td:
        ass_path = Path(td) / "measure.ass"
        ass_path.write_text(ass_content, encoding="utf-8")
        vf = subtitle_filter(ass_path, resolved_fonts)
        cmd = [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={canvas_width}x{canvas_height}:d=1",
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True)
            raw = res.stdout
            min_x = canvas_width
            max_x = -1
            for row_start in range(0, len(raw), canvas_width):
                row = raw[row_start : row_start + canvas_width]
                if any(row):
                    first_x = next(i for i, b in enumerate(row) if b > 0)
                    last_x = (
                        canvas_width - 1 - next(i for i, b in enumerate(reversed(row)) if b > 0)
                    )
                    if first_x < min_x:
                        min_x = first_x
                    if last_x > max_x:
                        max_x = last_x
            width = max_x - min_x + 1 if max_x >= min_x else 0
        except (subprocess.CalledProcessError, ValueError, OSError):
            width = int(len(cleaned) * font_size * 0.25)

    _WIDTH_CACHE[cache_key] = width
    return width


def wrap_caption_lines(
    words: Sequence[Word],
    max_chars: int = DEFAULT_MAX_CHARS_PER_LINE,
    *,
    max_width_px: int | None = None,
) -> tuple[tuple[Word, ...], ...]:
    """Break a caption into lines at word boundaries from the alignment.

    §4.3.5: "Insert line breaks yourself from the word alignment." A word longer than
    `max_chars` or `max_width_px` gets its own line rather than being dropped or split — a
    missing word in a caption is worse than a long line, and splitting Arabic-script mid-word
    breaks shaping.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if max_width_px is not None and max_width_px < 1:
        raise ValueError("max_width_px must be positive")

    if max_width_px is not None:
        lines: list[tuple[Word, ...]] = []
        current: list[Word] = []
        for word in words:
            if not current:
                current = [word]
                continue
            candidate_text = " ".join(w.w for w in [*current, word])
            cand_w = measure_rendered_caption_width(candidate_text)
            if cand_w > max_width_px:
                lines.append(tuple(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(tuple(current))
        return tuple(lines)

    lines_by_char: list[tuple[Word, ...]] = []
    current_by_char: list[Word] = []
    width = 0
    for word in words:
        addition = len(word.w) + (1 if current_by_char else 0)
        if current_by_char and width + addition > max_chars:
            lines_by_char.append(tuple(current_by_char))
            current_by_char, width = [word], len(word.w)
        else:
            current_by_char.append(word)
            width += addition
    if current_by_char:
        lines_by_char.append(tuple(current_by_char))
    return tuple(lines_by_char)


def chunk_caption_events(
    words: Sequence[Word],
    *,
    max_words: int = POPUP_MAX_WORDS,
    max_chars: int = POPUP_MAX_CHARS,
    max_width_px: int | None = None,
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
    if max_width_px is not None and max_width_px < 1:
        raise ValueError("max_width_px must be positive")
    if max_ms < 1:
        raise ValueError("max_ms must be positive")
    if max_gap_ms < 0:
        raise ValueError("max_gap_ms must be non-negative")

    chunks: list[tuple[Word, ...]] = []
    current: list[Word] = []
    width = 0
    for word in words:
        addition = len(word.w) + (1 if current else 0)
        closes = False
        if current:
            if max_width_px is not None:
                candidate_text = " ".join(w.w for w in [*current, word])
                cand_w = measure_rendered_caption_width(candidate_text)
                exceeds_width = cand_w > max_width_px
            else:
                exceeds_width = width + addition > max_chars

            closes = (
                len(current) >= max_words
                or exceeds_width
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


class EmphasisCategory(Enum):
    """Semantic category for keyword emphasis in Kurdish captions."""

    DEFAULT = "default"
    ENTITY = "entity"
    ACTION_ALERT = "action_alert"
    NUMERIC = "numeric"


_PUNCT_CLEANER: Final = re.compile(r"^[«»\"'“”،,.:!؟?\s]+|[«»\"'“”،,.:!؟?\s]+$")
_DIGITS_RE: Final = re.compile(r"^\d+$|^[٠-٩]+$")

_NUMERIC_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "یەک",
        "دوو",
        "سێ",
        "چوار",
        "پێنج",
        "شەش",
        "حەوت",
        "هەشت",
        "نۆ",
        "دە",
        "یازدە",
        "دوازدە",
        "سێزدە",
        "چواردە",
        "پازدە",
        "شازدە",
        "حەڤدە",
        "هەژدە",
        "نۆزدە",
        "بیست",
        "سی",
        "چل",
        "پەنجا",
        "شەست",
        "حەفتا",
        "هەشتا",
        "نەوەد",
        "سەد",
        "هەزار",
        "ملیۆن",
        "ملیار",
        "هەموو",
        "هەمووی",
        "هەموویان",
        "زۆرترین",
        "کەمترین",
        "یەکەم",
        "دووەم",
        "سێیەم",
        "چوارەم",
        "پێنجەم",
    }
)

_ACTION_ALERT_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "هەرگیز",
        "نەخێر",
        "مەحاڵ",
        "مەحاڵە",
        "کارەسات",
        "مەترسی",
        "مەترسیدار",
        "خراپترین",
        "گرنگترین",
        "گەورەترین",
        "سەرەکی",
        "تەواو",
        "ڕاستەوخۆ",
        "ئاشکرا",
        "بەڵێ",
        "تەنانەت",
        "بەڵام",
        "هەڵبوەشێنێتەوە",
        "شەڕ",
        "تیرۆر",
        "شکست",
        "مردن",
    }
)

_ENTITY_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "کوردستان",
        "عێراق",
        "ئەمریکا",
        "پێشمەرگە",
        "بەغدا",
        "هەولێر",
        "سلێمانی",
        "دهۆک",
        "کەرکووک",
        "پۆڵ",
        "برێمەر",
        "بارزانی",
        "تاڵەبانی",
        "سەددام",
        "ئێران",
        "تورکیا",
        "حکومەت",
        "پەرلەمان",
        "سەرۆک",
        "وەزیر",
    }
)

CATEGORY_COLORS: Final[dict[EmphasisCategory, str]] = {
    EmphasisCategory.DEFAULT: "&H0000E5FF",  # Electric Gold
    EmphasisCategory.ENTITY: "&H00FFFF00",  # Electric Cyan
    EmphasisCategory.ACTION_ALERT: "&H00303BFF",  # Vivid Coral
    EmphasisCategory.NUMERIC: "&H0066FF00",  # Neon Emerald
}

CATEGORY_SUFFIXES: Final[dict[EmphasisCategory, str]] = {
    EmphasisCategory.DEFAULT: "",
    EmphasisCategory.ENTITY: "Cyan",
    EmphasisCategory.ACTION_ALERT: "Coral",
    EmphasisCategory.NUMERIC: "Emerald",
}


@lru_cache(maxsize=10_000)
def classify_kurdish_emphasis(token: str) -> EmphasisCategory:
    """Classify a Kurdish word token into an emphasis category for visual styling."""
    clean = _PUNCT_CLEANER.sub("", token).strip()
    if not clean:
        return EmphasisCategory.DEFAULT
    if _DIGITS_RE.match(clean):
        return EmphasisCategory.NUMERIC
    norm = normalize_sorani(clean)
    if norm in _NUMERIC_KEYWORDS:
        return EmphasisCategory.NUMERIC
    if norm in _ACTION_ALERT_KEYWORDS:
        return EmphasisCategory.ACTION_ALERT
    if norm in _ENTITY_KEYWORDS:
        return EmphasisCategory.ENTITY
    return EmphasisCategory.DEFAULT


# How much larger the accented word is drawn. Scale rather than colour, because the colour
# channels are already spoken for: `\kf` sweeps `secondary` into `primary`, so recolouring a word
# would fight the highlight that tracks the voice.
EMPHASIS_SCALE: Final = 118


def emphasis_index(words: Sequence[Word]) -> int | None:
    """Which word in one caption event carries the accent, or `None` if none should.

    The longest word, which is a proxy for the carrying one and needs no model. Ties go to the
    earliest so a re-render never moves the accent. `None` for a single-word event: emphasising
    the only word on screen accents nothing, it just makes the caption bigger.
    """
    if len(words) < 2:
        return None
    return max(range(len(words)), key=lambda index: (len(words[index].w), -index))


def _karaoke(words: Sequence[Word], start_ms: int) -> str:
    """Karaoke spans for one run of words, tiling every gap so the sweep tracks the voice.

    Durations must tile the whole run, gaps included. Emitting only word durations makes the
    highlight run ahead by the length of every pause, so it drifts further from the speech
    with each silence. Reported by audit finding #7.
    """
    parts: list[str] = []
    cursor = start_ms
    accent = emphasis_index(words)
    for index, word in enumerate(words):
        gap_cs = max(0, (word.start_ms - cursor) // 10)
        if gap_cs:
            # An empty karaoke span holds the highlight through the silence.
            parts.append(f"{{\\kf{gap_cs}}}")
        span_cs = max(1, (word.end_ms - word.start_ms) // 10)
        text = _escape_ass_text(word.w)
        if index == accent:
            # A style override around the word, never a change to the word. The text a viewer
            # reads is the raw surface form either way — Kurdish invariant #1 governs the
            # transcript, and a caption that edits it to look better is editing the transcript.
            text = f"{{\\fscx{EMPHASIS_SCALE}\\fscy{EMPHASIS_SCALE}}}{text}{{\\fscx100\\fscy100}}"
        parts.append(f"{{\\kf{span_cs}}}{text} ")
        cursor = word.end_ms
    return "".join(parts).strip()


def compute_rtl_word_positions(
    words: Sequence[Word],
    font_name: str = "Noto Naskh Arabic",
    font_size: int = VIRAL_FONT_SIZE,
    canvas_width: int = 1080,
    fonts_dir: Path | None = None,
    ffmpeg: Path | None = None,
) -> list[tuple[Word, int]]:
    """Calculate the horizontal center pixel (X coordinate) for each word in an RTL sentence.

    In Kurdish (Arabic script), text flows Right-to-Left. To render individual words or
    highlighted runs at exact positions without libass inline-tag run reordering defects,
    each word is assigned an absolute center X coordinate derived from HarfBuzz font metrics:
        X_center = round((canvas_width + W_full) / 2 - W_prefix + W_word / 2)
    This guarantees X(w_0) > X(w_1) > ... > X(w_{n-1}) matching native RTL reading order.
    """
    if not words:
        return []
    if len(words) == 1:
        return [(words[0], canvas_width // 2)]

    full_text = " ".join(_escape_ass_text(w.w) for w in words)
    w_full = measure_rendered_caption_width(
        full_text,
        font_name=font_name,
        font_size=font_size,
        ffmpeg=ffmpeg,
        fonts_dir=fonts_dir,
        canvas_width=canvas_width,
    )

    positions: list[tuple[Word, int]] = []
    for i, word in enumerate(words):
        prefix_text = " ".join(_escape_ass_text(w.w) for w in words[: i + 1])
        w_prefix = measure_rendered_caption_width(
            prefix_text,
            font_name=font_name,
            font_size=font_size,
            ffmpeg=ffmpeg,
            fonts_dir=fonts_dir,
            canvas_width=canvas_width,
        )
        w_word = measure_rendered_caption_width(
            _escape_ass_text(word.w),
            font_name=font_name,
            font_size=font_size,
            ffmpeg=ffmpeg,
            fonts_dir=fonts_dir,
            canvas_width=canvas_width,
        )
        x_center = round((canvas_width + w_full) / 2 - w_prefix + (w_word / 2))
        positions.append((word, x_center))

    return positions


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
    title_ckb: str | None = None,
    max_line_width_px: int | None = None,
    max_popup_width_px: int | None = None,
    fonts_dir: Path | None = None,
    face_intervals: Sequence[tuple[int, int, int, int]] | None = None,
    plate_intervals: Sequence[tuple[int, int]] | None = None,
    speaker_turns: Sequence[tuple[int, int, str]] | None = None,
    speaker_metadata: dict[str, SpeakerBio] | None = None,
    end_card: EndCardConfig | None = None,
    keyword_emphasis: bool = True,
    margin_v: int | None = None,
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

    if style is CaptionStyle.BROADCAST_STUDIO and theme is REPORT_THEME:
        theme = BROADCAST_THEME
    if margin_v is not None:
        theme = replace(theme, margin_v=margin_v)

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
            *(
                [
                    theme.style_row(
                        f"Kurdish{CATEGORY_SUFFIXES[cat]}",
                        font_name,
                        font_size,
                        primary=color,
                    )
                    for cat, color in CATEGORY_COLORS.items()
                    if cat is not EmphasisCategory.DEFAULT
                ]
                if keyword_emphasis
                else []
            ),
            *(
                [
                    theme.style_row(
                        "KurdishDim",
                        font_name,
                        font_size,
                        primary=theme.secondary,
                    )
                ]
                if style is CaptionStyle.RTL_WORD_HIGHLIGHT
                else []
            ),
            *(
                [
                    theme.plate_style_row(
                        "KurdishPlate",
                        font_name,
                        font_size,
                    )
                ]
                if plate_intervals
                else []
            ),
            *(
                [
                    theme.plate_style_row(
                        f"KurdishPlate{CATEGORY_SUFFIXES[cat]}",
                        font_name,
                        font_size,
                        primary=color,
                    )
                    for cat, color in CATEGORY_COLORS.items()
                    if cat is not EmphasisCategory.DEFAULT
                ]
                if (keyword_emphasis and plate_intervals)
                else []
            ),
            *(
                [
                    theme.plate_style_row(
                        "KurdishPlateDim",
                        font_name,
                        font_size,
                        primary=theme.secondary,
                    )
                ]
                if (style is CaptionStyle.RTL_WORD_HIGHLIGHT and plate_intervals)
                else []
            ),
            *(
                [
                    theme.style_row(
                        "KurdishTop",
                        font_name,
                        font_size,
                        alignment=8,
                        margin_v=DEFAULT_TOP_MARGIN_V,
                    )
                ]
                if face_intervals
                else []
            ),
            *(
                [
                    theme.style_row(
                        f"KurdishTop{CATEGORY_SUFFIXES[cat]}",
                        font_name,
                        font_size,
                        alignment=8,
                        margin_v=DEFAULT_TOP_MARGIN_V,
                        primary=color,
                    )
                    for cat, color in CATEGORY_COLORS.items()
                    if cat is not EmphasisCategory.DEFAULT
                ]
                if (keyword_emphasis and face_intervals)
                else []
            ),
            *(
                [
                    theme.style_row(
                        "KurdishTopDim",
                        font_name,
                        font_size,
                        alignment=8,
                        margin_v=DEFAULT_TOP_MARGIN_V,
                        primary=theme.secondary,
                    )
                ]
                if (style is CaptionStyle.RTL_WORD_HIGHLIGHT and face_intervals)
                else []
            ),
            *(
                [
                    theme.plate_style_row(
                        "KurdishTopPlate",
                        font_name,
                        font_size,
                        alignment=8,
                        margin_v=DEFAULT_TOP_MARGIN_V,
                    )
                ]
                if face_intervals and plate_intervals
                else []
            ),
            *(
                [
                    theme.plate_style_row(
                        f"KurdishTopPlate{CATEGORY_SUFFIXES[cat]}",
                        font_name,
                        font_size,
                        alignment=8,
                        margin_v=DEFAULT_TOP_MARGIN_V,
                        primary=color,
                    )
                    for cat, color in CATEGORY_COLORS.items()
                    if cat is not EmphasisCategory.DEFAULT
                ]
                if (keyword_emphasis and face_intervals and plate_intervals)
                else []
            ),
            *(
                [
                    theme.plate_style_row(
                        "KurdishTopPlateDim",
                        font_name,
                        font_size,
                        alignment=8,
                        margin_v=DEFAULT_TOP_MARGIN_V,
                        primary=theme.secondary,
                    )
                ]
                if (style is CaptionStyle.RTL_WORD_HIGHLIGHT and face_intervals and plate_intervals)
                else []
            ),
            *(
                [HOOK_CARD_THEME.style_row("Hook", font_name, HOOK_CARD_FONT_SIZE)]
                if title_ckb
                else []
            ),
            *(
                [SPEAKER_TAG_THEME.style_row("SpeakerTag", font_name, SPEAKER_TAG_FONT_SIZE)]
                if speaker_metadata
                else []
            ),
            *(
                [END_CARD_THEME.style_row("EndCard", font_name, END_CARD_FONT_SIZE, alignment=5)]
                if (end_card and end_card.enabled)
                else []
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )

    def render(words: Sequence[Word]) -> str:
        if style is CaptionStyle.WORD_HIGHLIGHT:
            return _karaoke(words, words[0].start_ms)
        return " ".join(_escape_ass_text(word.w) for word in words)

    def choose_style(
        start_ms: int,
        end_ms: int,
        category: EmphasisCategory = EmphasisCategory.DEFAULT,
    ) -> str:
        is_top = should_use_top_caption_placement(start_ms, end_ms, face_intervals)
        is_plate = event_needs_plate(start_ms, end_ms, plate_intervals)
        suffix = CATEGORY_SUFFIXES[category] if keyword_emphasis else ""
        if is_top and is_plate:
            return f"KurdishTopPlate{suffix}"
        if is_top:
            return f"KurdishTop{suffix}"
        if is_plate:
            return f"KurdishPlate{suffix}"
        return f"Kurdish{suffix}"

    # The clip's timeline, not the source's. The kf spans are durations and are unaffected
    # — only the two absolute stamps below ever needed the offset, and for as long as they did
    # not have it, every clip cut from mid-episode shipped with no captions at all.
    def event(start_ms: int, end_ms: int, text: str, style_name: str = "Kurdish") -> str:
        return (
            f"Dialogue: 0,{_ass_time(start_ms - clip_in_ms)},"
            f"{_ass_time(end_ms - clip_in_ms)},"
            f"{style_name},,0,0,0,,{text}"
        )

    events: list[str] = []
    if title_ckb:
        # Layer 1, above the karaoke: they overlap in time by design — the card holds while the
        # first words are already being spoken, which is what a scroll-stopping open looks like.
        events.append(
            f"Dialogue: 1,{_ass_time(0)},{_ass_time(HOOK_CARD_MS)},Hook,,0,0,0,,"
            + "\\N".join(
                _escape_ass_text(line)
                for line in wrap_title_lines(title_ckb, max_chars=max_chars_per_line)
            )
        )
    if speaker_metadata and speaker_turns:
        # Layer 2, above hook card and karaoke: introduce speaker with lower-third badge
        last_speaker: str | None = None
        last_tag_end_ms: int = -10_000
        for turn_start, turn_end, speaker_id in speaker_turns:
            if speaker_id not in speaker_metadata:
                continue
            if speaker_id != last_speaker or (turn_start - last_tag_end_ms > 8_000):
                bio = speaker_metadata[speaker_id]
                ev_start = max(0, turn_start - clip_in_ms)
                ev_end = min(
                    (clip_duration_ms if clip_duration_ms is not None else (turn_end - clip_in_ms)),
                    ev_start + SPEAKER_TAG_MS,
                )
                if ev_end > ev_start:
                    escaped_name = _escape_ass_text(bio.name_ckb)
                    if bio.title_ckb:
                        escaped_title = _escape_ass_text(bio.title_ckb)
                        tag_text = (
                            f"{{\\fad(250,250)}}{escaped_name}\\N"
                            f"{{\\fs28\\c&HCCCCCC&}}{escaped_title}"
                        )
                    else:
                        tag_text = f"{{\\fad(250,250)}}{escaped_name}"
                    events.append(
                        f"Dialogue: 2,{_ass_time(ev_start)},{_ass_time(ev_end)},"
                        f"SpeakerTag,,0,0,0,,{tag_text}"
                    )
                    last_speaker = speaker_id
                    last_tag_end_ms = turn_start + SPEAKER_TAG_MS
    if end_card and end_card.enabled and clip_duration_ms is not None:
        # Layer 3, outro closing call-to-action card in final seconds
        ec_duration_ms = int(end_card.duration_s * 1000)
        ec_start = max(0, clip_duration_ms - ec_duration_ms)
        ec_parts: list[str] = []
        if end_card.title_ckb:
            for line in wrap_title_lines(end_card.title_ckb, max_chars=max_chars_per_line):
                ec_parts.append(_escape_ass_text(line))
        if end_card.subtitle_ckb:
            ec_parts.append(f"{{\\fs36\\c&HCCCCCC&}}{_escape_ass_text(end_card.subtitle_ckb)}")
        if end_card.handle:
            ec_parts.append(f"{{\\fs32\\c&HFFCC00&}}{_escape_ass_text(end_card.handle)}")
        if ec_parts:
            ec_text = "{\\fad(300,0)}" + "\\N".join(ec_parts)
            events.append(
                f"Dialogue: 3,{_ass_time(ec_start)},{_ass_time(clip_duration_ms)},"
                f"EndCard,,0,0,0,,{ec_text}"
            )
    for sentence in sentences:
        if style is CaptionStyle.BROADCAST_STUDIO:
            b_words = max_words_per_event if max_words_per_event is not None else 4
            chunks = chunk_caption_events(
                sentence.words,
                max_words=b_words,
                max_chars=max_chars_per_line,
                max_width_px=max_popup_width_px,
            )
            for index, chunk in enumerate(chunks):
                following = chunks[index + 1][0].start_ms if index + 1 < len(chunks) else None
                end_ms = chunk[-1].end_ms
                if following is not None and following - end_ms <= _POPUP_HOLD_MS:
                    end_ms = following
                is_top = should_use_top_caption_placement(chunk[0].start_ms, end_ms, face_intervals)
                is_plate = event_needs_plate(chunk[0].start_ms, end_ms, plate_intervals)
                style_name = (
                    ("KurdishTopPlate" if is_plate else "KurdishTop")
                    if is_top
                    else ("KurdishPlate" if is_plate else "Kurdish")
                )
                if keyword_emphasis:
                    parts = []
                    for w in chunk:
                        cat = classify_kurdish_emphasis(w.w)
                        escaped = _escape_ass_text(w.w)
                        if cat is not EmphasisCategory.DEFAULT and cat in CATEGORY_COLORS:
                            color = CATEGORY_COLORS[cat]
                            parts.append(f"{{\\c{color}&}}{escaped}{{\\r}}")
                        else:
                            parts.append(escaped)
                    chunk_text = " ".join(parts)
                else:
                    chunk_text = " ".join(_escape_ass_text(w.w) for w in chunk)
                events.append(event(chunk[0].start_ms, end_ms, chunk_text, style_name=style_name))
            continue

        if style is CaptionStyle.VIRAL_POPUP:
            v_words = max_words_per_event if max_words_per_event is not None else 2
            chunks = chunk_caption_events(
                sentence.words,
                max_words=v_words,
                max_chars=max_chars_per_line,
                max_width_px=max_popup_width_px,
            )
            for index, chunk in enumerate(chunks):
                following = chunks[index + 1][0].start_ms if index + 1 < len(chunks) else None
                end_ms = chunk[-1].end_ms
                if following is not None and following - end_ms <= _POPUP_HOLD_MS:
                    end_ms = following
                cat = EmphasisCategory.DEFAULT
                if keyword_emphasis:
                    cats = [classify_kurdish_emphasis(w.w) for w in chunk]
                    if EmphasisCategory.ACTION_ALERT in cats:
                        cat = EmphasisCategory.ACTION_ALERT
                    elif EmphasisCategory.ENTITY in cats:
                        cat = EmphasisCategory.ENTITY
                    elif EmphasisCategory.NUMERIC in cats:
                        cat = EmphasisCategory.NUMERIC
                style_name = choose_style(chunk[0].start_ms, end_ms, category=cat)
                popup_text = " ".join(_escape_ass_text(w.w) for w in chunk)
                bounce_tag = r"{\t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)}"
                events.append(
                    event(
                        chunk[0].start_ms,
                        end_ms,
                        f"{bounce_tag}{popup_text}",
                        style_name=style_name,
                    )
                )
            continue

        if style is CaptionStyle.RTL_WORD_HIGHLIGHT:
            r_words = max_words_per_event if max_words_per_event is not None else POPUP_MAX_WORDS
            chunks = chunk_caption_events(
                sentence.words,
                max_words=r_words,
                max_chars=max_chars_per_line,
                max_width_px=max_popup_width_px,
            )
            for index, chunk in enumerate(chunks):
                following = chunks[index + 1][0].start_ms if index + 1 < len(chunks) else None
                end_ms = chunk[-1].end_ms
                if following is not None and following - end_ms <= _POPUP_HOLD_MS:
                    end_ms = following
                is_top = should_use_top_caption_placement(chunk[0].start_ms, end_ms, face_intervals)
                is_plate = event_needs_plate(chunk[0].start_ms, end_ms, plate_intervals)
                align_tag = "\\an8" if is_top else "\\an2"
                y_pos = DEFAULT_TOP_MARGIN_V if is_top else (play_res_y - theme.margin_v)
                dim_st = (
                    ("KurdishTopPlateDim" if is_plate else "KurdishTopDim")
                    if is_top
                    else ("KurdishPlateDim" if is_plate else "KurdishDim")
                )

                positions = compute_rtl_word_positions(
                    chunk,
                    font_name=font_name,
                    font_size=font_size,
                    canvas_width=play_res_x,
                    fonts_dir=fonts_dir,
                )
                t_0 = chunk[0].start_ms
                time_points = sorted(
                    set([t_0] + [w.start_ms for w in chunk] + [w.end_ms for w in chunk] + [end_ms])
                )
                for ta, tb in pairwise(time_points):
                    if tb <= ta:
                        continue
                    active_idx = next(
                        (i for i, w in enumerate(chunk) if w.start_ms <= ta and tb <= w.end_ms),
                        None,
                    )
                    for j, (word, x_pos) in enumerate(positions):
                        if j == active_idx:
                            cat = (
                                classify_kurdish_emphasis(word.w)
                                if keyword_emphasis
                                else EmphasisCategory.DEFAULT
                            )
                            st = choose_style(ta, tb, category=cat)
                        else:
                            st = dim_st
                        escaped_word = _escape_ass_text(word.w)
                        word_text = f"{{{align_tag}\\pos({x_pos},{y_pos})}}{escaped_word}"
                        events.append(event(ta, tb, word_text, style_name=st))
            continue

        if max_words_per_event is None:
            lines = wrap_caption_lines(
                sentence.words,
                max_chars=max_chars_per_line,
                max_width_px=max_line_width_px,
            )
            style_name = choose_style(sentence.start_ms, sentence.end_ms)
            events.append(
                event(
                    sentence.start_ms,
                    sentence.end_ms,
                    "\\N".join(render(line) for line in lines),
                    style_name=style_name,
                )
            )
            continue
        # One event per popup. Each is short enough to fit one line, so no newline appears and
        # libass is never asked to lay a paragraph over live video.
        chunks = chunk_caption_events(
            sentence.words,
            max_words=max_words_per_event,
            max_chars=max_chars_per_line,
            max_width_px=max_popup_width_px,
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
            style_name = choose_style(chunk[0].start_ms, end_ms)
            events.append(event(chunk[0].start_ms, end_ms, render(chunk), style_name=style_name))

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
    source_video: Path | None = None,
    timestamp_s: float = 0.0,
) -> Path:
    """Burn one caption frame onto a black background or video source — the §4.3.6 golden render.

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

    sub_filter = subtitle_filter(ass_path, fonts_dir)
    if shaping != "complex":
        wrong = sub_filter.replace("shaping=complex", f"shaping={shaping}", 1)
        if wrong == sub_filter:
            raise ValueError(
                f"could not render with shaping={shaping!r}: {sub_filter!r} carries no "
                f"`shaping=complex` to replace, so this would silently render the right way "
                f"and the negative control would be measuring nothing"
            )
        sub_filter = wrong

    if source_video is not None:
        crop = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        filter_string = f"{crop},{sub_filter}"
        inputs = [
            "-ss",
            f"{timestamp_s:.3f}",
            "-i",
            str(source_video),
        ]
    else:
        filter_string = sub_filter
        inputs = [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:d=1",
        ]

    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            *inputs,
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
