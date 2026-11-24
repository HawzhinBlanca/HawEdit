"""HawEdit V8 Module 2: Unified Multimodal Director Brain & Watch-Before-Ship Critic (D-384, D-386).

Provides:
- Lightweight FFmpeg media proxy builders (``build_director_proxy`` @ 360p/1fps,
  ``build_critique_preview`` @ 480p/2fps) so cloud and local multimodal models watch the real
  video and hear the real Kurdish/English audio at negligible latency and token cost.
- Unified ``DirectorBrain`` protocol (structurally compatible with ``V8DirectorProtocol`` in
  ``hawedit.v8.compiler``) with three explicit, non-fallback backends:
  1. ``GeminiVideoDirector``: Cloud Gemini 2.5 Pro / Gemini 3 native video+audio via inline
     base64 MP4 (``inlineData``, ``video/mp4``) and strict ``responseSchema``.
  2. ``LocalOmniDirector``: Local GPU 1 Qwen2.5-Omni / Qwen3-Omni (or any OpenAI-compatible
     multimodal server via ``HAWEDIT_OMNI_URL``) with sampled JPEG keyframes + 16 kHz WAV audio.
  3. ``OfflineRestrainedDirector``: Explicit ``--director offline`` deterministic director
     enforcing locked ``1.00x`` tripod restraint (>= 80% locked, 0 sway, max 2-3 earned moves).
- Watch-Before-Ship multimodal self-critique (``critique_rendered_clip``).

Strict fail-stop policy: zero silent fallbacks between backends, zero silent stripping of media
inputs, zero invented dependencies (stdlib + existing HawEdit modules only).
"""

from __future__ import annotations

import array
import base64
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal, Protocol, runtime_checkable

from hawedit.caption_polish import repair_kurdish_asr_orthography
from hawedit.captions import find_ffmpeg
from hawedit.credentials import GEMINI_API_KEY, read_credential
from hawedit.gemini import API_ROOT, extract_response_text
from hawedit.http_transport import open_without_redirects
from hawedit.sentences import Sentence
from hawedit.silence import KURDISH_FILLER_TOKENS
from hawedit.transcripts import Word
from hawedit.v8.schema import (
    CameraMove,
    CaptionBeat,
    CritiqueVerdict,
    CutRegion,
    DirectorScript,
    DirectorScriptError,
    VisualInterrupt,
    WordRepair,
    validate_director_script,
)

__all__ = [
    "CRITIQUE_SYSTEM_PROMPT",
    "CRITIQUE_VERDICT_SCHEMA",
    "DEFAULT_GEMINI_DIRECTOR_MODEL",
    "DEFAULT_GEMINI_TIMEOUT_S",
    "DEFAULT_OMNI_TIMEOUT_S",
    "DEFAULT_OMNI_URL",
    "DIRECTOR_SCRIPT_SCHEMA",
    "DIRECTOR_SYSTEM_PROMPT",
    "MAX_DIRECTOR_RESPONSE_BYTES",
    "MAX_GEMINI_INLINE_BYTES",
    "MAX_OMNI_AUDIO_BYTES",
    "OMNI_MODALITY_ENV",
    "OMNI_MODEL_ENV",
    "OMNI_URL_ENV",
    "DirectorBackendName",
    "DirectorBrain",
    "DirectorUnavailable",
    "GeminiVideoDirector",
    "JumpCutInput",
    "LocalDirectorModality",
    "LocalOmniDirector",
    "OfflineRestrainedDirector",
    "ProxyBuildError",
    "Transport",
    "build_critique_preview",
    "build_director_proxy",
    "create_director_brain",
    "critique_rendered_clip",
]

DirectorBackendName = Literal["gemini", "local-omni", "offline"]
LocalDirectorModality = Literal["omni", "vision", "text"]
JumpCutInput = int | tuple[int, int]
Transport = Callable[[str, bytes | None, Mapping[str, str]], tuple[int, str]]

DEFAULT_GEMINI_DIRECTOR_MODEL: Final[str] = "gemini-4-neon"
DEFAULT_GEMINI_TIMEOUT_S: Final[float] = 180.0
DEFAULT_OMNI_URL: Final[str] = "http://127.0.0.1:1234/v1"
DEFAULT_OMNI_TIMEOUT_S: Final[float] = 240.0
OMNI_URL_ENV: Final[str] = "HAWEDIT_OMNI_URL"
OMNI_MODEL_ENV: Final[str] = "HAWEDIT_OMNI_MODEL"
OMNI_MODALITY_ENV: Final[str] = "HAWEDIT_OMNI_MODALITY"

MAX_GEMINI_INLINE_BYTES: Final[int] = 15 * 1024 * 1024
MAX_OMNI_AUDIO_BYTES: Final[int] = 12 * 1024 * 1024
MAX_DIRECTOR_RESPONSE_BYTES: Final[int] = 2 * 1024 * 1024
_MAX_ERROR_CHARS: Final[int] = 512
_FFMPEG_PROXY_TIMEOUT_S: Final[float] = 120.0
_MIN_MAJOR_JUMP_CUT_MS: Final[int] = 600

_THINK_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<(?:think|thinking)>.*?</(?:think|thinking)>",
    flags=re.DOTALL | re.IGNORECASE,
)
_CLOSING_THINK_RE: Final[re.Pattern[str]] = re.compile(
    r"</(?:think|thinking)>",
    flags=re.IGNORECASE,
)
_CODE_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)
_PUNCT_STRIP: Final[str] = " \t\n\r.,!?:;،؛؟۔…\"'«»()[]"
_KURDISH_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "و",
        "لە",
        "بە",
        "بۆ",
        "کە",
        "ئەم",
        "ئەو",
        "من",
        "تۆ",
        "ئێمە",
        "ئەوان",
        "لەم",
        "لەو",
        "بەم",
        "بەو",
        "تا",
        "یان",
        "چونکە",
        "بەڵام",
        "ئەگەر",
        "لەگەڵ",
        "لای",
        "ناو",
        "سەر",
        "پێش",
        "دوای",
        "هەموو",
        "هیچ",
        "ئەوە",
        "ئەمە",
        "بوو",
        "بێت",
        "بکە",
        "ئەکا",
        "دەکا",
    }
    | KURDISH_FILLER_TOKENS
)

DIRECTOR_SYSTEM_PROMPT: Final[str] = (
    "You are the Lead Multimodal Creative Director for HawEdit V8, producing viral 9:16 "
    "Central Kurdish (Sorani, Arabic script) short-form social reels.\n"
    "You receive the ACTUAL clip video proxy AND spoken audio alongside the word-indexed "
    "Sorani ASR transcript, detected source shot cuts, and candidate editorial jump-cuts.\n\n"
    "MANDATORY CREATIVE & TECHNICAL DIRECTIVES:\n"
    "1. LISTEN TO THE AUDIO TO REPAIR ASR GARBLES (`word_repairs`):\n"
    "   - Hear what the speaker actually says — especially English tech, brand, model, and "
    "proper-noun loanwords that Sorani ASR phonetically garbled (e.g. `ما فەیبوو فایف`, "
    "`ڕیستیک` -> `ڕیستریکت`, `مۆدەی` -> `مۆدێل`, `بەیانیەکەی` -> `بەیانییەکەی`, "
    "`ڕەستۆرانتەکە` -> `ڕێستۆرانتەکە`, `کاشەرەکە` -> `کاشێرەکە`).\n"
    "   - Emit strictly 1-to-1 single-token `word_repairs` keyed by exact 0-based `word_index`.\n"
    '   - `repaired` MUST be a non-empty string (minLength 1) — NEVER emit empty `""` to delete '
    "a token; `original` MUST match `words[word_index]` character-for-character.\n"
    "   - Preserve authentic spoken Sorani dialect; never translate or invent missing words.\n\n"
    "2. RESTRAIN CAMERA MOVEMENT (`camera_moves`, D-382):\n"
    "   - Default framing is a ROCK-STEADY `1.00x` LOCKED TRIPOD. ZERO wobble, ZERO sway.\n"
    "   - Emit ONLY 2-3 genuinely earned, strictly non-overlapping camera moves per 60 s clip "
    "(each 2500-3500 ms, strictly inside `[0, duration_ms]`, total combined duration <= 18% of "
    "`duration_ms` so >= 82% stays rock-steady 1.00x locked tripod — HARD REJECT above 25%):\n"
    "     * `punch_cut` (`scale_start=1.00, scale_end=1.12`, span `end_ms >= start_ms + 2000`, "
    "NEVER `end_ms == start_ms`): snaps immediately to `scale_end` at `start_ms` and holds "
    "rock-steady for 2-5 s until `end_ms`, ONLY on real punchlines or major editorial jump-cuts "
    "(>= 600 ms removed) — never on arbitrary timers.\n"
    "     * `slow_push` (gentle S-curve `1.00 -> 1.08` over 3-4 s, `end_ms >= start_ms + 2500`): "
    "at most 1-2 per clip on emotional reveals or rising story payoffs.\n"
    "     * `wide_release` (`scale_start=1.12, scale_end=1.00`, span `end_ms >= start_ms + 2000`): "
    "snaps cleanly back to `1.00x` at `start_ms` and holds until `end_ms`.\n"
    "   - Every `scale_start` and `scale_end` MUST stay inside `[1.00, 1.16]`.\n"
    "   - Never stack digital zoom on top of an existing source camera shot cut.\n\n"
    "3. SELECT VIRAL TIKTOK CAPTION BEATS & POWER WORDS (`caption_beats`, D-383):\n"
    "   - Emit ONLY the 4-10 highest-impact semantic `power_word_index` highlights as 1-word "
    'beats (`{"word_indices": [i], "power_word_index": i, "accent_color": "#B8FF2E"}`) '
    "with strictly increasing, non-duplicate word indices (our deterministic viral chunker "
    "handles all remaining 1-2 word / max-3-short <= 14 characters chunks automatically!).\n"
    "   - Pick semantic `power_word_index` on genuine story punchlines/concepts — NEVER on "
    "random loud filler words.\n\n"
    "4. TRIM DEAD AIR, FILLERS & TANGENTS (`cuts`):\n"
    "   - Emit `cuts: []` when the input proxy is already silence-trimmed; otherwise every cut "
    "`[start_ms, end_ms]` MUST lie strictly OUTSIDE every word's `[start_ms, end_ms]` (never "
    "slice mid-word).\n\n"
    "5. HOOK TITLE & EARNED MOTION-GRAPHIC CALLOUTS (`hook_title_ckb`, `visual_interrupts`):\n"
    "   - Write a punchy 4-6 word Central Kurdish (Sorani, Arabic script — NEVER English) "
    "`hook_title_ckb` using a curiosity-gap or emotional hook (never raw opening filler).\n"
    "   - Emit 1-3 `visual_interrupts` on clips >= 28 s (0 on clips < 28 s) spaced >= 9 s apart. "
    "Whenever the speaker states a vivid number, year, or percentage, format `text_ckb` as an "
    'animated Stat Card: `"<NUMBER> | <2-4 WORD SORANI LABEL>"` (e.g. `"80% | کۆمەڵگەی کوردی"` '
    'or `"1969 | گەیشتن بە مانگ"`).\n\n'
    "Respond with ONLY a single valid JSON object matching the exact schema."
)

