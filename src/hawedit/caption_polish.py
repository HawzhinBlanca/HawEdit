"""Clip-only Sorani caption polish and CTC micro-stutter deduplication (D-358).

Operates strictly on the chosen clip's display-layer `Sentence` sequence — never mutates
`transcript.raw.json` (Kurdish invariant #1) and never invents or alters word timestamps
(Kurdish invariant #5).
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.gemini import extract_response_text
from hawedit.http_transport import open_without_redirects
from hawedit.judge import StructuredJsonClient
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "CAPTION_POLISH_SCHEMA",
    "DEFAULT_LOCAL_LLM_TIMEOUT_S",
    "DEFAULT_LOCAL_LLM_URL",
    "DEFAULT_MAX_CHAR_DIVERGENCE",
    "DEFAULT_MAX_STUTTER_TOKEN_MS",
    "KURDISH_ASR_BIGRAM_FIXES",
    "KURDISH_ASR_ORTHOGRAPHY_FIXES",
    "LOCAL_LLM_MODEL_ENV",
    "LOCAL_LLM_URL_ENV",
    "MAX_INLINE_AUDIO_BYTES",
    "MAX_LOCAL_LLM_RESPONSE_BYTES",
    "CaptionPolishResult",
    "LocalLlmJsonClient",
    "LocalLlmUnavailable",
    "deduplicate_micro_stutters",
    "normalize_sorani_digits",
    "polish_clip_sentences",
    "repair_kurdish_asr_orthography",
]

DEFAULT_MAX_STUTTER_TOKEN_MS: Final[int] = 120
DEFAULT_MAX_CHAR_DIVERGENCE: Final[float] = 0.25
DEFAULT_LOCAL_LLM_URL: Final[str] = "http://127.0.0.1:1234/v1"
DEFAULT_LOCAL_LLM_TIMEOUT_S: Final[float] = 60.0
LOCAL_LLM_URL_ENV: Final[str] = "HAWEDIT_LOCAL_LLM_URL"
LOCAL_LLM_MODEL_ENV: Final[str] = "HAWEDIT_LOCAL_LLM_MODEL"
MAX_LOCAL_LLM_RESPONSE_BYTES: Final[int] = 1 << 20
# D-366: Rapid spoken Kurdish function/filler word repeats (e.g. `وەکو وەکو`, `بە بە`) up to
# 380 ms are conversational disfluencies rather than intentional emphasis (like `زۆر زۆر`).
_FUNCTION_STUTTER_WORDS: Final[frozenset[str]] = frozenset(
    {"وەکو", "وەک", "بە", "لە", "بۆ", "کە", "و", "ئەم", "ئەو", "تا", "یەعنی", "ئێ", "ئا"}
)
_FUNCTION_STUTTER_MAX_MS: Final[int] = 380
_FUNCTION_STUTTER_MAX_GAP_MS: Final[int] = 220
MAX_INLINE_AUDIO_BYTES: Final[int] = 10 * 1024 * 1024
_PUNCT_CHARS: Final[str] = " \t\n\r.,!?:؛،؟۔…"
_DIGIT_EDGE_PUNCT: Final[str] = " \t\n\r.,!?:؛،؟۔…«»\"'“”()[]"
_TERMINAL_PUNCT: Final[frozenset[str]] = frozenset(".!?؟۔…")
_DIGIT_TRANSLATION: Final = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_SORANI_DIGITS: Final[dict[str, str]] = {
    "0": "سفر",
    "1": "یەک",
    "2": "دوو",
    "3": "سێ",
    "4": "چوار",
    "5": "پێنج",
    "6": "شەش",
    "7": "حەوت",
    "8": "هەشت",
    "9": "نۆ",
    "10": "دە",
}

# D-381: Unambiguous single-token Sorani Kurdish ASR orthography and loanword repairs.
# Strictly 1-to-1 (preserving exact word count and CTC timestamps) and verified for zero
# false positives across multi-genre real Kurdish transcripts.
KURDISH_ASR_ORTHOGRAPHY_FIXES: Final[dict[str, str]] = {
    "ئەگەزانی": "ئەزانی",
    "نابزانی": "نازانی",
    "ئەزولێن": "ئەجووڵێن",
    "بەیانیەکەی": "بەیانییەکەی",
    "ڕێگریەکانی": "ڕێگرییەکانی",
    "ڕێگریانە": "ڕێگرییانە",
    "زانیاریەکان": "زانیارییەکان",
    "ڕەستۆرانت": "ڕێستۆرانت",
    "ڕەستۆرانتەکە": "ڕێستۆرانتەکە",
    "ڕەستۆرانتەکان": "ڕێستۆرانتەکان",
    "ڕەستۆرانتێک": "ڕێستۆرانتێک",
    "کاشەر": "کاشێر",
    "کاشەری": "کاشێری",
    "کاشەرەکە": "کاشێرەکە",
    "کاشەرەکان": "کاشێرەکان",
    "ڕیستیک": "ڕیستریکت",
    "ئەبدەیت": "ئەپدەیت",
    "ئەبدەیتانە": "ئەپدەیتانە",
    "دامەزراویەکی": "دامەزراوەیەکی",
    "تەکستێکی": "تێکستێکی",
}

# D-381: General Sorani double-yaa orthography rule for nouns ending in consonant + vowel `ی`
# followed by vowel-initial definite/plural suffixes (`ەکە*`, `ەکان*`). Excludes stems whose
# character before `ی` is already a vowel/glide (`ا، ە، ۆ، ێ، و، ی`, e.g. `کێشەیەکە`,
# `هاوڕێیەکە`, `ڤیدۆیەکە`, `ئایەکە`) and short stems (`< 3` chars before `ی`, e.g. `چیەکە`),
# while leaving consonant stems (`کۆمپیوتەرەکەی`) untouched.
_SORANI_DOUBLE_YAA_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<stem>.{2,}[^اەۆێویئؤةه\s])ی(?P<suf>ەکە(?:ی|م|ت|مان|تان|یان)?|ەکان(?:ی|م|ت|مان|تان|یان)?)$"
)

# D-381: Context-aware 2-word phonetic/boundary ASR repairs preserving strict 1-to-1 token
# count and exact per-word CTC timestamps. Never invents words.
KURDISH_ASR_BIGRAM_FIXES: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("مۆدەی", "بڵاو"): ("مۆدێل", "بڵاو"),
    ("هەرمی", "کوردستان"): ("هەرێمی", "کوردستان"),
    ("ئاینە", "چێتە"): ("ئای", "نەچێتە"),
    ("ئێ", "ئای"): ("ئەی", "ئای"),
    ("وەردەری", "کا"): ("ئۆردەری", "کا"),
}

_THINK_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*<think>.*?</think>\s*",
    flags=re.DOTALL | re.IGNORECASE,
)
_CODE_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$",
    flags=re.DOTALL | re.IGNORECASE,
)

_AUDIO_MIME_BY_SUFFIX: Final[dict[str, str]] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}

# OpenAPI 3.0 response schema (no `additionalProperties` for Gemini compatibility).
CAPTION_POLISH_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "replacements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "w": {"type": "string"},
                },
                "required": ["index", "w"],
            },
        },
    },
    "required": ["replacements"],
}

_POLISH_PROMPT_TEMPLATE: Final[str] = (
    "You are proofreading Central Kurdish (Sorani, Arabic script) ASR captions for a single "
    "short video clip.\n"
    "Review the numbered word list below (and the attached clip audio, if present). Aggressively "
    "repair clear ASR spelling mistakes, Sorani orthography errors, and phonetic manglings of "
    "English tech/brand/proper-noun loanwords or Arabic-Kurdish words using surrounding Kurdish "
    "context (and audio if provided):\n"
    "- English tech/loanword phonetic garbles: e.g. `ڕیستیک` -> `ڕیستریکت`, `مۆدەی` before "
    "`بڵاو` -> `مۆدێل`, `کاشەرەکە` -> `کاشێرەکە`, `ڕەستۆرانتەکە` -> `ڕێستۆرانتەکە`, "
    "`ئەبدەیتانە` -> `ئەپدەیتانە`, and garbled English model/version names like `ما فەیبوو فایف` "
    "when unambiguously identifiable from context or audio.\n"
    "- Phonetic Kurdish/Arabic ASR corruptions & word-boundary garbles: e.g. `ئەگەزانی` -> "
    "`ئەزانی`, `خمەم نوعیان`, `عالەمانەیان`, `ئاینە چێتە` -> `ئای` / `نەچێتە`.\n"
    "- Sorani double-yaa orthography: consonant+`ی` stems before `ەکە`/`ەکان` take `یی` "
    "(`بەیانیەکەی` -> `بەیانییەکەی`, `ڕێگریەکانی` -> `ڕێگرییەکانی`, `زانیاریەکان` -> "
    "`زانیارییەکان`); keep consonant stems (`کۆمپیوتەرەکەی`) and vowel-stem glides (`کێشەیەکە`, "
    "`هاوڕێیەکە`) unchanged.\n"
    "Strict rules:\n"
    "- Return ONLY 1-to-1 single-token replacements by 0-based word index as JSON: "
    '{{"replacements": [{{"index": 0, "w": "word"}}]}}.\n'
    "- NEVER add, delete, merge, or split words; preserve the exact 1-to-1 token count.\n"
    "- Preserve authentic spoken Sorani dialect (do NOT rewrite colloquial forms like `ئەکا`, "
    "`ئەڵێم`, `یەعنی`, `هەنێ` into formal literary Kurdish).\n"
    "- NEVER translate, paraphrase, invent missing words, or rewrite meaning.\n"
    "- NEVER emit empty strings or multi-word replacements containing whitespace.\n"
    "- Omit words that are already spelled accurately; return an empty list if none need fixes.\n\n"
    "Clip words:\n{word_lines}\n"
)


class LocalLlmUnavailable(RuntimeError):
    """Raised fail-loud when a configured local OpenAI-compatible LLM endpoint cannot serve."""


def _openai_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``schema`` with ``additionalProperties: False`` on object nodes."""

    def _convert(node: Any) -> Any:
        if isinstance(node, Mapping):
            out = {str(k): _convert(v) for k, v in node.items()}
            if out.get("type") == "object" and "additionalProperties" not in out:
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [_convert(item) for item in node]
        return node

    converted = _convert(schema)
    if not isinstance(converted, dict):
        raise ValueError("schema must be a JSON object mapping")
    return converted


