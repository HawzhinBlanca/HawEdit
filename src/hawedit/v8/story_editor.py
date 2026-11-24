"""HawEdit V10.2 Component 1: True Semantic Multi-Cut Story Architect & Meaning-Preserving Pruner.

Replaces single-span acoustic slicing with:
1. Whole-episode multi-cut story planning (``plan_episode_multicut_stories``) via
   ``gemini-4-neon`` (primary) or local OpenAI-compatible LLM (``local-omni``), assembling
   2-6 non-contiguous story beats (Hook -> Setup -> Escalation -> Payoff) + surgical word/clause
   filler/stumble drop ranges + Kurdified curiosity hooks + content-aware visual cues.
2. Independent meaning-preservation verification (``verify_story_meaning_preservation``) via
   ``gemini-4-carbon`` (or ``local-omni``) that surgically restores any ``DropRange`` risking
   negation flips, grammar breaks, or distorted speaker intent.
3. 16 kHz acoustic prosody boundary snapping (``compile_story_to_assembly_spans``) placing every
   cut edge in the local RMS energy valley (within +-40 ms) so consonants are never clipped.

Strict fail-stop policy (AGENTS.md / D-394): zero silent fallbacks between cloud and local
backends, bounded HTTP reads, no redirects, and strict JSON schema validation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from array import array
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal

from hawedit.assembly import AssemblySpan
from hawedit.credentials import GEMINI_API_KEY, read_credential
from hawedit.gemini import API_ROOT, extract_response_text
from hawedit.http_transport import open_without_redirects
from hawedit.sentences import DANGLING_CONJUNCTIONS_CKB, Sentence
from hawedit.silence import KURDISH_FILLER_TOKENS
from hawedit.transcripts import Word
from hawedit.v8.director import (
    DEFAULT_GEMINI_DIRECTOR_MODEL,
    DEFAULT_GEMINI_TIMEOUT_S,
    DEFAULT_OMNI_TIMEOUT_S,
    DEFAULT_OMNI_URL,
    OMNI_MODEL_ENV,
    OMNI_URL_ENV,
    _openai_strict_schema,
    _strip_json_wrappers,
)

__all__ = [
    "DEFAULT_STORY_ARCHITECT_MODEL",
    "DEFAULT_STORY_VERIFIER_MODEL",
    "MAX_STORY_RESPONSE_BYTES",
    "MEANING_CHECK_SCHEMA",
    "MULTICUT_EPISODE_SCHEMA",
    "STORY_REFINER_SCHEMA",
    "CompiledStoryTimeline",
    "DropKind",
    "DropRange",
    "MeaningVerificationResult",
    "MultiCutStoryRecipe",
    "StoryBeatRole",
    "StoryEditorError",
    "VisualCue",
    "VisualCueLayout",
    "WordSpan",
    "compile_story_to_assembly_spans",
    "plan_episode_multicut_stories",
    "refine_story_pruning",
    "snap_cut_to_rms_valley",
    "verify_story_meaning_preservation",
]

StoryBeatRole = Literal["cold_open", "hook", "setup", "escalation", "payoff"]
DropKind = Literal["filler", "stumble", "redundant_clause", "tangent"]
VisualCueLayout = Literal["broll_fullscreen", "broll_pip", "stat_card", "quote_card"]
StoryBackend = Literal["gemini", "local-omni"]
Transport = Callable[[str, bytes | None, Mapping[str, str]], tuple[int, str]]

DEFAULT_STORY_ARCHITECT_MODEL: Final[str] = DEFAULT_GEMINI_DIRECTOR_MODEL  # "gemini-4-neon"
DEFAULT_STORY_VERIFIER_MODEL: Final[str] = "gemini-4-carbon"
MAX_STORY_RESPONSE_BYTES: Final[int] = 4 * 1024 * 1024
_MAX_ERROR_CHARS: Final[int] = 512

_VALID_ROLES: Final[frozenset[str]] = frozenset(
    {"cold_open", "hook", "setup", "escalation", "payoff"}
)
_VALID_DROP_KINDS: Final[frozenset[str]] = frozenset(
    {"filler", "stumble", "redundant_clause", "tangent"}
)
_VALID_CUE_LAYOUTS: Final[frozenset[str]] = frozenset(
    {"broll_fullscreen", "broll_pip", "stat_card", "quote_card"}
)


class StoryEditorError(RuntimeError):
    """Strict fail-stop error raised when semantic multi-cut planning or verification fails."""


def _req_nonneg_int(val: object, name: str) -> int:
    if type(val) is not int or val < 0:
        raise StoryEditorError(f"{name} must be a non-negative int, got {val!r}")
    return val


@dataclass(frozen=True, slots=True)
class WordSpan:
    """One inclusive contiguous range of source transcript word indices forming a story beat."""

    start_word_idx: int
    end_word_idx: int
    role: StoryBeatRole

    def __post_init__(self) -> None:
        s = _req_nonneg_int(self.start_word_idx, "start_word_idx")
        e = _req_nonneg_int(self.end_word_idx, "end_word_idx")
        if e < s:
            raise StoryEditorError(f"WordSpan end_word_idx ({e}) < start_word_idx ({s})")
        if self.role not in _VALID_ROLES:
            raise StoryEditorError(f"Invalid WordSpan.role: {self.role!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_word_idx": self.start_word_idx,
            "end_word_idx": self.end_word_idx,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class DropRange:
    """One inclusive range of word indices to prune inside a kept beat without changing meaning."""

    start_word_idx: int
    end_word_idx: int
    kind: DropKind
    reason: str

    def __post_init__(self) -> None:
        s = _req_nonneg_int(self.start_word_idx, "start_word_idx")
        e = _req_nonneg_int(self.end_word_idx, "end_word_idx")
        if e < s:
            raise StoryEditorError(f"DropRange end_word_idx ({e}) < start_word_idx ({s})")
        if self.kind not in _VALID_DROP_KINDS:
            raise StoryEditorError(f"Invalid DropRange.kind: {self.kind!r}")
        if not isinstance(self.reason, str):
            raise StoryEditorError("DropRange.reason must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_word_idx": self.start_word_idx,
            "end_word_idx": self.end_word_idx,
            "kind": self.kind,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class VisualCue:
    """Content-aware visual insert anchored to a specific source transcript word index."""

    anchor_word_idx: int
    duration_ms: int
    layout: VisualCueLayout
    query_en: str
    stat_hero: str = ""
    label_ckb: str = ""

    def __post_init__(self) -> None:
        _req_nonneg_int(self.anchor_word_idx, "anchor_word_idx")
        if type(self.duration_ms) is not int or not (1_000 <= self.duration_ms <= 6_000):
            raise StoryEditorError(
                f"VisualCue.duration_ms must be in [1000, 6000], got {self.duration_ms!r}"
            )
        if self.layout not in _VALID_CUE_LAYOUTS:
            raise StoryEditorError(f"Invalid VisualCue.layout: {self.layout!r}")
        if not isinstance(self.query_en, str) or not self.query_en.strip():
            raise StoryEditorError("VisualCue.query_en must be a non-empty English visual query")

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_word_idx": self.anchor_word_idx,
            "duration_ms": self.duration_ms,
            "layout": self.layout,
            "query_en": self.query_en,
            "stat_hero": self.stat_hero,
            "label_ckb": self.label_ckb,
        }


@dataclass(frozen=True, slots=True)
class MultiCutStoryRecipe:
    """Complete non-contiguous multi-cut viral reel recipe anchored to exact source word indices."""

    story_id: str
    hook_title_ckb: str
    keep_spans: tuple[WordSpan, ...]
    drop_ranges: tuple[DropRange, ...]
    visual_cues: tuple[VisualCue, ...]
    rationale_ckb: str
    viral_score: float
    cold_open_span: WordSpan | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.story_id, str) or not self.story_id.strip():
            raise StoryEditorError("story_id must be non-empty")
        if not isinstance(self.hook_title_ckb, str) or not self.hook_title_ckb.strip():
            raise StoryEditorError("hook_title_ckb must be non-empty")
        if not self.keep_spans:
            raise StoryEditorError("MultiCutStoryRecipe must contain at least one keep_span")
        if (
            isinstance(self.viral_score, bool)
            or not isinstance(self.viral_score, int | float)
            or not math.isfinite(float(self.viral_score))
        ):
            raise StoryEditorError(f"viral_score must be finite, got {self.viral_score!r}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "story_id": self.story_id,
            "hook_title_ckb": self.hook_title_ckb,
            "keep_spans": [sp.to_dict() for sp in self.keep_spans],
            "drop_ranges": [dr.to_dict() for dr in self.drop_ranges],
            "visual_cues": [vc.to_dict() for vc in self.visual_cues],
            "rationale_ckb": self.rationale_ckb,
            "viral_score": round(float(self.viral_score), 4),
        }
        if self.cold_open_span is not None:
            out["cold_open_span"] = self.cold_open_span.to_dict()
        return out


@dataclass(frozen=True, slots=True)
class MeaningVerificationResult:
    """Audit outcome of the independent meaning-preservation gate (gemini-4-carbon)."""

    approved: bool
    restored_drop_indices: tuple[int, ...]
    reason_ckb: str
    model_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "restored_drop_indices": list(self.restored_drop_indices),
            "reason_ckb": self.reason_ckb,
            "model_id": self.model_id,
        }


@dataclass(frozen=True, slots=True)
class CompiledStoryTimeline:
    """Exact FFmpeg-ready non-contiguous multi-cut timeline compiled from a verified recipe."""

    recipe: MultiCutStoryRecipe
    assembly_spans: tuple[AssemblySpan, ...]
    remapped_words: tuple[Word, ...]
    semantic_cut_times_ms: tuple[tuple[int, int], ...]
    total_duration_ms: int
    original_to_output_word_idx: Mapping[int, int]
    word_idx_to_output_ms: Mapping[int, int]
    dropped_word_count: int
    cold_open_end_ms: int | None = None


STORY_ARCHITECT_SYSTEM_PROMPT: Final[str] = (
    "You are the Lead Viral Story Architect & Senior Kurdish (Sorani, Central Kurdish) Short-Form "
    "Video Editor for HawEdit V11.\n"
    "You receive the ENTIRE word-indexed Sorani podcast transcript (`idx:word`), annotated with "
    "Stage 0 acoustic vocal peaks (`[ENERGY:HIGH]`) and natural pauses (`[PAUSE:1.2s]`).\n"
    "Your job is to craft the MOST FUN, GRIPPING, SELF-CONTAINED viral vertical shorts (28-50 s "
    "each) by assembling TRUE MULTI-CUT stories and ruthlessly pruning dead verbal crutches "
    "WITHOUT changing the speaker's true meaning.\n\n"
    "MANDATORY EDITORIAL RULES:\n"
    "1. COMPLETE, SELF-CONTAINED MULTI-CUT STORIES (NEVER MID-THOUGHT):\n"
    "   - Every story MUST open with an irresistible hook (startling claim, sharp question, bold "
    "contrast, or dramatic peak — NEVER 'ئەوە', 'یانی', 'وەڵا', or dangling mid-sentence words) "
    "and END cleanly on a resolved punchline or complete thought.\n"
    "   - Assemble 2 to 5 non-contiguous `keep_spans` (`hook`, `setup`, `escalation`, `payoff`) "
    "jumping past boring tangents to build a tight, exciting narrative (each beat MUST start and "
    "end at natural clause boundaries).\n"
    "   - Stories MUST cover distinct non-overlapping parts of the episode.\n\n"
    "2. SURGICAL MEANING-PRESERVING PRUNING (`drop_ranges`):\n"
    "   - Mark Kurdish verbal crutches (`یانی`, `یەعنی`, `ئێ`, `ئا`, `وەڵا`, `وەڵڵا`, `ئەها`, "
    "`نازانم چی`, `و نازانم چی`, `بە هەر حاڵ`, `ئیتر`, `ئەوجا`), false starts/stumbles "
    "(e.g. speaker restarts a word or number -> drop the stumble and keep the clean phrase!), "
    "and redundant hedging phrases that add zero information.\n"
    "   - NEVER drop negations (`نە`, `نا`, `نییە`, `نەبوو`, `قەت`, `هیچ`), core subjects, verbs, "
    "or qualifiers that change what the speaker meant.\n\n"
    "3. PUNCHY KURDISH HOOK TITLE (`hook_title_ckb`):\n"
    "   - Write a scroll-stopping 4-6 word Central Kurdish (Sorani, Arabic script ONLY — NEVER "
    "English or Latin) title creating curiosity or tension.\n\n"
    "4. CONTENT-AWARE VISUAL CUES (`visual_cues`):\n"
    "   - Emit 2-4 visual cues per story anchored to exact `anchor_word_idx` values inside your "
    "`keep_spans`:\n"
    "     * `broll_fullscreen` (2200-3200 ms) or `broll_pip` (2200-3000 ms) with a specific "
    "English visual query matching the EXACT topic/object the speaker mentions at that word. "
    "Prefer placing B-roll over a major `drop_ranges` cut to hide jump-cuts cleanly!\n"
    "     * `stat_card` (2600-3200 ms) whenever the speaker states a vivid number, year, or "
    "percentage: fill `stat_hero` and a short 2-4 word Sorani `label_ckb`.\n\n"
    "Return ONLY valid JSON matching the exact schema."
)

STORY_REFINER_SYSTEM_PROMPT: Final[str] = (
    "You are the Line-by-Line Kurdish (Sorani) Master Short-Form Editor for HawEdit V11 (Pass 2).\n"
    "You receive ONE candidate multi-cut viral story (~120-220 words with exact original word "
    "indices `idx:word`). Your laser-focused job is surgical word-level polish WITHOUT changing "
    "the speaker's true meaning or breaking Sorani grammar:\n"
    "1. STUMBLES & FALSE STARTS (`kind: 'stumble'`): Catch every verbal restart or duplicate "
    "slip (e.g. `ئەم پۆست پۆدکاستە` -> drop `پۆست`; `لە لە ساڵی` -> drop first `لە`; "
    "`40 پەنجا زیاتر ساڵ ئێ پەنجا ساڵ` -> drop the stumble and keep the clean statement).\n"
    "2. KURDISH FILLER CRUTCHES (`kind: 'filler'`): Catch every `یانی`, `یەعنی`, `ئێ`, `ئا`, "
    "`وەڵا`, `وەڵڵا`, `ئەها`, `نازانم چی`, `و نازانم چی`, `بە هەر حاڵ`, `وەکو وتم`.\n"
    "3. DILUTING HEDGES (`kind: 'redundant_clause'`): Drop brief rambling filler clauses that "
    "repeat what was just said or add zero factual/emotional value.\n"
    "4. STRICT MEANING GUARD: NEVER drop negations (`نە`, `نا`, `نییە`, `نەبوو`, `قەت`, `هیچ`), "
    "numbers, names, or grammatical connectors needed for fluent Sorani speech.\n"
    "5. COLD-OPEN CLIMAX TEASER (`cold_open_start_word_idx`, `cold_open_end_word_idx`): If a "
    "dramatic 2.0-3.8 s punchline or shocking statement appears later in the story (not at the "
    "very first word), return its exact `start_word_idx` and `end_word_idx` so it plays at t=0 as "
    "a cold-open hook teaser; otherwise return `-1` for both.\n"
    "6. VISUAL CUES (`visual_cues`): Keep or upgrade 2-4 concrete visual cues (`broll_fullscreen` "
    "aligned near major cuts, `broll_pip` on vivid objects, `stat_card` on numbers/years).\n"
    "Return ONLY valid JSON matching the schema."
)

MEANING_VERIFIER_SYSTEM_PROMPT: Final[str] = (
    "You are the Strict Kurdish (Sorani) Editorial Integrity Verifier for HawEdit V10.2.\n"
    "You compare the ORIGINAL spoken Sorani passage against the PRUNED passage after removing "
    "numbered `drop_ranges`.\n"
    "Your ONLY job is to flag any `drop_range` index whose removal:\n"
    "- flips or weakens a negation (`نە`, `نییە`, `نەبوو`, `هیچ`, `بەڵام`),\n"
    "- changes a number, attribution, or factual claim,\n"
    "- breaks Sorani grammar so the spliced sentence sounds nonsensical or choppy.\n"
    "Legitimate removals of fillers (`یانی`, `ئێ`, `وەڵا`, `ئەها`, `نازانم چی`), stumbles, "
    "and truly redundant hedging MUST be APPROVED (do NOT restore pure fillers).\n"
    "Return ONLY valid JSON matching the schema: `approved` (true if zero drops need restoring), "
    "`restore_drop_indices` (0-based indices into `drop_ranges` that must be kept/restored), and "
    "`reason_ckb` (short Sorani explanation)."
)

MULTICUT_EPISODE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "story_id": {"type": "string"},
                    "hook_title_ckb": {"type": "string"},
                    "viral_score": {"type": "number"},
                    "rationale_ckb": {"type": "string"},
                    "keep_spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start_word_idx": {"type": "integer"},
                                "end_word_idx": {"type": "integer"},
                                "role": {
                                    "type": "string",
                                    "enum": ["hook", "setup", "escalation", "payoff"],
                                },
                            },
                            "required": ["start_word_idx", "end_word_idx", "role"],
                        },
                    },
                    "drop_ranges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start_word_idx": {"type": "integer"},
                                "end_word_idx": {"type": "integer"},
                                "kind": {
                                    "type": "string",
                                    "enum": [
                                        "filler",
                                        "stumble",
                                        "redundant_clause",
                                        "tangent",
                                    ],
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["start_word_idx", "end_word_idx", "kind", "reason"],
                        },
                    },
                    "visual_cues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "anchor_word_idx": {"type": "integer"},
                                "duration_ms": {"type": "integer"},
                                "layout": {
                                    "type": "string",
                                    "enum": [
                                        "broll_fullscreen",
                                        "broll_pip",
                                        "stat_card",
                                        "quote_card",
                                    ],
                                },
                                "query_en": {"type": "string"},
                                "stat_hero": {"type": "string"},
                                "label_ckb": {"type": "string"},
                            },
                            "required": ["anchor_word_idx", "duration_ms", "layout", "query_en"],
                        },
                    },
                },
                "required": [
                    "story_id",
                    "hook_title_ckb",
                    "viral_score",
                    "rationale_ckb",
                    "keep_spans",
                    "drop_ranges",
                    "visual_cues",
                ],
            },
        }
    },
    "required": ["stories"],
}

_NOMINATION_FIELDS = ("story_id", "hook_title_ckb", "viral_score", "rationale_ckb", "keep_spans")
_NOMINATION_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "required": ["stories"],
    "properties": {
        "stories": {
            "type": "array",
            "maxItems": 1,
            "items": {
                "type": "object",
                "required": list(_NOMINATION_FIELDS),
                "properties": {
                    key: MULTICUT_EPISODE_SCHEMA["properties"]["stories"]["items"]["properties"][
                        key
                    ]
                    for key in _NOMINATION_FIELDS
                },
            },
        }
    },
}
_NOMINATION_PROMPT = (
    "You edit Sorani podcasts. Nominate the single strongest standalone short in this excerpt. "
    "Choose 2-4 short source spans in spoken order with a hook, enough context "
    "and a resolved payoff. "
    "Preserve names, numbers, negation, attribution and speaker intent. Avoid mid-sentence starts, "
    "greetings, repeats and incomplete endings. Use inclusive word indices. Write a short Sorani "
    "headline and one sentence explaining the choice. Score editorial strength from 0 to 1. "
    "If there is no complete story of the target duration, return an empty stories array."
)


MEANING_CHECK_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "restore_drop_indices": {"type": "array", "items": {"type": "integer"}},
        "reason_ckb": {"type": "string"},
    },
    "required": ["approved", "restore_drop_indices", "reason_ckb"],
}

STORY_REFINER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "hook_title_ckb": {"type": "string"},
        "cold_open_start_word_idx": {"type": "integer"},
        "cold_open_end_word_idx": {"type": "integer"},
        "drop_ranges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_word_idx": {"type": "integer"},
                    "end_word_idx": {"type": "integer"},
                    "kind": {
                        "type": "string",
                        "enum": ["filler", "stumble", "redundant_clause", "tangent"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["start_word_idx", "end_word_idx", "kind", "reason"],
            },
        },
        "visual_cues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "anchor_word_idx": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "layout": {
                        "type": "string",
                        "enum": ["broll_fullscreen", "broll_pip", "stat_card", "quote_card"],
                    },
                    "query_en": {"type": "string"},
                    "stat_hero": {"type": "string"},
                    "label_ckb": {"type": "string"},
                },
                "required": ["anchor_word_idx", "duration_ms", "layout", "query_en"],
            },
        },
    },
    "required": [
        "hook_title_ckb",
        "cold_open_start_word_idx",
        "cold_open_end_word_idx",
        "drop_ranges",
        "visual_cues",
    ],
}


def _make_story_transport(timeout_s: float) -> Transport:
    def _send(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        req_headers = dict(headers)
        if body is not None:
            req_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(
            url,
            data=body,
            headers=req_headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with open_without_redirects(req, timeout=timeout_s) as resp:
                raw = resp.read(MAX_STORY_RESPONSE_BYTES + 1)
                if len(raw) > MAX_STORY_RESPONSE_BYTES:
                    raise StoryEditorError(
                        f"Story editor response from {url} exceeded {MAX_STORY_RESPONSE_BYTES} B"
                    )
                return int(resp.status), raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            try:
                err_raw = exc.read(MAX_STORY_RESPONSE_BYTES + 1)
                detail = err_raw[: _MAX_ERROR_CHARS * 4].decode("utf-8", errors="replace")
            except OSError:
                detail = ""
            return int(exc.code), detail
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, str(exc)

    return _send


def _resolve_gemini_key(explicit: str | None) -> str:
    try:
        key = explicit.strip() if explicit and explicit.strip() else read_credential(GEMINI_API_KEY)
    except (OSError, UnicodeError) as exc:
        raise StoryEditorError(f"Failed to read {GEMINI_API_KEY} credential: {exc}") from exc
    if not key:
        raise StoryEditorError(
            f"Missing {GEMINI_API_KEY} for Gemini 4 Story Architect. "
            "Store it via `python -m hawedit.credentials` or set the env var."
        )
    return key


def _resolve_local_model(base_url: str, explicit_model: str | None, transport: Transport) -> str:
    if explicit_model and explicit_model.strip():
        return explicit_model.strip()
    env_m = os.environ.get(OMNI_MODEL_ENV, "").strip()
    if env_m:
        return env_m
    status, body = transport(f"{base_url.rstrip('/')}/models", None, {})
    if status != 200:
        raise StoryEditorError(
            f"Local LLM server at {base_url} unavailable for Story Architect (HTTP {status}): "
            f"{body[:_MAX_ERROR_CHARS]}"
        )
    try:
        data = json.loads(body)
        models = data.get("data", []) if isinstance(data, Mapping) else []
        for entry in models:
            if not isinstance(entry, Mapping):
                continue
            mid = str(entry.get("id", "")).strip()
            if mid and "embed" not in mid.lower():
                return mid
    except ValueError as exc:
        raise StoryEditorError(f"Malformed /models response from {base_url}: {exc}") from exc
    raise StoryEditorError(f"No non-embedding chat model loaded on local LLM server {base_url}")


def _call_structured_llm(
    *,
    backend: StoryBackend,
    system_prompt: str,
    user_prompt: str,
    schema: Mapping[str, Any],
    schema_name: str,
    model_id: str | None,
    default_gemini_model: str,
    api_key: str | None,
    base_url: str | None,
    transport: Transport | None,
    local_reasoning_effort: str = "none",
    local_max_tokens: int = 4096,
) -> tuple[dict[str, Any], str]:
    if backend == "gemini":
        key = _resolve_gemini_key(api_key)
        resolved_model = model_id.strip() if model_id and model_id.strip() else default_gemini_model
        tx = transport or _make_story_transport(DEFAULT_GEMINI_TIMEOUT_S)
        payload = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                    "temperature": 0.2,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        url = f"{API_ROOT}/models/{resolved_model}:generateContent"
        status, body = tx(url, payload, {"x-goog-api-key": key})
        if status != 200:
            raise StoryEditorError(
                f"Gemini {resolved_model} request failed (HTTP {status}): {body[:_MAX_ERROR_CHARS]}"
            )
        try:
            raw_text = extract_response_text(body)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise StoryEditorError(f"Gemini {resolved_model} returned no content: {exc}") from exc
    elif backend == "local-omni":
        resolved_url = (
            base_url.strip()
            if base_url and base_url.strip()
            else os.environ.get(OMNI_URL_ENV, DEFAULT_OMNI_URL).strip() or DEFAULT_OMNI_URL
        ).rstrip("/")
        tx = transport or _make_story_transport(DEFAULT_OMNI_TIMEOUT_S)
        resolved_model = _resolve_local_model(resolved_url, model_id, tx)
        payload = json.dumps(
            {
                "model": resolved_model,
                "temperature": 0.0,
                "max_tokens": local_max_tokens,
                "reasoning_effort": local_reasoning_effort,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": _openai_strict_schema(schema),
                    },
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        status, body = tx(f"{resolved_url}/chat/completions", payload, {})
        if status in (408, 504) or (status == 0 and "timed out" in body.lower()):
            raise _LocalTimeout(f"Local model {resolved_model} timed out on the request")
        if status == 400 and any(
            marker in body.lower()
            for marker in (
                "exceed_context_size_error",
                "exceeds the available context size",
                "context_length_exceeded",
            )
        ):
            raise _ContextLimit(f"Local model {resolved_model} cannot fit this transcript section")
        if status != 200:
            raise StoryEditorError(
                f"Local LLM {resolved_model} request failed (HTTP {status}): "
                f"{body[:_MAX_ERROR_CHARS]}"
            )
        try:
            parsed_resp = json.loads(body)
            raw_text = str(parsed_resp["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise StoryEditorError(f"Local LLM returned malformed envelope: {exc}") from exc
    else:
        raise StoryEditorError(f"Unsupported story editor backend: {backend!r}")

    cleaned = _strip_json_wrappers(raw_text)
    try:
        parsed_json: object = json.loads(cleaned)
    except ValueError as exc:
        raise StoryEditorError(
            f"{resolved_model} returned malformed JSON: {exc} (snippet={cleaned[:240]!r})"
        ) from exc
    if not isinstance(parsed_json, dict):
        raise StoryEditorError(
            f"{resolved_model} returned {type(parsed_json).__name__}, expected JSON object"
        )
    return parsed_json, resolved_model


def _line_rms(samples: Sequence[int], sr: int, start_ms: int, end_ms: int) -> float:
    i0 = max(0, min(len(samples), int((start_ms * sr) // 1000)))
    i1 = max(i0, min(len(samples), int((end_ms * sr) // 1000)))
    if i1 <= i0:
        return 0.0
    step = max(1, (i1 - i0) // 400)
    sq = 0.0
    cnt = 0
    for i in range(i0, i1, step):
        v = samples[i]
        sq += v * v
        cnt += 1
    return math.sqrt(sq / max(1, cnt))


def _format_indexed_episode_transcript(
    words: Sequence[Word],
    *,
    audio_wav: Path | None = None,
) -> str:
    """Format episode words with indices, pause markers, and Stage 0 WAV acoustic energy peaks."""
    chunks: list[tuple[int, int, list[str], int]] = []
    buf: list[str] = []
    line_start_ms = words[0].start_ms if words else 0
    line_end_ms = words[0].end_ms if words else 0
    for idx, w in enumerate(words):
        gap_ms = (w.start_ms - words[idx - 1].end_ms) if idx > 0 else 0
        if idx > 0 and gap_ms >= 600 and buf:
            chunks.append((line_start_ms, line_end_ms, buf, gap_ms))
            buf = []
            line_start_ms = w.start_ms
        buf.append(f"{idx}:{w.w}")
        line_end_ms = w.end_ms
        if len(buf) >= 22:
            next_gap = (words[idx + 1].start_ms - w.end_ms) if idx + 1 < len(words) else 0
            chunks.append((line_start_ms, line_end_ms, buf, next_gap))
            buf = []
            if idx + 1 < len(words):
                line_start_ms = words[idx + 1].start_ms
    if buf:
        chunks.append((line_start_ms, line_end_ms, buf, 0))

    high_energy_lines: set[int] = set()
    pcm = _load_pcm16_mono(audio_wav) if audio_wav is not None else None
    if pcm is not None and chunks:
        samples, sr = pcm
        energies = [_line_rms(samples, sr, s_ms, e_ms) for s_ms, e_ms, _, _ in chunks]
        nonzero = sorted(e for e in energies if e > 0.0)
        if nonzero:
            median_e = nonzero[len(nonzero) // 2]
            p80_e = nonzero[min(len(nonzero) - 1, int(len(nonzero) * 0.80))]
            thresh = max(p80_e, median_e * 1.30)
            high_energy_lines = {i for i, e in enumerate(energies) if e >= thresh}

    lines: list[str] = []
    for c_idx, (s_ms, _e_ms, toks, gap_after) in enumerate(chunks):
        mm, ss = divmod(s_ms // 1000, 60)
        tag = " [ENERGY:HIGH]" if c_idx in high_energy_lines else ""
        pause = f" [PAUSE:{gap_after / 1000.0:.1f}s]" if gap_after >= 900 else ""
        lines.append(f"({mm:02d}:{ss:02d}){tag} " + " ".join(toks) + pause)
    return "\n".join(lines)


def _estimate_kept_duration_ms(
    words: Sequence[Word],
    keep_spans: Sequence[WordSpan],
    drop_ranges: Sequence[DropRange],
) -> int:
    dropped: set[int] = set()
    for dr in drop_ranges:
        dropped.update(range(dr.start_word_idx, dr.end_word_idx + 1))
    total = 0
    for sp in keep_spans:
        kept_indices = [
            i for i in range(sp.start_word_idx, sp.end_word_idx + 1) if i not in dropped
        ]
        if not kept_indices:
            continue
        # Estimate surviving run durations cleanly.
        run_s = kept_indices[0]
        prev = kept_indices[0]
        for idx in kept_indices[1:]:
            if idx == prev + 1:
                prev = idx
            else:
                total += max(120, words[prev].end_ms - words[run_s].start_ms)
                run_s = prev = idx
        total += max(120, words[prev].end_ms - words[run_s].start_ms)
    return total


def _parse_and_validate_recipes(
    payload: Mapping[str, Any],
    words: Sequence[Word],
    *,
    max_stories: int,
    min_duration_ms: int,
    max_duration_ms: int,
) -> tuple[MultiCutStoryRecipe, ...]:
    raw_stories = payload.get("stories")
    if not isinstance(raw_stories, list):
        raise StoryEditorError("Story Architect returned invalid stories")
    if not raw_stories:
        raise _NoStory("Story Architect returned zero stories")

    n_words = len(words)
    parsed: list[MultiCutStoryRecipe] = []
    for s_idx, item in enumerate(raw_stories):
        if not isinstance(item, Mapping):
            continue
        story_id = str(item.get("story_id") or f"story-{s_idx + 1:02d}").strip()
        hook_title = str(item.get("hook_title_ckb") or "").strip()
        rationale = str(item.get("rationale_ckb") or "").strip()
        try:
            viral_score = float(item.get("viral_score", 0.8))
        except (TypeError, ValueError):
            viral_score = 0.8
        if not hook_title:
            continue

        raw_keeps = item.get("keep_spans")
        if not isinstance(raw_keeps, list) or not raw_keeps:
            continue
        keeps: list[WordSpan] = []
        used_words: set[int] = set()
        for ks in raw_keeps:
            if not isinstance(ks, Mapping):
                continue
            s_w = ks.get("start_word_idx")
            e_w = ks.get("end_word_idx")
            role_raw = str(ks.get("role", "setup")).strip()
            if type(s_w) is not int or type(e_w) is not int:
                continue
            s_clamped = max(0, min(n_words - 1, s_w))
            e_clamped = max(s_clamped, min(n_words - 1, e_w))
            role: StoryBeatRole = role_raw if role_raw in _VALID_ROLES else "setup"  # type: ignore[assignment]
            # Prevent duplicate word indices across beats in the same story.
            if any(wi in used_words for wi in range(s_clamped, e_clamped + 1)):
                continue
            used_words.update(range(s_clamped, e_clamped + 1))
            keeps.append(WordSpan(start_word_idx=s_clamped, end_word_idx=e_clamped, role=role))
        if not keeps:
            continue

        drops: list[DropRange] = []
        raw_drops = item.get("drop_ranges")
        if isinstance(raw_drops, list):
            for dr in raw_drops:
                if not isinstance(dr, Mapping):
                    continue
                ds = dr.get("start_word_idx")
                de = dr.get("end_word_idx")
                kind_raw = str(dr.get("kind", "filler")).strip()
                reason = str(dr.get("reason", "")).strip()
                if type(ds) is not int or type(de) is not int or de < ds:
                    continue
                if not (0 <= ds <= de < n_words):
                    continue
                # Only keep drop ranges that lie inside the selected keep_spans.
                if not all(wi in used_words for wi in range(ds, de + 1)):
                    continue
                kind: DropKind = kind_raw if kind_raw in _VALID_DROP_KINDS else "filler"  # type: ignore[assignment]
                drops.append(
                    DropRange(start_word_idx=ds, end_word_idx=de, kind=kind, reason=reason)
                )

        # Guard: never drop > 45% of words in a story (protects against runaway pruning).
        dropped_set: set[int] = set()
        for dr in drops:
            dropped_set.update(range(dr.start_word_idx, dr.end_word_idx + 1))
        if len(used_words) - len(dropped_set) < 12:
            drops = []
            dropped_set = set()

        est_dur = _estimate_kept_duration_ms(words, keeps, drops)
        if est_dur < max(18_000, int(min_duration_ms * 0.78)) or est_dur > int(
            max_duration_ms * 1.45
        ):
            continue

        cues: list[VisualCue] = []
        raw_cues = item.get("visual_cues")
        if isinstance(raw_cues, list):
            for vc in raw_cues:
                if not isinstance(vc, Mapping):
                    continue
                anchor = vc.get("anchor_word_idx")
                dur = vc.get("duration_ms", 2600)
                layout_raw = str(vc.get("layout", "broll_pip")).strip()
                query_en = str(vc.get("query_en", "")).strip()
                stat_hero = str(vc.get("stat_hero", "")).strip()
                label_ckb = str(vc.get("label_ckb", "")).strip()
                if type(anchor) is not int or anchor not in used_words or anchor in dropped_set:
                    continue
                if not query_en:
                    continue
                dur_int = max(1_500, min(5_000, int(dur) if type(dur) is int else 2_600))
                layout: VisualCueLayout = (
                    layout_raw if layout_raw in _VALID_CUE_LAYOUTS else "broll_pip"  # type: ignore[assignment]
                )
                cues.append(
                    VisualCue(
                        anchor_word_idx=anchor,
                        duration_ms=dur_int,
                        layout=layout,
                        query_en=query_en,
                        stat_hero=stat_hero,
                        label_ckb=label_ckb,
                    )
                )

        cold_open_span: WordSpan | None = None
        raw_co = item.get("cold_open_span")
        if isinstance(raw_co, Mapping):
            co_s = raw_co.get("start_word_idx")
            co_e = raw_co.get("end_word_idx")
            if type(co_s) is int and type(co_e) is int and 0 <= co_s <= co_e < n_words:
                co_dur = words[co_e].end_ms - words[co_s].start_ms
                # Accept punchy 1.4-4.5 s climax teasers that don't trivially repeat beat 0.
                if (
                    1_400 <= co_dur <= 4_500
                    and (co_e - co_s + 1) >= 3
                    and co_s != keeps[0].start_word_idx
                ):
                    cold_open_span = WordSpan(
                        start_word_idx=co_s, end_word_idx=co_e, role="cold_open"
                    )

        parsed.append(
            MultiCutStoryRecipe(
                story_id=story_id,
                hook_title_ckb=hook_title,
                keep_spans=tuple(keeps),
                drop_ranges=tuple(drops),
                visual_cues=tuple(cues[:5]),
                rationale_ckb=rationale,
                viral_score=viral_score,
                cold_open_span=cold_open_span,
            )
        )

    if not parsed:
        raise _NoStory(
            "Story Architect returned no valid stories within duration & word-index bounds"
        )

    return _distinct_recipes(parsed, max_stories)


def _distinct_recipes(
    parsed: list[MultiCutStoryRecipe], max_stories: int
) -> tuple[MultiCutStoryRecipe, ...]:
    parsed.sort(key=lambda r: -r.viral_score)
    selected: list[MultiCutStoryRecipe] = []
    chosen_word_sets: list[set[int]] = []
    for rec in parsed:
        rec_words: set[int] = set()
        for sp in rec.keep_spans:
            rec_words.update(range(sp.start_word_idx, sp.end_word_idx + 1))
        if any(
            len(rec_words & prev) / max(1, min(len(rec_words), len(prev))) > 0.40
            for prev in chosen_word_sets
        ):
            continue
        selected.append(rec)
        chosen_word_sets.append(rec_words)
        if len(selected) >= max_stories:
            break

    return tuple(selected)


class _LocalTimeout(StoryEditorError):
    """A transient local model timeout."""


class _ContextLimit(StoryEditorError):
    """The local provider explicitly rejected the prompt length."""


class _NoStory(StoryEditorError):
    """A window contained no valid nomination."""


def _episode_recipe(recipe: MultiCutStoryRecipe, offset: int) -> MultiCutStoryRecipe:
    def move(span: WordSpan) -> WordSpan:
        return replace(
            span,
            start_word_idx=offset + span.start_word_idx,
            end_word_idx=offset + span.end_word_idx,
        )

    return replace(
        recipe,
        story_id=f"w{offset}-{recipe.story_id}",
        keep_spans=tuple(move(span) for span in recipe.keep_spans),
        cold_open_span=move(recipe.cold_open_span) if recipe.cold_open_span else None,
        drop_ranges=tuple(
            replace(
                r, start_word_idx=offset + r.start_word_idx, end_word_idx=offset + r.end_word_idx
            )
            for r in recipe.drop_ranges
        ),
        visual_cues=tuple(
            replace(c, anchor_word_idx=offset + c.anchor_word_idx) for c in recipe.visual_cues
        ),
    )


def plan_episode_multicut_stories(
    words: Sequence[Word],
    *,
    backend: StoryBackend,
    max_stories: int = 3,
    min_duration_ms: int = 26_000,
    max_duration_ms: int = 55_000,
    audio_wav: Path | None = None,
    model_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    transport: Transport | None = None,
    checkpoint_dir: Path | None = None,
) -> tuple[MultiCutStoryRecipe, ...]:
    """Plan non-contiguous semantic multi-cut stories across an entire episode transcript."""
    if not words:
        raise StoryEditorError("Cannot plan multi-cut stories from an empty transcript")
    if max_stories < 1:
        raise StoryEditorError(f"max_stories must be >= 1, got {max_stories}")

    if backend == "local-omni" and checkpoint_dir is not None:
        base_url = (
            (base_url or os.environ.get(OMNI_URL_ENV) or DEFAULT_OMNI_URL).strip().rstrip("/")
        )
        model_id = _resolve_local_model(
            base_url, model_id, transport or _make_story_transport(DEFAULT_OMNI_TIMEOUT_S)
        )
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def nominate(
        words: Sequence[Word], max_stories: int, compact: bool
    ) -> tuple[MultiCutStoryRecipe, ...]:
        ep_dur_s = (words[-1].end_ms - words[0].start_ms) / 1000.0
        indexed_text = _format_indexed_episode_transcript(words, audio_wav=audio_wav)
        user_prompt = (
            f"Source section duration: {ep_dur_s:.1f} s "
            f"({len(words)} total words, indices 0..{len(words) - 1}).\n"
            f"Return {max_stories} distinct non-overlapping viral multi-cut stories in `stories` "
            "(spread across early, middle, and late sections of the transcript).\n"
            f"Target edited duration per story (AFTER subtracting drop_ranges): "
            f"{min_duration_ms / 1000.0:.0f}s to {max_duration_ms / 1000.0:.0f}s "
            "(aim for 90-165 kept words across 2-4 beats per story).\n\n"
            f"INDEXED SORANI TRANSCRIPT:\n{indexed_text}\n"
        )

        system = _NOMINATION_PROMPT if compact else STORY_ARCHITECT_SYSTEM_PROMPT
        schema = _NOMINATION_SCHEMA if compact else MULTICUT_EPISODE_SCHEMA
        cache_file = None
        if checkpoint_dir is not None and backend == "local-omni":
            signature = json.dumps(
                [
                    base_url,
                    model_id,
                    schema,
                    system,
                    user_prompt,
                    [(w.start_ms, w.end_ms) for w in words],
                ],
                ensure_ascii=False,
            )
            cache_file = checkpoint_dir / (hashlib.sha256(signature.encode()).hexdigest() + ".json")

        def validate(payload: Mapping[str, Any]) -> tuple[MultiCutStoryRecipe, ...]:
            return _parse_and_validate_recipes(
                payload,
                words,
                max_stories=max_stories,
                min_duration_ms=min_duration_ms,
                max_duration_ms=max_duration_ms,
            )

        if cache_file is not None and cache_file.is_file():
            try:
                saved = json.loads(cache_file.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                saved = None
            if isinstance(saved, dict):
                if saved.get("stories") == []:
                    raise _NoStory("No story nominated in this source section")
                try:
                    return validate(saved)
                except StoryEditorError:
                    pass
        payload, _ = _call_structured_llm(
            backend=backend,
            system_prompt=system,
            user_prompt=user_prompt,
            schema=schema,
            schema_name="hawedit_local_nomination" if compact else "hawedit_v11_multicut_episode",
            model_id=model_id,
            default_gemini_model=DEFAULT_STORY_ARCHITECT_MODEL,
            api_key=api_key,
            base_url=base_url,
            transport=transport,
            local_max_tokens=700 if compact else 4096,
        )
        selected = () if payload.get("stories") == [] else validate(payload)
        if cache_file is not None:
            with tempfile.NamedTemporaryFile(dir=cache_file.parent, delete=False) as temp:
                staged = Path(temp.name)
            try:
                staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                staged.replace(cache_file)
            finally:
                staged.unlink(missing_ok=True)
        if not selected:
            raise _NoStory("No story nominated in this source section")
        return selected

    start = 0
    window_size = min(1200, len(words))
    nominations: list[MultiCutStoryRecipe] = []
    while start < len(words):
        end = min(start + window_size, len(words))
        whole_episode = start == 0 and end == len(words)
        try:
            compact = backend == "local-omni" and not whole_episode
            count = 1 if compact else (max_stories if whole_episode else min(3, max_stories))
            local = nominate(words[start:end], count, compact)
            if whole_episode:
                return local
            nominations.extend(_episode_recipe(story, start) for story in local)
        except (_LocalTimeout, _ContextLimit):
            if end - start <= 200:
                raise
            window_size = max(200, (end - start) // 2)
            continue
        except _NoStory:
            if whole_episode:
                raise
        if end == len(words):
            break
        start = end - min(200, window_size // 3)
    if not nominations:
        raise _NoStory("No episode window produced a valid source-grounded story")
    return _distinct_recipes(nominations, max_stories)


_DANGLING_HOOK_WORDS: Final[frozenset[str]] = (
    frozenset(
        {"و", "لە", "بە", "بۆ", "کە", "یا", "یان", "ئەو", "ئەم", "تا", "وەکو", "وەک", "وەکوو"}
    )
    | DANGLING_CONJUNCTIONS_CKB
)
_HOOK_FILLER = frozenset({"یانی", "یەعنی", "ئا", "ئێ", "ها", "ئەها", "وەڵا"})
_HOOK_TERMINAL = ".!?؟؛…"
_HOOK_EDGE = """،,؛;:؟?!."'«»…"""