CRITIQUE_SYSTEM_PROMPT: Final[str] = (
    "You are the Watch-Before-Ship Multimodal Quality Critic for HawEdit V10.2 (D-386, D-394).\n"
    "Watch the rendered 480p@2fps preview video and listen to its audio alongside the "
    "compiled DirectorScript JSON and transcript. Audit the reel against ALL FIVE checks:\n"
    "1. UNNECESSARY CAMERA MOTION & VISUAL VARIETY (`visual_variety`, `active_speaker_framing`): "
    "Flag wobble, drift, unmotivated zoom, > 4 moves per 60 s, > 25% moving-camera time, or "
    "misframed speaker on wide/2-person shots.\n"
    "2. BROKEN KURDISH TEXT (`kurdish_subtitle_accuracy`): Flag disconnected/reversed RTL Arabic "
    "glyphs, missing Sorani diacritics, or major surviving English/technical loanword garbles.\n"
    "3. AWKWARD CUTS & FILLER CLEANLINESS (`filler_cleanliness`): Flag unpruned verbal crutches "
    "(`یانی`, `ئێ`, `وەڵا`), clipped mid-word syllables, or long dead air >= 0.6 s.\n"
    "4. SUBTITLE READABILITY: Flag any 4+ word chunks, text/overlays colliding with the speaker's "
    "face, hands, or platform UI margins, glyph ghosting, or poor contrast.\n"
    "5. VIRAL HOOK STRENGTH & STORY COMPLETENESS (`story_completeness`): Flag missing/unreadable "
    "0-3 s hook title, mid-thought cutoffs, or incoherent jumps.\n\n"
    "Return ONLY valid JSON matching the CritiqueVerdict schema:\n"
    "- `approved`: true if all critical ship-stoppers pass (restrained camera >= 75% locked "
    "with zero sway, joined readable Kurdish RTL glyphs with core technical words accurate, "
    "zero clipped mid-word cuts or >= 0.6 s dead air, legible 1-2 word captions with zero face "
    "overlap). Do NOT reject for fixed clip-boundary endings, numeral style ('2' vs 'دوو'), "
    "minor spoken-dialect spelling variants, or brief natural breaths (< 0.4 s) that cannot be "
    "fixed by a DirectorScript patch.\n"
    "- `score`: float in `[0.0, 100.0]`.\n"
    "- `issues`: concrete, actionable list of ship-stopping defects (empty when approved).\n"
    "- `patch`: null if approved, or a minimal bounded DirectorScript patch object fixing "
    "ONLY the detected defects (allowed keys: `hook_title_ckb`, `word_repairs`, `cuts`, "
    "`camera_moves`, `caption_beats`, `visual_interrupts`, `cold_open_span_ms`). When patching "
    "`word_repairs`, include BOTH existing repairs and every newly fixed word (using the exact "
    "`word_index` and `original` from the transcript, and non-empty `repaired`)."
)

_WORD_REPAIR_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "word_index": {"type": "integer"},
        "original": {"type": "string", "minLength": 1},
        "repaired": {"type": "string", "minLength": 1},
        "reason": {"type": "string"},
    },
    "required": ["word_index", "original", "repaired", "reason"],
}

_CUT_REGION_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "start_ms": {"type": "integer"},
        "end_ms": {"type": "integer"},
        "kind": {"type": "string", "enum": ["filler", "silence", "tangent", "cold_open"]},
        "reason": {"type": "string"},
    },
    "required": ["start_ms", "end_ms", "kind", "reason"],
}

_CAMERA_MOVE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "start_ms": {"type": "integer"},
        "end_ms": {"type": "integer"},
        "kind": {
            "type": "string",
            "enum": ["locked", "punch_cut", "slow_push", "wide_release"],
        },
        "scale_start": {"type": "number"},
        "scale_end": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["start_ms", "end_ms", "kind", "scale_start", "scale_end", "reason"],
}

_CAPTION_BEAT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "word_indices": {"type": "array", "items": {"type": "integer"}},
        "power_word_index": {"type": "integer", "nullable": True},
        "accent_color": {"type": "string"},
    },
    "required": ["word_indices"],
}

_VISUAL_INTERRUPT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "start_ms": {"type": "integer"},
        "end_ms": {"type": "integer"},
        "text_ckb": {"type": "string"},
        "position": {"type": "string", "enum": ["top", "chest"]},
    },
    "required": ["start_ms", "end_ms", "text_ckb", "position"],
}

DIRECTOR_SCRIPT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "hook_title_ckb": {"type": "string"},
        "word_repairs": {"type": "array", "items": _WORD_REPAIR_SCHEMA},
        "cuts": {"type": "array", "items": _CUT_REGION_SCHEMA},
        "camera_moves": {"type": "array", "items": _CAMERA_MOVE_SCHEMA},
        "caption_beats": {"type": "array", "items": _CAPTION_BEAT_SCHEMA},
        "visual_interrupts": {"type": "array", "items": _VISUAL_INTERRUPT_SCHEMA},
        "cold_open_span_ms": {
            "type": "array",
            "items": {"type": "integer"},
            "nullable": True,
        },
    },
    "required": [
        "hook_title_ckb",
        "word_repairs",
        "cuts",
        "camera_moves",
        "caption_beats",
        "visual_interrupts",
    ],
}

CRITIQUE_VERDICT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "score": {"type": "number"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "patch": {
            "type": "object",
            "nullable": True,
            "properties": {
                "hook_title_ckb": {"type": "string"},
                "word_repairs": {"type": "array", "items": _WORD_REPAIR_SCHEMA},
                "cuts": {"type": "array", "items": _CUT_REGION_SCHEMA},
                "camera_moves": {"type": "array", "items": _CAMERA_MOVE_SCHEMA},
                "caption_beats": {"type": "array", "items": _CAPTION_BEAT_SCHEMA},
                "visual_interrupts": {"type": "array", "items": _VISUAL_INTERRUPT_SCHEMA},
                "cold_open_span_ms": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "nullable": True,
                },
            },
        },
    },
    "required": ["approved", "score", "issues"],
}


class DirectorUnavailable(RuntimeError):
    """Raised fail-loud when a director backend, media proxy, or model response fails."""


class ProxyBuildError(DirectorUnavailable):
    """Raised fail-loud when FFmpeg cannot build a director proxy or critique preview."""


@runtime_checkable
class DirectorBrain(Protocol):
    """Unified multimodal creative director & watch-before-ship critic protocol.

    Structurally compatible with ``hawedit.v8.compiler.V8DirectorProtocol``.
    """

    def direct_clip(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        clip_id: str,
        words: Sequence[Word],
        shot_cuts_ms: Sequence[int] = (),
        jump_cuts_ms: Sequence[JumpCutInput] = (),
    ) -> DirectorScript:
        """Direct one candidate clip and return a strictly validated ``DirectorScript``."""
        ...

    def critique_clip(
        self,
        *,
        rendered_mp4: Path,
        script: DirectorScript,
        words: Sequence[Word],
        preview_mp4: Path | None = None,
    ) -> CritiqueVerdict:
        """Inspect a rendered clip + script and return a bounded ``CritiqueVerdict``."""
        ...


def _resolve_ffmpeg_binary(ffmpeg: Path | None) -> Path:
    resolved = ffmpeg if ffmpeg is not None else find_ffmpeg()
    if resolved is None or not resolved.is_file():
        raise ProxyBuildError(
            "FFmpeg binary not found; run `bash scripts/fetch-ffmpeg.sh` or pass `ffmpeg=`."
        )
    return resolved


def _bounded_text(raw: str, limit: int = _MAX_ERROR_CHARS) -> str:
    printable = "".join(ch if ch.isprintable() else " " for ch in raw)
    collapsed = " ".join(printable.split())
    if len(collapsed) > limit:
        return f"{collapsed[: limit - 3]}..."
    return collapsed