def _strip_llm_json_wrappers(raw_text: str) -> str:
    """Strip optional reasoning `<think>...</think>` headers and markdown JSON code fences."""
    cleaned = _THINK_BLOCK_RE.sub("", raw_text).strip()
    fenced = _CODE_FENCE_RE.match(cleaned)
    if fenced is not None:
        return fenced.group(1).strip()
    return cleaned


class LocalLlmJsonClient:
    """Stdlib OpenAI-compatible local LLM client implementing ``StructuredJsonClient`` (D-381).

    Targets local OpenAI-compatible servers such as LM Studio (default
    ``http://127.0.0.1:1234/v1``) with zero external dependencies and strict fail-stop error
    reporting (raises ``LocalLlmUnavailable`` on connection, timeout, HTTP, or protocol errors).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = DEFAULT_LOCAL_LLM_TIMEOUT_S,
        api_key: str | None = None,
    ) -> None:
        raw_url = (
            (os.environ.get(LOCAL_LLM_URL_ENV, "").strip() or DEFAULT_LOCAL_LLM_URL)
            if base_url is None
            else base_url.strip()
        )
        parsed = urllib.parse.urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"base_url must be a valid http(s) URL, got {raw_url!r}")
        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, int | float)
            or not math.isfinite(float(timeout_s))
            or float(timeout_s) <= 0.0
        ):
            raise ValueError(f"timeout_s must be a positive finite number, got {timeout_s!r}")

        self.base_url: str = raw_url.rstrip("/")
        self.timeout_s: float = float(timeout_s)
        resolved_model = (
            os.environ.get(LOCAL_LLM_MODEL_ENV, "") if model is None else model
        ).strip()
        self.model_id: str = resolved_model
        self._api_key: str | None = (
            api_key.strip() if api_key is not None and api_key.strip() else None
        )

    def _headers(self, *, include_content_type: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body_bytes = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        )
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._headers(include_content_type=payload is not None),
            method=method,
        )
        try:
            with open_without_redirects(req, timeout=self.timeout_s) as resp:
                raw_bytes = resp.read(MAX_LOCAL_LLM_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(512).decode("utf-8", errors="replace").strip()
            except OSError:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise LocalLlmUnavailable(f"Local LLM HTTP {exc.code} from {url}{suffix}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LocalLlmUnavailable(f"Local LLM endpoint unavailable at {url}: {exc}") from exc

        if len(raw_bytes) > MAX_LOCAL_LLM_RESPONSE_BYTES:
            raise LocalLlmUnavailable(
                f"Local LLM response from {url} exceeded {MAX_LOCAL_LLM_RESPONSE_BYTES} bytes"
            )
        try:
            decoded: object = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise LocalLlmUnavailable(f"Local LLM returned invalid JSON from {url}: {exc}") from exc
        if not isinstance(decoded, dict):
            raise LocalLlmUnavailable(
                f"Local LLM response from {url} must be a JSON object, got {type(decoded).__name__}"
            )
        return decoded

    def probe_models(self) -> tuple[str, ...]:
        """Query ``GET /models`` on the local endpoint and return advertised model IDs."""
        data = self._request_json("GET", "/models")
        raw_models = data.get("data")
        if not isinstance(raw_models, list):
            raise LocalLlmUnavailable(
                f"Local LLM /models payload missing 'data' list at {self.base_url}/models"
            )
        model_ids: list[str] = []
        for item in raw_models:
            if isinstance(item, Mapping):
                mid = item.get("id")
                if isinstance(mid, str) and mid.strip():
                    model_ids.append(mid.strip())
        return tuple(model_ids)

    def resolve_model(self) -> str:
        """Return configured ``model_id`` or auto-select the first loaded non-embedding model."""
        if self.model_id:
            return self.model_id
        chat_models = [mid for mid in self.probe_models() if "embed" not in mid.lower()]
        if not chat_models:
            raise LocalLlmUnavailable(
                f"No chat model loaded at local LLM endpoint {self.base_url}/models"
            )
        self.model_id = chat_models[0]
        return self.model_id

    @staticmethod
    def _extract_prompt_text(parts: Sequence[Mapping[str, Any]]) -> str:
        text_blocks: list[str] = []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_blocks.append(text)
        return "\n\n".join(text_blocks)

    def count_parts(self, parts: list[dict[str, Any]]) -> int:
        """Estimate token budget for text parts without making a network round-trip."""
        prompt_text = self._extract_prompt_text(parts)
        return 0 if not prompt_text else max(1, len(prompt_text) // 4)

    def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
        """Call ``POST /chat/completions`` with strict JSON schema output and fail loud on error."""
        prompt_text = self._extract_prompt_text(parts)
        if not prompt_text:
            raise ValueError("parts must contain at least one non-empty text block")

        model_id = self.resolve_model()
        payload: dict[str, Any] = {
            "model": model_id,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON generator for Central Kurdish (Sorani) caption "
                        "proofreading. Respond with ONLY valid JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "caption_polish",
                    "strict": True,
                    "schema": _openai_strict_schema(schema),
                },
            },
        }
        response = self._request_json("POST", "/chat/completions", payload)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LocalLlmUnavailable(
                f"Local LLM chat completion missing 'choices' from {self.base_url}/chat/completions"
            )
        first = choices[0]
        message = first.get("message") if isinstance(first, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str) or not content.strip():
            raise LocalLlmUnavailable(
                "Local LLM chat completion returned empty or non-string message content"
            )
        return _strip_llm_json_wrappers(content)


@dataclass(frozen=True, slots=True)
class CaptionPolishResult:
    """Outcome of display-layer clip caption deduplication and optional spelling polish."""

    sentences: tuple[Sentence, ...]
    stutters_removed: int
    words_polished: int
    rejected_reason: str | None = None
    applied: bool = True


def _lexical_core(surface: str) -> str:
    return surface.strip(_PUNCT_CHARS)


def _merge_stutter_surface(first: str, last: str) -> str:
    """Keep the leading token's surface form while preserving trailing punctuation from the run."""
    first_rstripped = first.rstrip(_PUNCT_CHARS)
    if first_rstripped != first:
        return first
    last_rstripped = last.rstrip(_PUNCT_CHARS)
    trailing_punct = last[len(last_rstripped) :]
    return f"{first}{trailing_punct}" if trailing_punct else first