def _source_quote_hook(proposal: str, words: Sequence[Word]) -> str:
    """Choose a bounded, source-exact headline or omit the title when none qualifies."""

    def breaks_after(index: int) -> bool:
        return words[index].w.rstrip("""'"»""").endswith(tuple(_HOOK_TERMINAL)) or (
            index + 1 < len(words) and words[index + 1].start_ms - words[index].end_ms >= 300
        )

    def terms(phrase: str) -> set[str]:
        return {part.strip(_HOOK_EDGE).casefold() for part in phrase.split()}

    wanted = terms(proposal) - _DANGLING_HOOK_WORDS
    candidates = []
    start = 0
    for end, word in enumerate(words):
        if not breaks_after(end):
            continue
        if 3 <= end - start + 1 <= 12:
            phrase = " ".join(w.w for w in words[start : end + 1])
            tokens = phrase.split()
            first, last = tokens[0].strip(_HOOK_EDGE), tokens[-1].strip(_HOOK_EDGE)
            overlap = len(wanted & terms(phrase))
            if (
                3 <= len(tokens) <= 12
                and len(phrase) <= 76
                and first not in _DANGLING_HOOK_WORDS | _HOOK_FILLER
                and last not in _DANGLING_HOOK_WORDS | _HOOK_FILLER
            ):
                candidates.append((overlap, word.w.endswith(tuple(_HOOK_TERMINAL)), -start, phrase))
        start = end + 1
    return max(candidates)[-1] if candidates else ""