def _validate_positive_finite(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")
    return float(value)


def _validate_int_bound(value: int, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {value!r}")
    return value


def _run_ffmpeg(cmd: Sequence[str], *, label: str) -> None:
    try:
        completed = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            check=False,
            timeout=_FFMPEG_PROXY_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProxyBuildError(f"FFmpeg {label} execution failed: {exc}") from exc
    if completed.returncode != 0:
        detail = _bounded_text(completed.stderr or completed.stdout)
        raise ProxyBuildError(f"FFmpeg {label} exited {completed.returncode}: {detail}")


def build_director_proxy(
    source_mp4: Path,
    clip_in_ms: int,
    clip_out_ms: int,
    out_mp4: Path,
    *,
    fps: float = 1.0,
    height: int = 360,
    ffmpeg: Path | None = None,
) -> Path:
    """Build a lightweight 360p @ 1 fps H.264 + 64 kbps mono AAC proxy for multimodal directing."""
    if not source_mp4.is_file():
        raise FileNotFoundError(f"source_mp4 does not exist: {source_mp4}")
    start_ms = _validate_int_bound(clip_in_ms, "clip_in_ms", minimum=0)
    end_ms = _validate_int_bound(clip_out_ms, "clip_out_ms", minimum=start_ms + 1)
    fps_val = _validate_positive_finite(fps, "fps")
    height_val = _validate_int_bound(height, "height", minimum=64)
    ffmpeg_bin = _resolve_ffmpeg_binary(ffmpeg)

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    duration_s = (end_ms - start_ms) / 1000.0
    cmd = (
        str(ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_ms / 1000.0:.3f}",
        "-t",
        f"{duration_s:.3f}",
        "-i",
        str(source_mp4),
        "-vf",
        f"fps={fps_val:g},scale=-2:{height_val}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-movflags",
        "+faststart",
        str(out_mp4),
    )
    _run_ffmpeg(cmd, label="director proxy build")
    if not out_mp4.is_file() or out_mp4.stat().st_size == 0:
        raise ProxyBuildError(f"FFmpeg produced missing or empty director proxy at {out_mp4}")
    return out_mp4


def build_critique_preview(
    rendered_mp4: Path,
    out_mp4: Path,
    *,
    fps: float = 2.0,
    height: int = 480,
    ffmpeg: Path | None = None,
) -> Path:
    """Build a 480p @ 2 fps H.264 + 64 kbps mono AAC preview for Watch-Before-Ship critique."""
    if not rendered_mp4.is_file():
        raise FileNotFoundError(f"rendered_mp4 does not exist: {rendered_mp4}")
    fps_val = _validate_positive_finite(fps, "fps")
    height_val = _validate_int_bound(height, "height", minimum=64)
    ffmpeg_bin = _resolve_ffmpeg_binary(ffmpeg)

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        str(ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(rendered_mp4),
        "-vf",
        f"fps={fps_val:g},scale=-2:{height_val}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-movflags",
        "+faststart",
        str(out_mp4),
    )
    _run_ffmpeg(cmd, label="critique preview build")
    if not out_mp4.is_file() or out_mp4.stat().st_size == 0:
        raise ProxyBuildError(f"FFmpeg produced missing or empty critique preview at {out_mp4}")
    return out_mp4


def _make_http_transport(timeout_s: float) -> Transport:
    def _send(
        url: str,
        body: bytes | None,
        headers: Mapping[str, str],
    ) -> tuple[int, str]:
        request_headers = dict(headers)
        if body is not None:
            request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with open_without_redirects(req, timeout=timeout_s) as resp:
                raw = resp.read(MAX_DIRECTOR_RESPONSE_BYTES + 1)
                if len(raw) > MAX_DIRECTOR_RESPONSE_BYTES:
                    raise DirectorUnavailable(
                        f"Director response from {url} exceeded {MAX_DIRECTOR_RESPONSE_BYTES} bytes"
                    )
                return int(resp.status), raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            try:
                err_raw = exc.read(MAX_DIRECTOR_RESPONSE_BYTES + 1)
                detail = err_raw[: _MAX_ERROR_CHARS * 4].decode("utf-8", errors="replace")
            except OSError:
                detail = ""
            return int(exc.code), detail
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, str(exc)

    return _send


def _strip_json_wrappers(raw_text: str) -> str:
    """Strip ``<think>...</think>`` reasoning blocks and markdown code fences before JSON parse."""
    cleaned = _THINK_BLOCK_RE.sub("", raw_text).strip()
    # Some LM Studio chat templates inject the opening ``<think>`` tag in the prompt prefix so
    # the assistant message begins mid-thought and emits only the closing ``</think>`` marker.
    closing_matches = list(_CLOSING_THINK_RE.finditer(cleaned))
    if closing_matches:
        cleaned = cleaned[closing_matches[-1].end() :].strip()
    fenced = _CODE_FENCE_RE.search(cleaned)
    if fenced is not None:
        return fenced.group(1).strip()
    return cleaned


def _openai_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Convert OpenAPI 3.0 schema (with ``nullable: true``) to strict OpenAI JSON Schema."""

    def _convert(node: Any) -> Any:
        if isinstance(node, Mapping):
            nullable = bool(node.get("nullable", False))
            out: dict[str, Any] = {}
            for key, val in node.items():
                if key == "nullable":
                    continue
                out[str(key)] = _convert(val)
            if out.get("type") == "object" and "additionalProperties" not in out:
                out["additionalProperties"] = False
            if nullable and isinstance(out.get("type"), str):
                out["type"] = [out["type"], "null"]
            return out
        if isinstance(node, list):
            return [_convert(item) for item in node]
        return node

    converted = _convert(schema)
    if not isinstance(converted, dict):
        raise ValueError("schema root must be a JSON object")
    return converted


def _normalize_jump_cuts(jump_cuts_ms: Sequence[JumpCutInput]) -> tuple[tuple[int, int], ...]:
    """Normalize ``int`` cut positions or ``(at_ms, removed_ms)`` pairs into ``(at_ms, rem_ms)``."""
    normalized: list[tuple[int, int]] = []
    for item in jump_cuts_ms:
        if isinstance(item, tuple):
            at_ms, rem_ms = item
            normalized.append((int(at_ms), int(rem_ms)))
        else:
            normalized.append((int(item), _MIN_MAJOR_JUMP_CUT_MS))
    return tuple(normalized)


def _infer_duration_ms(
    *,
    duration_ms: int | None,
    script: DirectorScript,
    words: Sequence[Word],
) -> int:
    if duration_ms is not None:
        return _validate_int_bound(duration_ms, "duration_ms", minimum=1)
    candidates = [w.end_ms for w in words]
    candidates.extend(m.end_ms for m in script.camera_moves)
    candidates.extend(c.end_ms for c in script.cuts)
    candidates.extend(v.end_ms for v in script.visual_interrupts)
    if not candidates:
        raise ValueError("duration_ms cannot be inferred from empty words and script")
    return max(1, max(candidates))


def _parse_director_script_json(
    raw_text: str,
    *,
    clip_id: str,
    duration_ms: int,
    words: Sequence[Word],
) -> DirectorScript:
    cleaned = _strip_json_wrappers(raw_text)
    try:
        parsed: object = json.loads(cleaned)
    except ValueError as exc:
        raise DirectorUnavailable(f"Director returned malformed JSON: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise DirectorUnavailable(
            f"Expected JSON object for DirectorScript, got {type(parsed).__name__}"
        )
    merged = {str(k): v for k, v in parsed.items()}
    merged["clip_id"] = clip_id
    try:
        script = DirectorScript.from_dict(merged)
        if not script.hook_title_ckb.strip():
            raise DirectorScriptError("Director returned empty hook_title_ckb")
        validate_director_script(script, duration_ms=duration_ms, words=words)
    except (ValueError, DirectorScriptError) as exc:
        raise DirectorUnavailable(f"DirectorScript failed strict validation: {exc}") from exc
    return script


def _parse_critique_verdict_json(raw_text: str) -> CritiqueVerdict:
    cleaned = _strip_json_wrappers(raw_text)
    try:
        return CritiqueVerdict.from_json(cleaned)
    except (ValueError, DirectorScriptError) as exc:
        raise DirectorUnavailable(f"Critic returned invalid CritiqueVerdict JSON: {exc}") from exc


def _format_director_user_prompt(
    *,
    clip_id: str,
    words: Sequence[Word],
    duration_ms: int,
    shot_cuts_ms: Sequence[int],
    jump_cuts_ms: Sequence[tuple[int, int]],
    visual_context: Sequence[str] = (),
) -> str:
    word_lines = "\n".join(
        f"[{idx}] {w.start_ms}..{w.end_ms}ms: {w.w}" for idx, w in enumerate(words)
    )
    shot_str = ", ".join(f"{t}ms" for t in shot_cuts_ms) if shot_cuts_ms else "none"
    jump_str = (
        ", ".join(f"at={at_ms}ms (removed={rem_ms}ms)" for at_ms, rem_ms in jump_cuts_ms)
        if jump_cuts_ms
        else "none"
    )
    max_moves = max(2, math.ceil(duration_ms / 15_000))
    vis_block = (
        "Visual scene intelligence (VideoChat3-4B / TimeLens2-4B / ASD — coordinate camera moves "
        "& visual_interrupts with these grounded observations):\n"
        + "\n".join(f"- {ln}" for ln in visual_context)
        + "\n\n"
        if visual_context
        else ""
    )
    return (
        f"Clip ID: {clip_id}\n"
        f"Clip duration: {duration_ms} ms\n"
        f"Camera move hard cap: at most {max_moves} moves, <= 25% moving time, 0 sway.\n"
        f"Source shot cuts: {shot_str}\n"
        f"Candidate editorial jump-cuts: {jump_str}\n\n"
        f"{vis_block}"
        f"Word-indexed Central Kurdish (Sorani) ASR transcript ({len(words)} words):\n"
        f"{word_lines}\n"
    )


def _format_critique_user_prompt(
    *,
    clip_id: str,
    script: DirectorScript,
    words: Sequence[Word],
    duration_ms: int,
) -> str:
    word_lines = "\n".join(
        f"[{idx}] {w.start_ms}..{w.end_ms}ms: {w.w}" for idx, w in enumerate(words)
    )
    script_json = json.dumps(script.to_dict(), ensure_ascii=False)
    return (
        f"Clip ID: {clip_id}\n"
        f"Rendered clip duration: {duration_ms} ms\n\n"
        f"Compiled DirectorScript JSON:\n{script_json}\n\n"
        f"Transcript words:\n{word_lines}\n"
    )


def _validate_clip_inputs(
    *,
    clip_id: str,
    clip_in_ms: int,
    clip_out_ms: int,
    words: Sequence[Word],
) -> int:
    if not isinstance(clip_id, str) or not clip_id.strip():
        raise ValueError("clip_id must be a non-empty string")
    start_ms = _validate_int_bound(clip_in_ms, "clip_in_ms", minimum=0)
    end_ms = _validate_int_bound(clip_out_ms, "clip_out_ms", minimum=start_ms + 1)
    if not words:
        raise ValueError("words must be non-empty")
    return end_ms - start_ms


def _extract_gemini_error(status: int, body: str) -> str:
    try:
        msg: object = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        msg = body
    text = msg if isinstance(msg, str) else type(msg).__name__
    return f"HTTP {status}: {_bounded_text(text)}"


class GeminiVideoDirector:
    """Cloud Gemini 2.5 Pro / Gemini 3 native video+audio Multimodal Director (D-384, D-386)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = DEFAULT_GEMINI_DIRECTOR_MODEL,
        timeout_s: float = DEFAULT_GEMINI_TIMEOUT_S,
        ffmpeg: Path | None = None,
        transport: Transport | None = None,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        self.model_id: str = model_id.strip()
        self.timeout_s: float = _validate_positive_finite(timeout_s, "timeout_s")
        self._api_key: str | None = api_key.strip() if api_key and api_key.strip() else None
        self._ffmpeg: Path | None = ffmpeg
        self._transport: Transport = transport or _make_http_transport(self.timeout_s)

    def _resolve_headers(self) -> dict[str, str]:
        try:
            key = self._api_key or read_credential(GEMINI_API_KEY)
        except (OSError, UnicodeError) as exc:
            raise DirectorUnavailable(
                "Gemini credential storage could not be read; no request was sent."
            ) from exc
        if not key:
            raise DirectorUnavailable(
                f"No {GEMINI_API_KEY} configured. Run `python -m hawedit.credentials` or set "
                f"{GEMINI_API_KEY} in the environment."
            )
        self._api_key = key
        return {"x-goog-api-key": key, "Content-Type": "application/json"}

    @staticmethod
    def _encode_inline_mp4(mp4_path: Path, *, label: str) -> dict[str, Any]:
        if not mp4_path.is_file():
            raise DirectorUnavailable(f"{label} video file not found: {mp4_path}")
        size = mp4_path.stat().st_size
        if size <= 0:
            raise DirectorUnavailable(f"{label} video file is empty: {mp4_path}")
        if size > MAX_GEMINI_INLINE_BYTES:
            raise DirectorUnavailable(
                f"{label} video size {size} bytes exceeds inline limit "
                f"{MAX_GEMINI_INLINE_BYTES} bytes; build a lighter proxy first."
            )
        encoded = base64.b64encode(mp4_path.read_bytes()).decode("ascii")
        return {"inlineData": {"mimeType": "video/mp4", "data": encoded}}

    def _call_generate_content(
        self,
        *,
        system_prompt: str,
        parts: list[dict[str, Any]],
        response_schema: Mapping[str, Any],
    ) -> str:
        url = f"{API_ROOT}/models/{self.model_id}:generateContent"
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": dict(response_schema),
            },
        }
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, body = self._transport(url, body_bytes, self._resolve_headers())
        if status != 200:
            raise DirectorUnavailable(
                f"GeminiVideoDirector ({self.model_id}) request failed — "
                f"{_extract_gemini_error(status, body)}"
            )
        try:
            text = extract_response_text(body)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise DirectorUnavailable(
                f"GeminiVideoDirector response missing candidate text: {exc}"
            ) from exc
        if not text.strip():
            raise DirectorUnavailable("GeminiVideoDirector returned empty response text")
        return text

    def direct_clip(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        clip_id: str,
        words: Sequence[Word],
        shot_cuts_ms: Sequence[int] = (),
        jump_cuts_ms: Sequence[JumpCutInput] = (),
        video_proxy: Path | None = None,
        visual_context: Sequence[str] = (),
    ) -> DirectorScript:
        duration_ms = _validate_clip_inputs(
            clip_id=clip_id,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            words=words,
        )
        normalized_jumps = _normalize_jump_cuts(jump_cuts_ms)
        user_prompt = _format_director_user_prompt(
            clip_id=clip_id,
            words=words,
            duration_ms=duration_ms,
            shot_cuts_ms=shot_cuts_ms,
            jump_cuts_ms=normalized_jumps,
            visual_context=visual_context,
        )
        if video_proxy is not None:
            video_part = self._encode_inline_mp4(video_proxy, label="director proxy")
        else:
            with tempfile.TemporaryDirectory(prefix="hawedit-v8-gemini-proxy-") as tmp_dir:
                built_proxy = build_director_proxy(
                    source_mp4,
                    clip_in_ms,
                    clip_out_ms,
                    Path(tmp_dir) / "director_proxy.mp4",
                    ffmpeg=self._ffmpeg,
                )
                video_part = self._encode_inline_mp4(built_proxy, label="director proxy")

        raw_text = self._call_generate_content(
            system_prompt=DIRECTOR_SYSTEM_PROMPT,
            parts=[video_part, {"text": user_prompt}],
            response_schema=DIRECTOR_SCRIPT_SCHEMA,
        )
        return _parse_director_script_json(
            raw_text,
            clip_id=clip_id,
            duration_ms=duration_ms,
            words=words,
        )

    def critique_clip(
        self,
        *,
        rendered_mp4: Path,
        script: DirectorScript,
        words: Sequence[Word],
        duration_ms: int | None = None,
        preview_mp4: Path | None = None,
    ) -> CritiqueVerdict:
        if not words:
            raise ValueError("words must be non-empty")
        resolved_dur = _infer_duration_ms(duration_ms=duration_ms, script=script, words=words)
        user_prompt = _format_critique_user_prompt(
            clip_id=script.clip_id,
            script=script,
            words=words,
            duration_ms=resolved_dur,
        )
        if preview_mp4 is not None:
            preview_part = self._encode_inline_mp4(preview_mp4, label="critique preview")
        else:
            with tempfile.TemporaryDirectory(prefix="hawedit-v8-gemini-critique-") as tmp_dir:
                built_preview = build_critique_preview(
                    rendered_mp4,
                    Path(tmp_dir) / "critique_preview.mp4",
                    ffmpeg=self._ffmpeg,
                )
                preview_part = self._encode_inline_mp4(built_preview, label="critique preview")

        raw_text = self._call_generate_content(
            system_prompt=CRITIQUE_SYSTEM_PROMPT,
            parts=[preview_part, {"text": user_prompt}],
            response_schema=CRITIQUE_VERDICT_SCHEMA,
        )
        return _parse_critique_verdict_json(raw_text)


