"""HawEdit V8 Module 3 — Viral TikTok Animated Kurdish (Sorani RTL) Subtitles (D-383).

Three strict fail-stop building blocks:
1. :func:`chunk_viral_kurdish_words` — 1 word (``>= 8`` chars or power word), 2 words
   default, 3 words ONLY when ``<= 14`` chars total & no pause ``> 260 ms``, never 4+.
2. :func:`render_tiktok_overlay_video` — HarfBuzz (``uharfbuzz``, Apache-2.0) + Skia
   (``skia-python``, BSD-3-Clause) 1080×1920 alpha overlay piped to FFmpeg with spring
   pop-in, sliding rounded active-word pill (Studio Gold / Electric Lime), and hook title.
3. :func:`build_viral_tiktok_ass` — Zero-dep ``libass`` fallback with 0.00 px ghosting.
"""

from __future__ import annotations

import importlib
import math
import re
import subprocess
import tempfile
import unicodedata
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.captions import DEFAULT_CAPTION_FONT, RTL_MARK, assert_font_covers_kurdish, find_ffmpeg
from hawedit.transcripts import Word
from hawedit.v8.styles import ClientStylePreset, resolve_client_style_preset

__all__ = [
    "ACTIVE_DARK_TEXT_HEX",
    "DEFAULT_FONT_SIZE_PX",
    "DEFAULT_LONG_WORD_CHARS",
    "DEFAULT_MAX_SHORT_3_CHARS",
    "DEFAULT_PAUSE_SPLIT_MS",
    "DEFAULT_Y_CENTER_PX",
    "END_CARD_DURATION_MS",
    "END_CARD_SPRING_MS",
    "HOOK_DURATION_MS",
    "INACTIVE_TEXT_HEX",
    "KURDISH_PROCLITICS",
    "PILL_GLIDE_MS",
    "POWER_PILL_HEX",
    "SPEAKER_BIO_END_MS",
    "SPEAKER_BIO_FADE_OUT_MS",
    "SPEAKER_BIO_SPRING_MS",
    "SPEAKER_BIO_START_MS",
    "SPRING_BOUNCE_MS",
    "STUDIO_GOLD_PILL_HEX",
    "VISUAL_INTERRUPT_CHEST_Y_PX",
    "VISUAL_INTERRUPT_FADE_OUT_MS",
    "VISUAL_INTERRUPT_MIN_START_MS",
    "VISUAL_INTERRUPT_SPRING_MS",
    "VISUAL_INTERRUPT_TOP_Y_PX",
    "TikTokSubtitleError",
    "ViralCaptionChunk",
    "ViralCaptionWord",
    "build_viral_tiktok_ass",
    "chunk_viral_kurdish_words",
    "pill_glide_progress",
    "render_tiktok_frame_rgba",
    "render_tiktok_overlay_video",
    "render_tiktok_preview_png",
    "spring_bounce_scale",
]

DEFAULT_MAX_SHORT_3_CHARS: Final = 14
DEFAULT_LONG_WORD_CHARS: Final = 8
DEFAULT_PAUSE_SPLIT_MS: Final = 260
DEFAULT_FONT_SIZE_PX: Final = 90
DEFAULT_Y_CENTER_PX: Final = 1380
SPRING_BOUNCE_MS: Final = 140
PILL_GLIDE_MS: Final = 60
HOOK_DURATION_MS: Final = 2400
VISUAL_INTERRUPT_MIN_START_MS: Final = 2600
VISUAL_INTERRUPT_TOP_Y_PX: Final = 210
VISUAL_INTERRUPT_CHEST_Y_PX: Final = 1130
VISUAL_INTERRUPT_SPRING_MS: Final = 140
VISUAL_INTERRUPT_FADE_OUT_MS: Final = 200
SPEAKER_BIO_START_MS: Final = 2600
SPEAKER_BIO_END_MS: Final = 6200
SPEAKER_BIO_SPRING_MS: Final = 160
SPEAKER_BIO_FADE_OUT_MS: Final = 260
END_CARD_DURATION_MS: Final = 2000
END_CARD_SPRING_MS: Final = 180

STUDIO_GOLD_PILL_HEX: Final = "#FFD700"
POWER_PILL_HEX: Final = "#B8FF2E"
ACTIVE_DARK_TEXT_HEX: Final = "#0B0B0F"
INACTIVE_TEXT_HEX: Final = "#FFFFFF"
KURDISH_PROCLITICS: Final[frozenset[str]] = frozenset({"و", "لە", "بە", "بۆ", "کە", "ئەم", "ئەو"})

_EDGE_PUNCT_RE: Final = re.compile(
    r"^[«»\"'“”‘’()\[\]{}،,.;:!؟?…\-–—\s]+|[«»\"'“”‘’()\[\]{}،,.;:!؟?…\-–—\s]+$"
)
_TERMINAL_PUNCT: Final[frozenset[str]] = frozenset(".!؟?؛…")
_HEX_COLOR_RE: Final = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ASS_BRACE_RE: Final = re.compile(r"[{}]")
_RTL_BIDI: Final[frozenset[str]] = frozenset({"R", "AL"})
_LTR_BIDI: Final[frozenset[str]] = frozenset({"L", "EN", "AN"})


class TikTokSubtitleError(RuntimeError):
    """Raised on any strict fail-stop violation in V8 viral subtitle rendering."""


@dataclass(frozen=True, slots=True)
class ViralCaptionWord:
    """One timed word inside a :class:`ViralCaptionChunk`."""

    index: int
    text: str
    start_ms: int
    end_ms: int
    is_power_word: bool = False

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"word index must be >= 0, got {self.index}")
        if not self.text or not self.text.strip():
            raise ValueError("word text must be non-empty")
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError(f"invalid word range {self.start_ms}..{self.end_ms} ms")


@dataclass(frozen=True, slots=True)
class ViralCaptionChunk:
    """One viral TikTok display chunk (strictly 1–2 words, or 3 short words ``<= 14`` chars)."""

    words: tuple[ViralCaptionWord, ...]
    start_ms: int
    end_ms: int
    has_power_word: bool = False
    accent_color: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.words) <= 3:
            raise ValueError(f"ViralCaptionChunk must hold 1..3 words, got {len(self.words)}")
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError(f"invalid chunk range {self.start_ms}..{self.end_ms} ms")
        if self.accent_color is not None and not _HEX_COLOR_RE.match(self.accent_color):
            raise ValueError(f"accent_color must be #RRGGBB hex, got {self.accent_color!r}")

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _clean(text: str) -> str:
    return _EDGE_PUNCT_RE.sub("", text.strip())


def _ends_sentence(text: str) -> bool:
    s = text.rstrip("«»\"'“”‘’()[] ")
    return bool(s) and s[-1] in _TERMINAL_PUNCT


def chunk_viral_kurdish_words(
    words: Sequence[Word],
    *,
    power_word_indices: AbstractSet[int] = frozenset(),
    max_short_3_chars: int = DEFAULT_MAX_SHORT_3_CHARS,
    long_word_chars: int = DEFAULT_LONG_WORD_CHARS,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> tuple[ViralCaptionChunk, ...]:
    """Chunk ASR words into 1–2 (max 3 short ``<= 14`` char) viral TikTok Kurdish beats."""
    if max_short_3_chars < 3:
        raise ValueError(f"max_short_3_chars must be >= 3, got {max_short_3_chars}")
    if long_word_chars < 1:
        raise ValueError(f"long_word_chars must be >= 1, got {long_word_chars}")
    if pause_split_ms < 0:
        raise ValueError(f"pause_split_ms must be >= 0, got {pause_split_ms}")
    if not words:
        return ()

    items: list[ViralCaptionWord] = []
    for idx, w in enumerate(words):
        raw = w.w.strip()
        is_pw = idx in power_word_indices
        parts = raw.split()
        if len(parts) <= 1:
            items.append(ViralCaptionWord(idx, raw, w.start_ms, w.end_ms, is_pw))
            continue
        # Expand space-separated multi-word ASR repairs (e.g. 'جوابت ئەیاتەوە') proportionally
        # so the 1-2 word / max-3-short (<= 14 chars) law holds strictly on rendered tokens.
        total_chars = sum(max(1, len(p)) for p in parts)
        span_ms = w.end_ms - w.start_ms
        cur_ms = w.start_ms
        for p_idx, part in enumerate(parts):
            if p_idx == len(parts) - 1:
                next_ms = w.end_ms
            else:
                share = max(1, round(span_ms * (max(1, len(part)) / total_chars)))
                next_ms = min(w.end_ms - (len(parts) - 1 - p_idx), cur_ms + share)
            if next_ms <= cur_ms:
                next_ms = cur_ms + 1
            items.append(ViralCaptionWord(idx, part, cur_ms, next_ms, is_pw))
            cur_ms = next_ms
    n = len(items)

    def is_solo(pos: int) -> bool:
        return items[pos].is_power_word or len(_clean(items[pos].text)) >= long_word_chars

    def can_pair(a: int, b: int) -> bool:
        return (
            b < n
            and not is_solo(a)
            and not is_solo(b)
            and not _ends_sentence(items[a].text)
            and (items[b].start_ms - items[a].end_ms) <= pause_split_ms
        )

    chunks: list[ViralCaptionChunk] = []
    i = 0
    while i < n:
        group: tuple[ViralCaptionWord, ...]
        if is_solo(i) or not can_pair(i, i + 1):
            group = (items[i],)
        else:
            can_third = (
                can_pair(i + 1, i + 2)
                and len(f"{items[i].text} {items[i + 1].text} {items[i + 2].text}")
                <= max_short_3_chars
            )
            if _clean(items[i + 1].text) in KURDISH_PROCLITICS:
                if can_third:
                    group = (items[i], items[i + 1], items[i + 2])
                elif can_pair(i + 1, i + 2):
                    group = (items[i],)  # avoid dangling proclitic at chunk end
                else:
                    group = (items[i], items[i + 1])
            elif can_third:
                ends_clause = (
                    i + 3 >= n
                    or _ends_sentence(items[i + 2].text)
                    or is_solo(i + 3)
                    or (items[i + 3].start_ms - items[i + 2].end_ms) > pause_split_ms
                )
                dangles = _clean(items[i + 2].text) in KURDISH_PROCLITICS and can_pair(i + 2, i + 3)
                leads_proc = _clean(items[i].text) in KURDISH_PROCLITICS and (
                    ends_clause or can_pair(i + 3, i + 4)
                )
                group = (
                    (items[i], items[i + 1], items[i + 2])
                    if not dangles and (ends_clause or leads_proc)
                    else (items[i], items[i + 1])
                )
            else:
                group = (items[i], items[i + 1])
        i += len(group)
        chunks.append(
            ViralCaptionChunk(
                words=group,
                start_ms=group[0].start_ms,
                end_ms=max(w.end_ms for w in group),
                has_power_word=any(w.is_power_word for w in group),
            )
        )
    return tuple(chunks)


def spring_bounce_scale(elapsed_ms: float, *, duration_ms: float = SPRING_BOUNCE_MS) -> float:
    """Damped spring-bounce pop ``0.82 -> 1.07 -> 1.00`` over ``duration_ms``."""
    if elapsed_ms <= 0.0:
        return 0.82
    if elapsed_ms >= duration_ms:
        return 1.00
    peak = duration_ms * 0.5
    if elapsed_ms < peak:
        u = elapsed_ms / peak
        return 0.82 + 0.25 * (1.0 - (1.0 - u) ** 3)
    u = (elapsed_ms - peak) / (duration_ms - peak)
    return 1.07 - 0.07 * (3.0 * u * u - 2.0 * u * u * u)


def pill_glide_progress(elapsed_ms: float, *, glide_ms: float = PILL_GLIDE_MS) -> float:
    """Cubic ease-out progress ``0.0 -> 1.0`` for active-word pill RTL glide."""
    if elapsed_ms <= 0.0:
        return 0.0
    if elapsed_ms >= glide_ms:
        return 1.0
    u = elapsed_ms / glide_ms
    return 1.0 - (1.0 - u) ** 3


def _hex_to_rgb(c: str) -> tuple[int, int, int]:
    if not _HEX_COLOR_RE.match(c):
        raise ValueError(f"expected #RRGGBB hex color, got {c!r}")
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))