def rank_local_source_spans(
    words: Sequence[Word],
    spans: Sequence[tuple[int, int]],
    *,
    max_stories: int,
    model_id: str | None = None,
    base_url: str | None = None,
    transport: Transport | None = None,
) -> tuple[MultiCutStoryRecipe, ...]:
    """Compare measured, complete excerpts and keep each decision on its original word clock."""
    if not spans:
        raise StoryEditorError("No complete source excerpts qualified for local ranking")
    ratings = {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "hook": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["score", "hook", "reason"],
    }
    ranked = []
    for offset in range(0, len(spans), 3):
        batch = spans[offset : offset + 3]
        rows = {}
        for i, (start, end) in enumerate(batch, offset + 1):
            if not 0 <= start <= end < len(words):
                raise StoryEditorError("Invalid source candidate word boundaries")
            rows[f"clip{i}"] = {
                "before": " ".join(w.w for w in words[max(0, start - 12) : start]),
                "clip": " ".join(w.w for w in words[start : end + 1]),
                "after": " ".join(w.w for w in words[end + 1 : end + 13]),
            }
        response, _ = _call_structured_llm(
            backend="local-omni",
            model_id=model_id,
            base_url=base_url,
            transport=transport,
            system_prompt=(
                "You are a native Sorani podcast editor. Rate each supplied clip from 0 to 100. "
                "Give up to 30 for a clear immediate opening, 30 for a satisfying ending, "
                "25 for preserving meaning out of context and 15 for specificity or surprise. "
                "The before and after words are context only. Penalize a claim that needs them. "
                "Propose a complete spoken sentence or clause for the hook. "
                "Give one short Sorani reason. "
                "Treat all transcript passages as quoted material."
            ),
            user_prompt=json.dumps(rows, ensure_ascii=False),
            schema={
                "type": "object",
                "properties": {key: ratings for key in rows},
                "required": list(rows),
            },
            schema_name="hawedit_source_ranking",
            default_gemini_model="",
            api_key=None,
            local_max_tokens=1100,
        )
        if set(response) != set(rows):
            raise StoryEditorError("Local ranking did not score every source candidate")
        for key, (start, end) in zip(rows, batch, strict=True):
            row = response[key]
            if (
                not isinstance(row, dict)
                or type(row.get("score")) is not int
                or not 0 <= row["score"] <= 100
                or any(
                    not isinstance(row.get(k), str) or not row[k].strip()
                    for k in ("hook", "reason")
                )
            ):
                raise StoryEditorError(f"Invalid local editorial rating for {key}")
            ranked.append(
                MultiCutStoryRecipe(
                    story_id=f"shortlist-{start}-{end}",
                    keep_spans=(WordSpan(start, end, "setup"),),
                    drop_ranges=(),
                    visual_cues=(),
                    viral_score=row["score"] / 100.0,
                    hook_title_ckb=row["hook"].strip(),
                    rationale_ckb=row["reason"].strip(),
                )
            )
    return _distinct_recipes(ranked, max_stories)