def deduplicate_micro_stutters(
    sentences: Sequence[Sentence],
    *,
    max_token_ms: int = DEFAULT_MAX_STUTTER_TOKEN_MS,
) -> tuple[tuple[Sentence, ...], int]:
    """Deterministically collapse rapid CTC micro-stutters while keeping emphatic repeats.

    Removes runs of ``>= 2`` identical consecutive words inside a sentence when *each* token
    lasts ``<= max_token_ms`` and consecutive tokens are separated by ``<= max_token_ms``.
    The surviving token spans ``[run[0].start_ms, max(w.end_ms for w in run)]``, preserving
    monotone timestamps and ``Sentence.complete``.

    Intentional Kurdish emphatic repeats (e.g. ``زۆر زۆر`` at ``250 ms`` each) exceed
    ``max_token_ms`` and are strictly preserved.
    """
    if isinstance(max_token_ms, bool) or max_token_ms < 0:
        raise ValueError(f"max_token_ms must be a non-negative integer, got {max_token_ms!r}")
    if not sentences:
        return (), 0

    cleaned_sentences: list[Sentence] = []
    total_removed = 0

    for sentence in sentences:
        words = sentence.words
        if len(words) < 2:
            cleaned_sentences.append(sentence)
            continue

        new_words: list[Word] = []
        idx = 0
        n = len(words)
        while idx < n:
            head = words[idx]
            head_core = _lexical_core(head.w)
            head_dur = head.end_ms - head.start_ms
            is_fn_stutter = max_token_ms > 0 and head_core in _FUNCTION_STUTTER_WORDS
            eff_max_dur = (
                max(max_token_ms, _FUNCTION_STUTTER_MAX_MS) if is_fn_stutter else max_token_ms
            )
            eff_max_gap = (
                max(max_token_ms, _FUNCTION_STUTTER_MAX_GAP_MS) if is_fn_stutter else max_token_ms
            )

            if head_core and head_dur <= eff_max_dur:
                end_idx = idx + 1
                while end_idx < n:
                    prev_w = words[end_idx - 1]
                    cand = words[end_idx]
                    cand_dur = cand.end_ms - cand.start_ms
                    gap_ms = cand.start_ms - prev_w.end_ms
                    if (
                        _lexical_core(cand.w) == head_core
                        and cand_dur <= eff_max_dur
                        and gap_ms <= eff_max_gap
                    ):
                        end_idx += 1
                    else:
                        break

                run_len = end_idx - idx
                if run_len >= 2:
                    run = words[idx:end_idx]
                    merged = Word(
                        w=_merge_stutter_surface(run[0].w, run[-1].w),
                        start_ms=run[0].start_ms,
                        end_ms=max(w.end_ms for w in run),
                        conf=max(w.conf for w in run),
                    )
                    new_words.append(merged)
                    total_removed += run_len - 1
                    idx = end_idx
                    continue

            new_words.append(head)
            idx += 1

        cleaned_sentences.append(Sentence(words=tuple(new_words), complete=sentence.complete))

    return tuple(cleaned_sentences), total_removed


