"""HawEdit V10.2 Component 3: Content-Aware B-Roll Retrieval, Semantic Verification & Generation.

Provides commercial-safe, provenance-signed B-roll resolution with strict relevance gating:
1. Local content-addressable cache (``broll_cache/``) writing valid ``.provenance.json`` sidecars
   for ``hawedit.render.assert_asset_provenance``.
2. Provider 1: Local commercial studio B-roll folder (``--broll-dir``).
3. Provider 2: Free commercial stock APIs (Pexels, Pixabay, Wikimedia Commons CC0/PD/CC-BY only;
   NonCommercial licences are strictly rejected per DECISIONS.md).
4. Semantic Verification Gate (``verify_broll_relevance``): computes cosine similarity between
   candidate image/middle-frame and ``query_en`` via ``gemini-embedding-2`` (multimodal text+image
   vector space) and hard-rejects candidates below ``0.26``.
5. Provider 3: Bespoke editorial still fallback via ``gemini-nano-banana-2.1`` (<= 2 per reel,
   animated via subtle Ken Burns zoom in FFmpeg).
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.atomic_fs import write_text_atomic
from hawedit.captions import find_ffmpeg
from hawedit.credentials import GEMINI_API_KEY, read_credential
from hawedit.gemini import API_ROOT
from hawedit.http_transport import open_without_redirects
from hawedit.render import BRollItem
from hawedit.transcripts import Word
from hawedit.v8.director import (
    DEFAULT_OMNI_URL,
    OMNI_MODEL_ENV,
    OMNI_URL_ENV,
    _openai_strict_schema,
    _strip_json_wrappers,
)
from hawedit.v8.schema import VisualInterrupt
from hawedit.v8.story_editor import VisualCue

__all__ = [
    "DEFAULT_BROLL_CACHE_DIR",
    "DEFAULT_BROLL_MIN_SIMILARITY",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_IMAGE_GEN_MODEL",
    "DEFAULT_LOCAL_VISION_MIN_SCORE",
    "BRollAsset",
    "BRollError",
    "cosine_similarity",
    "extract_kurdish_stat_interrupts",
    "generate_bespoke_broll_image",
    "resolve_visual_cues_to_broll",
    "search_local_broll",
    "search_wikimedia_broll",
    "verify_broll_relevance",
    "verify_broll_relevance_local",
    "write_asset_provenance",
]

DEFAULT_EMBEDDING_MODEL: Final[str] = "gemini-embedding-2"
DEFAULT_IMAGE_GEN_MODEL: Final[str] = "gemini-nano-banana-2.1"
DEFAULT_BROLL_MIN_SIMILARITY: Final[float] = 0.26
DEFAULT_LOCAL_VISION_MIN_SCORE: Final[float] = 0.70
DEFAULT_BROLL_CACHE_DIR: Final[Path] = Path(r"D:\HawEdit-media\broll_cache")
MAX_BROLL_DOWNLOAD_BYTES: Final[int] = 25 * 1024 * 1024
MAX_API_RESPONSE_BYTES: Final[int] = 8 * 1024 * 1024

_IMAGE_EXTS: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_VIDEO_EXTS: Final[frozenset[str]] = frozenset({".mp4", ".mov", ".mkv", ".webm"})
_DISALLOWED_LICENSE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:non[\s-]*commercial|\bnc\b|all\s+rights\s+reserved|copyrighted|fair\s+use)",
    re.IGNORECASE,
)
_COMMERCIAL_SAFE_LICENSE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:cc0|public\s+domain|\bpd\b|cc[\s-]*by(?:\s*-sa)?(?:\s*[0-9.]+)?|pexels|pixabay|local)",
    re.IGNORECASE,
)
_WIKIMEDIA_CLUTTER_TITLE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:book|cover|poster|flyer|brochure|logo|icon|diagram|chart|graph|slide|pdf|scan|page|text|campaign|title)",
    re.IGNORECASE,
)
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_LOCAL_BROLL_VERIFY_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "score": {"type": "number"},
        "has_text_clutter": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["relevant", "score", "has_text_clutter", "reason"],
}

Transport = Callable[[str, bytes | None, Mapping[str, str]], tuple[int, bytes]]


class BRollError(RuntimeError):
    """Raised when B-roll retrieval, provenance writing, or semantic verification fails."""


@dataclass(frozen=True, slots=True)
class BRollAsset:
    """A locally cached, provenance-verified B-roll image or video asset."""

    path: Path
    provider: str
    license_name: str
    query_en: str
    similarity: float
    is_video: bool


def _default_binary_transport(timeout_s: float = 30.0) -> Transport:
    def _send(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, bytes]:
        req_headers = {"User-Agent": "HawEdit/10.2 (https://github.com/hawedit)"}
        req_headers.update(headers)
        if body is not None:
            req_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(
            url,
            data=body,
            headers=req_headers,
            method="POST" if body is not None else "GET",
        )
        max_bytes = MAX_BROLL_DOWNLOAD_BYTES if body is None else MAX_API_RESPONSE_BYTES
        try:
            with open_without_redirects(req, timeout=timeout_s) as resp:
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise BRollError(f"Response from {url} exceeded {max_bytes} bytes")
                return int(resp.status), raw
        except urllib.error.HTTPError as exc:
            try:
                err_raw = exc.read(65_536)
            except OSError:
                err_raw = b""
            return int(exc.code), err_raw
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, str(exc).encode("utf-8", errors="replace")

    return _send


def write_asset_provenance(
    asset_path: Path,
    *,
    provider: str,
    license_name: str,
    query_en: str,
    source_url: str = "",
    similarity: float = 1.0,
) -> Path:
    """Write a cryptographic ``.provenance.json`` sidecar for ``assert_asset_provenance``."""
    if not asset_path.is_file():
        raise FileNotFoundError(f"Cannot write provenance for missing asset: {asset_path}")
    if _DISALLOWED_LICENSE_RE.search(license_name):
        raise BRollError(f"Refusing NonCommercial or restricted license: {license_name!r}")
    sha256 = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    sidecar = asset_path.with_name(f"{asset_path.name}.provenance.json")
    payload = {
        "sha256": sha256,
        "provider": provider,
        "license": license_name,
        "query_en": query_en,
        "source_url": source_url,
        "similarity": round(float(similarity), 4),
    }
    write_text_atomic(sidecar, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return sidecar


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Compute exact cosine similarity in ``[-1.0, 1.0]`` between two equal-length embeddings."""
    if not vec_a or len(vec_a) != len(vec_b):
        raise ValueError("Embedding vectors must be non-empty and of equal length")
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def _extract_middle_frame_jpeg(asset_path: Path, *, ffmpeg: Path | None = None) -> bytes:
    suffix = asset_path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".webp"):
        return asset_path.read_bytes()
    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise BRollError("No ffmpeg binary available to extract B-roll verification frame")
    with tempfile.TemporaryDirectory(prefix="hawedit-broll-frame-") as tmp_dir:
        out_jpg = Path(tmp_dir) / "mid.jpg"
        proc = subprocess.run(
            [
                str(binary),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "1.0",
                "-i",
                str(asset_path),
                "-vframes",
                "1",
                "-vf",
                "scale=512:-2",
                "-y",
                str(out_jpg),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
        )
        if proc.returncode != 0 or not out_jpg.is_file():
            raise BRollError(f"Failed to extract verification frame from {asset_path.name}")
        return out_jpg.read_bytes()


def _embed_gemini_parts(
    parts: list[dict[str, Any]],
    *,
    api_key: str,
    model_id: str = DEFAULT_EMBEDDING_MODEL,
    transport: Transport,
) -> list[float]:
    url = f"{API_ROOT}/models/{model_id}:embedContent"
    payload = json.dumps(
        {
            "content": {"parts": parts},
            "outputDimensionality": 768,
        }
    ).encode("utf-8")
    status, raw = transport(url, payload, {"x-goog-api-key": api_key})
    if status != 200:
        detail = raw.decode("utf-8", errors="replace")[:300]
        raise BRollError(f"{model_id} embedContent failed (HTTP {status}): {detail}")
    try:
        data = json.loads(raw.decode("utf-8"))
        values = data["embedding"]["values"]
        if not isinstance(values, list) or not values:
            raise ValueError("empty embedding values")
        return [float(v) for v in values]
    except (ValueError, KeyError, TypeError) as exc:
        raise BRollError(f"Malformed {model_id} response: {exc}") from exc


def verify_broll_relevance(
    asset_path: Path,
    query_en: str,
    *,
    api_key: str | None = None,
    min_similarity: float = DEFAULT_BROLL_MIN_SIMILARITY,
    model_id: str = DEFAULT_EMBEDDING_MODEL,
    ffmpeg: Path | None = None,
    transport: Transport | None = None,
) -> tuple[bool, float]:
    """Verify B-roll visual relevance against ``query_en`` using ``gemini-embedding-2``."""
    key = api_key.strip() if api_key and api_key.strip() else read_credential(GEMINI_API_KEY)
    if not key:
        raise BRollError(f"Missing {GEMINI_API_KEY} for {model_id} B-roll semantic verification")
    tx = transport or _default_binary_transport(25.0)
    img_bytes = _extract_middle_frame_jpeg(asset_path, ffmpeg=ffmpeg)
    mime = (
        "image/png"
        if asset_path.suffix.lower() == ".png"
        else ("image/webp" if asset_path.suffix.lower() == ".webp" else "image/jpeg")
    )
    text_vec = _embed_gemini_parts(
        [{"text": query_en}], api_key=key, model_id=model_id, transport=tx
    )
    img_vec = _embed_gemini_parts(
        [{"inlineData": {"mimeType": mime, "data": base64.b64encode(img_bytes).decode("ascii")}}],
        api_key=key,
        model_id=model_id,
        transport=tx,
    )
    sim = cosine_similarity(text_vec, img_vec)
    return sim >= min_similarity, round(sim, 4)


def _resolve_local_vision_model(
    base_url: str,
    explicit_model: str | None,
    transport: Transport,
) -> str:
    if explicit_model and explicit_model.strip():
        return explicit_model.strip()
    env_m = os.environ.get(OMNI_MODEL_ENV, "").strip()
    if env_m:
        return env_m
    status, raw = transport(f"{base_url.rstrip('/')}/models", None, {})
    if status != 200:
        raise BRollError(f"Local vision server at {base_url} unavailable (HTTP {status})")
    try:
        models = json.loads(raw.decode("utf-8", errors="replace")).get("data", [])
        for entry in models:
            if isinstance(entry, Mapping):
                mid = str(entry.get("id", "")).strip()
                if mid and "embed" not in mid.lower():
                    return mid
    except (ValueError, AttributeError) as exc:
        raise BRollError(f"Malformed /models payload from {base_url}: {exc}") from exc
    raise BRollError(f"No vision-capable model loaded at {base_url}")


def verify_broll_relevance_local(
    asset_path: Path,
    query_en: str,
    *,
    base_url: str | None = None,
    model_id: str | None = None,
    min_score: float = DEFAULT_LOCAL_VISION_MIN_SCORE,
    ffmpeg: Path | None = None,
    transport: Transport | None = None,
) -> tuple[bool, float]:
    """Verify B-roll visual relevance & zero text clutter using local VLM vision (D-398)."""
    resolved_url = (
        base_url.strip()
        if base_url and base_url.strip()
        else os.environ.get(OMNI_URL_ENV, DEFAULT_OMNI_URL).strip() or DEFAULT_OMNI_URL
    ).rstrip("/")
    tx = transport or _default_binary_transport(45.0)
    resolved_model = _resolve_local_vision_model(resolved_url, model_id, tx)
    img_bytes = _extract_middle_frame_jpeg(asset_path, ffmpeg=ffmpeg)
    mime = (
        "image/png"
        if asset_path.suffix.lower() == ".png"
        else ("image/webp" if asset_path.suffix.lower() == ".webp" else "image/jpeg")
    )
    b64 = base64.b64encode(img_bytes).decode("ascii")
    prompt = (
        f'Evaluate this candidate B-roll image for the editorial visual query: "{query_en}".\n'
        "Return JSON with:\n"
        "- `relevant`: true ONLY if the image clearly and cinematically illustrates the query.\n"
        "- `score`: float in [0.0, 1.0] measuring visual match quality.\n"
        "- `has_text_clutter`: true if the image is a book cover, poster, slide, screenshot, "
        "document scan, meme, or contains prominent English text/watermarks.\n"
        "- `reason`: concise 5-12 word explanation."
    )
    payload = json.dumps(
        {
            "model": resolved_model,
            "temperature": 0.0,
            "max_tokens": 160,
            "reasoning_effort": "none",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "hawedit_local_broll_verify",
                    "strict": True,
                    "schema": _openai_strict_schema(_LOCAL_BROLL_VERIFY_SCHEMA),
                },
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    status, raw = tx(f"{resolved_url}/chat/completions", payload, {})
    if status != 200:
        detail = raw.decode("utf-8", errors="replace")[:260]
        raise BRollError(f"Local vision B-roll check failed (HTTP {status}): {detail}")
    try:
        outer = json.loads(raw.decode("utf-8", errors="replace"))
        content = _strip_json_wrappers(str(outer["choices"][0]["message"]["content"]))
        verdict = json.loads(content)
        relevant = bool(verdict.get("relevant", False))
        score = float(verdict.get("score", 0.0))
        clutter = bool(verdict.get("has_text_clutter", True))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise BRollError(f"Malformed local vision B-roll verdict: {exc}") from exc
    passed = relevant and (not clutter) and score >= min_score
    return passed, round(max(0.0, min(1.0, score)), 4)


_ARABIC_TO_ASCII_DIGITS: Final[dict[int, int]] = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)
_SORANI_NUMBER_WORDS: Final[dict[str, str]] = {
    "دە": "10",
    "پازدە": "15",
    "بیست": "20",
    "سی": "30",
    "چل": "40",
    "پەنجا": "50",
    "شەست": "60",
    "حەفتا": "70",
    "هەشتا": "80",
    "هەشتای": "80",
    "نەوەد": "90",
    "سەد": "100",
}
_PCT_PREFIX_CKB: Final[frozenset[str]] = frozenset({"سەتا", "سەدا", "لەسەدا", "لەسەتا"})
_UNIT_WORDS_CKB: Final[dict[str, str]] = {
    "ساڵ": "ساڵ",
    "ساڵە": "ساڵ",
    "ساڵەی": "ساڵ",
    "ملیۆن": "ملیۆن",
    "ملیار": "ملیار",
    "هەزار": "هەزار",
}
_STAT_STOP_CKB: Final[frozenset[str]] = frozenset(
    {"و", "کە", "لە", "بە", "بۆ", "ئەو", "ئەم", "ئەوەی", "ی", "ئەگەر", "ڕەنگە", "بەڵێ"}
)
_STAT_STRIP: Final[str] = ".,،!؟?؛;:\"'«»()[]"


def _parse_stat_num(raw: str) -> str | None:
    cleaned = raw.strip().strip(_STAT_STRIP).translate(_ARABIC_TO_ASCII_DIGITS)
    if not cleaned:
        return None
    if cleaned.isdigit():
        return cleaned
    return _SORANI_NUMBER_WORDS.get(cleaned)


def _stat_context_label(words: Sequence[Word], start_idx: int, end_idx: int) -> str:
    """Pick 2-4 crisp surrounding Sorani context words for a numeric Stat Card label."""
    after = [
        words[k].w.strip().strip(_STAT_STRIP)
        for k in range(end_idx + 1, min(len(words), end_idx + 6))
    ]
    meaningful = [t for t in after if t and t not in _STAT_STOP_CKB][:3]
    if len(meaningful) >= 2:
        return " ".join(meaningful)
    before = [
        words[k].w.strip().strip(_STAT_STRIP) for k in range(max(0, start_idx - 4), start_idx)
    ]
    meaningful_before = [t for t in before if t and t not in _STAT_STOP_CKB][-3:]
    chosen = meaningful_before or meaningful
    return " ".join(chosen)


def extract_kurdish_stat_interrupts(
    words: Sequence[Word],
    *,
    duration_ms: int,
    existing_interrupts: Sequence[VisualInterrupt] = (),
    occupied_broll_ms: Sequence[tuple[int, int]] = (),
    max_cards: int = 2,
    min_spacing_ms: int = 8_000,
) -> tuple[VisualInterrupt, ...]:
    """Extract crisp Skia Stat Cards from spoken Sorani percentages, years, and numeric units."""
    if not words or duration_ms < 8_000 or max_cards <= 0:
        return ()

    candidates: list[tuple[int, int, str]] = []  # (priority, anchor_ms, "HERO | LABEL")
    n = len(words)
    i = 0
    while i < n:
        tok = words[i].w.strip().strip(_STAT_STRIP)
        norm = tok.translate(_ARABIC_TO_ASCII_DIGITS)

        # 1. Explicit percentage token (e.g. '80%')
        if norm.endswith("%") and norm[:-1].isdigit():
            label = _stat_context_label(words, i, i)
            if label:
                candidates.append((3, words[i].start_ms, f"{norm} | {label}"))
            i += 1
            continue

        # 2. Spoken Sorani percentage: 'سەتا 15 بۆ 20' or 'سەتا هەشتای'
        if tok in _PCT_PREFIX_CKB and i + 1 < n:
            n1 = _parse_stat_num(words[i + 1].w)
            if n1 is not None:
                if (
                    i + 3 < n
                    and words[i + 2].w.strip().strip(_STAT_STRIP) in ("بۆ", "تا")
                    and (n2 := _parse_stat_num(words[i + 3].w)) is not None
                ):
                    label = _stat_context_label(words, i, i + 3)
                    if label:
                        candidates.append((3, words[i].start_ms, f"{n1}–{n2}% | {label}"))
                    i += 4
                    continue
                label = _stat_context_label(words, i, i + 1)
                if label:
                    candidates.append((3, words[i].start_ms, f"{n1}% | {label}"))
                i += 2
                continue

        # 3. 4-digit historical/future year (1900..2150) or meaningful unit ('50 ساڵ', '12 ساڵەی')
        num_val = _parse_stat_num(tok)
        if num_val is not None:
            int_v = int(num_val)
            if 1900 <= int_v <= 2150 and norm.isdigit():
                label = _stat_context_label(words, i, i)
                if label:
                    candidates.append((2, words[i].start_ms, f"{num_val} | {label}"))
                i += 1
                continue
            if i + 1 < n:
                nxt_tok = words[i + 1].w.strip().strip(_STAT_STRIP)
                unit = _UNIT_WORDS_CKB.get(nxt_tok)
                if unit is not None and int_v >= 2:
                    label = _stat_context_label(words, i, i + 1)
                    if label:
                        candidates.append((2, words[i].start_ms, f"{num_val} {unit} | {label}"))
                    i += 2
                    continue
        i += 1

    # Prioritize percentages > years/units, enforce safe margins (clear of hook & end card).
    candidates.sort(key=lambda item: (-item[0], item[1]))
    chosen: list[VisualInterrupt] = []
    occupied = [
        *((vi.start_ms, vi.end_ms) for vi in existing_interrupts),
        *occupied_broll_ms,
    ]
    for _prio, anchor_ms, text_ckb in candidates:
        if len(chosen) >= max_cards:
            break
        s_ms = max(3_200, anchor_ms)
        e_ms = min(duration_ms - 2_600, s_ms + 2_800)
        if e_ms - s_ms < 1_800:
            continue
        if any(abs(s_ms - os_) < min_spacing_ms for os_, _ in occupied):
            continue
        if any(abs(s_ms - c.start_ms) < min_spacing_ms for c in chosen):
            continue
        chosen.append(
            VisualInterrupt(
                start_ms=s_ms,
                end_ms=e_ms,
                text_ckb=text_ckb,
                position="top",
            )
        )
    chosen.sort(key=lambda vi: vi.start_ms)
    return tuple(chosen)


def search_local_broll(broll_dir: Path, query_en: str) -> BRollAsset | None:
    """Match a local commercial B-roll clip/image from ``broll_dir`` by keyword overlap."""
    if not broll_dir.is_dir():
        return None
    q_tokens = set(_TOKEN_RE.findall(query_en.lower()))
    if not q_tokens:
        return None

    best_path: Path | None = None
    best_score = 0.0
    for candidate in sorted(broll_dir.rglob("*")):
        if not candidate.is_file():
            continue
        ext = candidate.suffix.lower()
        if ext not in _IMAGE_EXTS and ext not in _VIDEO_EXTS:
            continue
        c_tokens = set(_TOKEN_RE.findall(candidate.stem.lower().replace("_", " ")))
        if not c_tokens:
            continue
        overlap = len(q_tokens & c_tokens) / float(len(q_tokens))
        if overlap > best_score:
            best_score = overlap
            best_path = candidate

    if best_path is None or best_score < 0.25:
        return None
    prov = best_path.with_name(f"{best_path.name}.provenance.json")
    if not prov.is_file():
        write_asset_provenance(
            best_path,
            provider="local_broll_dir",
            license_name="local_studio_commercial",
            query_en=query_en,
            similarity=best_score,
        )
    return BRollAsset(
        path=best_path,
        provider="local_broll_dir",
        license_name="local_studio_commercial",
        query_en=query_en,
        similarity=round(best_score, 4),
        is_video=best_path.suffix.lower() in _VIDEO_EXTS,
    )


def _cache_key(provider: str, query_en: str, layout: str) -> str:
    norm = " ".join(_TOKEN_RE.findall(query_en.lower()))
    return hashlib.sha256(f"{provider}|{layout}|{norm}".encode()).hexdigest()[:16]


def _search_wikimedia_candidates(
    query_en: str,
    cache_dir: Path,
    *,
    layout: str = "broll_pip",
    max_candidates: int = 3,
    transport: Transport | None = None,
) -> list[BRollAsset]:
    """Fetch up to ``max_candidates`` commercial-safe, clutter-filtered Wikimedia Commons photos."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key("wikimedia", query_en, layout)
    cached_jpg = cache_dir / f"wm_{key}.jpg"
    if (
        cached_jpg.is_file()
        and cached_jpg.with_name(f"{cached_jpg.name}.provenance.json").is_file()
    ):
        return [
            BRollAsset(
                path=cached_jpg,
                provider="wikimedia_commons",
                license_name="CC0/CC-BY",
                query_en=query_en,
                similarity=0.5,
                is_video=False,
            )
        ]

    tx = transport or _default_binary_transport(20.0)
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query_en} filetype:bitmap",
            "gsrnamespace": "6",
            "gsrlimit": "10",
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata|mime",
            "iiurlwidth": "1280",
            "format": "json",
        }
    )
    url = f"https://commons.wikimedia.org/w/api.php?{params}"
    status, raw = tx(url, None, {})
    if status != 200:
        return []
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
        pages = data.get("query", {}).get("pages", {})
    except (ValueError, AttributeError):
        return []
    if not isinstance(pages, Mapping):
        return []

    found: list[BRollAsset] = []
    for page in pages.values():
        if len(found) >= max_candidates:
            break
        if not isinstance(page, Mapping):
            continue
        title = str(page.get("title", ""))
        if _WIKIMEDIA_CLUTTER_TITLE_RE.search(title):
            continue
        infos = page.get("imageinfo")
        if not isinstance(infos, list) or not infos:
            continue
        info = infos[0]
        if not isinstance(info, Mapping):
            continue
        mime = str(info.get("mime", "")).lower()
        if mime not in ("image/jpeg", "image/png"):
            continue
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        if width < 640 or height < 480:
            continue
        meta = info.get("extmetadata", {})
        lic_short = (
            str(meta.get("LicenseShortName", {}).get("value", ""))
            if isinstance(meta, Mapping)
            else ""
        )
        if _DISALLOWED_LICENSE_RE.search(lic_short) or not _COMMERCIAL_SAFE_LICENSE_RE.search(
            lic_short
        ):
            continue
        img_url = str(info.get("thumburl") or info.get("url") or "").strip()
        if not img_url.startswith("https://"):
            continue
        img_status, img_bytes = tx(img_url, None, {})
        if img_status != 200 or len(img_bytes) < 4096:
            continue
        slot_path = cached_jpg if not found else cache_dir / f"wm_{key}_{len(found)}.jpg"
        slot_path.write_bytes(img_bytes)
        write_asset_provenance(
            slot_path,
            provider="wikimedia_commons",
            license_name=lic_short or "CC-BY",
            query_en=query_en,
            source_url=img_url,
            similarity=0.5,
        )
        found.append(
            BRollAsset(
                path=slot_path,
                provider="wikimedia_commons",
                license_name=lic_short or "CC-BY",
                query_en=query_en,
                similarity=0.5,
                is_video=False,
            )
        )
    return found


def search_wikimedia_broll(
    query_en: str,
    cache_dir: Path,
    *,
    layout: str = "broll_pip",
    transport: Transport | None = None,
) -> BRollAsset | None:
    """Fetch a commercial-safe (CC0 / Public Domain / CC-BY) photo from Wikimedia Commons."""
    cands = _search_wikimedia_candidates(
        query_en, cache_dir, layout=layout, max_candidates=1, transport=transport
    )
    return cands[0] if cands else None


def search_pexels_broll(
    query_en: str,
    cache_dir: Path,
    *,
    layout: str = "broll_fullscreen",
    api_key: str | None = None,
    transport: Transport | None = None,
) -> BRollAsset | None:
    """Fetch a commercial-safe HD vertical MP4 clip from Pexels when ``PEXELS_API_KEY`` is set."""
    key = (api_key or os.environ.get("PEXELS_API_KEY", "") or "").strip()
    if not key:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    ck = _cache_key("pexels", query_en, layout)
    cached_mp4 = cache_dir / f"px_{ck}.mp4"
    if (
        cached_mp4.is_file()
        and cached_mp4.with_name(f"{cached_mp4.name}.provenance.json").is_file()
    ):
        return BRollAsset(
            path=cached_mp4,
            provider="pexels",
            license_name="Pexels Commercial License",
            query_en=query_en,
            similarity=0.6,
            is_video=True,
        )

    tx = transport or _default_binary_transport(25.0)
    orientation = "portrait" if layout == "broll_fullscreen" else "landscape"
    params = urllib.parse.urlencode(
        {"query": query_en, "per_page": "4", "orientation": orientation}
    )
    status, raw = tx(f"https://api.pexels.com/videos/search?{params}", None, {"Authorization": key})
    if status != 200:
        return None
    try:
        videos = json.loads(raw.decode("utf-8")).get("videos", [])
    except (ValueError, AttributeError):
        return None
    for vid in videos:
        files = vid.get("video_files", []) if isinstance(vid, Mapping) else []
        hd = [
            f
            for f in files
            if isinstance(f, Mapping)
            and str(f.get("file_type", "")).lower() == "video/mp4"
            and 720 <= int(f.get("width", 0) or 0) <= 1920
        ]
        if not hd:
            continue
        link = str(hd[0].get("link", "")).strip()
        if not link.startswith("https://"):
            continue
        v_status, v_bytes = tx(link, None, {})
        if v_status != 200 or len(v_bytes) < 16_384:
            continue
        cached_mp4.write_bytes(v_bytes)
        write_asset_provenance(
            cached_mp4,
            provider="pexels",
            license_name="Pexels Commercial License",
            query_en=query_en,
            source_url=link,
            similarity=0.6,
        )
        return BRollAsset(
            path=cached_mp4,
            provider="pexels",
            license_name="Pexels Commercial License",
            query_en=query_en,
            similarity=0.6,
            is_video=True,
        )
    return None


def generate_bespoke_broll_image(
    query_en: str,
    cache_dir: Path,
    *,
    layout: str = "broll_fullscreen",
    api_key: str | None = None,
    model_id: str = DEFAULT_IMAGE_GEN_MODEL,
    transport: Transport | None = None,
) -> BRollAsset | None:
    """Generate a high-contrast dark-studio editorial still via ``gemini-nano-banana-2.1``."""
    key = api_key.strip() if api_key and api_key.strip() else read_credential(GEMINI_API_KEY)
    if not key:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    ck = _cache_key(model_id, query_en, layout)
    cached_png = cache_dir / f"nb_{ck}.png"
    if (
        cached_png.is_file()
        and cached_png.with_name(f"{cached_png.name}.provenance.json").is_file()
    ):
        return BRollAsset(
            path=cached_png,
            provider=model_id,
            license_name="Google Gemini Generated Commercial",
            query_en=query_en,
            similarity=0.95,
            is_video=False,
        )

    tx = transport or _default_binary_transport(45.0)
    aspect = "vertical 9:16" if layout == "broll_fullscreen" else "clean 16:9 card"
    prompt = (
        f"Ultra-crisp cinematic dark-studio editorial photography/illustration ({aspect}): "
        f"{query_en}. Dramatic lighting, high contrast, rich depth of field, documentary broadcast "
        "quality, ZERO text, ZERO watermarks, ZERO logos."
    )
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
    ).encode("utf-8")
    url = f"{API_ROOT}/models/{model_id}:generateContent"
    status, raw = tx(url, payload, {"x-goog-api-key": key})
    if status != 200:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
        parts = data["candidates"][0]["content"]["parts"]
        for part in parts:
            inline = part.get("inlineData") if isinstance(part, Mapping) else None
            if isinstance(inline, Mapping) and inline.get("data"):
                img_bytes = base64.b64decode(str(inline["data"]))
                cached_png.write_bytes(img_bytes)
                write_asset_provenance(
                    cached_png,
                    provider=model_id,
                    license_name="Google Gemini Generated Commercial",
                    query_en=query_en,
                    similarity=0.95,
                )
                return BRollAsset(
                    path=cached_png,
                    provider=model_id,
                    license_name="Google Gemini Generated Commercial",
                    query_en=query_en,
                    similarity=0.95,
                    is_video=False,
                )
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return None


def resolve_visual_cues_to_broll(
    cues: Sequence[VisualCue],
    word_idx_to_output_ms: Mapping[int, int],
    *,
    duration_ms: int,
    cache_dir: Path = DEFAULT_BROLL_CACHE_DIR,
    broll_dir: Path | None = None,
    enable_web_stock: bool = True,
    enable_ai_images: bool = True,
    max_ai_images: int = 2,
    verify_with_gemini: bool = True,
    verify_with_local_vision: bool = False,
    local_vision_url: str | None = None,
    local_vision_model: str | None = None,
    min_similarity: float = DEFAULT_BROLL_MIN_SIMILARITY,
    api_key: str | None = None,
    ffmpeg: Path | None = None,
    transport: Transport | None = None,
) -> tuple[tuple[BRollItem, ...], tuple[VisualInterrupt, ...]]:
    """Resolve ``VisualCue`` entries into verified ``BRollItem``s and fallback Skia Stat Cards."""
    broll_items: list[BRollItem] = []
    stat_interrupts: list[VisualInterrupt] = []
    ai_generated = 0
    occupied_broll: list[tuple[int, int]] = []

    def _verify_candidate(cand: BRollAsset, query_en: str) -> BRollAsset | None:
        if verify_with_gemini:
            try:
                passed, sim = verify_broll_relevance(
                    cand.path,
                    query_en,
                    api_key=api_key,
                    min_similarity=min_similarity,
                    ffmpeg=ffmpeg,
                    transport=transport,
                )
                return (
                    BRollAsset(
                        path=cand.path,
                        provider=cand.provider,
                        license_name=cand.license_name,
                        query_en=cand.query_en,
                        similarity=sim,
                        is_video=cand.is_video,
                    )
                    if passed
                    else None
                )
            except BRollError:
                return (
                    cand if cand.provider in ("local_broll_dir", DEFAULT_IMAGE_GEN_MODEL) else None
                )
        if verify_with_local_vision:
            try:
                passed, score = verify_broll_relevance_local(
                    cand.path,
                    query_en,
                    base_url=local_vision_url,
                    model_id=local_vision_model,
                    ffmpeg=ffmpeg,
                    transport=transport,
                )
                return (
                    BRollAsset(
                        path=cand.path,
                        provider=cand.provider,
                        license_name=cand.license_name,
                        query_en=cand.query_en,
                        similarity=score,
                        is_video=cand.is_video,
                    )
                    if passed
                    else None
                )
            except BRollError:
                return cand if cand.provider == "local_broll_dir" else None
        return cand

    for cue in cues:
        anchor_ms = word_idx_to_output_ms.get(cue.anchor_word_idx)
        if anchor_ms is None:
            continue
        start_ms = max(2_800, min(duration_ms - 2_400, anchor_ms))
        end_ms = min(duration_ms - 1_200, start_ms + cue.duration_ms)
        if end_ms - start_ms < 1_200:
            continue

        if cue.layout in ("stat_card", "quote_card"):
            text_ckb = (
                f"{cue.stat_hero} | {cue.label_ckb}"
                if cue.stat_hero and cue.label_ckb
                else (cue.label_ckb or cue.stat_hero)
            )
            if text_ckb.strip():
                stat_interrupts.append(
                    VisualInterrupt(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text_ckb=text_ckb.strip(),
                        position="top",
                    )
                )
            continue

        # Avoid overlapping two B-roll items within 1.5 s of each other.
        if any(not (end_ms + 1_500 <= s or start_ms >= e + 1_500) for s, e in occupied_broll):
            continue

        asset: BRollAsset | None = None
        if broll_dir is not None:
            local_cand = search_local_broll(broll_dir, cue.query_en)
            if local_cand is not None:
                asset = _verify_candidate(local_cand, cue.query_en)
        if asset is None and enable_web_stock:
            px = search_pexels_broll(
                cue.query_en, cache_dir, layout=cue.layout, transport=transport
            )
            if px is not None:
                asset = _verify_candidate(px, cue.query_en)
            if asset is None:
                wm_cands = _search_wikimedia_candidates(
                    cue.query_en,
                    cache_dir,
                    layout=cue.layout,
                    max_candidates=3 if (verify_with_gemini or verify_with_local_vision) else 1,
                    transport=transport,
                )
                for wm in wm_cands:
                    verified = _verify_candidate(wm, cue.query_en)
                    if verified is not None:
                        asset = verified
                        break

        if asset is None and enable_ai_images and ai_generated < max_ai_images:
            asset = generate_bespoke_broll_image(
                cue.query_en, cache_dir, layout=cue.layout, api_key=api_key, transport=transport
            )
            if asset is not None:
                ai_generated += 1

        if asset is not None:
            pos = "fullscreen" if cue.layout == "broll_fullscreen" else "top_pip"
            width = 1080 if pos == "fullscreen" else 860
            broll_items.append(
                BRollItem(
                    path=asset.path,
                    start_ms=start_ms,
                    duration_ms=end_ms - start_ms,
                    position=pos,
                    width=width,
                    ken_burns=not asset.is_video,
                )
            )
            occupied_broll.append((start_ms, end_ms))
        elif cue.stat_hero or cue.label_ckb:
            text_ckb = (
                f"{cue.stat_hero} | {cue.label_ckb}"
                if cue.stat_hero and cue.label_ckb
                else (cue.label_ckb or cue.stat_hero)
            )
            stat_interrupts.append(
                VisualInterrupt(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text_ckb=text_ckb.strip(),
                    position="top",
                )
            )

    return tuple(broll_items), tuple(stat_interrupts)