def _hex_to_ass_bgr(c: str) -> str:
    r, g, b = _hex_to_rgb(c)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _has_rtl(text: str) -> bool:
    return any(unicodedata.bidirectional(ch) in _RTL_BIDI for ch in text)


def _split_directional_runs(text: str, *, base_rtl: bool) -> list[tuple[str, bool]]:
    """Split text into ``(run, is_rtl)`` segments using stdlib ``unicodedata`` (UAX #9 N1/N2).

    Neutral/weak characters (spaces, hyphens, punctuation) between opposing directional
    runs resolve to ``base_rtl`` so tokens like ``AIـەکە``, ``AI-یەکە``, and
    ``AI و مرۆڤ`` keep Latin characters strictly LTR while preserving RTL word/suffix order.
    """
    if not text:
        return []
    n = len(text)
    classes = [unicodedata.bidirectional(ch) for ch in text]
    strong_dirs: list[bool | None] = [
        True if bc in _RTL_BIDI else (False if bc in _LTR_BIDI else None) for bc in classes
    ]
    if all(d is None for d in strong_dirs):
        return [(text, base_rtl)]

    # Attach European terminators (e.g. '%' in '100%', '$' in '$50') to adjacent EN digits.
    for idx, bc in enumerate(classes):
        if bc == "ET" and (
            (idx > 0 and classes[idx - 1] == "EN") or (idx + 1 < n and classes[idx + 1] == "EN")
        ):
            strong_dirs[idx] = False

    # Resolve remaining weak/neutral chars via nearest surrounding strong runs (UAX #9 N1/N2).
    resolved: list[bool] = []
    for idx, d in enumerate(strong_dirs):
        if d is not None:
            resolved.append(d)
            continue
        prev_d = base_rtl
        for j in range(idx - 1, -1, -1):
            cand = strong_dirs[j]
            if cand is not None:
                prev_d = cand
                break
        next_d = base_rtl
        for j in range(idx + 1, n):
            cand = strong_dirs[j]
            if cand is not None:
                next_d = cand
                break
        resolved.append(prev_d if prev_d == next_d else base_rtl)

    runs: list[tuple[str, bool]] = []
    start = 0
    for idx in range(1, n):
        if resolved[idx] != resolved[start]:
            runs.append((text[start:idx], resolved[start]))
            start = idx
    runs.append((text[start:], resolved[start]))
    return runs


def _load_skia_harfbuzz() -> tuple[Any, Any]:
    """Load BSD-3-Clause ``skia-python`` and Apache-2.0 ``uharfbuzz`` fail-stop."""
    try:
        skia_mod = importlib.import_module("skia")
    except ImportError as exc:
        raise TikTokSubtitleError("skia-python is required for V8 RGBA subtitles") from exc
    try:
        hb_mod = importlib.import_module("uharfbuzz")
    except ImportError as exc:
        raise TikTokSubtitleError("uharfbuzz is required for V8 Kurdish RTL shaping") from exc
    return skia_mod, hb_mod


@dataclass(frozen=True, slots=True)
class _ShapedWord:
    blob: Any
    advance_px: float
    ink_left: float
    ink_top: float
    ink_right: float
    ink_bottom: float


@dataclass(frozen=True, slots=True)
class _LaidOutWord:
    word: ViralCaptionWord
    shaped: _ShapedWord
    x_origin: float
    pill_left: float
    pill_right: float


@dataclass(frozen=True, slots=True)
class _LaidOutChunk:
    chunk: ViralCaptionChunk
    words: tuple[_LaidOutWord, ...]
    baseline_y: float
    pill_top: float
    pill_bottom: float
    center_x: float
    center_y: float
    font_size_px: float


@dataclass(frozen=True, slots=True)
class _HookTitleLayout:
    lines: tuple[tuple[_ShapedWord, float, float], ...]
    box_left: float
    box_top: float
    box_right: float
    box_bottom: float
    center_x: float
    center_y: float
    accent_bar_rect: tuple[float, float, float, float] | None = None
    accent_line_index: int | None = None