def _split_edge_punct(surface: str) -> tuple[str, str, str]:
    """Split a token into ``(leading_punct, lexical_core, trailing_punct)``."""
    stripped_left = surface.lstrip(_DIGIT_EDGE_PUNCT)
    lead = surface[: len(surface) - len(stripped_left)]
    core = stripped_left.rstrip(_DIGIT_EDGE_PUNCT)
    trail = stripped_left[len(core) :]
    return lead, core, trail


def normalize_sorani_digits(sentences: Sequence[Sentence]) -> tuple[Sentence, ...]:
    """Convert isolated Western (`0`-`10`) and Arabic-Indic (`٠`-`١٠`) numerals to Sorani words.

    Preserves leading and trailing punctuation, exact ``Word.start_ms``, ``Word.end_ms``,
    ``Word.conf``, 1-to-1 word count, and ``Sentence.complete`` without mutating the input
    sentences or ``transcript.raw.json``.
    """
    if not sentences:
        return ()

    normalized_sentences: list[Sentence] = []
    for sentence in sentences:
        changed = False
        new_words: list[Word] = []
        for word in sentence.words:
            lead, core, trail = _split_edge_punct(word.w)
            ascii_core = core.translate(_DIGIT_TRANSLATION) if core else ""
            sorani = _SORANI_DIGITS.get(ascii_core)
            if sorani is not None:
                changed = True
                new_words.append(
                    Word(
                        w=f"{lead}{sorani}{trail}",
                        start_ms=word.start_ms,
                        end_ms=word.end_ms,
                        conf=word.conf,
                    )
                )
            else:
                new_words.append(word)
        if changed:
            normalized_sentences.append(
                Sentence(words=tuple(new_words), complete=sentence.complete)
            )
        else:
            normalized_sentences.append(sentence)
    return tuple(normalized_sentences)