def _extract_omni_media(
    video_mp4: Path,
    *,
    fps: float,
    max_frames: int,
    height: int = 360,
    include_audio: bool = True,
    audio_wav: Path | None = None,
    ffmpeg: Path | None = None,
) -> tuple[tuple[bytes, ...], bytes | None]:
    """Extract sampled JPEG keyframes and optional 16 kHz mono WAV audio for LocalOmniDirector."""
    if not video_mp4.is_file() or video_mp4.stat().st_size == 0:
        raise DirectorUnavailable(f"Video file missing or empty for LocalOmniDirector: {video_mp4}")
    ffmpeg_bin = _resolve_ffmpeg_binary(ffmpeg)

    with tempfile.TemporaryDirectory(prefix="hawedit-v8-omni-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        frame_pattern = tmp_path / "frame_%04d.jpg"
        frame_cmd = (
            str(ffmpeg_bin),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_mp4),
            "-vf",
            f"fps={fps:g},scale=-2:{height}",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "6",
            str(frame_pattern),
        )
        _run_ffmpeg(frame_cmd, label="omni keyframe extraction")
        frame_paths = sorted(tmp_path.glob("frame_*.jpg"))
        if not frame_paths:
            raise DirectorUnavailable(
                f"FFmpeg extracted 0 keyframes from {video_mp4} for LocalOmniDirector"
            )
        frames = tuple(p.read_bytes() for p in frame_paths[:max_frames])

        audio_bytes: bytes | None = None
        if include_audio:
            if audio_wav is not None:
                if not audio_wav.is_file() or audio_wav.stat().st_size == 0:
                    raise DirectorUnavailable(f"audio_wav missing or empty: {audio_wav}")
                if audio_wav.stat().st_size > MAX_OMNI_AUDIO_BYTES:
                    raise DirectorUnavailable(
                        f"audio_wav exceeds {MAX_OMNI_AUDIO_BYTES} bytes for LocalOmniDirector"
                    )
                audio_bytes = audio_wav.read_bytes()
            else:
                extracted_wav = tmp_path / "audio.wav"
                audio_cmd = (
                    str(ffmpeg_bin),
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(video_mp4),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(extracted_wav),
                )
                _run_ffmpeg(audio_cmd, label="omni audio extraction")
                if not extracted_wav.is_file() or extracted_wav.stat().st_size <= 44:
                    raise DirectorUnavailable(
                        f"FFmpeg extracted empty audio track from {video_mp4}"
                    )
                if extracted_wav.stat().st_size > MAX_OMNI_AUDIO_BYTES:
                    raise DirectorUnavailable(
                        f"Extracted WAV exceeds {MAX_OMNI_AUDIO_BYTES} bytes for LocalOmniDirector"
                    )
                audio_bytes = extracted_wav.read_bytes()

    return frames, audio_bytes


_AUDIO_REJECT_HINTS: Final[tuple[str, ...]] = (
    "unsupported",
    "not support",
    "does not support",
    "invalid",
    "unknown",
    "unrecognized",
    "failed to parse",
    "expected",
    "cannot",
    "not allowed",
)
_VISION_REJECT_HINTS: Final[tuple[str, ...]] = (
    "unsupported",
    "not support",
    "does not support",
    "invalid",
    "unknown",
    "unrecognized",
    "not a vision",
    "no mmproj",
    "mmproj",
    "failed to parse",
    "cannot",
    "not allowed",
)


def _is_input_audio_rejection(status: int, error_body: str) -> bool:
    """Return True only when HTTP 400 specifically rejects ``input_audio`` content blocks."""
    if status != 400:
        return False
    low = error_body.lower()
    if "input_audio" in low:
        return True
    if "image_url" in low and "text" in low and ("either" in low or "invalid 'content'" in low):
        return True
    return "audio" in low and any(hint in low for hint in _AUDIO_REJECT_HINTS)


def _is_image_url_rejection(status: int, error_body: str) -> bool:
    """Return True only when HTTP 400 specifically rejects ``image_url``/vision content blocks."""
    if status != 400:
        return False
    low = error_body.lower()
    if "image_url" in low:
        return True
    return ("image" in low or "vision" in low or "multimodal" in low) and any(
        hint in low for hint in _VISION_REJECT_HINTS
    )