@dataclass(frozen=True, slots=True)
class _VisualInterruptLayout:
    start_ms: int
    end_ms: int
    position: str
    border_rgb: tuple[int, int, int]
    lines: tuple[tuple[_ShapedWord, float, float], ...]
    box_left: float
    box_top: float
    box_right: float
    box_bottom: float
    center_x: float
    center_y: float
    dirty_band: tuple[int, int]
    stat_hero: tuple[_ShapedWord, float, float] | None = None
    divider_rect: tuple[float, float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class _SpeakerBioLayout:
    start_ms: int
    end_ms: int
    is_rtl: bool
    name_line: tuple[_ShapedWord, float, float]
    role_line: tuple[_ShapedWord, float, float] | None
    box_left: float
    box_top: float
    box_right: float
    box_bottom: float
    accent_bar_rect: tuple[float, float, float, float]
    center_x: float
    center_y: float
    dirty_band: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _EndCardLayout:
    start_ms: int
    end_ms: int
    title_lines: tuple[tuple[_ShapedWord, float, float], ...]
    subtitle_lines: tuple[tuple[_ShapedWord, float, float], ...]
    handle_line: tuple[_ShapedWord, float, float] | None
    handle_pill_rect: tuple[float, float, float, float] | None
    accent_bar_rect: tuple[float, float, float, float]
    box_left: float
    box_top: float
    box_right: float
    box_bottom: float
    center_x: float
    center_y: float
    dirty_band: tuple[int, int]


class _SkiaHarfBuzzShaper:
    """HarfBuzz RTL Kurdish shaper paired with a matching Skia variable-weight typeface."""

    def __init__(self, font_path: Path, *, weight: float = 800.0) -> None:
        if not font_path.is_file():
            raise TikTokSubtitleError(f"subtitle font file does not exist: {font_path}")
        assert_font_covers_kurdish(font_path)
        skia, hb = _load_skia_harfbuzz()
        self.skia: Any = skia
        self._hb: Any = hb
        hb_face = hb.Face(hb.Blob(font_path.read_bytes()))
        self._upem = float(hb_face.upem)
        if self._upem <= 0.0:
            raise TikTokSubtitleError(f"font {font_path} reports invalid upem={self._upem}")
        hb_font = hb.Font(hb_face)
        tf = skia.Typeface.MakeFromFile(str(font_path))
        if tf is None:
            raise TikTokSubtitleError(f"Skia could not load typeface from {font_path}")
        params = tf.getVariationDesignParameters()
        wght = next((p for p in params if p.tag == 0x77676874), None) if params else None
        if wght is not None:
            w_val = max(float(wght.min), min(float(wght.max), weight))
            hb_font.set_variations({"wght": w_val})
            coord = skia.FontArguments.VariationPosition.Coordinate(wght.tag, w_val)
            pos = skia.FontArguments.VariationPosition(
                skia.FontArguments.VariationPosition.Coordinates([coord])
            )
            cloned = tf.makeClone(skia.FontArguments().setVariationDesignPosition(pos))
            if cloned is not None:
                tf = cloned
        self._hb_font: Any = hb_font
        self._typeface: Any = tf
        self._sk_fonts: dict[int, Any] = {}

    def _sk_font(self, size_px: float) -> Any:
        key = round(size_px * 10)
        if key not in self._sk_fonts:
            f = self.skia.Font(self._typeface, size_px)
            f.setSubpixel(True)
            f.setEdging(self.skia.Font.Edging.kAntiAlias)
            self._sk_fonts[key] = f
        return self._sk_fonts[key]

    def shape_token(self, text: str, size_px: float, *, base_rtl: bool = True) -> _ShapedWord:
        skia, hb, scale = self.skia, self._hb, size_px / self._upem
        runs = _split_directional_runs(text, base_rtl=base_rtl)
        glyphs: list[int] = []
        positions: list[Any] = []
        pen_x = 0.0
        for run_text, run_rtl in reversed(runs) if base_rtl else runs:
            buf = hb.Buffer()
            buf.add_str(run_text)
            buf.direction, buf.script, buf.language = (
                ("rtl", "Arab", "ckb") if run_rtl else ("ltr", "Latn", "en")
            )
            hb.shape(self._hb_font, buf)
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
                gid = int(info.codepoint)
                if gid == 0:
                    raise TikTokSubtitleError(f"HarfBuzz emitted .notdef for {run_text!r}")
                glyphs.append(gid)
                positions.append(skia.Point(pen_x + pos.x_offset * scale, -pos.y_offset * scale))
                pen_x += pos.x_advance * scale
        if not glyphs:
            raise TikTokSubtitleError(f"HarfBuzz shaped zero glyphs for {text!r}")
        builder = skia.TextBlobBuilder()
        builder.allocRunPos(self._sk_font(size_px), glyphs, positions)
        blob = builder.make()
        if blob is None:
            raise TikTokSubtitleError(f"Skia TextBlobBuilder returned None for {text!r}")
        b = blob.bounds()
        return _ShapedWord(
            blob, pen_x, float(b.left()), float(b.top()), float(b.right()), float(b.bottom())
        )

    def layout_chunk(
        self, chunk: ViralCaptionChunk, *, width: int, y_center_px: int
    ) -> _LaidOutChunk:
        rtl = any(_has_rtl(w.text) for w in chunk.words)
        max_w = float(width - 152)

        def measure(px: float) -> tuple[list[_ShapedWord], float, float]:
            shaped = [self.shape_token(w.text, px, base_rtl=rtl) for w in chunk.words]
            gap = px * 0.48
            return shaped, gap, sum(s.advance_px for s in shaped) + gap * (len(shaped) - 1)

        px = float(DEFAULT_FONT_SIZE_PX)
        shaped, gap, total_w = measure(px)
        pad_x = px * 0.24
        if total_w + 2.0 * pad_x > max_w and total_w > 0.0:
            px = max(46.0, px * ((max_w - 2.0 * pad_x) / total_w))
            shaped, gap, total_w = measure(px)
            pad_x = px * 0.24

        origins: list[float] = []
        cursor = (width + total_w) * 0.5 if rtl else (width - total_w) * 0.5
        for s in shaped:
            if rtl:
                cursor -= s.advance_px
                origins.append(cursor)
                cursor -= gap
            else:
                origins.append(cursor)
                cursor += s.advance_px + gap

        ascent = min(min(s.ink_top for s in shaped), -px * 0.72)
        descent = max(max(s.ink_bottom for s in shaped), px * 0.28)
        baseline_y = float(y_center_px) - (ascent + descent) * 0.5
        laid_out = tuple(
            _LaidOutWord(
                w,
                s,
                x,
                x + min(0.0, s.ink_left) - pad_x,
                x + max(s.advance_px, s.ink_right) + pad_x,
            )
            for w, s, x in zip(chunk.words, shaped, origins, strict=True)
        )
        return _LaidOutChunk(
            chunk,
            laid_out,
            baseline_y,
            baseline_y + ascent - px * 0.16,
            baseline_y + descent + px * 0.18,
            width * 0.5,
            float(y_center_px),
            px,
        )

    def layout_hook_title(
        self, hook_title_ckb: str, *, width: int, y_top_px: float = 250.0
    ) -> _HookTitleLayout:
        tokens = hook_title_ckb.strip().split()
        if not tokens:
            raise ValueError("hook_title_ckb must not be whitespace-only")
        lines_text = _balance_hook_lines(
            tokens, max_single_line_chars=16 if len(tokens) >= 3 else 24
        )
        max_w, pad_x, pad_y, size = float(width - 180), 34.0, 22.0, 54.0
        accent_h, accent_gap = 5.0, 12.0
        shaped = [self.shape_token(t, size, base_rtl=_has_rtl(t)) for t in lines_text]
        widest = max(s.advance_px for s in shaped)
        if widest + 2.0 * pad_x > max_w and widest > 0.0:
            size = max(34.0, size * ((max_w - 2.0 * pad_x) / widest))
            shaped = [self.shape_token(t, size, base_rtl=_has_rtl(t)) for t in lines_text]
            widest = max(s.advance_px for s in shaped)
        accent_w = max(84.0, min(widest * 0.44, 150.0))
        accent_top = y_top_px + 14.0
        accent_bar = (
            (width - accent_w) * 0.5,
            accent_top,
            (width + accent_w) * 0.5,
            accent_top + accent_h,
        )
        first_base = accent_top + accent_h + accent_gap - min(s.ink_top for s in shaped)
        placed = tuple(
            (s, (width - s.advance_px) * 0.5, first_base + idx * size * 1.32)
            for idx, s in enumerate(shaped)
        )
        box_bottom = placed[-1][2] + max(s.ink_bottom for s in shaped) + pad_y
        accent_idx: int | None = len(shaped) - 1 if len(shaped) >= 2 else None
        return _HookTitleLayout(
            placed,
            (width - widest) * 0.5 - pad_x,
            y_top_px,
            (width + widest) * 0.5 + pad_x,
            box_bottom,
            width * 0.5,
            (y_top_px + box_bottom) * 0.5,
            accent_bar_rect=accent_bar,
            accent_line_index=accent_idx,
        )

    def layout_visual_interrupt(
        self,
        start_ms: int,
        end_ms: int,
        text_ckb: str,
        position: str,
        *,
        width: int,
        height: int,
        y_center_px: int,
        preset: ClientStylePreset,
    ) -> _VisualInterruptLayout:
        tokens = text_ckb.strip().split()
        if not tokens:
            raise ValueError("visual_interrupt text_ckb must not be empty")
        border_hex = (
            preset.interrupt_top_border_hex
            if position == "top"
            else preset.interrupt_chest_border_hex
        )
        border_rgb = _hex_to_rgb(border_hex)

        # Animated Stat Card mode when formatted as "<HERO_STAT> | <KURDISH_LABEL>"
        if " | " in text_ckb:
            hero_raw, label_raw = (part.strip() for part in text_ckb.split(" | ", 1))
            if hero_raw and label_raw:
                max_w, pad_x, pad_y = float(width - 180), 42.0, 22.0
                hero_sz, label_sz = 82.0, 40.0
                hero_s = self.shape_token(hero_raw, hero_sz, base_rtl=_has_rtl(hero_raw))
                if hero_s.advance_px + 2.0 * pad_x > max_w and hero_s.advance_px > 0.0:
                    hero_sz = max(48.0, hero_sz * ((max_w - 2.0 * pad_x) / hero_s.advance_px))
                    hero_s = self.shape_token(hero_raw, hero_sz, base_rtl=_has_rtl(hero_raw))
                label_lines = _balance_hook_lines(label_raw.split(), max_single_line_chars=24)
                shaped_labels = [
                    self.shape_token(t, label_sz, base_rtl=_has_rtl(t)) for t in label_lines
                ]
                widest_lbl = max(s.advance_px for s in shaped_labels)
                if widest_lbl + 2.0 * pad_x > max_w and widest_lbl > 0.0:
                    label_sz = max(28.0, label_sz * ((max_w - 2.0 * pad_x) / widest_lbl))
                    shaped_labels = [
                        self.shape_token(t, label_sz, base_rtl=_has_rtl(t)) for t in label_lines
                    ]
                    widest_lbl = max(s.advance_px for s in shaped_labels)
                widest = max(hero_s.advance_px, widest_lbl, 220.0)
                hero_h = hero_s.ink_bottom - hero_s.ink_top
                div_gap_top, div_h, div_gap_bot = 14.0, 4.0, 16.0
                lbl_step = label_sz * 1.28
                lbl_top = min(s.ink_top for s in shaped_labels)
                lbl_bot = max(s.ink_bottom for s in shaped_labels)
                lbl_h = (len(shaped_labels) - 1) * lbl_step + (lbl_bot - lbl_top)
                box_h = pad_y + hero_h + div_gap_top + div_h + div_gap_bot + lbl_h + pad_y
                target_y = (
                    float(VISUAL_INTERRUPT_TOP_Y_PX + 28)
                    if position == "top"
                    else float(VISUAL_INTERRUPT_CHEST_Y_PX)
                )
                if position == "chest" and y_center_px > 400:
                    target_y = min(target_y, float(y_center_px - 110) - box_h * 0.5)
                box_top = max(72.0, min(float(height) - box_h - 72.0, target_y - box_h * 0.5))
                box_bottom = box_top + box_h
                hero_base = box_top + pad_y - hero_s.ink_top
                div_y = box_top + pad_y + hero_h + div_gap_top
                div_w = min(widest * 0.65, 220.0)
                div_rect = ((width - div_w) * 0.5, div_y, (width + div_w) * 0.5, div_y + div_h)
                first_lbl_base = div_y + div_h + div_gap_bot - lbl_top
                placed_lbl = tuple(
                    (s, (width - s.advance_px) * 0.5, first_lbl_base + idx * lbl_step)
                    for idx, s in enumerate(shaped_labels)
                )
                dirty = (max(0, math.floor(box_top - 64)), min(height, math.ceil(box_bottom + 64)))
                return _VisualInterruptLayout(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    position=position,
                    border_rgb=border_rgb,
                    lines=placed_lbl,
                    box_left=(width - widest) * 0.5 - pad_x,
                    box_top=box_top,
                    box_right=(width + widest) * 0.5 + pad_x,
                    box_bottom=box_bottom,
                    center_x=width * 0.5,
                    center_y=(box_top + box_bottom) * 0.5,
                    dirty_band=dirty,
                    stat_hero=(hero_s, (width - hero_s.advance_px) * 0.5, hero_base),
                    divider_rect=div_rect,
                )

        lines_text = _balance_hook_lines(tokens, max_single_line_chars=26)
        max_w, pad_x, pad_y, size = float(width - 160), 34.0, 20.0, 48.0
        shaped = [self.shape_token(t, size, base_rtl=_has_rtl(t)) for t in lines_text]
        widest = max(s.advance_px for s in shaped)
        if widest + 2.0 * pad_x > max_w and widest > 0.0:
            size = max(32.0, size * ((max_w - 2.0 * pad_x) / widest))
            shaped = [self.shape_token(t, size, base_rtl=_has_rtl(t)) for t in lines_text]
            widest = max(s.advance_px for s in shaped)
        line_step = size * 1.30
        top_asc = min(s.ink_top for s in shaped)
        bot_desc = max(s.ink_bottom for s in shaped)
        content_h = (len(shaped) - 1) * line_step + (bot_desc - top_asc)
        box_h = content_h + 2.0 * pad_y

        target_y = (
            float(VISUAL_INTERRUPT_TOP_Y_PX)
            if position == "top"
            else float(VISUAL_INTERRUPT_CHEST_Y_PX)
        )
        # Keep chest badge strictly above bottom subtitle pill (zero overlap).
        if position == "chest" and y_center_px > 400:
            max_center = float(y_center_px - 110) - box_h * 0.5
            target_y = min(target_y, max_center)
        box_top = max(72.0, min(float(height) - box_h - 72.0, target_y - box_h * 0.5))
        box_bottom = box_top + box_h
        first_base = box_top + pad_y - top_asc
        placed = tuple(
            (s, (width - s.advance_px) * 0.5, first_base + idx * line_step)
            for idx, s in enumerate(shaped)
        )
        dirty = (max(0, math.floor(box_top - 64)), min(height, math.ceil(box_bottom + 64)))
        return _VisualInterruptLayout(
            start_ms=start_ms,
            end_ms=end_ms,
            position=position,
            border_rgb=border_rgb,
            lines=placed,
            box_left=(width - widest) * 0.5 - pad_x,
            box_top=box_top,
            box_right=(width + widest) * 0.5 + pad_x,
            box_bottom=box_bottom,
            center_x=width * 0.5,
            center_y=(box_top + box_bottom) * 0.5,
            dirty_band=dirty,
        )

    def layout_speaker_bio(
        self,
        name_ckb: str,
        role_ckb: str | None,
        *,
        width: int,
        height: int,
        y_center_px: int,
        start_ms: int = SPEAKER_BIO_START_MS,
        end_ms: int = SPEAKER_BIO_END_MS,
    ) -> _SpeakerBioLayout:
        is_rtl = _has_rtl(name_ckb) or (role_ckb is not None and _has_rtl(role_ckb))
        name_sz, role_sz = 42.0, 30.0
        pad_x, pad_y, bar_w, bar_gap, edge_pad, line_gap = 30.0, 20.0, 7.0, 20.0, 18.0, 14.0
        max_text_w = float(width - 280) - (pad_x + edge_pad + bar_w + bar_gap)

        name_s = self.shape_token(name_ckb, name_sz, base_rtl=_has_rtl(name_ckb))
        role_s = (
            self.shape_token(role_ckb, role_sz, base_rtl=_has_rtl(role_ckb))
            if role_ckb is not None
            else None
        )
        widest = max(name_s.advance_px, role_s.advance_px if role_s is not None else 0.0)
        if widest > max_text_w and widest > 0.0:
            shrink = max(0.62, max_text_w / widest)
            name_sz *= shrink
            role_sz *= shrink
            name_s = self.shape_token(name_ckb, name_sz, base_rtl=_has_rtl(name_ckb))
            role_s = (
                self.shape_token(role_ckb, role_sz, base_rtl=_has_rtl(role_ckb))
                if role_ckb is not None
                else None
            )
            widest = max(name_s.advance_px, role_s.advance_px if role_s is not None else 0.0)

        text_w = max(120.0, widest)
        box_w = text_w + pad_x + edge_pad + bar_w + bar_gap
        name_h = name_s.ink_bottom - name_s.ink_top
        role_h = (role_s.ink_bottom - role_s.ink_top) if role_s is not None else 0.0
        content_h = name_h + (line_gap + role_h if role_s is not None else 0.0)
        box_h = content_h + 2.0 * pad_y

        # Place cleanly BELOW bottom TikTok subtitle pill (>= 150 px from pill center)
        # so it never collides with subtitle pill, hook card (0..2400 ms), or chest badges.
        preferred_top = float(y_center_px + 150)
        if preferred_top + box_h <= float(height) - 96.0:
            box_top = preferred_top
        else:
            box_top = max(72.0, float(y_center_px - 150) - box_h)
        box_bottom = box_top + box_h

        if is_rtl:
            # Anchor inside TikTok right safe margin (136 px clear of right-edge UI buttons).
            box_right = float(width - 136)
            box_left = max(72.0, box_right - box_w)
            bar_right = box_right - edge_pad
            bar_left = bar_right - bar_w
            text_right = bar_left - bar_gap
            name_x = text_right - name_s.advance_px
            role_x = (text_right - role_s.advance_px) if role_s is not None else 0.0
        else:
            box_left = 96.0
            box_right = min(float(width - 136), box_left + box_w)
            bar_left = box_left + edge_pad
            bar_right = bar_left + bar_w
            text_left = bar_right + bar_gap
            name_x = text_left
            role_x = text_left

        name_base = box_top + pad_y - name_s.ink_top
        role_line = (
            (role_s, role_x, name_base + name_s.ink_bottom + line_gap - role_s.ink_top)
            if role_s is not None
            else None
        )
        accent_bar = (bar_left, box_top + 16.0, bar_right, box_bottom - 16.0)
        dirty = (max(0, math.floor(box_top - 48)), min(height, math.ceil(box_bottom + 48)))
        return _SpeakerBioLayout(
            start_ms=start_ms,
            end_ms=end_ms,
            is_rtl=is_rtl,
            name_line=(name_s, name_x, name_base),
            role_line=role_line,
            box_left=box_left,
            box_top=box_top,
            box_right=box_right,
            box_bottom=box_bottom,
            accent_bar_rect=accent_bar,
            center_x=(box_left + box_right) * 0.5,
            center_y=(box_top + box_bottom) * 0.5,
            dirty_band=dirty,
        )

    def layout_end_card(
        self,
        title_ckb: str,
        subtitle_ckb: str | None,
        handle: str | None,
        *,
        start_ms: int,
        end_ms: int,
        width: int,
        height: int,
        y_center_px: int,
    ) -> _EndCardLayout:
        max_inner_w = float(width - 220)
        pad_x, pad_y = 52.0, 44.0
        accent_w, accent_h, accent_gap = 88.0, 7.0, 28.0

        title_texts = _balance_hook_lines(title_ckb.split(), max_single_line_chars=22)
        title_sz = 56.0
        title_shaped = [self.shape_token(t, title_sz, base_rtl=_has_rtl(t)) for t in title_texts]
        title_widest = max(s.advance_px for s in title_shaped)
        if title_widest > max_inner_w and title_widest > 0.0:
            title_sz = max(34.0, title_sz * (max_inner_w / title_widest))
            title_shaped = [
                self.shape_token(t, title_sz, base_rtl=_has_rtl(t)) for t in title_texts
            ]
            title_widest = max(s.advance_px for s in title_shaped)
        title_step = title_sz * 1.32
        t_asc = min(s.ink_top for s in title_shaped)
        t_desc = max(s.ink_bottom for s in title_shaped)
        title_h = (len(title_shaped) - 1) * title_step + (t_desc - t_asc)

        sub_shaped: list[_ShapedWord] = []
        sub_sz, sub_step, sub_asc, sub_h, sub_widest = 36.0, 0.0, 0.0, 0.0, 0.0
        if subtitle_ckb is not None:
            sub_texts = _balance_hook_lines(subtitle_ckb.split(), max_single_line_chars=30)
            sub_shaped = [self.shape_token(t, sub_sz, base_rtl=_has_rtl(t)) for t in sub_texts]
            sub_widest = max(s.advance_px for s in sub_shaped)
            if sub_widest > max_inner_w and sub_widest > 0.0:
                sub_sz = max(24.0, sub_sz * (max_inner_w / sub_widest))
                sub_shaped = [self.shape_token(t, sub_sz, base_rtl=_has_rtl(t)) for t in sub_texts]
                sub_widest = max(s.advance_px for s in sub_shaped)
            sub_step = sub_sz * 1.30
            sub_asc = min(s.ink_top for s in sub_shaped)
            sub_desc = max(s.ink_bottom for s in sub_shaped)
            sub_h = (len(sub_shaped) - 1) * sub_step + (sub_desc - sub_asc)

        handle_shaped: _ShapedWord | None = None
        h_pad_x, h_pad_y, handle_pill_w, handle_pill_h = 34.0, 16.0, 0.0, 0.0
        if handle is not None:
            h_sz = 38.0
            handle_shaped = self.shape_token(handle, h_sz, base_rtl=_has_rtl(handle))
            if (
                handle_shaped.advance_px + 2.0 * h_pad_x > max_inner_w
                and handle_shaped.advance_px > 0.0
            ):
                h_sz = max(24.0, h_sz * ((max_inner_w - 2.0 * h_pad_x) / handle_shaped.advance_px))
                handle_shaped = self.shape_token(handle, h_sz, base_rtl=_has_rtl(handle))
            handle_pill_w = handle_shaped.advance_px + 2.0 * h_pad_x
            handle_pill_h = (handle_shaped.ink_bottom - handle_shaped.ink_top) + 2.0 * h_pad_y

        sub_gap = 24.0 if sub_shaped else 0.0
        handle_gap = 32.0 if handle_shaped is not None else 0.0
        content_h = accent_h + accent_gap + title_h + sub_gap + sub_h + handle_gap + handle_pill_h
        box_h = content_h + 2.0 * pad_y
        widest = max(title_widest, sub_widest, handle_pill_w)
        box_w = min(float(width - 120), max(560.0, widest + 2.0 * pad_x))

        # Vertically centered in upper-middle frame, keeping clear of bottom subtitle pill.
        target_cy = float(height) * 0.46
        if y_center_px > 600:
            target_cy = min(target_cy, float(y_center_px - 150) - box_h * 0.5)
        box_top = max(140.0, min(float(height) - box_h - 140.0, target_cy - box_h * 0.5))
        box_bottom = box_top + box_h
        box_left = (width - box_w) * 0.5
        box_right = (width + box_w) * 0.5

        cursor_y = box_top + pad_y
        accent_bar = (
            width * 0.5 - accent_w * 0.5,
            cursor_y,
            width * 0.5 + accent_w * 0.5,
            cursor_y + accent_h,
        )
        cursor_y += accent_h + accent_gap

        title_first_base = cursor_y - t_asc
        title_lines = tuple(
            (s, (width - s.advance_px) * 0.5, title_first_base + idx * title_step)
            for idx, s in enumerate(title_shaped)
        )
        cursor_y += title_h

        subtitle_lines: tuple[tuple[_ShapedWord, float, float], ...] = ()
        if sub_shaped:
            cursor_y += sub_gap
            sub_first_base = cursor_y - sub_asc
            subtitle_lines = tuple(
                (s, (width - s.advance_px) * 0.5, sub_first_base + idx * sub_step)
                for idx, s in enumerate(sub_shaped)
            )
            cursor_y += sub_h

        handle_line: tuple[_ShapedWord, float, float] | None = None
        handle_pill_rect: tuple[float, float, float, float] | None = None
        if handle_shaped is not None:
            cursor_y += handle_gap
            hp_left = (width - handle_pill_w) * 0.5
            hp_right = (width + handle_pill_w) * 0.5
            hp_top = cursor_y
            hp_bottom = cursor_y + handle_pill_h
            handle_pill_rect = (hp_left, hp_top, hp_right, hp_bottom)
            h_base = hp_top + h_pad_y - handle_shaped.ink_top
            handle_line = (handle_shaped, (width - handle_shaped.advance_px) * 0.5, h_base)

        dirty = (max(0, math.floor(box_top - 64)), min(height, math.ceil(box_bottom + 64)))
        return _EndCardLayout(
            start_ms=start_ms,
            end_ms=end_ms,
            title_lines=title_lines,
            subtitle_lines=subtitle_lines,
            handle_line=handle_line,
            handle_pill_rect=handle_pill_rect,
            accent_bar_rect=accent_bar,
            box_left=box_left,
            box_top=box_top,
            box_right=box_right,
            box_bottom=box_bottom,
            center_x=width * 0.5,
            center_y=(box_top + box_bottom) * 0.5,
            dirty_band=dirty,
        )


def _balance_hook_lines(tokens: Sequence[str], *, max_single_line_chars: int = 24) -> list[str]:
    joined = " ".join(tokens)
    if len(tokens) <= 2 or len(joined) <= max_single_line_chars:
        return [joined]
    best = min(
        range(1, len(tokens)),
        key=lambda k: abs(len(" ".join(tokens[:k])) - len(" ".join(tokens[k:])))
        + (8 if _clean(tokens[k - 1]) in KURDISH_PROCLITICS else 0),
    )
    return [" ".join(tokens[:best]), " ".join(tokens[best:])]


def _active_word_state(
    layout: _LaidOutChunk, t_ms: float, preset: ClientStylePreset
) -> tuple[int, float, float, tuple[int, int, int], int, tuple[int, int, int], bool]:
    words = layout.words
    idx = 0
    for k, lw in enumerate(words):
        if t_ms >= lw.word.start_ms:
            idx = k
        else:
            break

    def word_colors(lw: _LaidOutWord) -> tuple[tuple[int, int, int], int, tuple[int, int, int]]:
        if lw.word.is_power_word:
            return (_hex_to_rgb(preset.power_pill_hex), 255, _hex_to_rgb(preset.power_text_hex))
        pill_hex = layout.chunk.accent_color or preset.active_pill_hex
        return (
            _hex_to_rgb(pill_hex),
            preset.active_pill_alpha,
            _hex_to_rgb(preset.active_text_hex),
        )

    cur = words[idx]
    cur_rgb, cur_alpha, cur_ink = word_colors(cur)
    if idx == 0 or (dt := t_ms - cur.word.start_ms) >= PILL_GLIDE_MS:
        return (
            idx,
            cur.pill_left,
            cur.pill_right,
            cur_rgb,
            cur_alpha,
            cur_ink,
            cur.word.is_power_word,
        )
    prev = words[idx - 1]
    prev_rgb, prev_alpha, prev_ink = word_colors(prev)
    g = pill_glide_progress(dt)
    rgb = (
        round(prev_rgb[0] + (cur_rgb[0] - prev_rgb[0]) * g),
        round(prev_rgb[1] + (cur_rgb[1] - prev_rgb[1]) * g),
        round(prev_rgb[2] + (cur_rgb[2] - prev_rgb[2]) * g),
    )
    ink = (
        round(prev_ink[0] + (cur_ink[0] - prev_ink[0]) * g),
        round(prev_ink[1] + (cur_ink[1] - prev_ink[1]) * g),
        round(prev_ink[2] + (cur_ink[2] - prev_ink[2]) * g),
    )
    fill_alpha = round(prev_alpha + (cur_alpha - prev_alpha) * g)
    return (
        idx,
        prev.pill_left + (cur.pill_left - prev.pill_left) * g,
        prev.pill_right + (cur.pill_right - prev.pill_right) * g,
        rgb,
        fill_alpha,
        ink,
        cur.word.is_power_word,
    )


def _draw_hook_title(
    skia: Any, canvas: Any, hook: _HookTitleLayout, t_ms: float, preset: ClientStylePreset
) -> None:
    if not 0.0 <= t_ms < HOOK_DURATION_MS:
        return
    scale = spring_bounce_scale(t_ms, duration_ms=140.0)
    alpha = (
        0.35 + 0.65 * (t_ms / 45.0)
        if t_ms < 45.0
        else (
            max(0.0, (HOOK_DURATION_MS - t_ms) / 250.0) if t_ms > HOOK_DURATION_MS - 250.0 else 1.0
        )
    )
    rrect = skia.RRect.MakeRectXY(
        skia.Rect.MakeLTRB(hook.box_left, hook.box_top, hook.box_right, hook.box_bottom), 24.0, 24.0
    )
    hr, hg, hb, ha = preset.hook_fill_rgba
    br, bg, bb = _hex_to_rgb(preset.hook_border_hex)
    canvas.save()
    canvas.translate(hook.center_x, hook.center_y)
    canvas.scale(scale, scale)
    canvas.translate(-hook.center_x, -hook.center_y)
    sh = skia.Paint(
        AntiAlias=True,
        Color=skia.ColorSetARGB(round(145 * alpha), 0, 0, 0),
        MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 11.0),
    )
    canvas.save()
    canvas.translate(0.0, 8.0)
    canvas.drawRRect(rrect, sh)
    canvas.restore()
    canvas.drawRRect(
        rrect, skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(round(ha * alpha), hr, hg, hb))
    )
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=2.0,
            Color=skia.ColorSetARGB(round(preset.hook_border_alpha * alpha), br, bg, bb),
        ),
    )
    full_a = max(0, min(255, round(alpha * 255)))
    if hook.accent_bar_rect is not None:
        al, at, ar_, ab = hook.accent_bar_rect
        bar_rrect = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(al, at, ar_, ab), 3.0, 3.0)
        canvas.drawRRect(
            bar_rrect,
            skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(full_a, 255, 215, 0)),
        )
    t_sh = skia.Paint(
        AntiAlias=True,
        Color=skia.ColorSetARGB(round(170 * alpha), 0, 0, 0),
        MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 4.0),
    )
    t_fg = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(full_a, 255, 255, 255))
    t_gold = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(full_a, 255, 215, 0))
    for line_idx, (shaped, bx, by) in enumerate(hook.lines):
        canvas.drawTextBlob(shaped.blob, bx, by + 3.0, t_sh)
        paint = t_gold if hook.accent_line_index == line_idx else t_fg
        canvas.drawTextBlob(shaped.blob, bx, by, paint)
    canvas.restore()