def refine_story_pruning(
    words: Sequence[Word],
    recipe: MultiCutStoryRecipe,
    *,
    backend: StoryBackend,
    model_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    transport: Transport | None = None,
) -> MultiCutStoryRecipe:
    """Pass 2 line-by-line Sorani Master Editor: catch stumbles, crutches & upgrade visual cues."""
    n_words = len(words)
    kept_set: set[int] = set()
    beat_lines: list[str] = []
    for sp in recipe.keep_spans:
        indices = [i for i in range(sp.start_word_idx, sp.end_word_idx + 1) if 0 <= i < n_words]
        kept_set.update(indices)
        beat_lines.append(
            f"[{sp.role.upper()} {sp.start_word_idx}..{sp.end_word_idx}] "
            + " ".join(f"{i}:{words[i].w}" for i in indices)
        )
    if not kept_set:
        return recipe

    existing_drops_txt = (
        "\n".join(
            f"- {dr.start_word_idx}..{dr.end_word_idx} ({dr.kind}): "
            + " ".join(words[i].w for i in range(dr.start_word_idx, dr.end_word_idx + 1))
            for dr in recipe.drop_ranges
        )
        if recipe.drop_ranges
        else "none"
    )
    user_prompt = (
        f"Story ID: {recipe.story_id}\n"
        f"Current Kurdish Hook Title: {recipe.hook_title_ckb}\n"
        f"Pass-1 drop_ranges:\n{existing_drops_txt}\n\n"
        "WORD-INDEXED STORY BEATS (inspect EVERY word for stumbles, repeated restarts, Kurdish "
        "verbal crutches, and non-essential hedges; return the COMPLETE final `drop_ranges` and "
        "2-4 concrete `visual_cues` anchored to surviving word indices):\n"
        + "\n".join(beat_lines)
        + "\n"
    )
    payload, _ = _call_structured_llm(
        backend=backend,
        system_prompt=STORY_REFINER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=STORY_REFINER_SCHEMA,
        schema_name="hawedit_v11_story_refiner",
        model_id=model_id,
        default_gemini_model=DEFAULT_STORY_ARCHITECT_MODEL,
        api_key=api_key,
        base_url=base_url,
        transport=transport,
        local_reasoning_effort="none",
    )

    new_drops: list[DropRange] = list(recipe.drop_ranges)
    seen_spans: set[tuple[int, int]] = {(dr.start_word_idx, dr.end_word_idx) for dr in new_drops}
    raw_drops = payload.get("drop_ranges")
    if isinstance(raw_drops, list):
        for dr in raw_drops:
            if not isinstance(dr, Mapping):
                continue
            ds = dr.get("start_word_idx")
            de = dr.get("end_word_idx")
            kind_raw = str(dr.get("kind", "filler")).strip()
            reason = str(dr.get("reason", "")).strip()
            if type(ds) is not int or type(de) is not int or de < ds:
                continue
            if not all(wi in kept_set for wi in range(ds, de + 1)):
                continue
            if (ds, de) in seen_spans:
                continue
            seen_spans.add((ds, de))
            kind: DropKind = kind_raw if kind_raw in _VALID_DROP_KINDS else "filler"  # type: ignore[assignment]
            new_drops.append(
                DropRange(start_word_idx=ds, end_word_idx=de, kind=kind, reason=reason)
            )

    # Guard: never exceed 45% word pruning or drop below 12 surviving words.
    dropped_set: set[int] = set()
    for dr in new_drops:
        dropped_set.update(range(dr.start_word_idx, dr.end_word_idx + 1))
    if len(dropped_set) > int(len(kept_set) * 0.45) or (len(kept_set) - len(dropped_set)) < 12:
        final_drops = recipe.drop_ranges
        dropped_set = set()
        for dr in final_drops:
            dropped_set.update(range(dr.start_word_idx, dr.end_word_idx + 1))
    else:
        final_drops = tuple(sorted(new_drops, key=lambda d: (d.start_word_idx, d.end_word_idx)))

    refined_cues: list[VisualCue] = []
    raw_cues = payload.get("visual_cues")
    if isinstance(raw_cues, list):
        for vc in raw_cues:
            if not isinstance(vc, Mapping):
                continue
            anchor = vc.get("anchor_word_idx")
            dur = vc.get("duration_ms", 2600)
            layout_raw = str(vc.get("layout", "broll_pip")).strip()
            query_en = str(vc.get("query_en", "")).strip()
            stat_hero = str(vc.get("stat_hero", "")).strip()
            label_ckb = str(vc.get("label_ckb", "")).strip()
            if type(anchor) is not int or anchor not in kept_set or anchor in dropped_set:
                continue
            if not query_en:
                continue
            dur_int = max(1_500, min(5_000, int(dur) if type(dur) is int else 2_600))
            layout: VisualCueLayout = (
                layout_raw if layout_raw in _VALID_CUE_LAYOUTS else "broll_pip"  # type: ignore[assignment]
            )
            refined_cues.append(
                VisualCue(
                    anchor_word_idx=anchor,
                    duration_ms=dur_int,
                    layout=layout,
                    query_en=query_en,
                    stat_hero=stat_hero,
                    label_ckb=label_ckb,
                )
            )
    final_cues = (
        tuple(refined_cues[:5])
        if refined_cues
        else tuple(vc for vc in recipe.visual_cues if vc.anchor_word_idx not in dropped_set)
    )
    hook_cand = str(payload.get("hook_title_ckb") or "").strip()
    final_hook = hook_cand if hook_cand and len(hook_cand) >= 4 else recipe.hook_title_ckb
    if recipe.story_id.startswith("shortlist-"):
        final_hook = recipe.hook_title_ckb
    final_cold_open = recipe.cold_open_span
    co_s = payload.get("cold_open_start_word_idx")
    co_e = payload.get("cold_open_end_word_idx")
    if (
        type(co_s) is int
        and type(co_e) is int
        and 0 <= co_s <= co_e < n_words
        and co_s in kept_set
        and co_e in kept_set
        and co_s != recipe.keep_spans[0].start_word_idx
    ):
        co_dur = words[co_e].end_ms - words[co_s].start_ms
        if 1_400 <= co_dur <= 4_500 and (co_e - co_s + 1) >= 3:
            final_cold_open = WordSpan(start_word_idx=co_s, end_word_idx=co_e, role="cold_open")
    return replace(
        recipe,
        hook_title_ckb=final_hook,
        drop_ranges=final_drops,
        visual_cues=final_cues,
        cold_open_span=final_cold_open,
    )