def _repair_single_sorani_core(core: str) -> str:
    """Apply unambiguous single-word Sorani ASR spelling and double-yaa orthography fixes."""
    if not core:
        return core
    direct = KURDISH_ASR_ORTHOGRAPHY_FIXES.get(core)
    if direct is not None:
        return direct
    match = _SORANI_DOUBLE_YAA_RE.match(core)
    if match is not None:
        return f"{match.group('stem')}یی{match.group('suf')}"
    return core


def repair_kurdish_asr_orthography(
    sentences: Sequence[Sentence],
) -> tuple[tuple[Sentence, ...], int]:
    """Deterministically repair unambiguous Sorani ASR spelling and 2-word phonetic garbles.

    Applies:
    1. Exact single-word fixes from ``KURDISH_ASR_ORTHOGRAPHY_FIXES``.
    2. General Sorani double-yaa orthography rule on consonant+``ی`` stems before definite/plural
       suffixes (``ەکە*``, ``ەکان*``), leaving consonant stems (``کۆمپیوتەرەکەی``) and vowel-stem
       glides (``کێشەیەکە``, ``هاوڕێیەکە``, ``ئایەکە``) untouched.
    3. Context-aware 2-word phonetic/boundary repairs from ``KURDISH_ASR_BIGRAM_FIXES`` within
       each sentence (never bridging terminal sentence punctuation).

    Strictly preserves 1-to-1 word count, leading/trailing punctuation, exact ``Word.start_ms``,
    ``Word.end_ms``, ``Word.conf``, ``Sentence.complete``, and leaves input sentences immutable.
    """
    if not sentences:
        return (), 0

    repaired_sentences: list[Sentence] = []
    total_repaired = 0

    for sentence in sentences:
        if not sentence.words:
            repaired_sentences.append(sentence)
            continue

        parts_list: list[list[str]] = []
        for word in sentence.words:
            lead, core, trail = _split_edge_punct(word.w)
            fixed_core = _repair_single_sorani_core(core)
            parts_list.append([lead, fixed_core, trail])

        for idx in range(len(parts_list) - 1):
            trail_left = parts_list[idx][2]
            if any(ch in _TERMINAL_PUNCT for ch in trail_left):
                continue
            pair = (parts_list[idx][1], parts_list[idx + 1][1])
            fixed_pair = KURDISH_ASR_BIGRAM_FIXES.get(pair)
            if fixed_pair is not None:
                parts_list[idx][1] = fixed_pair[0]
                parts_list[idx + 1][1] = fixed_pair[1]

        changed = False
        new_words: list[Word] = []
        for orig_word, (lead, core, trail) in zip(sentence.words, parts_list, strict=True):
            new_surface = f"{lead}{core}{trail}"
            if new_surface != orig_word.w:
                changed = True
                total_repaired += 1
                new_words.append(
                    Word(
                        w=new_surface,
                        start_ms=orig_word.start_ms,
                        end_ms=orig_word.end_ms,
                        conf=orig_word.conf,
                    )
                )
            else:
                new_words.append(orig_word)

        if changed:
            repaired_sentences.append(Sentence(words=tuple(new_words), complete=sentence.complete))
        else:
            repaired_sentences.append(sentence)

    return tuple(repaired_sentences), total_repaired