def _draw_caption_chunk(
    skia: Any, canvas: Any, layout: _LaidOutChunk, t_ms: float, preset: ClientStylePreset
) -> None:
    dt = t_ms - layout.chunk.start_ms
    active_idx, p_left, p_right, rgb, pill_alpha, active_ink_rgb, is_power = _active_word_state(
        layout, t_ms, preset
    )
    scale = spring_bounce_scale(dt) * (1.04 if is_power else 1.0)
    fade = 1.0 if dt >= 40.0 else 0.35 + 0.65 * max(0.0, dt / 40.0)
    a_full = max(0, min(255, round(fade * 255)))
    a_pill = max(0, min(255, round(fade * pill_alpha)))
    radius = min(26.0, (layout.pill_bottom - layout.pill_top) * 0.28)
    pill = skia.RRect.MakeRectXY(
        skia.Rect.MakeLTRB(p_left, layout.pill_top, p_right, layout.pill_bottom), radius, radius
    )
    canvas.save()
    canvas.translate(layout.center_x, layout.center_y)
    canvas.scale(scale, scale)
    canvas.translate(-layout.center_x, -layout.center_y)
    canvas.save()
    canvas.translate(0.0, 8.0)
    canvas.drawRRect(
        pill,
        skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(round(165 * fade), 0, 0, 0),
            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 11.0),
        ),
    )
    canvas.restore()
    canvas.drawRRect(pill, skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_pill, *rgb)))
    if not is_power and preset.active_pill_border_hex is not None:
        border_rgb = _hex_to_rgb(preset.active_pill_border_hex)
        border_a = round(preset.active_pill_border_alpha * fade)
    else:
        border_rgb = (255, 255, 255)
        border_a = round((75 if is_power else preset.active_pill_border_alpha) * fade)
    if preset.active_pill_border_width_px > 0.0 and border_a > 0:
        canvas.drawRRect(
            pill,
            skia.Paint(
                AntiAlias=True,
                Style=skia.Paint.kStroke_Style,
                StrokeWidth=preset.active_pill_border_width_px,
                Color=skia.ColorSetARGB(border_a, *border_rgb),
            ),
        )
    outline_rgb = _hex_to_rgb(preset.inactive_outline_hex)
    white_rgb = _hex_to_rgb(preset.inactive_text_hex)
    canvas.save()
    canvas.clipRRect(pill, skia.ClipOp.kDifference, True)
    sh = skia.Paint(
        AntiAlias=True,
        Color=skia.ColorSetARGB(round(190 * fade), 0, 0, 0),
        MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 6.0),
    )
    stroke = skia.Paint(
        AntiAlias=True,
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=max(8.0, layout.font_size_px * 0.13),
        StrokeJoin=skia.Paint.kRound_Join,
        StrokeCap=skia.Paint.kRound_Cap,
        Color=skia.ColorSetARGB(a_full, *outline_rgb),
    )
    fill = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, *white_rgb))
    for lw in layout.words:
        canvas.drawTextBlob(lw.shaped.blob, lw.x_origin, layout.baseline_y + 5.0, sh)
        canvas.drawTextBlob(lw.shaped.blob, lw.x_origin, layout.baseline_y, stroke)
        canvas.drawTextBlob(lw.shaped.blob, lw.x_origin, layout.baseline_y, fill)
    canvas.restore()

    canvas.save()
    canvas.clipRRect(pill, skia.ClipOp.kIntersect, True)
    ink_luma = 0.2126 * active_ink_rgb[0] + 0.7152 * active_ink_rgb[1] + 0.0722 * active_ink_rgb[2]
    if ink_luma > 140.0:
        ink_sh = skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(round(145 * fade), 0, 0, 0),
            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 3.0),
        )
        for lw in layout.words:
            canvas.drawTextBlob(lw.shaped.blob, lw.x_origin, layout.baseline_y + 2.5, ink_sh)
    ink = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, *active_ink_rgb))
    for lw in layout.words:
        canvas.drawTextBlob(lw.shaped.blob, lw.x_origin, layout.baseline_y, ink)
    canvas.restore()
    canvas.restore()