def _resolve_local_modality(
    modality: LocalDirectorModality | None,
    *,
    include_audio: bool,
) -> LocalDirectorModality:
    raw: str | None = modality
    if raw is None:
        env_val = os.environ.get(OMNI_MODALITY_ENV, "").strip().lower()
        if env_val:
            raw = env_val
        else:
            return "omni" if include_audio else "vision"
    if raw == "omni":
        return "omni"
    if raw == "vision":
        return "vision"
    if raw == "text":
        return "text"
    raise ValueError(
        f"Unsupported local director modality {raw!r}; expected 'omni', 'vision', or 'text'."
    )


def _build_omni_user_content(
    user_prompt: str,
    *,
    frames: Sequence[bytes],
    audio_bytes: bytes | None,
    modality: LocalDirectorModality,
) -> str | list[dict[str, Any]]:
    if modality == "text":
        return (
            f"{user_prompt}\n"
            "[Local director modality: text-only transcript mode - no video frames or audio "
            "blocks attached; direct strictly from transcript timestamps and shot/jump cuts.]\n"
        )
    user_content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for frame in frames:
        b64_frame = base64.b64encode(frame).decode("ascii")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_frame}"},
            }
        )
    if modality == "omni" and audio_bytes is not None:
        b64_audio = base64.b64encode(audio_bytes).decode("ascii")
        user_content.append(
            {
                "type": "input_audio",
                "input_audio": {"data": b64_audio, "format": "wav"},
            }
        )
    return user_content