def _levenshtein(source: str, target: str) -> int:
    """Exact Levenshtein character edit distance using O(min(m, n)) memory."""
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)
    if len(source) < len(target):
        source, target = target, source

    prev_row = list(range(len(target) + 1))
    for i, s_char in enumerate(source, start=1):
        curr_row = [i]
        for j, t_char in enumerate(target, start=1):
            cost = 0 if s_char == t_char else 1
            curr_row.append(
                min(
                    prev_row[j] + 1,
                    curr_row[j - 1] + 1,
                    prev_row[j - 1] + cost,
                )
            )
        prev_row = curr_row
    return prev_row[-1]


def _audio_mime_type(audio_path: Path) -> str:
    return _AUDIO_MIME_BY_SUFFIX.get(audio_path.suffix.lower(), "audio/wav")


def _build_polish_parts(
    flat_words: Sequence[Word],
    audio_path: Path | None,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    if audio_path is not None:
        if not audio_path.is_file():
            raise FileNotFoundError(f"audio_path does not exist: {audio_path}")
        size = audio_path.stat().st_size
        if 0 < size <= MAX_INLINE_AUDIO_BYTES:
            encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
            parts.append(
                {
                    "inlineData": {
                        "mimeType": _audio_mime_type(audio_path),
                        "data": encoded,
                    }
                }
            )

    word_lines = "\n".join(
        f"{idx} ({w.start_ms / 1000.0:.2f}-{w.end_ms / 1000.0:.2f}s): {w.w}"
        for idx, w in enumerate(flat_words)
    )
    parts.append({"text": _POLISH_PROMPT_TEMPLATE.format(word_lines=word_lines)})
    return parts


def _parse_replacements(
    raw_response: str,
    word_count: int,
) -> tuple[dict[int, str] | None, str | None]:
    """Parse and validate 1-to-1 replacements from raw JSON or Gemini envelope."""
    try:
        parsed: object = json.loads(raw_response)
        if isinstance(parsed, dict) and "candidates" in parsed:
            parsed = json.loads(extract_response_text(raw_response))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return None, f"unusable caption polish JSON response: {exc}"

    if not isinstance(parsed, dict):
        return None, f"caption polish payload must be a JSON object, got {type(parsed).__name__}"
    raw_items = parsed.get("replacements")
    if not isinstance(raw_items, list):
        return None, "caption polish payload missing 'replacements' array"

    replacements: dict[int, str] = {}
    for pos, item in enumerate(raw_items):
        if not isinstance(item, dict):
            return None, f"replacements[{pos}] must be a JSON object"
        raw_idx = item.get("index")
        raw_w = item.get("w")
        if isinstance(raw_idx, bool) or not isinstance(raw_idx, int):
            return None, f"replacements[{pos}].index must be an integer, got {raw_idx!r}"
        if not 0 <= raw_idx < word_count:
            return None, f"replacements[{pos}].index {raw_idx} out of range [0, {word_count})"
        if raw_idx in replacements:
            return None, f"duplicate replacement index {raw_idx}"
        if not isinstance(raw_w, str):
            return None, f"replacements[{pos}].w must be a string"

        cleaned_w = raw_w.strip()
        if not cleaned_w:
            return None, f"replacements[{pos}] at index {raw_idx} is empty"
        if cleaned_w.splitlines() != [cleaned_w]:
            return None, f"replacements[{pos}] at index {raw_idx} contains a line break"
        if any(ch.isspace() for ch in cleaned_w):
            return (
                None,
                f"replacements[{pos}] at index {raw_idx} contains whitespace (alters word count)",
            )
        replacements[raw_idx] = cleaned_w

    return replacements, None


def polish_clip_sentences(
    sentences: Sequence[Sentence],
    *,
    client: StructuredJsonClient | None = None,
    audio_path: Path | None = None,
    max_char_divergence: float = DEFAULT_MAX_CHAR_DIVERGENCE,
    max_stutter_token_ms: int = DEFAULT_MAX_STUTTER_TOKEN_MS,
) -> CaptionPolishResult:
    """Polish display-layer captions for one chosen clip with strict safety guardrails.

    1. Always runs ``deduplicate_micro_stutters``, ``normalize_sorani_digits``, and
       ``repair_kurdish_asr_orthography`` deterministically (preserving exact CTC timestamps).
    2. When ``client`` is supplied, requests 1-to-1 Sorani spelling & phonetic loanword fixes
       (with optional small inline clip audio) and rejects any invalid, empty, multi-word, or
       divergent (``> max_char_divergence``) response without mutating captions or timestamps.
    """
    if (
        isinstance(max_char_divergence, bool)
        or not isinstance(max_char_divergence, int | float)
        or not math.isfinite(float(max_char_divergence))
        or not 0.0 <= float(max_char_divergence) <= 1.0
    ):
        raise ValueError(
            f"max_char_divergence must be a finite float in [0.0, 1.0], got {max_char_divergence!r}"
        )

    cleaned, stutters_removed = deduplicate_micro_stutters(
        sentences,
        max_token_ms=max_stutter_token_ms,
    )
    cleaned = normalize_sorani_digits(cleaned)
    cleaned, ortho_repaired = repair_kurdish_asr_orthography(cleaned)
    if not cleaned or client is None:
        return CaptionPolishResult(
            sentences=cleaned,
            stutters_removed=stutters_removed,
            words_polished=ortho_repaired,
            rejected_reason=None,
            applied=True,
        )

    flat_words = tuple(w for sentence in cleaned for w in sentence.words)
    if not flat_words:
        return CaptionPolishResult(
            sentences=cleaned,
            stutters_removed=stutters_removed,
            words_polished=ortho_repaired,
            rejected_reason=None,
            applied=True,
        )

    parts = _build_polish_parts(flat_words, audio_path)
    raw_response = client.generate_json(parts, CAPTION_POLISH_SCHEMA)
    replacements, parse_error = _parse_replacements(raw_response, len(flat_words))
    if parse_error is not None or replacements is None:
        return CaptionPolishResult(
            sentences=cleaned,
            stutters_removed=stutters_removed,
            words_polished=ortho_repaired,
            rejected_reason=parse_error or "caption polish response rejected",
            applied=False,
        )

    if not replacements:
        return CaptionPolishResult(
            sentences=cleaned,
            stutters_removed=stutters_removed,
            words_polished=ortho_repaired,
            rejected_reason=None,
            applied=True,
        )

    candidate_words: list[Word] = []
    llm_polished = 0
    for idx, word in enumerate(flat_words):
        new_w = replacements.get(idx, word.w)
        if new_w != word.w:
            llm_polished += 1
            candidate_words.append(
                Word(w=new_w, start_ms=word.start_ms, end_ms=word.end_ms, conf=word.conf)
            )
        else:
            candidate_words.append(word)

    orig_text = unicodedata.normalize("NFC", " ".join(w.w for w in flat_words))
    new_text = unicodedata.normalize("NFC", " ".join(w.w for w in candidate_words))
    divergence = _levenshtein(orig_text, new_text) / max(len(orig_text), 1)
    if divergence > float(max_char_divergence):
        return CaptionPolishResult(
            sentences=cleaned,
            stutters_removed=stutters_removed,
            words_polished=ortho_repaired,
            rejected_reason=(
                f"character divergence {divergence:.3f} exceeds max_char_divergence "
                f"{float(max_char_divergence):.3f}"
            ),
            applied=False,
        )

    rebuilt: list[Sentence] = []
    offset = 0
    for sentence in cleaned:
        count = len(sentence.words)
        rebuilt.append(
            Sentence(
                words=tuple(candidate_words[offset : offset + count]),
                complete=sentence.complete,
            )
        )
        offset += count

    return CaptionPolishResult(
        sentences=tuple(rebuilt),
        stutters_removed=stutters_removed,
        words_polished=ortho_repaired + llm_polished,
        rejected_reason=None,
        applied=True,
    )