def _render_recipe_texts(
    words: Sequence[Word],
    recipe: MultiCutStoryRecipe,
) -> tuple[str, str]:
    dropped: set[int] = set()
    for dr in recipe.drop_ranges:
        dropped.update(range(dr.start_word_idx, dr.end_word_idx + 1))
    orig_parts: list[str] = []
    edited_parts: list[str] = []
    for sp in recipe.keep_spans:
        beat_orig = [words[i].w for i in range(sp.start_word_idx, sp.end_word_idx + 1)]
        beat_edit = [
            words[i].w for i in range(sp.start_word_idx, sp.end_word_idx + 1) if i not in dropped
        ]
        orig_parts.append(f"[{sp.role.upper()}] " + " ".join(beat_orig))
        edited_parts.append(f"[{sp.role.upper()}] " + " ".join(beat_edit))
    return "\n".join(orig_parts), "\n".join(edited_parts)


def verify_story_meaning_preservation(
    words: Sequence[Word],
    recipe: MultiCutStoryRecipe,
    *,
    backend: StoryBackend,
    model_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    transport: Transport | None = None,
) -> tuple[MultiCutStoryRecipe, MeaningVerificationResult]:
    """Verify pruned DropRanges preserve speaker meaning; surgically restore risky drops."""
    if not recipe.drop_ranges:
        return (
            recipe,
            MeaningVerificationResult(
                approved=True,
                restored_drop_indices=(),
                reason_ckb="هیچ لابردنێک نییە؛ دەقەکە تەواو پارێزراوە.",
                model_id=model_id or DEFAULT_STORY_VERIFIER_MODEL,
            ),
        )

    original_ckb, edited_ckb = _render_recipe_texts(words, recipe)
    drop_lines = "\n".join(
        f"drop[{idx}] ({dr.kind}, words {dr.start_word_idx}..{dr.end_word_idx}): "
        f"{' '.join(words[i].w for i in range(dr.start_word_idx, dr.end_word_idx + 1))} "
        f"(reason: {dr.reason})"
        for idx, dr in enumerate(recipe.drop_ranges)
    )
    user_prompt = (
        f"Story ID: {recipe.story_id}\n\n"
        f"ORIGINAL SPOKEN BEATS:\n{original_ckb}\n\n"
        f"PROPOSED DROP RANGES:\n{drop_lines}\n\n"
        f"PRUNED RESULT:\n{edited_ckb}\n"
    )
    payload, used_model = _call_structured_llm(
        backend=backend,
        system_prompt=MEANING_VERIFIER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=MEANING_CHECK_SCHEMA,
        schema_name="hawedit_v10_meaning_check",
        model_id=model_id,
        default_gemini_model=DEFAULT_STORY_VERIFIER_MODEL,
        api_key=api_key,
        base_url=base_url,
        transport=transport,
        local_reasoning_effort="none",
    )
    approved = bool(payload.get("approved", False))
    raw_restore = payload.get("restore_drop_indices", [])
    restored: list[int] = []
    if isinstance(raw_restore, list):
        for val in raw_restore:
            if type(val) is int and 0 <= val < len(recipe.drop_ranges) and val not in restored:
                restored.append(val)
    reason_ckb = str(payload.get("reason_ckb") or "").strip()

    if not approved and not restored:
        # Strict safety: if verifier rejected without indices, restore non-filler drops.
        restored = [
            idx
            for idx, dr in enumerate(recipe.drop_ranges)
            if dr.kind in ("redundant_clause", "tangent")
        ] or list(range(len(recipe.drop_ranges)))

    restored_set = set(restored)
    surviving_drops = tuple(
        dr for idx, dr in enumerate(recipe.drop_ranges) if idx not in restored_set
    )
    updated_recipe = replace(recipe, drop_ranges=surviving_drops) if restored_set else recipe
    return (
        updated_recipe,
        MeaningVerificationResult(
            approved=not restored_set,
            restored_drop_indices=tuple(sorted(restored_set)),
            reason_ckb=reason_ckb,
            model_id=used_model,
        ),
    )