def _normalize_visual_interrupts(
    visual_interrupts: Sequence[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Validate visual interrupts and enforce strict post-hook (>= 2600 ms) clearance."""
    out: list[tuple[int, int, str, str]] = []
    for start_ms, end_ms, text_ckb, position in visual_interrupts:
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError(f"invalid visual_interrupt time range {start_ms}..{end_ms} ms")
        cleaned = " ".join(text_ckb.strip().split())
        if not cleaned:
            raise ValueError("visual_interrupt text_ckb must not be empty")
        if position not in ("top", "chest"):
            raise ValueError(
                f"visual_interrupt position must be 'top' or 'chest', got {position!r}"
            )
        eff_start = max(start_ms, VISUAL_INTERRUPT_MIN_START_MS)
        if end_ms <= eff_start:
            continue
        out.append((eff_start, end_ms, cleaned, position))
    return out


def _normalize_speaker_bio(
    speaker_bio: tuple[str, str | None] | None,
) -> tuple[str, str | None] | None:
    if speaker_bio is None:
        return None
    if not isinstance(speaker_bio, tuple) or len(speaker_bio) != 2:
        raise ValueError("speaker_bio must be a (name_ckb, role_ckb) 2-tuple")
    name_raw, role_raw = speaker_bio
    if not isinstance(name_raw, str):
        raise ValueError("speaker_bio name_ckb must be a string")
    name_clean = " ".join(name_raw.strip().split())
    if not name_clean:
        raise ValueError("speaker_bio name_ckb must not be empty")
    if role_raw is not None and not isinstance(role_raw, str):
        raise ValueError("speaker_bio role_ckb must be a string or None")
    role_clean = " ".join(role_raw.strip().split()) if role_raw is not None else None
    return (name_clean, role_clean or None)


def _normalize_end_card(
    end_card: tuple[str, str | None, str | None] | None,
) -> tuple[str, str | None, str | None] | None:
    if end_card is None:
        return None
    if not isinstance(end_card, tuple) or len(end_card) != 3:
        raise ValueError("end_card must be a (title_ckb, subtitle_ckb, handle) 3-tuple")
    title_raw, subtitle_raw, handle_raw = end_card
    if not isinstance(title_raw, str):
        raise ValueError("end_card title_ckb must be a string")
    title_clean = " ".join(title_raw.strip().split())
    if not title_clean:
        raise ValueError("end_card title_ckb must not be empty")
    if subtitle_raw is not None and not isinstance(subtitle_raw, str):
        raise ValueError("end_card subtitle_ckb must be a string or None")
    if handle_raw is not None and not isinstance(handle_raw, str):
        raise ValueError("end_card handle must be a string or None")
    subtitle_clean = " ".join(subtitle_raw.strip().split()) if subtitle_raw is not None else None
    handle_clean = " ".join(handle_raw.strip().split()) if handle_raw is not None else None
    return (title_clean, subtitle_clean or None, handle_clean or None)


def _resolve_end_card_window(
    duration_ms: int | None,
    chunks: Sequence[ViralCaptionChunk],
    *,
    t_ms: int | None = None,
) -> tuple[int, int]:
    if duration_ms is not None:
        if duration_ms <= 0:
            raise ValueError(f"duration_ms must be > 0, got {duration_ms}")
        return (max(0, duration_ms - END_CARD_DURATION_MS), duration_ms)
    if chunks:
        max_end = max(c.end_ms for c in chunks)
        return (max(0, max_end - END_CARD_DURATION_MS), max_end)
    if t_ms is not None:
        return (max(0, t_ms - 500), t_ms + 1500)
    return (0, END_CARD_DURATION_MS)


def _interrupt_spring_scale(
    elapsed_ms: float, *, duration_ms: float = VISUAL_INTERRUPT_SPRING_MS
) -> float:
    """Spring pop-in ``0.86 -> 1.04 -> 1.00`` over ``duration_ms``."""
    if elapsed_ms <= 0.0:
        return 0.86
    if elapsed_ms >= duration_ms:
        return 1.00
    peak = duration_ms * 0.5
    if elapsed_ms < peak:
        u = elapsed_ms / peak
        return 0.86 + 0.18 * (1.0 - (1.0 - u) ** 3)
    u = (elapsed_ms - peak) / (duration_ms - peak)
    return 1.04 - 0.04 * (3.0 * u * u - 2.0 * u * u * u)


def _draw_visual_interrupt(
    skia: Any,
    canvas: Any,
    item: _VisualInterruptLayout,
    t_ms: float,
    preset: ClientStylePreset,
) -> None:
    if not item.start_ms <= t_ms < item.end_ms:
        return
    dt = t_ms - item.start_ms
    rem = item.end_ms - t_ms
    scale = _interrupt_spring_scale(dt)
    if dt < 40.0:
        alpha = 0.25 + 0.75 * (dt / 40.0)
    elif rem < VISUAL_INTERRUPT_FADE_OUT_MS:
        alpha = max(0.0, rem / VISUAL_INTERRUPT_FADE_OUT_MS)
    else:
        alpha = 1.0

    rrect = skia.RRect.MakeRectXY(
        skia.Rect.MakeLTRB(item.box_left, item.box_top, item.box_right, item.box_bottom),
        22.0,
        22.0,
    )
    ir, ig, ib, ia = preset.interrupt_fill_rgba
    canvas.save()
    canvas.translate(item.center_x, item.center_y)
    canvas.scale(scale, scale)
    canvas.translate(-item.center_x, -item.center_y)

    canvas.save()
    canvas.translate(0.0, 8.0)
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(round(150 * alpha), 0, 0, 0),
            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 11.0),
        ),
    )
    canvas.restore()
    canvas.drawRRect(
        rrect, skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(round(ia * alpha), ir, ig, ib))
    )
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=3.0,
            Color=skia.ColorSetARGB(round(240 * alpha), *item.border_rgb),
        ),
    )
    t_sh = skia.Paint(
        AntiAlias=True,
        Color=skia.ColorSetARGB(round(170 * alpha), 0, 0, 0),
        MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 4.0),
    )
    if item.stat_hero is not None:
        hero_s, hx, hy = item.stat_hero
        hero_glow = skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(round(125 * alpha), *item.border_rgb),
            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10.0),
        )
        hero_fg = skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(max(0, min(255, round(alpha * 255))), *item.border_rgb),
        )
        canvas.drawTextBlob(hero_s.blob, hx, hy + 4.0, t_sh)
        canvas.drawTextBlob(hero_s.blob, hx, hy, hero_glow)
        canvas.drawTextBlob(hero_s.blob, hx, hy, hero_fg)
    if item.divider_rect is not None:
        dl, dt_, dr, db = item.divider_rect
        canvas.drawRRect(
            skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(dl, dt_, dr, db), 2.0, 2.0),
            skia.Paint(
                AntiAlias=True,
                Color=skia.ColorSetARGB(round(215 * alpha), *item.border_rgb),
            ),
        )
    t_fg = skia.Paint(
        AntiAlias=True, Color=skia.ColorSetARGB(max(0, min(255, round(alpha * 255))), 255, 255, 255)
    )
    for shaped, bx, by in item.lines:
        canvas.drawTextBlob(shaped.blob, bx, by + 3.0, t_sh)
        canvas.drawTextBlob(shaped.blob, bx, by, t_fg)
    canvas.restore()


def _draw_speaker_bio(
    skia: Any,
    canvas: Any,
    bio: _SpeakerBioLayout,
    t_ms: float,
    preset: ClientStylePreset,
) -> None:
    if not bio.start_ms <= t_ms < bio.end_ms:
        return
    dt = t_ms - bio.start_ms
    rem = bio.end_ms - t_ms
    scale = _interrupt_spring_scale(dt, duration_ms=float(SPEAKER_BIO_SPRING_MS))
    slide_u = min(1.0, max(0.0, dt / float(SPEAKER_BIO_SPRING_MS)))
    slide_px = (1.0 - (1.0 - slide_u) ** 3 - 1.0) * (-18.0 if bio.is_rtl else 18.0)
    if dt < 60.0:
        alpha = 0.15 + 0.85 * (dt / 60.0)
    elif rem < SPEAKER_BIO_FADE_OUT_MS:
        alpha = max(0.0, rem / float(SPEAKER_BIO_FADE_OUT_MS))
    else:
        alpha = 1.0

    rrect = skia.RRect.MakeRectXY(
        skia.Rect.MakeLTRB(bio.box_left, bio.box_top, bio.box_right, bio.box_bottom), 20.0, 20.0
    )
    hr, hg, hb, ha = preset.hook_fill_rgba
    fill_a = max(224, ha)
    accent_rgb = _hex_to_rgb(preset.accent_hex)
    border_rgb = _hex_to_rgb(preset.hook_border_hex)
    a_full = max(0, min(255, round(alpha * 255)))

    canvas.save()
    canvas.translate(bio.center_x + slide_px, bio.center_y)
    canvas.scale(scale, scale)
    canvas.translate(-bio.center_x, -bio.center_y)

    canvas.save()
    canvas.translate(0.0, 7.0)
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(round(150 * alpha), 0, 0, 0),
            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10.0),
        ),
    )
    canvas.restore()
    canvas.drawRRect(
        rrect,
        skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(round(fill_a * alpha), hr, hg, hb)),
    )
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=2.0,
            Color=skia.ColorSetARGB(round(205 * alpha), *border_rgb),
        ),
    )
    bl, bt, br_x, bb = bio.accent_bar_rect
    bar_rrect = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(bl, bt, br_x, bb), 3.5, 3.5)
    canvas.drawRRect(
        bar_rrect, skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, *accent_rgb))
    )

    t_sh = skia.Paint(
        AntiAlias=True,
        Color=skia.ColorSetARGB(round(160 * alpha), 0, 0, 0),
        MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 3.0),
    )
    name_fg = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, 255, 255, 255))
    name_s, nx, ny = bio.name_line
    canvas.drawTextBlob(name_s.blob, nx, ny + 2.5, t_sh)
    canvas.drawTextBlob(name_s.blob, nx, ny, name_fg)
    if bio.role_line is not None:
        role_s, rx, ry = bio.role_line
        role_fg = skia.Paint(
            AntiAlias=True, Color=skia.ColorSetARGB(round(235 * alpha), 216, 224, 238)
        )
        canvas.drawTextBlob(role_s.blob, rx, ry + 2.0, t_sh)
        canvas.drawTextBlob(role_s.blob, rx, ry, role_fg)
    canvas.restore()


def _draw_end_card(
    skia: Any,
    canvas: Any,
    card: _EndCardLayout,
    t_ms: float,
    preset: ClientStylePreset,
) -> None:
    if not card.start_ms <= t_ms < card.end_ms:
        return
    dt = t_ms - card.start_ms
    scale = _interrupt_spring_scale(dt, duration_ms=float(END_CARD_SPRING_MS))
    alpha = min(1.0, max(0.0, dt / 140.0)) if dt < 140.0 else 1.0
    a_full = max(0, min(255, round(alpha * 255)))

    rrect = skia.RRect.MakeRectXY(
        skia.Rect.MakeLTRB(card.box_left, card.box_top, card.box_right, card.box_bottom), 32.0, 32.0
    )
    hr, hg, hb, _ = preset.hook_fill_rgba
    border_rgb = _hex_to_rgb(preset.hook_border_hex)
    accent_rgb = _hex_to_rgb(preset.accent_hex)

    canvas.save()
    canvas.translate(card.center_x, card.center_y)
    canvas.scale(scale, scale)
    canvas.translate(-card.center_x, -card.center_y)

    canvas.save()
    canvas.translate(0.0, 12.0)
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Color=skia.ColorSetARGB(round(175 * alpha), 0, 0, 0),
            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 18.0),
        ),
    )
    canvas.restore()
    canvas.drawRRect(
        rrect, skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(round(238 * alpha), hr, hg, hb))
    )
    canvas.drawRRect(
        rrect,
        skia.Paint(
            AntiAlias=True,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=3.0,
            Color=skia.ColorSetARGB(round(235 * alpha), *border_rgb),
        ),
    )

    al, at, ar, ab = card.accent_bar_rect
    canvas.drawRRect(
        skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(al, at, ar, ab), 3.5, 3.5),
        skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, *accent_rgb)),
    )

    t_sh = skia.Paint(
        AntiAlias=True,
        Color=skia.ColorSetARGB(round(170 * alpha), 0, 0, 0),
        MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 4.0),
    )
    t_fg = skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, 255, 255, 255))
    for shaped, bx, by in card.title_lines:
        canvas.drawTextBlob(shaped.blob, bx, by + 3.0, t_sh)
        canvas.drawTextBlob(shaped.blob, bx, by, t_fg)

    if card.subtitle_lines:
        s_fg = skia.Paint(
            AntiAlias=True, Color=skia.ColorSetARGB(round(235 * alpha), 216, 223, 236)
        )
        for shaped, bx, by in card.subtitle_lines:
            canvas.drawTextBlob(shaped.blob, bx, by + 2.0, t_sh)
            canvas.drawTextBlob(shaped.blob, bx, by, s_fg)

    if card.handle_line is not None and card.handle_pill_rect is not None:
        hl, ht, hr_x, hb_y = card.handle_pill_rect
        h_rad = min(24.0, (hb_y - ht) * 0.48)
        h_rrect = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(hl, ht, hr_x, hb_y), h_rad, h_rad)
        hp_rgb = _hex_to_rgb(preset.active_pill_hex)
        hp_a = max(0, min(255, round(preset.active_pill_alpha * alpha)))
        canvas.drawRRect(
            h_rrect, skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(hp_a, *hp_rgb))
        )
        if preset.active_pill_border_hex is not None:
            hb_rgb = _hex_to_rgb(preset.active_pill_border_hex)
            canvas.drawRRect(
                h_rrect,
                skia.Paint(
                    AntiAlias=True,
                    Style=skia.Paint.kStroke_Style,
                    StrokeWidth=preset.active_pill_border_width_px,
                    Color=skia.ColorSetARGB(
                        round(preset.active_pill_border_alpha * alpha), *hb_rgb
                    ),
                ),
            )
        h_ink_rgb = _hex_to_rgb(preset.active_text_hex)
        h_shaped, hx, hy = card.handle_line
        h_luma = 0.2126 * h_ink_rgb[0] + 0.7152 * h_ink_rgb[1] + 0.0722 * h_ink_rgb[2]
        if h_luma > 140.0:
            canvas.drawTextBlob(h_shaped.blob, hx, hy + 2.0, t_sh)
        canvas.drawTextBlob(
            h_shaped.blob,
            hx,
            hy,
            skia.Paint(AntiAlias=True, Color=skia.ColorSetARGB(a_full, *h_ink_rgb)),
        )
    canvas.restore()


def _active_chunk_idx(layouts: Sequence[_LaidOutChunk], t_ms: float) -> int | None:
    return next(
        (i for i, lay in enumerate(layouts) if lay.chunk.start_ms <= t_ms < lay.chunk.end_ms), None
    )


def _active_interrupt_indices(
    interrupts: Sequence[_VisualInterruptLayout], t_ms: float
) -> tuple[int, ...]:
    return tuple(i for i, it in enumerate(interrupts) if it.start_ms <= t_ms < it.end_ms)


def _frame_state_key(
    layouts: Sequence[_LaidOutChunk],
    hook: _HookTitleLayout | None,
    interrupts: Sequence[_VisualInterruptLayout],
    bio: _SpeakerBioLayout | None,
    end_card: _EndCardLayout | None,
    t_ms: float,
    preset: ClientStylePreset,
) -> tuple[object, ...]:
    hook_key: object = (
        ("anim", round(t_ms))
        if hook is not None
        and 0.0 <= t_ms < HOOK_DURATION_MS
        and (t_ms < 160.0 or t_ms > HOOK_DURATION_MS - 250.0)
        else (("hold",) if hook is not None and 0.0 <= t_ms < HOOK_DURATION_MS else None)
    )
    int_keys: list[object] = []
    for i_idx in _active_interrupt_indices(interrupts, t_ms):
        it = interrupts[i_idx]
        dt = t_ms - it.start_ms
        rem = it.end_ms - t_ms
        if dt < VISUAL_INTERRUPT_SPRING_MS or rem < VISUAL_INTERRUPT_FADE_OUT_MS:
            int_keys.append((i_idx, "anim", round(dt)))
        else:
            int_keys.append((i_idx, "hold"))
    int_key: object = tuple(int_keys) if int_keys else None

    bio_key: object = None
    if bio is not None and bio.start_ms <= t_ms < bio.end_ms:
        b_dt = t_ms - bio.start_ms
        b_rem = bio.end_ms - t_ms
        bio_key = (
            ("anim", round(b_dt))
            if b_dt < SPEAKER_BIO_SPRING_MS or b_rem < SPEAKER_BIO_FADE_OUT_MS
            else ("hold",)
        )

    end_key: object = None
    if end_card is not None and end_card.start_ms <= t_ms < end_card.end_ms:
        e_dt = t_ms - end_card.start_ms
        end_key = ("anim", round(e_dt)) if e_dt < END_CARD_SPRING_MS else ("hold",)

    chunk_idx = _active_chunk_idx(layouts, t_ms)
    if chunk_idx is None:
        return (hook_key, int_key, bio_key, end_key, None)
    lay = layouts[chunk_idx]
    dt = t_ms - lay.chunk.start_ms
    active_w, _, _, _, _, _, _ = _active_word_state(lay, t_ms, preset)
    g_dt = t_ms - lay.words[active_w].word.start_ms if active_w > 0 else PILL_GLIDE_MS
    return (
        hook_key,
        int_key,
        bio_key,
        end_key,
        chunk_idx,
        round(dt) if dt < SPRING_BOUNCE_MS else -1,
        active_w,
        round(g_dt) if g_dt < PILL_GLIDE_MS else -1,
    )


def _render_single_surface(
    chunks: Sequence[ViralCaptionChunk],
    *,
    t_ms: int,
    font_path: Path,
    hook_title_ckb: str | None,
    visual_interrupts: Sequence[tuple[int, int, str, str]],
    style_preset: ClientStylePreset | str | None,
    speaker_bio: tuple[str, str | None] | None,
    end_card: tuple[str, str | None, str | None] | None,
    duration_ms: int | None,
    width: int,
    height: int,
    y_center_px: int,
    background_rgba: tuple[int, int, int, int],
    hook_y_top_px: float = 250.0,
    split_screen_windows_ms: Sequence[tuple[int, int]] = (),
) -> tuple[Any, Any]:
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid frame dimensions {width}x{height}")
    if not 0 < y_center_px < height:
        raise ValueError(f"y_center_px={y_center_px} must lie inside 1..{height - 1}")
    preset = resolve_client_style_preset(style_preset)
    norm_interrupts = _normalize_visual_interrupts(visual_interrupts)
    norm_bio = _normalize_speaker_bio(speaker_bio)
    norm_end_card = _normalize_end_card(end_card)
    shaper = _SkiaHarfBuzzShaper(font_path)
    skia = shaper.skia

    def _resolve_chunk_y_center(
        chunk: ViralCaptionChunk,
        *,
        y_center_px: int,
        height: int,
        duration_ms: int | None,
        has_end_card: bool,
        split_screen_windows_ms: Sequence[tuple[int, int]],
    ) -> int:
        if split_screen_windows_ms:
            mid = (chunk.start_ms + chunk.end_ms) // 2
            in_end_card = (
                has_end_card
                and duration_ms is not None
                and mid >= max(0, duration_ms - END_CARD_DURATION_MS)
            )
            c_dur = max(1, chunk.end_ms - chunk.start_ms)
            if not in_end_card and any(
                s_ms <= mid < e_ms
                or (min(chunk.end_ms, e_ms) - max(chunk.start_ms, s_ms)) * 3 >= c_dur
                for s_ms, e_ms in split_screen_windows_ms
            ):
                return height // 2
        return y_center_px

    layouts = [
        shaper.layout_chunk(
            c,
            width=width,
            y_center_px=_resolve_chunk_y_center(
                c,
                y_center_px=y_center_px,
                height=height,
                duration_ms=duration_ms,
                has_end_card=norm_end_card is not None,
                split_screen_windows_ms=split_screen_windows_ms,
            ),
        )
        for c in chunks
    ]
    hook = (
        shaper.layout_hook_title(hook_title_ckb, width=width, y_top_px=hook_y_top_px)
        if hook_title_ckb and hook_title_ckb.strip()
        else None
    )
    interrupt_layouts = [
        shaper.layout_visual_interrupt(
            s, e, txt, pos, width=width, height=height, y_center_px=y_center_px, preset=preset
        )
        for s, e, txt, pos in norm_interrupts
    ]
    bio_layout = (
        shaper.layout_speaker_bio(
            norm_bio[0], norm_bio[1], width=width, height=height, y_center_px=y_center_px
        )
        if norm_bio is not None
        else None
    )
    end_card_layout: _EndCardLayout | None = None
    if norm_end_card is not None:
        ec_start, ec_end = _resolve_end_card_window(duration_ms, chunks, t_ms=t_ms)
        end_card_layout = shaper.layout_end_card(
            norm_end_card[0],
            norm_end_card[1],
            norm_end_card[2],
            start_ms=ec_start,
            end_ms=ec_end,
            width=width,
            height=height,
            y_center_px=y_center_px,
        )
    info = skia.ImageInfo.Make(
        width, height, skia.ColorType.kRGBA_8888_ColorType, skia.AlphaType.kPremul_AlphaType
    )
    surface = skia.Surface.MakeRaster(info)
    if surface is None:
        raise TikTokSubtitleError(f"Skia failed to allocate {width}x{height} surface")
    canvas = surface.getCanvas()
    r, g, b, a = background_rgba
    canvas.clear(skia.ColorSetARGB(a, r, g, b))
    if hook is not None:
        _draw_hook_title(skia, canvas, hook, float(t_ms), preset)
    for i_idx in _active_interrupt_indices(interrupt_layouts, float(t_ms)):
        _draw_visual_interrupt(skia, canvas, interrupt_layouts[i_idx], float(t_ms), preset)
    if bio_layout is not None:
        _draw_speaker_bio(skia, canvas, bio_layout, float(t_ms), preset)
    if end_card_layout is not None:
        _draw_end_card(skia, canvas, end_card_layout, float(t_ms), preset)
    if (idx := _active_chunk_idx(layouts, float(t_ms))) is not None:
        _draw_caption_chunk(skia, canvas, layouts[idx], float(t_ms), preset)
    return skia, surface


def render_tiktok_frame_rgba(
    chunks: Sequence[ViralCaptionChunk],
    *,
    t_ms: int,
    font_path: Path,
    hook_title_ckb: str | None = None,
    visual_interrupts: Sequence[tuple[int, int, str, str]] = (),
    style_preset: ClientStylePreset | str | None = None,
    speaker_bio: tuple[str, str | None] | None = None,
    end_card: tuple[str, str | None, str | None] | None = None,
    duration_ms: int | None = None,
    width: int = 1080,
    height: int = 1920,
    y_center_px: int = DEFAULT_Y_CENTER_PX,
    background_rgba: tuple[int, int, int, int] = (0, 0, 0, 0),
    split_screen_windows_ms: Sequence[tuple[int, int]] = (),
) -> bytes:
    """Render one 1080×1920 straight-RGBA frame at ``t_ms``."""
    skia, surface = _render_single_surface(
        chunks,
        t_ms=t_ms,
        font_path=font_path,
        hook_title_ckb=hook_title_ckb,
        visual_interrupts=visual_interrupts,
        style_preset=style_preset,
        speaker_bio=speaker_bio,
        end_card=end_card,
        duration_ms=duration_ms,
        width=width,
        height=height,
        y_center_px=y_center_px,
        background_rgba=background_rgba,
        split_screen_windows_ms=split_screen_windows_ms,
    )
    out = bytearray(width * height * 4)
    unpremul = skia.ImageInfo.Make(
        width, height, skia.ColorType.kRGBA_8888_ColorType, skia.AlphaType.kUnpremul_AlphaType
    )
    if not surface.readPixels(unpremul, out, width * 4, 0, 0):
        raise TikTokSubtitleError("Skia Surface.readPixels failed")
    return bytes(out)


def render_tiktok_preview_png(
    chunks: Sequence[ViralCaptionChunk],
    *,
    t_ms: int,
    output_png: Path,
    font_path: Path,
    hook_title_ckb: str | None = None,
    visual_interrupts: Sequence[tuple[int, int, str, str]] = (),
    style_preset: ClientStylePreset | str | None = None,
    speaker_bio: tuple[str, str | None] | None = None,
    end_card: tuple[str, str | None, str | None] | None = None,
    duration_ms: int | None = None,
    width: int = 1080,
    height: int = 1920,
    y_center_px: int = DEFAULT_Y_CENTER_PX,
    background_rgba: tuple[int, int, int, int] = (18, 20, 28, 255),
    split_screen_windows_ms: Sequence[tuple[int, int]] = (),
) -> Path:
    """Render one 1080×1920 PNG preview frame directly via Skia."""
    skia, surface = _render_single_surface(
        chunks,
        t_ms=t_ms,
        font_path=font_path,
        hook_title_ckb=hook_title_ckb,
        visual_interrupts=visual_interrupts,
        style_preset=style_preset,
        speaker_bio=speaker_bio,
        end_card=end_card,
        duration_ms=duration_ms,
        width=width,
        height=height,
        y_center_px=y_center_px,
        background_rgba=background_rgba,
        split_screen_windows_ms=split_screen_windows_ms,
    )
    encoded = surface.makeImageSnapshot().encodeToData(skia.kPNG, 100)
    if encoded is None:
        raise TikTokSubtitleError(f"Skia PNG encode failed for {output_png}")
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_png.write_bytes(bytes(encoded))
    return output_png


def render_tiktok_overlay_video(
    chunks: Sequence[ViralCaptionChunk],
    *,
    duration_ms: int,
    output_mov_or_mkv: Path,
    font_path: Path,
    hook_title_ckb: str | None = None,
    visual_interrupts: Sequence[tuple[int, int, str, str]] = (),
    style_preset: ClientStylePreset | str | None = None,
    speaker_bio: tuple[str, str | None] | None = None,
    end_card: tuple[str, str | None, str | None] | None = None,
    fps: float = 25.0,
    width: int = 1080,
    height: int = 1920,
    y_center_px: int = DEFAULT_Y_CENTER_PX,
    hook_y_top_px: float = 250.0,
    split_screen_windows_ms: Sequence[tuple[int, int]] = (),
    ffmpeg: Path | None = None,
) -> Path:
    """Pipe a 1080×1920 transparent-alpha Skia+HarfBuzz subtitle stream into FFmpeg."""
    if duration_ms <= 0 or fps <= 0.0 or not math.isfinite(fps) or width <= 0 or height <= 0:
        raise ValueError("duration_ms, fps, width, and height must be finite and > 0")
    if not 0 < y_center_px < height:
        raise ValueError(f"y_center_px={y_center_px} must lie inside 1..{height - 1}")
    preset = resolve_client_style_preset(style_preset)
    norm_interrupts = _normalize_visual_interrupts(visual_interrupts)
    norm_bio = _normalize_speaker_bio(speaker_bio)
    norm_end_card = _normalize_end_card(end_card)
    codec_map = {
        ".mov": ["-c:v", "qtrle", "-pix_fmt", "argb"],
        ".mkv": ["-c:v", "png", "-pix_fmt", "rgba"],
    }
    codec_args = codec_map.get(output_mov_or_mkv.suffix.lower())
    if codec_args is None:
        raise ValueError(
            f"transparent overlay output must end in .mov or .mkv, got {output_mov_or_mkv}"
        )
    ffmpeg_bin = ffmpeg if ffmpeg is not None else find_ffmpeg()
    if ffmpeg_bin is None or not ffmpeg_bin.is_file():
        raise TikTokSubtitleError("ffmpeg binary not found for render_tiktok_overlay_video")

    shaper = _SkiaHarfBuzzShaper(font_path)
    skia = shaper.skia

    def _resolve_chunk_y_center(
        chunk: ViralCaptionChunk,
        *,
        y_center_px: int,
        height: int,
        duration_ms: int | None,
        has_end_card: bool,
        split_screen_windows_ms: Sequence[tuple[int, int]],
    ) -> int:
        if split_screen_windows_ms:
            mid = (chunk.start_ms + chunk.end_ms) // 2
            in_end_card = (
                has_end_card
                and duration_ms is not None
                and mid >= max(0, duration_ms - END_CARD_DURATION_MS)
            )
            c_dur = max(1, chunk.end_ms - chunk.start_ms)
            if not in_end_card and any(
                s_ms <= mid < e_ms
                or (min(chunk.end_ms, e_ms) - max(chunk.start_ms, s_ms)) * 3 >= c_dur
                for s_ms, e_ms in split_screen_windows_ms
            ):
                return height // 2
        return y_center_px

    layouts = [
        shaper.layout_chunk(
            c,
            width=width,
            y_center_px=_resolve_chunk_y_center(
                c,
                y_center_px=y_center_px,
                height=height,
                duration_ms=duration_ms,
                has_end_card=norm_end_card is not None,
                split_screen_windows_ms=split_screen_windows_ms,
            ),
        )
        for c in chunks
    ]
    hook = (
        shaper.layout_hook_title(hook_title_ckb, width=width, y_top_px=hook_y_top_px)
        if hook_title_ckb and hook_title_ckb.strip()
        else None
    )
    interrupt_layouts = [
        shaper.layout_visual_interrupt(
            s, e, txt, pos, width=width, height=height, y_center_px=y_center_px, preset=preset
        )
        for s, e, txt, pos in norm_interrupts
    ]
    bio_layout = (
        shaper.layout_speaker_bio(
            norm_bio[0], norm_bio[1], width=width, height=height, y_center_px=y_center_px
        )
        if norm_bio is not None
        else None
    )
    end_card_layout = (
        shaper.layout_end_card(
            norm_end_card[0],
            norm_end_card[1],
            norm_end_card[2],
            start_ms=max(0, duration_ms - END_CARD_DURATION_MS),
            end_ms=duration_ms,
            width=width,
            height=height,
            y_center_px=y_center_px,
        )
        if norm_end_card is not None
        else None
    )
    surface = skia.Surface.MakeRaster(
        skia.ImageInfo.Make(
            width, height, skia.ColorType.kRGBA_8888_ColorType, skia.AlphaType.kPremul_AlphaType
        )
    )
    if surface is None:
        raise TikTokSubtitleError(f"Skia failed to allocate {width}x{height} surface")
    canvas = surface.getCanvas()

    row_bytes, total_frames = width * 4, max(1, math.ceil((duration_ms / 1000.0) * fps))
    frame_buf = bytearray(row_bytes * height)
    frame_view, blank = memoryview(frame_buf), bytes(row_bytes * height)
    cap_band = (
        (
            max(0, math.floor(min(x.pill_top for x in layouts) - 80)),
            min(height, math.ceil(max(x.pill_bottom for x in layouts) + 80)),
        )
        if layouts
        else None
    )
    hook_band = (
        (max(0, math.floor(hook.box_top - 64)), min(height, math.ceil(hook.box_bottom + 64)))
        if hook is not None
        else None
    )
    band_infos: dict[int, Any] = {}
    output_mov_or_mkv.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:g}",
        "-i",
        "pipe:0",
        *codec_args,
        str(output_mov_or_mkv),
    ]
    last_key: tuple[object, ...] | None = None
    last_payload: bytes | bytearray = blank
    dirty: list[tuple[int, int]] = []
    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr_file
        )
        assert proc.stdin is not None
        try:
            for f_idx in range(total_frames):
                t_ms = (f_idx * 1000.0) / fps
                key = _frame_state_key(
                    layouts, hook, interrupt_layouts, bio_layout, end_card_layout, t_ms, preset
                )
                if key != last_key:
                    if key == (None, None, None, None, None):
                        last_payload = blank
                    else:
                        for y0, y1 in dirty:
                            frame_buf[y0 * row_bytes : y1 * row_bytes] = blank[
                                : (y1 - y0) * row_bytes
                            ]
                        canvas.clear(0)
                        bands: list[tuple[int, int]] = []
                        if hook is not None and 0.0 <= t_ms < HOOK_DURATION_MS:
                            _draw_hook_title(skia, canvas, hook, t_ms, preset)
                            if hook_band is not None and hook_band[1] > hook_band[0]:
                                bands.append(hook_band)
                        for i_idx in _active_interrupt_indices(interrupt_layouts, t_ms):
                            it_lay = interrupt_layouts[i_idx]
                            _draw_visual_interrupt(skia, canvas, it_lay, t_ms, preset)
                            if it_lay.dirty_band[1] > it_lay.dirty_band[0]:
                                bands.append(it_lay.dirty_band)
                        if (
                            bio_layout is not None
                            and bio_layout.start_ms <= t_ms < bio_layout.end_ms
                        ):
                            _draw_speaker_bio(skia, canvas, bio_layout, t_ms, preset)
                            if bio_layout.dirty_band[1] > bio_layout.dirty_band[0]:
                                bands.append(bio_layout.dirty_band)
                        if (
                            end_card_layout is not None
                            and end_card_layout.start_ms <= t_ms < end_card_layout.end_ms
                        ):
                            _draw_end_card(skia, canvas, end_card_layout, t_ms, preset)
                            if end_card_layout.dirty_band[1] > end_card_layout.dirty_band[0]:
                                bands.append(end_card_layout.dirty_band)
                        if (c_idx := _active_chunk_idx(layouts, t_ms)) is not None:
                            _draw_caption_chunk(skia, canvas, layouts[c_idx], t_ms, preset)
                            if cap_band is not None and cap_band[1] > cap_band[0]:
                                bands.append(cap_band)
                        merged: list[tuple[int, int]] = []
                        for y0, y1 in sorted(bands):
                            if merged and y0 <= merged[-1][1]:
                                merged[-1] = (merged[-1][0], max(merged[-1][1], y1))
                            else:
                                merged.append((y0, y1))
                        for y0, y1 in merged:
                            h = y1 - y0
                            info = band_infos.setdefault(
                                h,
                                skia.ImageInfo.Make(
                                    width,
                                    h,
                                    skia.ColorType.kRGBA_8888_ColorType,
                                    skia.AlphaType.kUnpremul_AlphaType,
                                ),
                            )
                            if not surface.readPixels(
                                info, frame_view[y0 * row_bytes : y1 * row_bytes], row_bytes, 0, y0
                            ):
                                raise TikTokSubtitleError(
                                    f"Skia readPixels failed at frame {f_idx}"
                                )
                        dirty, last_payload = merged, frame_buf
                    last_key = key
                try:
                    proc.stdin.write(last_payload)
                except BrokenPipeError as exc:
                    proc.wait(timeout=10.0)
                    stderr_file.seek(0)
                    err_text = stderr_file.read(8192).decode("utf-8", errors="replace").strip()
                    raise TikTokSubtitleError(
                        f"FFmpeg overlay pipe closed early: {err_text or exc}"
                    ) from exc
            proc.stdin.close()
            encode_timeout_s = max(120.0, (duration_ms / 1000.0) * 4.0)
            rc = proc.wait(timeout=encode_timeout_s)
            stderr_file.seek(0)
            stderr = stderr_file.read(8192).decode("utf-8", errors="replace").strip()
            if rc != 0:
                raise TikTokSubtitleError(f"FFmpeg overlay encode failed: {stderr}")
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10.0)
            raise
    if not output_mov_or_mkv.is_file() or output_mov_or_mkv.stat().st_size == 0:
        raise TikTokSubtitleError(f"FFmpeg produced empty overlay: {output_mov_or_mkv}")
    return output_mov_or_mkv


def _ass_ts(ms: int) -> str:
    sec, cs = divmod(max(0, ms) // 10, 100)
    minutes, sec = divmod(sec, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}.{cs:02d}"


def _esc_ass(text: str) -> str:
    return _ASS_BRACE_RE.sub("", text).replace("\n", " ").replace("\r", " ")


def build_viral_tiktok_ass(
    chunks: Sequence[ViralCaptionChunk],
    *,
    clip_in_ms: int = 0,
    clip_duration_ms: int | None = None,
    font_name: str = DEFAULT_CAPTION_FONT,
    font_size: int = 86,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    margin_v: int = 480,
    hook_title_ckb: str | None = None,
    visual_interrupts: Sequence[tuple[int, int, str, str]] = (),
    style_preset: ClientStylePreset | str | None = None,
    speaker_bio: tuple[str, str | None] | None = None,
    end_card: tuple[str, str | None, str | None] | None = None,
) -> str:
    """Zero-dependency ``libass`` viral TikTok subtitle fallback (0.00 px ghosting)."""
    if clip_in_ms < 0:
        raise ValueError(f"clip_in_ms must be >= 0, got {clip_in_ms}")
    if clip_duration_ms is not None and clip_duration_ms <= 0:
        raise ValueError(f"clip_duration_ms must be > 0, got {clip_duration_ms}")
    if font_size <= 0:
        raise ValueError(f"font_size must be > 0, got {font_size}")
    preset = resolve_client_style_preset(style_preset)
    norm_interrupts = _normalize_visual_interrupts(visual_interrupts)
    norm_bio = _normalize_speaker_bio(speaker_bio)
    norm_end_card = _normalize_end_card(end_card)

    active_bgr = _hex_to_ass_bgr(preset.accent_hex)
    power_bgr = _hex_to_ass_bgr(preset.power_pill_hex)
    white = _hex_to_ass_bgr(preset.inactive_text_hex)
    outline = _hex_to_ass_bgr(preset.inactive_outline_hex)
    hook_bgr = _hex_to_ass_bgr(preset.hook_border_hex)
    int_top_bgr = _hex_to_ass_bgr(preset.interrupt_top_border_hex)
    int_chest_bgr = _hex_to_ass_bgr(preset.interrupt_chest_border_hex)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},{white},{active_bgr},{outline},&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,6.0,2.5,2,80,80,{margin_v},0",
        f"Style: HookTitle,{font_name},56,{hook_bgr},{hook_bgr},{outline},&HB40F0B0B,"
        "-1,0,0,0,100,100,0,0,3,14.0,0.0,8,70,70,210,0",
        f"Style: InterruptTop,{font_name},48,{white},{int_top_bgr},&H231C120F,&H231C120F,"
        "-1,0,0,0,100,100,0,0,3,16.0,0.0,8,70,70,175,0",
        f"Style: InterruptChest,{font_name},48,{white},{int_chest_bgr},&H231C120F,&H231C120F,"
        "-1,0,0,0,100,100,0,0,3,16.0,0.0,2,70,70,750,0",
    ]
    if norm_bio is not None:
        lines.append(
            f"Style: SpeakerBio,{font_name},40,{white},{active_bgr},&H2018120E,&H2018120E,"
            "-1,0,0,0,100,100,0,0,3,14.0,0.0,3,90,136,240,0"
        )
    if norm_end_card is not None:
        lines.append(
            f"Style: EndCard,{font_name},52,{white},{active_bgr},&H1418120E,&H1418120E,"
            "-1,0,0,0,100,100,0,0,3,22.0,0.0,5,90,90,120,0"
        )
    lines.extend(
        [
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    if hook_title_ckb and hook_title_ckb.strip():
        h_end = (
            min(HOOK_DURATION_MS, clip_duration_ms)
            if clip_duration_ms is not None
            else HOOK_DURATION_MS
        )
        if h_end > 0:
            body = r"\N".join(
                f"{RTL_MARK}{_esc_ass(t)}"
                for t in _balance_hook_lines(hook_title_ckb.strip().split())
            )
            anim = (
                r"{\fscx86\fscy86\t(0,75,\fscx105\fscy105)\t(75,150,\fscx100\fscy100)\fad(40,220)}"
            )
            lines.append(
                f"Dialogue: 1,{_ass_ts(0)},{_ass_ts(h_end)},HookTitle,,0,0,0,,{anim}{body}"
            )

    def clamp(ms: int) -> int:
        v = max(0, ms - clip_in_ms)
        return min(v, clip_duration_ms) if clip_duration_ms is not None else v

    int_anim = r"{\fscx86\fscy86\t(0,70,\fscx104\fscy104)\t(70,140,\fscx100\fscy100)\fad(40,200)}"
    for i_start, i_end, i_text, i_pos in norm_interrupts:
        s_ms = max(VISUAL_INTERRUPT_MIN_START_MS, clamp(i_start))
        e_ms = clamp(i_end)
        if e_ms <= s_ms:
            continue
        style_name = "InterruptTop" if i_pos == "top" else "InterruptChest"
        i_body = r"\N".join(
            f"{RTL_MARK}{_esc_ass(t)}"
            for t in _balance_hook_lines(i_text.split(), max_single_line_chars=26)
        )
        lines.append(
            f"Dialogue: 2,{_ass_ts(s_ms)},{_ass_ts(e_ms)},{style_name},,0,0,0,,{int_anim}{i_body}"
        )

    if norm_bio is not None:
        bio_start = SPEAKER_BIO_START_MS
        bio_end = (
            min(SPEAKER_BIO_END_MS, clip_duration_ms)
            if clip_duration_ms is not None
            else SPEAKER_BIO_END_MS
        )
        if bio_end > bio_start:
            b_name, b_role = norm_bio
            bio_parts = [f"{RTL_MARK}{_esc_ass(b_name)}"]
            if b_role is not None:
                bio_parts.append(rf"{{\fs30\c{active_bgr}&}}{RTL_MARK}{_esc_ass(b_role)}")
            bio_anim = (
                r"{\fscx88\fscy88\t(0,80,\fscx103\fscy103)\t(80,160,\fscx100\fscy100)\fad(60,260)}"
            )
            lines.append(
                f"Dialogue: 3,{_ass_ts(bio_start)},{_ass_ts(bio_end)},SpeakerBio,,0,0,0,,"
                f"{bio_anim}" + r"\N".join(bio_parts)
            )

    if norm_end_card is not None:
        ec_total = (
            clip_duration_ms
            if clip_duration_ms is not None
            else max((clamp(c.end_ms) for c in chunks), default=END_CARD_DURATION_MS)
        )
        ec_start = max(0, ec_total - END_CARD_DURATION_MS)
        if ec_total > ec_start:
            ec_title, ec_sub, ec_handle = norm_end_card
            ec_parts = [
                f"{RTL_MARK}{_esc_ass(t)}"
                for t in _balance_hook_lines(ec_title.split(), max_single_line_chars=22)
            ]
            if ec_sub is not None:
                ec_parts.append(rf"{{\fs34}}{RTL_MARK}{_esc_ass(ec_sub)}")
            if ec_handle is not None:
                ec_parts.append(rf"{{\fs38\c{active_bgr}&}}{_esc_ass(ec_handle)}")
            ec_anim = (
                r"{\fscx88\fscy88\t(0,90,\fscx103\fscy103)\t(90,180,\fscx100\fscy100)\fad(140,0)}"
            )
            lines.append(
                f"Dialogue: 4,{_ass_ts(ec_start)},{_ass_ts(ec_total)},EndCard,,0,0,0,,"
                f"{ec_anim}" + r"\N".join(ec_parts)
            )

    solo_anim = r"\fscx84\fscy84\t(0,65,\fscx108\fscy108)\t(65,130,\fscx100\fscy100)"
    multi_anim = r"\fscx88\fscy88\t(0,65,\fscx106\fscy106)\t(65,130,\fscx100\fscy100)"
    for chunk in chunks:
        c_start, c_end = clamp(chunk.start_ms), clamp(chunk.end_ms)
        if c_end <= c_start:
            continue
        if len(chunk.words) == 1:
            w = chunk.words[0]
            accent = (
                power_bgr
                if w.is_power_word
                else (_hex_to_ass_bgr(chunk.accent_color) if chunk.accent_color else active_bgr)
            )
            lines.append(
                f"Dialogue: 0,{_ass_ts(c_start)},{_ass_ts(c_end)},Default,,0,0,0,,"
                f"{{{solo_anim}\\c{accent}&}}{RTL_MARK}{_esc_ass(w.text)}"
            )
            continue
        for idx, aw in enumerate(chunk.words):
            s_start = c_start if idx == 0 else clamp(aw.start_ms)
            s_end = (
                max(s_start, min(c_end, clamp(chunk.words[idx + 1].start_ms)))
                if idx + 1 < len(chunk.words)
                else c_end
            )
            if s_end <= s_start:
                continue
            accent = (
                power_bgr
                if aw.is_power_word
                else (_hex_to_ass_bgr(chunk.accent_color) if chunk.accent_color else active_bgr)
            )
            parts = [
                rf"{{\c{accent if j == idx else white}&}}{_esc_ass(w.text)}"
                for j, w in enumerate(chunk.words)
            ]
            prefix = f"{{{multi_anim}}}" if idx == 0 else ""
            body = f"{prefix}{RTL_MARK}" + " ".join(parts)
            lines.append(f"Dialogue: 0,{_ass_ts(s_start)},{_ass_ts(s_end)},Default,,0,0,0,,{body}")
    return "\n".join(lines) + "\n"