class LocalOmniDirector:
    """Local GPU 1 Qwen-Omni / LM Studio OpenAI-compatible Director (D-384, D-386, D-391)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model_id: str | None = None,
        timeout_s: float = DEFAULT_OMNI_TIMEOUT_S,
        api_key: str | None = None,
        include_audio: bool = True,
        modality: LocalDirectorModality | None = None,
        keyframe_fps: float = 0.5,
        max_keyframes: int = 24,
        ffmpeg: Path | None = None,
        transport: Transport | None = None,
    ) -> None:
        raw_url = (
            (os.environ.get(OMNI_URL_ENV, "").strip() or DEFAULT_OMNI_URL)
            if base_url is None
            else base_url.strip()
        )
        parsed = urllib.parse.urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"base_url must be a valid http(s) URL, got {raw_url!r}")
        resolved_modality = _resolve_local_modality(modality, include_audio=bool(include_audio))
        self.base_url: str = raw_url.rstrip("/")
        self.timeout_s: float = _validate_positive_finite(timeout_s, "timeout_s")
        self.keyframe_fps: float = _validate_positive_finite(keyframe_fps, "keyframe_fps")
        self.max_keyframes: int = _validate_int_bound(max_keyframes, "max_keyframes", minimum=1)
        self.modality: LocalDirectorModality = resolved_modality
        self.supports_vision: bool = resolved_modality in ("omni", "vision")
        self.supports_audio: bool = resolved_modality == "omni" and bool(include_audio)
        self.include_audio: bool = self.supports_audio
        self.model_id: str = (
            os.environ.get(OMNI_MODEL_ENV, "") if model_id is None else model_id
        ).strip()
        self.last_modality_used: LocalDirectorModality | None = None
        self.last_diagnostics: dict[str, Any] = {}
        self._api_key: str | None = api_key.strip() if api_key and api_key.strip() else None
        if (
            self._api_key is not None
            and parsed.scheme == "http"
            and (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError(
                "LocalOmniDirector requires https:// when sending an api_key to a "
                f"non-loopback host: {raw_url!r}"
            )
        self._ffmpeg: Path | None = ffmpeg
        self._transport: Transport = transport or _make_http_transport(self.timeout_s)

    def _headers(self, *, json_body: bool) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _send_json(
        self, path: str, payload: Mapping[str, Any] | None = None
    ) -> tuple[int, str, str]:
        url = f"{self.base_url}{path}"
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        )
        status, text = self._transport(url, body, self._headers(json_body=payload is not None))
        return status, text, url

    @staticmethod
    def _decode_json_object(text: str, *, url: str) -> dict[str, Any]:
        try:
            decoded: object = json.loads(text)
        except ValueError as exc:
            raise DirectorUnavailable(
                f"LocalOmniDirector returned invalid JSON from {url}: {exc}"
            ) from exc
        if not isinstance(decoded, dict):
            raise DirectorUnavailable(
                f"LocalOmniDirector response from {url} must be a JSON object"
            )
        return decoded

    def _request_json(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        status, text, url = self._send_json(path, payload)
        if status != 200:
            raise DirectorUnavailable(
                f"LocalOmniDirector HTTP {status} from {url}: {_bounded_text(text)}"
            )
        return self._decode_json_object(text, url=url)

    def resolve_model(self) -> str:
        """Return configured ``model_id`` or auto-select the first loaded non-embedding model."""
        if self.model_id:
            return self.model_id
        data = self._request_json("/models")
        raw_models = data.get("data")
        if not isinstance(raw_models, list):
            raise DirectorUnavailable(
                f"LocalOmniDirector /models payload missing 'data' list at {self.base_url}/models"
            )
        for item in raw_models:
            if isinstance(item, Mapping):
                mid = item.get("id")
                if isinstance(mid, str) and mid.strip() and "embed" not in mid.lower():
                    self.model_id = mid.strip()
                    return self.model_id
        raise DirectorUnavailable(
            f"No multimodal/chat model loaded at LocalOmniDirector endpoint {self.base_url}/models"
        )

    def _call_chat_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        frames: Sequence[bytes],
        audio_bytes: bytes | None,
        schema_name: str,
        schema: Mapping[str, Any],
    ) -> str:
        model_id = self.resolve_model()
        active_modality: LocalDirectorModality = self.modality
        if active_modality == "omni" and audio_bytes is None:
            active_modality = "vision" if frames else "text"
        elif active_modality == "vision" and not frames:
            active_modality = "text"

        rejections: list[dict[str, Any]] = []
        strict_schema = _openai_strict_schema(schema)
        response: dict[str, Any] | None = None

        while True:
            user_content = _build_omni_user_content(
                user_prompt,
                frames=frames,
                audio_bytes=audio_bytes,
                modality=active_modality,
            )
            payload: dict[str, Any] = {
                "model": model_id,
                "temperature": 0.1,
                "reasoning_effort": "none",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": strict_schema,
                    },
                },
            }
            status, text, url = self._send_json("/chat/completions", payload)
            if status == 200:
                response = self._decode_json_object(text, url=url)
                break
            if active_modality == "omni" and _is_input_audio_rejection(status, text):
                rejections.append(
                    {
                        "rejected_modality": "omni",
                        "http_status": status,
                        "reason": _bounded_text(text),
                    }
                )
                active_modality = "vision" if frames else "text"
                continue
            if active_modality == "vision" and _is_image_url_rejection(status, text):
                rejections.append(
                    {
                        "rejected_modality": "vision",
                        "http_status": status,
                        "reason": _bounded_text(text),
                    }
                )
                active_modality = "text"
                continue
            self.last_modality_used = None
            self.last_diagnostics = {
                "configured_modality": self.modality,
                "effective_modality": None,
                "model_id": model_id,
                "endpoint": url,
                "modality_rejections": rejections,
                "error": f"HTTP {status}: {_bounded_text(text)}",
            }
            raise DirectorUnavailable(
                f"LocalOmniDirector HTTP {status} from {url}: {_bounded_text(text)}"
            )

        self.last_modality_used = active_modality
        self.last_diagnostics = {
            "configured_modality": self.modality,
            "effective_modality": active_modality,
            "model_id": model_id,
            "endpoint": f"{self.base_url}/chat/completions",
            "modality_rejections": rejections,
            "error": None,
        }

        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DirectorUnavailable(
                f"LocalOmniDirector missing 'choices' from {self.base_url}/chat/completions"
            )
        first = choices[0]
        message = first.get("message") if isinstance(first, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str) or not content.strip():
            raise DirectorUnavailable(
                "LocalOmniDirector chat completion returned empty or non-string content"
            )
        return content

    def direct_clip(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        clip_id: str,
        words: Sequence[Word],
        shot_cuts_ms: Sequence[int] = (),
        jump_cuts_ms: Sequence[JumpCutInput] = (),
        video_proxy: Path | None = None,
        audio_wav: Path | None = None,
        visual_context: Sequence[str] = (),
    ) -> DirectorScript:
        duration_ms = _validate_clip_inputs(
            clip_id=clip_id,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            words=words,
        )
        normalized_jumps = _normalize_jump_cuts(jump_cuts_ms)
        frames: tuple[bytes, ...] = ()
        audio_bytes: bytes | None = None
        if self.supports_vision or self.supports_audio:
            if video_proxy is not None:
                frames, audio_bytes = _extract_omni_media(
                    video_proxy,
                    fps=self.keyframe_fps,
                    max_frames=self.max_keyframes,
                    include_audio=self.supports_audio,
                    audio_wav=audio_wav,
                    ffmpeg=self._ffmpeg,
                )
            else:
                with tempfile.TemporaryDirectory(prefix="hawedit-v8-omni-proxy-") as tmp_dir:
                    built_proxy = build_director_proxy(
                        source_mp4,
                        clip_in_ms,
                        clip_out_ms,
                        Path(tmp_dir) / "director_proxy.mp4",
                        ffmpeg=self._ffmpeg,
                    )
                    frames, audio_bytes = _extract_omni_media(
                        built_proxy,
                        fps=self.keyframe_fps,
                        max_frames=self.max_keyframes,
                        include_audio=self.supports_audio,
                        audio_wav=audio_wav,
                        ffmpeg=self._ffmpeg,
                    )

        user_prompt = _format_director_user_prompt(
            clip_id=clip_id,
            words=words,
            duration_ms=duration_ms,
            shot_cuts_ms=shot_cuts_ms,
            jump_cuts_ms=normalized_jumps,
            visual_context=visual_context,
        )
        raw_text = self._call_chat_completion(
            system_prompt=DIRECTOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            frames=frames,
            audio_bytes=audio_bytes,
            schema_name="director_script",
            schema=DIRECTOR_SCRIPT_SCHEMA,
        )
        return _parse_director_script_json(
            raw_text,
            clip_id=clip_id,
            duration_ms=duration_ms,
            words=words,
        )

    def critique_clip(
        self,
        *,
        rendered_mp4: Path,
        script: DirectorScript,
        words: Sequence[Word],
        duration_ms: int | None = None,
        preview_mp4: Path | None = None,
    ) -> CritiqueVerdict:
        if not words:
            raise ValueError("words must be non-empty")
        resolved_dur = _infer_duration_ms(duration_ms=duration_ms, script=script, words=words)
        frames: tuple[bytes, ...] = ()
        audio_bytes: bytes | None = None
        if self.supports_vision or self.supports_audio:
            if preview_mp4 is not None:
                frames, audio_bytes = _extract_omni_media(
                    preview_mp4,
                    fps=min(1.0, max(self.keyframe_fps, 0.5)),
                    max_frames=self.max_keyframes,
                    include_audio=self.supports_audio,
                    ffmpeg=self._ffmpeg,
                )
            else:
                with tempfile.TemporaryDirectory(prefix="hawedit-v8-omni-critique-") as tmp_dir:
                    built_preview = build_critique_preview(
                        rendered_mp4,
                        Path(tmp_dir) / "critique_preview.mp4",
                        ffmpeg=self._ffmpeg,
                    )
                    frames, audio_bytes = _extract_omni_media(
                        built_preview,
                        fps=min(1.0, max(self.keyframe_fps, 0.5)),
                        max_frames=self.max_keyframes,
                        include_audio=self.supports_audio,
                        ffmpeg=self._ffmpeg,
                    )

        user_prompt = _format_critique_user_prompt(
            clip_id=script.clip_id,
            script=script,
            words=words,
            duration_ms=resolved_dur,
        )
        raw_text = self._call_chat_completion(
            system_prompt=CRITIQUE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            frames=frames,
            audio_bytes=audio_bytes,
            schema_name="critique_verdict",
            schema=CRITIQUE_VERDICT_SCHEMA,
        )
        return _parse_critique_verdict_json(raw_text)


def _compute_word_energy_zscores(words: Sequence[Word], audio_wav: Path | None) -> list[float]:
    """Compute per-word acoustic RMS Z-scores via stdlib ``wave`` (or lexical salience)."""
    if audio_wav is None:
        return _lexical_salience_scores(words)
    if not audio_wav.is_file():
        raise FileNotFoundError(f"audio_wav does not exist: {audio_wav}")

    with wave.open(str(audio_wav), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        total_frames = wf.getnframes()
        if sample_rate <= 0 or n_channels < 1 or sampwidth != 2:
            raise ValueError(
                f"Expected 16-bit PCM WAV for offline director energy scoring, got "
                f"sr={sample_rate}, ch={n_channels}, width={sampwidth}"
            )
        if total_frames == 0:
            return _lexical_salience_scores(words)

        rms_values: list[float] = []
        for word in words:
            s_frame = max(0, min(total_frames, int(round(word.start_ms * sample_rate / 1000.0))))
            e_frame = max(
                s_frame, min(total_frames, int(round(word.end_ms * sample_rate / 1000.0)))
            )
            if e_frame <= s_frame:
                rms_values.append(0.0)
                continue
            wf.setpos(s_frame)
            raw = wf.readframes(e_frame - s_frame)
            pcm = array.array("h")
            pcm.frombytes(raw)
            if sys.byteorder == "big":
                pcm.byteswap()
            if not pcm:
                rms_values.append(0.0)
                continue
            if n_channels == 1:
                sq_sum = sum(float(s) * float(s) for s in pcm)
                count = len(pcm)
            else:
                count = len(pcm) // n_channels
                sq_sum = 0.0
                for frame_i in range(count):
                    base = frame_i * n_channels
                    mono = sum(pcm[base + ch] for ch in range(n_channels)) / n_channels
                    sq_sum += mono * mono
            rms_values.append(math.sqrt(sq_sum / max(1, count)) / 32768.0)

    mean = sum(rms_values) / len(rms_values)
    var = sum((v - mean) ** 2 for v in rms_values) / len(rms_values)
    std = math.sqrt(var)
    if std <= 1e-9:
        return _lexical_salience_scores(words)
    return [(v - mean) / std for v in rms_values]


def _lexical_salience_scores(words: Sequence[Word]) -> list[float]:
    scores: list[float] = []
    n = len(words)
    for idx, word in enumerate(words):
        core = word.w.strip(_PUNCT_STRIP)
        if not core or core in _KURDISH_STOP_WORDS:
            scores.append(-1.0)
            continue
        pos_bonus = 0.5 if n > 4 and idx >= int(n * 0.55) else 0.0
        scores.append(min(2.5, len(core) / 4.0) + pos_bonus)
    return scores


def _build_offline_caption_beats(
    repaired_words: Sequence[Word],
    *,
    power_indices: frozenset[int],
    max_short_3_chars: int = 14,
    long_word_chars: int = 8,
    pause_split_ms: int = 260,
) -> tuple[CaptionBeat, ...]:
    """Chunk words into strict 1-2 word (max 3 short <= 14 chars) viral ``CaptionBeat`` tuples."""
    beats: list[CaptionBeat] = []
    n = len(repaired_words)
    idx = 0
    while idx < n:
        core0 = repaired_words[idx].w.strip(_PUNCT_STRIP)
        if idx in power_indices or len(core0) >= long_word_chars:
            beats.append(
                CaptionBeat(
                    word_indices=(idx,),
                    power_word_index=idx if idx in power_indices else None,
                    accent_color="#B8FF2E" if idx in power_indices else "#FFE500",
                )
            )
            idx += 1
            continue

        # Attempt 3 short words ONLY if <= max_short_3_chars total (matching schema.py D-383 law).
        if idx + 2 < n:
            w0, w1, w2 = repaired_words[idx], repaired_words[idx + 1], repaired_words[idx + 2]
            c1 = w1.w.strip(_PUNCT_STRIP)
            c2 = w2.w.strip(_PUNCT_STRIP)
            gap01 = w1.start_ms - w0.end_ms
            gap12 = w2.start_ms - w1.end_ms
            surface_3 = f"{w0.w} {w1.w} {w2.w}"
            if (
                (idx + 1) not in power_indices
                and (idx + 2) not in power_indices
                and len(c1) < long_word_chars
                and len(c2) < long_word_chars
                and gap01 <= pause_split_ms
                and gap12 <= pause_split_ms
                and len(surface_3) <= max_short_3_chars
            ):
                beats.append(CaptionBeat(word_indices=(idx, idx + 1, idx + 2)))
                idx += 3
                continue

        # Default viral 2-word rhythm when next word is not isolated by pause/length/power.
        if idx + 1 < n:
            w0, w1 = repaired_words[idx], repaired_words[idx + 1]
            c1 = w1.w.strip(_PUNCT_STRIP)
            gap01 = w1.start_ms - w0.end_ms
            if (
                (idx + 1) not in power_indices
                and len(c1) < long_word_chars
                and gap01 <= pause_split_ms
            ):
                beats.append(CaptionBeat(word_indices=(idx, idx + 1)))
                idx += 2
                continue

        beats.append(CaptionBeat(word_indices=(idx,)))
        idx += 1
    return tuple(beats)


class OfflineRestrainedDirector:
    """Explicit ``--director offline`` deterministic content-aware director (NEVER auto-fallback).

    Enforces strict human camera restraint (D-382):
    - Default ``1.00x`` locked tripod (``0`` sway, ``>= 80%`` locked screen time).
    - Emits ONLY 2-3 genuinely earned camera moves:
      (a) Max 1 gentle S-curve ``slow_push`` (``1.00 -> 1.08x`` over 3.5 s) on the highest-energy
          payoff build-up.
      (b) Max 2 crisp ``punch_cut`` (``1.00 -> 1.12x`` / ``1.12 -> 1.00x``) ONLY on major
          editorial jump-cuts (``>= 600 ms`` removed) — NEVER on arbitrary timers.
    - Applies deterministic Sorani ASR orthography repair, VAD/silence & isolated filler cuts,
      acoustic-Z-score semantic power words, and 0-2 earned callouts ONLY on clips ``>= 28 s``.
    """

    def __init__(self, *, audio_wav: Path | None = None) -> None:
        self._default_audio_wav: Path | None = audio_wav

    def direct_clip(
        self,
        *,
        source_mp4: Path,
        clip_in_ms: int,
        clip_out_ms: int,
        clip_id: str,
        words: Sequence[Word],
        shot_cuts_ms: Sequence[int] = (),
        jump_cuts_ms: Sequence[JumpCutInput] = (),
        audio_wav: Path | None = None,
        visual_context: Sequence[str] = (),
    ) -> DirectorScript:
        _ = (source_mp4, visual_context)
        duration_ms = _validate_clip_inputs(
            clip_id=clip_id,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            words=words,
        )
        resolved_wav = audio_wav if audio_wav is not None else self._default_audio_wav

        # 1. Deterministic Sorani ASR orthography repair (strictly 1:1 token-preserving).
        repaired_sentences, _ = repair_kurdish_asr_orthography(
            [Sentence(words=tuple(words), complete=True)]
        )
        repaired_words = repaired_sentences[0].words
        word_repairs = tuple(
            WordRepair(
                word_index=idx,
                original=orig.w,
                repaired=rep.w,
                reason="deterministic Sorani ASR orthography repair",
            )
            for idx, (orig, rep) in enumerate(zip(words, repaired_words, strict=True))
            if orig.w != rep.w
        )

        # 2. Silence & isolated conversational filler cuts strictly on word boundaries.
        cuts: list[CutRegion] = []
        derived_jump_cuts: list[tuple[int, int]] = []
        for idx in range(len(words) - 1):
            gap_ms = words[idx + 1].start_ms - words[idx].end_ms
            if gap_ms >= _MIN_MAJOR_JUMP_CUT_MS:
                cut_start = words[idx].end_ms + 75
                cut_end = words[idx + 1].start_ms - 75
                if cut_end > cut_start and cut_end <= duration_ms:
                    cuts.append(
                        CutRegion(
                            start_ms=cut_start,
                            end_ms=cut_end,
                            kind="silence",
                            reason=f"dead-air pause ({gap_ms} ms) tightened on word boundaries",
                        )
                    )
                    derived_jump_cuts.append((cut_start, gap_ms))

        for idx, word in enumerate(words):
            if idx < 2 or idx >= len(words) - 2:
                continue
            core = word.w.strip(_PUNCT_STRIP)
            if core not in KURDISH_FILLER_TOKENS:
                continue
            prev_gap = word.start_ms - words[idx - 1].end_ms
            next_gap = words[idx + 1].start_ms - word.end_ms
            if prev_gap >= 120 and next_gap >= 120 and word.end_ms <= duration_ms:
                overlaps = any(
                    not (word.end_ms <= c.start_ms or word.start_ms >= c.end_ms) for c in cuts
                )
                if not overlaps:
                    cuts.append(
                        CutRegion(
                            start_ms=word.start_ms,
                            end_ms=word.end_ms,
                            kind="filler",
                            reason=f"isolated conversational filler `{core}`",
                        )
                    )
        cuts.sort(key=lambda c: (c.start_ms, c.end_ms))

        # 3. Per-word acoustic energy Z-scores (or lexical salience if no WAV supplied).
        energy_scores = _compute_word_energy_zscores(repaired_words, resolved_wav)
        salient_candidates = [
            (energy_scores[idx], idx)
            for idx, w in enumerate(repaired_words)
            if len(w.w.strip(_PUNCT_STRIP)) >= 3
            and w.w.strip(_PUNCT_STRIP) not in _KURDISH_STOP_WORDS
        ]
        salient_candidates.sort(key=lambda item: (-item[0], item[1]))
        max_power = max(1, min(6, round(len(repaired_words) * 0.14)))
        chosen_power: list[int] = []
        for _score, idx in salient_candidates:
            if all(abs(idx - existing) >= 3 for existing in chosen_power):
                chosen_power.append(idx)
            if len(chosen_power) >= max_power:
                break
        power_indices = frozenset(chosen_power)

        # 4. Strict human camera restraint: >= 80% locked 1.00x, 0 sway, max 2-3 earned moves.
        normalized_jumps = _normalize_jump_cuts(jump_cuts_ms)
        camera_moves = self._plan_restrained_camera_moves(
            words=repaired_words,
            energy_scores=energy_scores,
            duration_ms=duration_ms,
            shot_cuts_ms=shot_cuts_ms,
            jump_cuts_ms=normalized_jumps if normalized_jumps else derived_jump_cuts,
        )

        # 5. Viral 1-2 (max 3 short <= 14 chars) caption beats with semantic power words.
        caption_beats = _build_offline_caption_beats(
            repaired_words,
            power_indices=power_indices,
        )

        # 6. Earned visual interrupts: 0 on clips < 28 s, 1-2 on clips >= 28 s.
        visual_interrupts = self._plan_visual_interrupts(
            repaired_words=repaired_words,
            chosen_power=chosen_power,
            duration_ms=duration_ms,
        )

        # 7. Concise 4-7 word Sorani hook title from repaired opening words.
        title_tokens = [
            w.w.strip(_PUNCT_STRIP) for w in repaired_words[:6] if w.w.strip(_PUNCT_STRIP)
        ]
        hook_title_ckb = " ".join(title_tokens[:6]) if title_tokens else repaired_words[0].w.strip()

        script = DirectorScript(
            clip_id=clip_id,
            hook_title_ckb=hook_title_ckb,
            word_repairs=word_repairs,
            cuts=tuple(cuts),
            camera_moves=camera_moves,
            caption_beats=caption_beats,
            visual_interrupts=visual_interrupts,
            cold_open_span_ms=None,
        )
        validate_director_script(script, duration_ms=duration_ms, words=words)
        return script

    @staticmethod
    def _plan_restrained_camera_moves(
        *,
        words: Sequence[Word],
        energy_scores: Sequence[float],
        duration_ms: int,
        shot_cuts_ms: Sequence[int],
        jump_cuts_ms: Sequence[tuple[int, int]],
    ) -> tuple[CameraMove, ...]:
        max_moves = min(3, max(2, math.ceil(duration_ms / 15_000)))
        max_moving_ms = int(duration_ms * 0.20)  # Guarantees >= 80% rock-steady locked tripod.
        moves: list[CameraMove] = []
        used_moving_ms = 0

        # (a) Max 1 gentle S-curve slow_push (1.00 -> 1.08x over 3.5 s) on payoff build-up.
        push_dur = 3_500 if duration_ms >= 18_000 else min(2_400, max_moving_ms)
        if duration_ms >= 12_000 and 1_500 <= push_dur <= max_moving_ms:
            payoff_candidates = [
                (energy_scores[idx], idx)
                for idx, w in enumerate(words)
                if int(duration_ms * 0.40) <= w.start_ms <= int(duration_ms * 0.88)
            ]
            if payoff_candidates:
                payoff_candidates.sort(key=lambda item: (-item[0], item[1]))
                peak_ms = words[payoff_candidates[0][1]].start_ms
                push_end = min(duration_ms - 800, max(push_dur + 1_000, peak_ms + 700))
                push_start = max(1_000, push_end - push_dur)
                if 1_500 <= push_end - push_start <= max_moving_ms:
                    moves.append(
                        CameraMove(
                            start_ms=push_start,
                            end_ms=push_end,
                            kind="slow_push",
                            scale_start=1.00,
                            scale_end=1.08,
                            reason="earned payoff build-up slow push",
                        )
                    )
                    used_moving_ms += push_end - push_start

        # (b) Max 2 crisp punch_cuts ONLY on major editorial jump-cuts (>= 600 ms removed).
        major_jumps = [
            (at_ms, rem_ms)
            for at_ms, rem_ms in jump_cuts_ms
            if rem_ms >= _MIN_MAJOR_JUMP_CUT_MS
            and 2_500 <= at_ms <= duration_ms - 2_000
            and all(abs(at_ms - shot_ms) >= 500 for shot_ms in shot_cuts_ms)
        ]
        major_jumps.sort(key=lambda item: (-item[1], item[0]))

        selected_jumps: list[tuple[int, int, int]] = []
        for at_ms, rem_ms in major_jumps:
            if len(selected_jumps) >= 2 or len(moves) + len(selected_jumps) >= max_moves:
                break
            remaining_budget = max_moving_ms - used_moving_ms
            if remaining_budget < 800:
                break
            hold_ms = min(2_000, remaining_budget, duration_ms - at_ms - 400)
            if hold_ms < 800:
                continue
            cand_end = at_ms + hold_ms
            overlaps_existing = any(
                not (cand_end <= m.start_ms - 400 or at_ms >= m.end_ms + 400) for m in moves
            )
            if overlaps_existing:
                continue
            if any(abs(at_ms - prev_at) < 4_000 for prev_at, _, _ in selected_jumps):
                continue
            selected_jumps.append((at_ms, cand_end, rem_ms))
            used_moving_ms += hold_ms

        selected_jumps.sort(key=lambda item: item[0])
        for at_ms, end_ms, rem_ms in selected_jumps:
            moves.append(
                CameraMove(
                    start_ms=at_ms,
                    end_ms=end_ms,
                    kind="punch_cut",
                    scale_start=1.00,
                    scale_end=1.12,
                    reason=f"disguise major editorial jump-cut ({rem_ms} ms removed)",
                )
            )

        moves.sort(key=lambda m: (m.start_ms, m.end_ms))
        return tuple(moves)

    @staticmethod
    def _plan_visual_interrupts(
        *,
        repaired_words: Sequence[Word],
        chosen_power: Sequence[int],
        duration_ms: int,
    ) -> tuple[VisualInterrupt, ...]:
        if duration_ms < 28_000:
            return ()
        interrupts: list[VisualInterrupt] = []

        # 1. Prioritize animated Stat Cards ("<NUMBER> | <KURDISH LABEL>") whenever a vivid
        # number, year, or percentage is spoken in the body window.
        _spoken_pct: dict[str, str] = {
            "هەشتا": "80%",
            "هەشتای": "80%",
            "بیست": "20%",
            "پازدە": "15%",
            "دە": "10%",
            "پەنجا": "50%",
            "نەوەد": "90%",
            "سەد": "100%",
        }
        for idx, w in enumerate(repaired_words):
            if len(interrupts) >= 2:
                break
            if w.start_ms < 4_200 or w.start_ms > duration_ms - 3_500:
                continue
            if any(abs(w.start_ms - prev.start_ms) < 9_000 for prev in interrupts):
                continue
            tok = w.w.strip(_PUNCT_STRIP)
            stat_hero: str | None = None
            label_start = idx + 1
            if tok == "سەتا" and idx + 1 < len(repaired_words):
                nxt = repaired_words[idx + 1].w.strip(_PUNCT_STRIP)
                if nxt in _spoken_pct:
                    stat_hero = _spoken_pct[nxt]
                    label_start = idx + 2
                elif nxt.isdigit():
                    stat_hero = f"{nxt}%"
                    label_start = idx + 2
                    # Coalesce spoken ranges like "سەتا 15 بۆ 20" -> "15-20%"
                    if (
                        idx + 3 < len(repaired_words)
                        and repaired_words[idx + 2].w.strip(_PUNCT_STRIP)
                        in {"بۆ", "تا", "یان", "و"}
                        and repaired_words[idx + 3].w.strip(_PUNCT_STRIP).isdigit()
                    ):
                        hi_num = repaired_words[idx + 3].w.strip(_PUNCT_STRIP)
                        stat_hero = f"{nxt}-{hi_num}%"
                        label_start = idx + 4
            elif tok.isdigit() and (len(tok) >= 4 or int(tok) >= 10):
                prev_tok = repaired_words[idx - 1].w.strip(_PUNCT_STRIP) if idx > 0 else ""
                if prev_tok == "سەتا":
                    continue  # Already handled at "سەتا"
                stat_hero = tok
            if stat_hero is None:
                continue
            ctx = [
                pw.w.strip(_PUNCT_STRIP)
                for pw in repaired_words[label_start : min(len(repaired_words), label_start + 5)]
                if len(pw.w.strip(_PUNCT_STRIP)) > 1
                and not pw.w.strip(_PUNCT_STRIP).isdigit()
                and pw.w.strip(_PUNCT_STRIP) not in _KURDISH_STOP_WORDS
            ]
            if not ctx and idx > 0:
                ctx = [
                    pw.w.strip(_PUNCT_STRIP)
                    for pw in repaired_words[max(0, idx - 3) : idx]
                    if len(pw.w.strip(_PUNCT_STRIP)) > 1
                    and not pw.w.strip(_PUNCT_STRIP).isdigit()
                    and pw.w.strip(_PUNCT_STRIP) not in _KURDISH_STOP_WORDS
                ]
            if not ctx:
                continue
            label = " ".join(ctx[:3])
            end_ms = min(duration_ms - 400, w.start_ms + 2_600)
            if end_ms > w.start_ms + 600:
                interrupts.append(
                    VisualInterrupt(
                        start_ms=w.start_ms,
                        end_ms=end_ms,
                        text_ckb=f"{stat_hero} | {label}",
                        position="top",
                    )
                )

        # 2. Fill remaining earned callout slots (up to 3 total on >= 36 s reels, 2 otherwise).
        cap = 3 if duration_ms >= 36_000 else 2
        for word_idx in sorted(chosen_power):
            if len(interrupts) >= cap:
                break
            w = repaired_words[word_idx]
            if w.start_ms < 4_500 or w.start_ms > duration_ms - 3_500:
                continue
            if any(abs(w.start_ms - prev.start_ms) < 9_000 for prev in interrupts):
                continue
            raw_slice = repaired_words[word_idx : min(len(repaired_words), word_idx + 3)]
            phrase_words = [raw_slice[0]]
            for nxt_w in raw_slice[1:]:
                if nxt_w.start_ms - phrase_words[-1].end_ms >= 350:
                    break
                phrase_words.append(nxt_w)
            _dangling = {"و", "لە", "بە", "بۆ", "کە", "یا", "یان", "ئەو", "ئەم", "تا"}
            while len(phrase_words) > 2 and phrase_words[-1].w.strip(_PUNCT_STRIP) in _dangling:
                phrase_words.pop()
            phrase = " ".join(
                pw.w.strip(_PUNCT_STRIP) for pw in phrase_words if pw.w.strip(_PUNCT_STRIP)
            )
            if not phrase:
                continue
            end_ms = min(duration_ms - 400, w.start_ms + 2_400)
            if end_ms > w.start_ms + 600:
                interrupts.append(
                    VisualInterrupt(
                        start_ms=w.start_ms,
                        end_ms=end_ms,
                        text_ckb=phrase,
                        position="top",
                    )
                )
        interrupts.sort(key=lambda item: item.start_ms)
        return tuple(interrupts)

    def critique_clip(
        self,
        *,
        rendered_mp4: Path,
        script: DirectorScript,
        words: Sequence[Word],
        duration_ms: int | None = None,
        preview_mp4: Path | None = None,
    ) -> CritiqueVerdict:
        if not words:
            raise ValueError("words must be non-empty")
        target_video = preview_mp4 if preview_mp4 is not None else rendered_mp4
        if not target_video.is_file() or target_video.stat().st_size == 0:
            raise DirectorUnavailable(f"Critique video missing or empty: {target_video}")
        resolved_dur = _infer_duration_ms(duration_ms=duration_ms, script=script, words=words)

        issues: list[str] = []
        patch: dict[str, Any] = {}

        # Check 1: Unnecessary camera motion (D-382).
        max_moves = max(2, math.ceil(resolved_dur / 15_000))
        active_moves = [m for m in script.camera_moves if m.kind != "locked"]
        moving_ms = sum(m.end_ms - m.start_ms for m in script.camera_moves if m.is_moving)
        bad_scale = any(
            not (1.00 <= m.scale_start <= 1.16 and 1.00 <= m.scale_end <= 1.16)
            for m in script.camera_moves
        )
        if bad_scale:
            issues.append("unnecessary_motion: camera scale outside [1.00, 1.16]")
            patch["camera_moves"] = []
        if len(active_moves) > max_moves:
            issues.append(
                f"unnecessary_motion: {len(active_moves)} active moves exceeds cap {max_moves}"
            )
            patch["camera_moves"] = [m.to_dict() for m in active_moves[:max_moves]]
        if moving_ms * 4 > resolved_dur:
            issues.append(
                f"unnecessary_motion: moving time {moving_ms}ms exceeds 25% of {resolved_dur}ms"
            )
            patch["camera_moves"] = []

        # Check 2: Broken Kurdish text (surviving deterministic Sorani ASR errors).
        repaired_sentences, _ = repair_kurdish_asr_orthography(
            [Sentence(words=tuple(words), complete=True)]
        )
        repaired_words = repaired_sentences[0].words
        existing_repair_indices = {r.word_index for r in script.word_repairs}
        missing_repairs = [
            WordRepair(
                word_index=idx,
                original=orig.w,
                repaired=rep.w,
                reason="watch-before-ship deterministic Sorani ASR repair",
            )
            for idx, (orig, rep) in enumerate(zip(words, repaired_words, strict=True))
            if orig.w != rep.w and idx not in existing_repair_indices
        ]
        if missing_repairs:
            issues.append(
                f"broken_kurdish_text: {len(missing_repairs)} unrepaired Sorani ASR token(s)"
            )
            patch["word_repairs"] = [r.to_dict() for r in (*script.word_repairs, *missing_repairs)]

        # Check 3: Awkward mid-word cuts.
        clean_cuts: list[CutRegion] = []
        mid_word_found = False
        for cut in script.cuts:
            splits_word = next(
                (
                    w
                    for w in words
                    if w.start_ms < cut.start_ms < w.end_ms or w.start_ms < cut.end_ms < w.end_ms
                ),
                None,
            )
            if splits_word is not None:
                mid_word_found = True
                issues.append(
                    f"awkward_cut: cut {cut.start_ms}..{cut.end_ms}ms splits word `{splits_word.w}`"
                )
            else:
                clean_cuts.append(cut)
        if mid_word_found:
            patch["cuts"] = [c.to_dict() for c in clean_cuts]

        # Check 4: Subtitle readability (strict 1-2 word / max-3 <= 14 char rule).
        for beat in script.caption_beats:
            if len(beat.word_indices) > 3:
                issues.append(
                    f"subtitle_readability: beat has {len(beat.word_indices)} words (max 3)"
                )
            elif len(beat.word_indices) == 3:
                text = " ".join(words[i].w for i in beat.word_indices if 0 <= i < len(words))
                if len(text) > 14:
                    issues.append(f"subtitle_readability: 3-word beat `{text}` exceeds 14 chars")

        # Check 5: Viral hook strength (empty title is allowed when no source clause qualifies).
        hook_words = [tok for tok in script.hook_title_ckb.split() if tok.strip(_PUNCT_STRIP)]
        if 0 < len(hook_words) < 2:
            issues.append("viral_hook_strength: hook_title_ckb is too short (< 2 words)")
            fallback_tokens = [
                w.w.strip(_PUNCT_STRIP) for w in repaired_words[:5] if w.w.strip(_PUNCT_STRIP)
            ]
            if len(fallback_tokens) >= 2:
                patch["hook_title_ckb"] = " ".join(fallback_tokens)

        approved = len(issues) == 0
        score = max(0.0, round(1.0 - 0.18 * len(issues), 3))
        return CritiqueVerdict(
            approved=approved,
            score=score,
            issues=tuple(issues),
            patch=patch if patch and not approved else None,
        )


def critique_rendered_clip(
    brain: DirectorBrain,
    *,
    rendered_mp4: Path,
    script: DirectorScript,
    words: Sequence[Word],
    preview_out_mp4: Path | None = None,
    fps: float = 2.0,
    height: int = 480,
    ffmpeg: Path | None = None,
) -> CritiqueVerdict:
    """Build a 480p @ 2 fps preview of ``rendered_mp4`` and run Watch-Before-Ship critique."""
    if preview_out_mp4 is not None:
        preview = build_critique_preview(
            rendered_mp4,
            preview_out_mp4,
            fps=fps,
            height=height,
            ffmpeg=ffmpeg,
        )
        return brain.critique_clip(
            rendered_mp4=rendered_mp4,
            script=script,
            words=words,
            preview_mp4=preview,
        )

    with tempfile.TemporaryDirectory(prefix="hawedit-v8-critique-") as tmp_dir:
        preview = build_critique_preview(
            rendered_mp4,
            Path(tmp_dir) / "critique_preview.mp4",
            fps=fps,
            height=height,
            ffmpeg=ffmpeg,
        )
        return brain.critique_clip(
            rendered_mp4=rendered_mp4,
            script=script,
            words=words,
            preview_mp4=preview,
        )


def create_director_brain(
    backend: DirectorBackendName,
    *,
    api_key: str | None = None,
    model_id: str | None = None,
    base_url: str | None = None,
    timeout_s: float | None = None,
    include_audio: bool = True,
    modality: LocalDirectorModality | None = None,
    audio_wav: Path | None = None,
    ffmpeg: Path | None = None,
    transport: Transport | None = None,
) -> DirectorBrain:
    """Instantiate an explicit ``DirectorBrain`` backend with ZERO silent fallback."""
    if backend == "gemini":
        return GeminiVideoDirector(
            api_key=api_key,
            model_id=model_id if model_id is not None else DEFAULT_GEMINI_DIRECTOR_MODEL,
            timeout_s=timeout_s if timeout_s is not None else DEFAULT_GEMINI_TIMEOUT_S,
            ffmpeg=ffmpeg,
            transport=transport,
        )
    if backend == "local-omni":
        return LocalOmniDirector(
            base_url=base_url,
            model_id=model_id,
            timeout_s=timeout_s if timeout_s is not None else DEFAULT_OMNI_TIMEOUT_S,
            api_key=api_key,
            include_audio=include_audio,
            modality=modality,
            ffmpeg=ffmpeg,
            transport=transport,
        )
    if backend == "offline":
        return OfflineRestrainedDirector(audio_wav=audio_wav)
    raise ValueError(
        f"Unsupported director backend {backend!r}; expected 'gemini', 'local-omni', or 'offline'."
    )