def _load_pcm16_mono(audio_wav: Path) -> tuple[Sequence[int], int] | None:
    if not audio_wav.is_file():
        return None
    try:
        with wave.open(str(audio_wav), "rb") as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                return None
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, OSError, EOFError):
        return None
    if not raw or sr <= 0:
        return None
    samples: array[int] = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples, sr


def snap_cut_to_rms_valley(
    samples: Sequence[int],
    sample_rate: int,
    target_ms: int,
    *,
    min_ms: int,
    max_ms: int,
    search_radius_ms: int = 40,
    window_ms: int = 10,
    step_ms: int = 5,
) -> int:
    """Snap a cut timestamp into the lowest-energy 10 ms RMS valley within ``±search_radius_ms``."""
    lo = max(min_ms, target_ms - search_radius_ms)
    hi = min(max_ms, target_ms + search_radius_ms)
    if hi <= lo or not samples or sample_rate <= 0:
        return max(min_ms, min(max_ms, target_ms))

    win_n = max(1, (sample_rate * window_ms) // 1000)
    total_n = len(samples)
    best_t = max(lo, min(hi, target_ms))
    best_rms = float("inf")
    t = lo
    while t <= hi:
        center = int((t * sample_rate) // 1000)
        i0 = max(0, center - win_n // 2)
        i1 = min(total_n, i0 + win_n)
        if i1 > i0:
            sq = sum(s * s for s in samples[i0:i1])
            rms = math.sqrt(sq / (i1 - i0))
            if rms < best_rms - 1e-6 or (
                abs(rms - best_rms) <= 1e-6 and abs(t - target_ms) < abs(best_t - target_ms)
            ):
                best_rms = rms
                best_t = t
        t += step_ms
    return best_t


_AUTO_PRUNE_FILLER_SINGLES: Final[frozenset[str]] = frozenset(
    {
        "یانی",
        "یانى",
        "یەعنی",
        "یەعنى",
        "ئێ",
        "ئا",
        "ئەها",
        "وەڵا",
        "وەڵڵا",
        "بەوەڵا",
        "بەوەڵڵا",
        "بەخوا",
    }
)
_AUTO_PRUNE_FILLER_PHRASES: Final[tuple[tuple[str, ...], ...]] = (
    ("نازانم", "چی", "و", "چی"),
    ("و", "نازانم", "چی"),
    ("نازانم", "چی"),
    ("نازانم", "بەخوا"),
    ("بەخوا", "نازانم"),
    ("بە", "هەر", "حاڵ"),
)
# Legitimate Kurdish emphatic reduplications (NEVER prune as stumbles, D-397).
_KURDISH_EMPHATIC_DOUBLES: Final[frozenset[str]] = frozenset(
    {
        "زۆر",
        "کەم",
        "وردە",
        "پەیتا",
        "جوان",
        "هێواش",
        "تاک",
        "جیا",
        "بەش",
        "پۆل",
        "دانە",
        "یەک",
        "دوو",
    }
)
_DANGLING_ENDING_TAILS: Final[frozenset[str]] = DANGLING_CONJUNCTIONS_CKB | frozenset(
    {"و", "بەس", "جا", "هتد", "ئەمانە", "ئەمانەیان"}
)
_STRIP_PUNCT_FILLER: Final[str] = ".,،!؟?؛;:\"'«»()[]"


def _detect_spoken_filler_indices(
    words: Sequence[Word],
    keep_spans: Sequence[WordSpan],
) -> set[int]:
    """Identify pure Kurdish verbal crutches & non-emphatic adjacent word stumbles."""
    found: set[int] = set()
    for sp in keep_spans:
        s_idx, e_idx = sp.start_word_idx, sp.end_word_idx
        if e_idx - s_idx < 4:
            continue
        i = s_idx
        while i <= e_idx:
            # Check multi-word filler phrases first (longest match).
            matched_phrase = False
            for phrase in _AUTO_PRUNE_FILLER_PHRASES:
                plen = len(phrase)
                if i + plen - 1 <= e_idx:
                    window = tuple(
                        words[i + k].w.strip().strip(_STRIP_PUNCT_FILLER) for k in range(plen)
                    )
                    if window == phrase:
                        found.update(range(i, i + plen))
                        i += plen
                        matched_phrase = True
                        break
            if matched_phrase:
                continue
            tok = words[i].w.strip().strip(_STRIP_PUNCT_FILLER)
            if tok in _AUTO_PRUNE_FILLER_SINGLES and tok in KURDISH_FILLER_TOKENS:
                found.add(i)
            elif (
                i + 1 <= e_idx
                and tok
                and tok not in _KURDISH_EMPHATIC_DOUBLES
                and tok == words[i + 1].w.strip().strip(_STRIP_PUNCT_FILLER)
                and (words[i + 1].start_ms - words[i].end_ms) <= 350
            ):
                # Drop first token of immediate non-emphatic spoken stumble (e.g. 'ئەوە ئەوە').
                found.add(i)
            i += 1
    return found


def _split_span_on_pcm_silences(
    span_in: int,
    span_out: int,
    samples: Sequence[int],
    sr: int,
    *,
    max_silence_ms: int = 380,
    keep_edge_ms: int = 55,
    floor_db: float = -34.0,
) -> list[tuple[int, int]]:
    """Split a source span across any measured 16 kHz silent trough >= ``max_silence_ms``."""
    if span_out - span_in <= max_silence_ms or not samples or sr <= 0:
        return [(span_in, span_out)]
    frame_ms = 20
    step_n = max(1, (sr * frame_ms) // 1000)
    floor_rms = 32768.0 * (10.0 ** (floor_db / 20.0))

    silent_runs: list[tuple[int, int]] = []
    run_s = -1
    t = span_in
    while t < span_out:
        i0 = max(0, min(len(samples) - 1, int(t * sr // 1000)))
        i1 = min(len(samples), i0 + step_n)
        rms = math.sqrt(sum(s * s for s in samples[i0:i1]) / max(1, i1 - i0))
        if rms < floor_rms:
            if run_s < 0:
                run_s = t
        else:
            if run_s >= 0 and (t - run_s) >= max_silence_ms:
                silent_runs.append((run_s, t))
            run_s = -1
        t += frame_ms
    if run_s >= 0 and (span_out - run_s) >= max_silence_ms:
        silent_runs.append((run_s, span_out))

    if not silent_runs:
        return [(span_in, span_out)]

    sub_spans: list[tuple[int, int]] = []
    cursor = span_in
    for s_start, s_end in silent_runs:
        cut_out = min(s_end, s_start + keep_edge_ms)
        if cut_out > cursor + 80:
            sub_spans.append((cursor, cut_out))
        cursor = max(cut_out, s_end - keep_edge_ms)
    if span_out > cursor + 80:
        sub_spans.append((cursor, span_out))
    return sub_spans or [(span_in, span_out)]


def compile_story_to_assembly_spans(
    words: Sequence[Word],
    recipe: MultiCutStoryRecipe,
    audio_wav: Path | None = None,
    *,
    clip_pad_before_ms: int = 80,
    clip_pad_after_ms: int = 120,
    min_micro_span_ms: int = 180,
    voice_clearance_ms: int = 25,
    source_duration_ms: int | None = None,
    auto_prune_fillers: bool = True,
    max_internal_pause_ms: int = 380,
    target_pause_ms: int = 120,
) -> CompiledStoryTimeline:
    """Compile a verified ``MultiCutStoryRecipe`` into exact prosody-snapped ``AssemblySpan``s."""
    if not words:
        raise StoryEditorError("Cannot compile multi-cut story with empty words")

    dropped: set[int] = set()
    for dr in recipe.drop_ranges:
        dropped.update(range(dr.start_word_idx, dr.end_word_idx + 1))
    if auto_prune_fillers:
        dropped.update(_detect_spoken_filler_indices(words, recipe.keep_spans))

    pcm = _load_pcm16_mono(audio_wav) if audio_wav is not None else None
    max_source_ms = (
        source_duration_ms
        if source_duration_ms is not None
        else max(w.end_ms for w in words) + clip_pad_after_ms
    )

    # Tighten CTC-smeared silence edges against 16 kHz PCM so interior dead air is exposed.
    eff_src_words = list(words)
    if pcm is not None:
        samples, sr = pcm
        floor_rms = 32768.0 * (10.0 ** (-35.0 / 20.0))
        step_n = max(1, (sr * 20) // 1000)

        def _win_rms(ms: int) -> float:
            i0 = max(0, min(len(samples) - 1, int(ms * sr // 1000)))
            i1 = min(len(samples), i0 + step_n)
            if i1 <= i0:
                return 0.0
            sq = sum(s * s for s in samples[i0:i1])
            return math.sqrt(sq / (i1 - i0))

        spans_to_tighten = (
            (recipe.cold_open_span, *recipe.keep_spans)
            if recipe.cold_open_span is not None
            else recipe.keep_spans
        )
        for sp in spans_to_tighten:
            for idx in range(sp.start_word_idx, sp.end_word_idx + 1):
                if idx in dropped:
                    continue
                w = eff_src_words[idx]
                if w.end_ms - w.start_ms < 450:
                    continue
                t = w.start_ms
                first_voiced: int | None = None
                last_voiced: int | None = None
                while t < w.end_ms:
                    if _win_rms(t) >= floor_rms:
                        if first_voiced is None:
                            first_voiced = t
                        last_voiced = t + 20
                    t += 20
                if first_voiced is not None and last_voiced is not None:
                    new_s = (
                        max(w.start_ms, first_voiced - 25)
                        if (first_voiced - w.start_ms) >= 180
                        else w.start_ms
                    )
                    new_e = (
                        min(w.end_ms, last_voiced + 35)
                        if (w.end_ms - last_voiced) >= 180
                        else w.end_ms
                    )
                    if new_e - new_s >= 60:
                        eff_src_words[idx] = Word(w=w.w, start_ms=new_s, end_ms=new_e, conf=w.conf)

    # Collect ordered contiguous surviving word runs, prepending any cold_open_span teaser at t=0.
    raw_runs: list[tuple[list[int], StoryBeatRole]] = []
    if recipe.cold_open_span is not None:
        co = recipe.cold_open_span
        co_indices = [
            idx
            for idx in range(co.start_word_idx, co.end_word_idx + 1)
            if 0 <= idx < len(eff_src_words) and idx not in dropped
        ]
        if co_indices:
            raw_runs.append((co_indices, "cold_open"))
    dropped_word_count = 0
    for sp in recipe.keep_spans:
        cur: list[int] = []
        for idx in range(sp.start_word_idx, sp.end_word_idx + 1):
            if idx in dropped:
                dropped_word_count += 1
                if cur:
                    raw_runs.append((cur, sp.role))
                    cur = []
            else:
                if (
                    cur
                    and max_internal_pause_ms > 0
                    and (eff_src_words[idx].start_ms - eff_src_words[cur[-1]].end_ms)
                    >= max_internal_pause_ms
                ):
                    raw_runs.append((cur, sp.role))
                    cur = [idx]
                else:
                    cur.append(idx)
        if cur:
            raw_runs.append((cur, sp.role))

    if not raw_runs:
        raise StoryEditorError(f"Story {recipe.story_id!r} has zero surviving words after drops")

    # Never terminate a reel mid-thought on a dangling Kurdish conjunction/tail.
    while raw_runs and len(raw_runs[-1][0]) > 1:
        last_tok = eff_src_words[raw_runs[-1][0][-1]].w.strip().strip(_STRIP_PUNCT_FILLER)
        if last_tok in _DANGLING_ENDING_TAILS:
            raw_runs[-1][0].pop()
            dropped_word_count += 1
        else:
            break

    assembly_spans: list[AssemblySpan] = []
    remapped_words: list[Word] = []
    semantic_cuts: list[tuple[int, int]] = []
    orig_to_out_idx: dict[int, int] = {}
    orig_to_out_ms: dict[int, int] = {}
    out_cursor_ms = 0
    half_pause_pad = max(voice_clearance_ms, target_pause_ms // 2)

    for run_pos, (run_indices, role) in enumerate(raw_runs):
        first_idx = run_indices[0]
        last_idx = run_indices[-1]
        first_w = eff_src_words[first_idx]
        last_w = eff_src_words[last_idx]

        # Compute safe non-overlapping audio bounds around the run without bleeding into neighbors.
        if run_pos == 0:
            raw_in = max(0, first_w.start_ms - clip_pad_before_ms)
            min_in = max(0, first_w.start_ms - clip_pad_before_ms)
            max_in = first_w.start_ms
        else:
            prev_end = eff_src_words[first_idx - 1].end_ms if first_idx > 0 else 0
            gap_before = max(0, first_w.start_ms - prev_end)
            lead = min(half_pause_pad, gap_before // 2) if gap_before > 0 else 0
            raw_in = max(0, first_w.start_ms - lead)
            min_in = max(prev_end, first_w.start_ms - min(half_pause_pad, gap_before))
            max_in = first_w.start_ms

        if run_pos == len(raw_runs) - 1:
            raw_out = min(max_source_ms, last_w.end_ms + clip_pad_after_ms)
            min_out = last_w.end_ms
            max_out = min(max_source_ms, last_w.end_ms + clip_pad_after_ms)
        else:
            next_start = (
                eff_src_words[last_idx + 1].start_ms
                if last_idx + 1 < len(eff_src_words)
                else max_source_ms
            )
            gap_after = max(0, next_start - last_w.end_ms)
            tail = min(half_pause_pad, gap_after // 2) if gap_after > 0 else 0
            raw_out = min(max_source_ms, last_w.end_ms + tail)
            min_out = last_w.end_ms
            max_out = min(max_source_ms, next_start, last_w.end_ms + min(half_pause_pad, gap_after))

        if pcm is not None:
            samples, sr = pcm
            span_in = snap_cut_to_rms_valley(samples, sr, raw_in, min_ms=min_in, max_ms=max_in)
            span_out = snap_cut_to_rms_valley(samples, sr, raw_out, min_ms=min_out, max_ms=max_out)
        else:
            span_in, span_out = raw_in, raw_out

        # Guarantee every kept word fits strictly inside [span_in, span_out].
        span_in = min(span_in, first_w.start_ms)
        span_out = max(span_out, last_w.end_ms)
        span_dur = span_out - span_in

        # Skip ultra-tiny orphan micro-fragments (< min_micro_span_ms) when multiple runs exist.
        if span_dur < min_micro_span_ms and len(raw_runs) > 1 and len(run_indices) == 1:
            continue

        # Split across any real 16 kHz silent trough >= max_internal_pause_ms (including troughs
        # trapped inside smeared single words) so forensic grill long_silences stays strictly 0.
        sub_windows = (
            _split_span_on_pcm_silences(
                span_in,
                span_out,
                pcm[0],
                pcm[1],
                max_silence_ms=max_internal_pause_ms,
                keep_edge_ms=max(40, target_pause_ms // 2),
            )
            if pcm is not None and max_internal_pause_ms > 0
            else [(span_in, span_out)]
        )

        is_reordered_hook = role == "cold_open" or (
            role == "hook"
            and run_pos == 0
            and len(recipe.keep_spans) > 1
            and recipe.keep_spans[0].start_word_idx > recipe.keep_spans[1].start_word_idx
        )
        span_role: Literal["body", "cold_open"] = "cold_open" if is_reordered_hook else "body"

        # Assign each source word in run_indices to the SINGLE sub-window with the largest
        # overlap so splitting across a CTC-smeared silence trough NEVER duplicates a word.
        assigned_per_sub: list[list[int]] = [[] for _ in sub_windows]
        for src_i in run_indices:
            w = eff_src_words[src_i]
            best_sub = -1
            best_ov = 0
            for s_idx, (sub_in, sub_out) in enumerate(sub_windows):
                ov = min(sub_out, w.end_ms) - max(sub_in, w.start_ms)
                if ov > best_ov:
                    best_ov = ov
                    best_sub = s_idx
            if best_sub >= 0:
                assigned_per_sub[best_sub].append(src_i)

        for (sub_in, sub_out), sub_word_indices in zip(sub_windows, assigned_per_sub, strict=True):
            sub_dur = sub_out - sub_in
            if sub_dur <= 0 or not sub_word_indices:
                continue
            if assembly_spans:
                prev_sp = assembly_spans[-1]
                removed_ms = abs(sub_in - prev_sp.source_out_ms)
                if removed_ms >= 250 or sub_in < prev_sp.source_out_ms:
                    semantic_cuts.append((out_cursor_ms, max(removed_ms, 250)))

            sub_words_src = tuple(
                Word(
                    w=eff_src_words[i].w,
                    start_ms=max(sub_in, eff_src_words[i].start_ms),
                    end_ms=min(sub_out, eff_src_words[i].end_ms),
                    conf=eff_src_words[i].conf,
                )
                for i in sub_word_indices
                if min(sub_out, eff_src_words[i].end_ms) > max(sub_in, eff_src_words[i].start_ms)
            )
            if not sub_words_src:
                continue
            assembly_spans.append(
                AssemblySpan(
                    span_index=len(assembly_spans),
                    source_in_ms=sub_in,
                    source_out_ms=sub_out,
                    duration_ms=sub_dur,
                    sentences=(Sentence(words=sub_words_src, complete=True),),
                    role=span_role,
                )
            )

            for src_i in sub_word_indices:
                w = eff_src_words[src_i]
                ws = out_cursor_ms + max(0, w.start_ms - sub_in)
                we = out_cursor_ms + min(sub_dur, w.end_ms - sub_in)
                if we <= ws:
                    continue
                if span_role != "cold_open" or src_i not in orig_to_out_idx:
                    orig_to_out_idx[src_i] = len(remapped_words)
                    orig_to_out_ms[src_i] = ws
                remapped_words.append(Word(w=w.w, start_ms=ws, end_ms=we, conf=w.conf))

            out_cursor_ms += sub_dur

    # Never leave a tiny < 900 ms trailing fragment after a jump-cut at the very end of the
    # reel (prevents jarring trailing cuts in the final 0.80 s).
    while len(assembly_spans) >= 2 and assembly_spans[-1].duration_ms < 900:
        dropped_tail = assembly_spans.pop()
        out_cursor_ms -= dropped_tail.duration_ms
        remapped_words = [w for w in remapped_words if w.end_ms <= out_cursor_ms]
        semantic_cuts = [sc for sc in semantic_cuts if sc[0] < out_cursor_ms]

    if not assembly_spans or not remapped_words:
        raise StoryEditorError(f"Story {recipe.story_id!r} compiled to zero assembly spans")

    cold_open_end_ms: int | None = None
    co_acc = 0
    for a_sp in assembly_spans:
        if a_sp.role == "cold_open":
            co_acc += a_sp.duration_ms
        else:
            if co_acc > 0:
                cold_open_end_ms = co_acc
            break

    return CompiledStoryTimeline(
        recipe=recipe,
        assembly_spans=tuple(assembly_spans),
        remapped_words=tuple(remapped_words),
        semantic_cut_times_ms=tuple(semantic_cuts),
        total_duration_ms=out_cursor_ms,
        original_to_output_word_idx=orig_to_out_idx,
        word_idx_to_output_ms=orig_to_out_ms,
        dropped_word_count=dropped_word_count,
        cold_open_end_ms=cold_open_end_ms,
    )
