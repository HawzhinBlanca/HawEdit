"""HawEdit V9 one-command full-episode arc discovery & multi-reel compiler (D-389, D-390).

Combines Stage 0/1 transcript acquisition (explicit ``--transcript`` JSON or WSL OmniASR),
deterministic local acoustic+Kurdish arc discovery (or Gemini Path A discovery), per-reel
``compile_v8_clip(...)`` compilation, complete ``ClientDeliveryPack`` publication, and
episode-level ``episode.v8.json`` + ``client-review.html`` generation with strict fail-stop.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from hawedit.atomic_fs import write_text_atomic
from hawedit.audio_signals import SentenceAudioMetrics, analyze_sentence_audio
from hawedit.captions import find_ffmpeg
from hawedit.ingest import extract_audio, ingest, probe_duration_ms
from hawedit.normalize import normalize_sorani
from hawedit.sentences import DANGLING_CONJUNCTIONS_CKB, Sentence, segment_sentences
from hawedit.transcripts import NormalizedTranscript, TranscriptStore, Word
from hawedit.v8.compiler import (
    DirectorBackend,
    ReelQualityError,
    SubtitleEngine,
    V8CompileConfig,
    V8CompileError,
    V8CompileResult,
    compile_v8_clip,
    load_transcript_words,
)
from hawedit.v8.delivery_pack import (
    ClientDeliveryPack,
    DeliveryPackError,
    verify_client_pack_complete,
    write_client_delivery_pack,
    write_client_review_html,
)
from hawedit.v8.story_editor import (
    StoryEditorError,
    compile_story_to_assembly_spans,
    plan_episode_multicut_stories,
    refine_story_pruning,
    verify_story_meaning_preservation,
)

__all__ = [
    "V8EpisodeClipItem",
    "V8EpisodeConfig",
    "V8EpisodeError",
    "V8EpisodeResult",
    "compile_v8_episode",
    "discover_viral_arcs_offline",
]

_DIRECTOR_BACKENDS: Final[frozenset[str]] = frozenset({"gemini", "local-omni", "offline"})
_SUBTITLE_ENGINES: Final[frozenset[str]] = frozenset({"skia", "libass"})
_HEX_COLOR_RE: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DIGIT_RE: Final[re.Pattern[str]] = re.compile(r"[0-9\u0660-\u0669\u06F0-\u06F9]+")
_PUNCT_STRIP: Final[str] = ".,،!؟?؛;:\"'«»()[]{}-—–…"

# Kurdish Sorani hook-opening & narrative heuristics for deterministic offline discovery.
_QUESTION_WORDS_CKB: Final[frozenset[str]] = frozenset(
    {"ئایا", "بۆچی", "چۆن", "کێ", "چی", "کەی", "لەکوێ", "چەند", "کام", "کێشە", "چییە"}
)
_CONTRAST_HOOK_MARKERS_CKB: Final[tuple[str, ...]] = (
    "لە ڕاستیدا",
    "ڕاستییەکەی",
    "بە پێچەوانەوە",
    "بەڵام لە ڕاستیدا",
    "خەڵک وا دەزانێت",
    "هەڵەیە",
    "نەخێر",
    "سەیرە",
    "نهێنی",
    "گرنگترین",
    "سەرسوڕهێنەر",
    "مەترسی",
    "دەرکەوت",
    "بەڕاستی",
    "یەکەم جار",
    "هەرگیز",
)
_NUMBER_WORDS_CKB: Final[frozenset[str]] = frozenset(
    {
        "سەد",
        "هەزار",
        "ملیۆن",
        "ملیار",
        "پەنجا",
        "بیست",
        "سی",
        "چل",
        "دە",
        "سێ",
        "پێنج",
        "حەوت",
        "نەوەد",
        "لەسەدا",
        "دۆلار",
        "ساڵ",
    }
)
_PAYOFF_MARKERS_CKB: Final[tuple[str, ...]] = (
    "کەواتە",
    "بۆیە",
    "لە ئەنجامدا",
    "ئەنجامەکەی",
    "ئەنجام",
    "دەرکەوت",
    "ڕاستییەکەی",
    "واتە",
    "گرنگە",
    "تەواو",
    "دەبێت",
)
# Dependent pronouns & continuation words that make weak cold starts without prior context.
_UNRESOLVED_OPENERS_CKB: Final[frozenset[str]] = frozenset(
    {
        "ئەوە",
        "ئەمە",
        "ئەوانە",
        "ئەویش",
        "ئەمانە",
        "لەبەرئەوە",
        "لەبەرئەوەی",
        "بۆیە",
        "کەواتە",
        "چونکە",
        "چونكە",
        "وە",
        "یان",
        "کە",
        "كە",
        "هەروەها",
        "ئینجا",
        "دواتر",
        "پاشان",
        "بەڵێ",
        "ئا",
        "ئێ",
        "هم",
        "جا",
    }
)


class V8EpisodeError(V8CompileError):
    """Raised on any strict fail-stop violation during V8/V9 episode discovery or batch compile."""


@dataclass(frozen=True, slots=True)
class V8EpisodeConfig:
    """Explicit configuration for full-episode V8/V9 multi-reel production."""

    director: DirectorBackend = "offline"
    sub_engine: SubtitleEngine = "skia"
    max_clips: int = 3
    min_duration_ms: int = 28_000
    max_duration_ms: int = 68_000
    min_separation_ms: int = 30_000
    condense: bool = False
    cold_open: bool = False
    fps: float = 25.0
    encoder: str = "h264_nvenc"
    cinema_grade: bool = True
    enable_critique: bool = True
    enable_asd: bool = True
    enable_grill: bool = True
    silence_threshold_ms: int = 420
    silence_target_gap_ms: int = 140
    excise_fillers: bool = True
    progress_bar: bool = True
    keep_overlay: bool = False
    style_preset: str = "viral_gold"
    brand_accent_hex: str | None = None
    speaker_name_ckb: str | None = None
    speaker_role_ckb: str | None = None
    end_card_title_ckb: str | None = None
    end_card_subtitle_ckb: str | None = None
    end_card_handle: str | None = None
    director_model: str | None = None
    omni_url: str | None = None
    local_modality: str | None = None
    asd_onnx_path: Path | None = None
    fonts_dir: Path | None = None
    ffmpeg: Path | None = None
    omni_asr_runtime: str = "auto"
    wsl_distro: str | None = None
    story_mode: Literal["auto", "semantic-multicut", "legacy"] = "auto"
    subtitle_languages: tuple[str, ...] = ()
    dub_languages: tuple[str, ...] = ()
    translation_model: str | None = None
    allow_web_stock: bool = False
    enable_broll: bool = True
    broll_dir: Path | None = None
    enable_banter_split: bool = True
    music_mood: Literal["none", "curious", "cinematic", "energetic"] = "none"
    overgenerate_candidates: bool = True
    enable_local_vlm: bool = True

    def __post_init__(self) -> None:
        if self.director not in _DIRECTOR_BACKENDS:
            raise V8EpisodeError(f"Unsupported director backend: {self.director!r}")
        if self.sub_engine not in _SUBTITLE_ENGINES:
            raise V8EpisodeError(f"Unsupported sub_engine: {self.sub_engine!r}")
        if isinstance(self.max_clips, bool) or self.max_clips < 1:
            raise V8EpisodeError(f"max_clips must be >= 1, got {self.max_clips!r}")
        if self.min_duration_ms <= 0 or self.max_duration_ms < self.min_duration_ms:
            raise V8EpisodeError(
                f"Invalid duration bounds [{self.min_duration_ms}, {self.max_duration_ms}] ms"
            )
        if self.min_separation_ms < 0:
            raise V8EpisodeError(f"min_separation_ms must be >= 0, got {self.min_separation_ms!r}")
        if not math.isfinite(self.fps) or self.fps <= 0.0:
            raise V8EpisodeError(f"fps must be positive finite, got {self.fps!r}")
        if not self.encoder.strip():
            raise V8EpisodeError("encoder must be non-empty")
        if self.silence_threshold_ms < 0 or self.silence_target_gap_ms < 0:
            raise V8EpisodeError("silence thresholds must be non-negative")
        if not self.style_preset.strip():
            raise V8EpisodeError("style_preset must be non-empty")
        if (
            self.brand_accent_hex is not None
            and _HEX_COLOR_RE.fullmatch(self.brand_accent_hex) is None
        ):
            raise V8EpisodeError(
                f"brand_accent_hex must be #RRGGBB hex, got {self.brand_accent_hex!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "director": self.director,
            "sub_engine": self.sub_engine,
            "max_clips": self.max_clips,
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "min_separation_ms": self.min_separation_ms,
            "condense": self.condense,
            "cold_open": self.cold_open,
            "fps": self.fps,
            "encoder": self.encoder,
            "cinema_grade": self.cinema_grade,
            "enable_critique": self.enable_critique,
            "enable_asd": self.enable_asd,
            "enable_grill": self.enable_grill,
            "silence_threshold_ms": self.silence_threshold_ms,
            "silence_target_gap_ms": self.silence_target_gap_ms,
            "excise_fillers": self.excise_fillers,
            "progress_bar": self.progress_bar,
            "keep_overlay": self.keep_overlay,
            "style_preset": self.style_preset,
            "brand_accent_hex": self.brand_accent_hex,
            "speaker_name_ckb": self.speaker_name_ckb,
            "speaker_role_ckb": self.speaker_role_ckb,
            "subtitle_languages": self.subtitle_languages,
            "dub_languages": self.dub_languages,
            "allow_web_stock": self.allow_web_stock,
            "end_card_title_ckb": self.end_card_title_ckb,
            "end_card_handle": self.end_card_handle,
            "director_model": self.director_model,
            "omni_url": self.omni_url,
        }


@dataclass(frozen=True, slots=True)
class V8EpisodeClipItem:
    """One compiled reel & verified client delivery pack within an episode batch."""

    rank: int
    clip_id: str
    sentence_indices: tuple[int, ...]
    clip_in_ms: int
    clip_out_ms: int
    discovery_score: float
    discovery_reason: str
    compile_result: V8CompileResult
    delivery_pack: ClientDeliveryPack
    wall_time_s: float

    @property
    def grill_passed(self) -> bool | None:
        return self.delivery_pack.grill_passed

    @property
    def grill_summary(self) -> str:
        return self.delivery_pack.grill_summary

    @property
    def hook_title_ckb(self) -> str:
        return self.delivery_pack.hook_title_ckb

    @property
    def duration_s(self) -> float:
        return round(self.delivery_pack.duration_ms / 1000.0, 3)

    @property
    def face_share(self) -> float:
        return self.delivery_pack.face_share

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "clip_id": self.clip_id,
            "sentence_indices": list(self.sentence_indices),
            "clip_in_ms": self.clip_in_ms,
            "clip_out_ms": self.clip_out_ms,
            "discovery_score": self.discovery_score,
            "discovery_reason": self.discovery_reason,
            "grill_passed": self.grill_passed,
            "grill_summary": self.grill_summary,
            "hook_title_ckb": self.hook_title_ckb,
            "duration_s": self.duration_s,
            "face_share": self.face_share,
            "wall_time_s": round(self.wall_time_s, 3),
            "delivery_pack": self.delivery_pack.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class V8EpisodeResult:
    """Immutable audit manifest of a full-episode multi-reel production run."""

    media_id: str
    source_mp4: Path
    out_dir: Path
    transcript_path: Path | None
    director: DirectorBackend
    clips: tuple[V8EpisodeClipItem, ...]
    episode_json_path: Path
    review_html_path: Path
    total_wall_s: float
    all_grills_passed: bool
    quarantined: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "source_mp4": str(self.source_mp4),
            "out_dir": str(self.out_dir),
            "transcript_path": str(self.transcript_path) if self.transcript_path else None,
            "director": self.director,
            "clip_count": len(self.clips),
            "quarantined_count": len(self.quarantined),
            "all_grills_passed": self.all_grills_passed,
            "total_wall_s": round(self.total_wall_s, 3),
            "episode_json_path": str(self.episode_json_path),
            "review_html_path": str(self.review_html_path),
            "clips": [c.to_dict() for c in self.clips],
            "quarantined": list(self.quarantined),
        }


def _clean_token(token: str) -> str:
    return token.strip().strip(_PUNCT_STRIP)


def _ends_with_dangling(sentence: Sentence) -> bool:
    if not sentence.words:
        return True
    last = _clean_token(sentence.words[-1].w)
    if last in DANGLING_CONJUNCTIONS_CKB:
        return True
    if len(sentence.words) >= 2:
        pair = f"{_clean_token(sentence.words[-2].w)} {last}"
        if pair in ("لەبەر ئەوەی", "لەبەر ئەوە", "هەر بۆیە"):
            return True
    return False


def _subsegment_long_utterances(
    sentences: Sequence[Sentence],
    *,
    max_clause_ms: int = 28_000,
    min_clause_ms: int = 6_000,
    min_pause_ms: int = 220,
) -> tuple[Sentence, ...]:
    """Recursively split giant unpunctuated run-on ASR utterances at breath pauses.

    Fast-speaking unpunctuated Kurdish podcasts often run 75-250 s without a >= 600 ms
    pause; splitting only utterances > ``max_clause_ms`` at their longest non-dangling
    interior pause >= ``min_pause_ms`` unlocks full-episode viral arc discovery and
    meaningful ``--condense`` story cuts without touching normal-length sentences.
    """
    out: list[Sentence] = []

    def _split_one(sent: Sentence) -> None:
        words = sent.words
        dur_ms = sent.end_ms - sent.start_ms
        if len(words) < 8 or dur_ms <= max_clause_ms:
            out.append(sent)
            return

        best_idx = -1
        best_gap = -1
        for i in range(len(words) - 1):
            gap = words[i + 1].start_ms - words[i].end_ms
            if gap < min_pause_ms:
                continue
            left_dur = words[i].end_ms - words[0].start_ms
            right_dur = words[-1].end_ms - words[i + 1].start_ms
            if left_dur < min_clause_ms or right_dur < min_clause_ms:
                continue
            if _clean_token(words[i].w) in DANGLING_CONJUNCTIONS_CKB:
                continue
            if gap > best_gap:
                best_gap = gap
                best_idx = i

        if best_idx < 0:
            out.append(sent)
            return

        _split_one(Sentence(words=words[: best_idx + 1], complete=True))
        _split_one(Sentence(words=words[best_idx + 1 :], complete=sent.complete))

    for sentence in sentences:
        _split_one(sentence)
    return tuple(out)


def _score_span_heuristics(
    sentences: Sequence[Sentence],
    metrics: Sequence[SentenceAudioMetrics],
    start_idx: int,
    end_idx: int,
    *,
    min_duration_ms: int,
    max_duration_ms: int,
) -> tuple[float, str]:
    span_sents = sentences[start_idx : end_idx + 1]
    span_metrics = metrics[start_idx : end_idx + 1]
    span_ms = span_sents[-1].end_ms - span_sents[0].start_ms
    span_s = max(1.0, span_ms / 1000.0)

    # 1. Real Stage 0 WAV acoustic energy, variance, and vocal bursts.
    n = len(span_metrics)
    mean_excite = sum(m.excitement_score for m in span_metrics) / n
    peak_excite = max(m.excitement_score for m in span_metrics)
    total_bursts = sum(m.peak_burst_count for m in span_metrics)
    burst_density = min(1.0, total_bursts / max(2.5, span_s / 8.0))
    if n >= 2:
        mean_z = sum(m.rms_z for m in span_metrics) / n
        var_z = sum((m.rms_z - mean_z) ** 2 for m in span_metrics) / n
        energy_variance = min(1.0, math.sqrt(var_z) / 1.4)
    else:
        energy_variance = min(0.55, 0.55 * burst_density)

    acoustic_score = (
        0.30 * mean_excite + 0.16 * energy_variance + 0.14 * burst_density + 0.10 * peak_excite
    )

    # 2. Kurdish hook-opening & narrative completeness heuristics.
    opening = span_sents[0]
    opening_text = opening.text.strip()
    opening_tokens = [_clean_token(w.w) for w in opening.words[:8] if _clean_token(w.w)]
    first_tok = opening_tokens[0] if opening_tokens else ""
    first_two = " ".join(opening_tokens[:2])

    tags: list[str] = []
    hook_bonus = 0.0

    is_question = (
        "؟" in opening_text
        or "?" in opening_text
        or any(tok in _QUESTION_WORDS_CKB for tok in opening_tokens[:6])
    )
    if is_question:
        hook_bonus += 0.18
        tags.append("question-hook")

    opening_window = " ".join(opening_tokens)
    has_contrast = any(m in opening_window for m in _CONTRAST_HOOK_MARKERS_CKB)
    if has_contrast:
        hook_bonus += 0.14
        tags.append("contrast-hook")

    span_text = " ".join(s.text for s in span_sents)
    has_numbers = bool(_DIGIT_RE.search(span_text)) or any(
        _clean_token(w.w) in _NUMBER_WORDS_CKB for s in span_sents for w in s.words
    )
    if has_numbers:
        hook_bonus += 0.10
        tags.append("concrete-numbers")

    if span_metrics[0].pause_before_ms >= 600:
        hook_bonus += 0.06
        tags.append("topic-reset")

    second_half_start = max(0, n // 2)
    second_half_text = " ".join(s.text for s in span_sents[second_half_start:])
    if any(p in second_half_text for p in _PAYOFF_MARKERS_CKB):
        hook_bonus += 0.07
        tags.append("payoff-arc")

    # Penalize unresolved pronouns or continuation conjunctions at clip start.
    if first_tok in _UNRESOLVED_OPENERS_CKB or first_two in ("لەبەر ئەوە", "لەبەر ئەوەی"):
        hook_bonus -= 0.24
        tags.append("unresolved-opener")
    elif first_tok == "بەڵام" and not has_contrast:
        hook_bonus -= 0.08
        tags.append("mid-argument-opener")

    # 3. Duration sweet-spot shaping (~45 s viral target) & healthy speech density.
    target_ms = min(max_duration_ms, max(min_duration_ms, 45_000))
    half_win = max(15_000.0, (max_duration_ms - min_duration_ms) / 2.0)
    dur_bonus = 0.08 * max(0.0, 1.0 - abs(span_ms - target_ms) / half_win)

    total_words = sum(len(s.words) for s in span_sents)
    wps = total_words / span_s
    if 1.8 <= wps <= 4.5:
        pace_bonus = 0.05
    elif wps < 1.0:
        pace_bonus = -0.15
    else:
        pace_bonus = 0.0

    total = round(max(0.0, acoustic_score + hook_bonus + dur_bonus + pace_bonus), 4)
    tag_str = "+".join(tags) if tags else "clean-opener"
    reason = (
        f"acoustic={acoustic_score:.2f} (excite={mean_excite:.2f}, var={energy_variance:.2f}, "
        f"bursts={total_bursts}), hook={tag_str}, {span_s:.1f}s, s{start_idx}..s{end_idx}"
    )
    return total, reason


def discover_viral_arcs_offline(
    sentences: Sequence[Sentence],
    audio_wav_path: Path,
    *,
    max_clips: int = 3,
    min_duration_ms: int = 28_000,
    max_duration_ms: int = 68_000,
    min_separation_ms: int = 30_000,
) -> tuple[tuple[tuple[int, ...], float, str], ...]:
    """Deterministically discover top non-overlapping complete-sentence viral arcs locally.

    Scores contiguous complete-sentence spans ``[i..j]`` inside
    ``[min_duration_ms, max_duration_ms]`` using real Stage 0 WAV acoustic energy variance &
    bursts (``hawedit.audio_signals.analyze_sentence_audio``) plus Kurdish hook-opening
    heuristics, then applies greedy non-maximum suppression with ``>= min_separation_ms``
    separation between selected clips.
    """
    if not sentences:
        raise V8EpisodeError("Cannot discover viral arcs from empty sentences sequence")
    if not audio_wav_path.is_file() or audio_wav_path.stat().st_size == 0:
        raise V8EpisodeError(f"Stage 0 audio WAV missing or empty: {audio_wav_path}")
    if isinstance(max_clips, bool) or max_clips < 1:
        raise V8EpisodeError(f"max_clips must be >= 1, got {max_clips!r}")
    if min_duration_ms <= 0 or max_duration_ms < min_duration_ms:
        raise V8EpisodeError(f"Invalid duration range [{min_duration_ms}, {max_duration_ms}] ms")
    if min_separation_ms < 0:
        raise V8EpisodeError(f"min_separation_ms must be >= 0, got {min_separation_ms!r}")

    try:
        metrics = analyze_sentence_audio(audio_wav_path, sentences)
    except (OSError, ValueError) as exc:
        raise V8EpisodeError(f"Stage 0 WAV acoustic analysis failed: {exc}") from exc

    n = len(sentences)
    candidates: list[tuple[float, int, int, tuple[int, ...], str]] = []
    for i in range(n):
        s_start = sentences[i]
        if not s_start.complete:
            continue
        start_ms = s_start.start_ms
        for j in range(i, n):
            s_end = sentences[j]
            span_ms = s_end.end_ms - start_ms
            if span_ms > max_duration_ms:
                break
            if span_ms < min_duration_ms:
                continue
            if not s_end.complete or _ends_with_dangling(s_end):
                continue
            score, reason = _score_span_heuristics(
                sentences,
                metrics,
                i,
                j,
                min_duration_ms=min_duration_ms,
                max_duration_ms=max_duration_ms,
            )
            candidates.append((score, start_ms, s_end.end_ms, tuple(range(i, j + 1)), reason))

    if not candidates:
        raise V8EpisodeError(
            f"No complete-sentence viral arcs found within "
            f"[{min_duration_ms / 1000.0:.1f}s, {max_duration_ms / 1000.0:.1f}s] "
            f"across {n} sentences"
        )

    # Deterministic descending score; break ties by earliest start_ms, then shortest end_ms.
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    selected: list[tuple[tuple[int, ...], float, str]] = []
    picked_spans: list[tuple[int, int]] = []
    for score, start_ms, end_ms, indices, reason in candidates:
        if any(
            not (end_ms + min_separation_ms <= p_start or start_ms >= p_end + min_separation_ms)
            for p_start, p_end in picked_spans
        ):
            continue
        selected.append((indices, score, reason))
        picked_spans.append((start_ms, end_ms))
        if len(selected) >= max_clips:
            break

    return tuple(selected)


def _safe_media_id(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-")
    return cleaned or "episode"


def _build_compile_config(cfg: V8EpisodeConfig) -> V8CompileConfig:
    kwargs: dict[str, Any] = {
        "director_backend": cfg.director,
        "sub_engine": cfg.sub_engine,
        "fps": cfg.fps,
        "cinema_grade": cfg.cinema_grade,
        "enable_critique": cfg.enable_critique,
        "enable_asd": cfg.enable_asd,
        "encoder": cfg.encoder,
        "ffmpeg": cfg.ffmpeg,
        "condense": cfg.condense,
        "cold_open": cfg.cold_open,
        "silence_threshold_ms": cfg.silence_threshold_ms,
        "silence_target_gap_ms": cfg.silence_target_gap_ms,
        "excise_fillers": cfg.excise_fillers,
        "progress_bar": cfg.progress_bar,
        "asd_onnx_path": cfg.asd_onnx_path,
        "fonts_dir": cfg.fonts_dir,
        "director_model": cfg.director_model,
        "omni_url": cfg.omni_url,
        "enable_grill": cfg.enable_grill,
    }
    supported = {f.name for f in dataclasses.fields(V8CompileConfig)}
    optional_v9: dict[str, Any] = {
        "style_preset": cfg.style_preset,
        "brand_accent_hex": cfg.brand_accent_hex,
        "speaker_name_ckb": cfg.speaker_name_ckb,
        "speaker_role_ckb": cfg.speaker_role_ckb,
        "end_card_title_ckb": cfg.end_card_title_ckb,
        "end_card_subtitle_ckb": cfg.end_card_subtitle_ckb,
        "end_card_handle": cfg.end_card_handle,
        "local_modality": cfg.local_modality,
        "allow_web_stock": cfg.allow_web_stock,
        "enable_broll": cfg.enable_broll,
        "broll_dir": cfg.broll_dir,
        "enable_banter_split": cfg.enable_banter_split,
        "music_mood": cfg.music_mood,
        "enable_local_vlm": cfg.enable_local_vlm,
        # Keep .v8.overlay.mov until write_client_delivery_pack verifies & reclaims it (D-390).
        "keep_overlay": True,
    }
    for key, val in optional_v9.items():
        if key in supported:
            kwargs[key] = val
    return V8CompileConfig(**kwargs)


def _run_stage1_omni_asr(
    source: Path,
    work_dir: Path,
    cfg: V8EpisodeConfig,
) -> tuple[tuple[Word, ...], Path, Path]:
    """Run Stage 0 ingest + Stage 1 WSL OmniASR via ``hawedit.ingest`` and ``hawedit.asr``."""
    from hawedit.asr import (
        create_omni_asr_producer,
        discover_default_champion_checkpoint,
        resolve_champion_adapter,
        resolve_champion_checkpoint,
    )

    ffmpeg_bin = cfg.ffmpeg or find_ffmpeg()
    if ffmpeg_bin is None:
        raise V8EpisodeError("No ffmpeg binary available for Stage 0/1 OmniASR ingest")

    media_id = _safe_media_id(source.stem)
    try:
        ingested = ingest(source, work_dir / "stage0", ffmpeg=ffmpeg_bin)
        checkpoint = resolve_champion_checkpoint() or discover_default_champion_checkpoint()
        adapter = resolve_champion_adapter() if checkpoint is None else None
        producer = create_omni_asr_producer(
            cfg.omni_asr_runtime,
            distro=cfg.wsl_distro,
            lora_adapter=adapter,
            fused_checkpoint=checkpoint,
        )
        raw = producer.transcribe(
            media_id,
            Path(ingested.audio_path),
            ingested.speech,
            work_dir / "stage1",
            ffmpeg_bin,
        )
    except Exception as exc:
        raise V8EpisodeError(f"Stage 1 OmniASR transcription failed for {source}: {exc}") from exc

    if not raw.words:
        raise V8EpisodeError(f"Stage 1 OmniASR returned zero words for {source}")

    store = TranscriptStore(work_dir / "transcripts")
    raw_path = work_dir / "transcripts" / f"{media_id}.transcript.raw.json"
    if not raw_path.is_file():
        store.write_raw(raw)
    return tuple(raw.words), raw_path, Path(ingested.audio_path)


def _discover_arcs_gemini_path_a(
    *,
    media_id: str,
    words: Sequence[Word],
    sentences: Sequence[Sentence],
    audio_wav_path: Path | None,
    cfg: V8EpisodeConfig,
    gemini_discoverer: Callable[..., Sequence[Any]] | None = None,
) -> tuple[tuple[tuple[int, ...], float, str], ...]:
    """Discover viral arcs via Gemini Path A (strict fail-stop; never falls back to offline)."""
    from hawedit.path_a import PathADiscovery

    raw_text = " ".join(w.w for w in words)
    norm_text = normalize_sorani(raw_text)
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    norm_transcript = NormalizedTranscript(
        media_id=_safe_media_id(media_id),
        text_ckb=norm_text,
        source_sha256=digest,
        words=tuple(words),
    )
    audio_metrics = (
        analyze_sentence_audio(audio_wav_path, sentences)
        if audio_wav_path is not None and audio_wav_path.is_file()
        else None
    )

    try:
        if gemini_discoverer is not None:
            candidates = gemini_discoverer(
                norm_transcript, sentences=sentences, audio_metrics=audio_metrics
            )
        else:
            candidates = PathADiscovery().discover(
                norm_transcript, sentences=sentences, audio_metrics=audio_metrics
            )
    except Exception as exc:
        raise V8EpisodeError(f"Gemini Path A arc discovery failed: {exc}") from exc

    if not candidates:
        raise V8EpisodeError("Gemini Path A arc discovery returned zero candidates")

    selected: list[tuple[tuple[int, ...], float, str]] = []
    picked_spans: list[tuple[int, int]] = []
    ordered = sorted(
        candidates,
        key=lambda c: (-(float(c.score) if c.score is not None else 0.0), int(c.in_ms)),
    )
    for cand in ordered:
        c_in = int(cand.in_ms)
        c_out = int(cand.out_ms)
        indices = tuple(
            idx
            for idx, sent in enumerate(sentences)
            if sent.start_ms >= c_in and sent.end_ms <= c_out
        )
        if not indices:
            continue
        if not sentences[indices[0]].complete or not sentences[indices[-1]].complete:
            continue
        span_start = sentences[indices[0]].start_ms
        span_end = sentences[indices[-1]].end_ms
        if any(
            not (
                span_end + cfg.min_separation_ms <= p_s or span_start >= p_e + cfg.min_separation_ms
            )
            for p_s, p_e in picked_spans
        ):
            continue
        score = round(float(cand.score) if cand.score is not None else 1.0, 4)
        reason = (
            f"gemini-path-a rank={getattr(cand, 'rank', len(selected) + 1)} "
            f"score={score:.2f} s{indices[0]}..s{indices[-1]}"
        )
        selected.append((indices, score, reason))
        picked_spans.append((span_start, span_end))
        if len(selected) >= cfg.max_clips:
            break

    if not selected:
        raise V8EpisodeError(
            "Gemini Path A candidates did not align to any complete non-overlapping sentences"
        )
    return tuple(selected)


def compile_v8_episode(
    source: Path,
    out_dir: Path,
    *,
    transcript_path: Path | None = None,
    use_omni_asr: bool = False,
    config: V8EpisodeConfig | None = None,
    sentence_ranges: Sequence[Sequence[int]] | None = None,
    audio_wav_path: Path | None = None,
    clip_compiler: Callable[..., V8CompileResult] | None = None,
    cover_extractor: Callable[[Path, Path, float], Path] | None = None,
    asr_runner: Callable[[Path, Path], tuple[Sequence[Word], Path]] | None = None,
    gemini_discoverer: Callable[..., Sequence[Any]] | None = None,
    on_progress: Callable[[str, str, int], None] | None = None,
) -> V8EpisodeResult:
    """One-command full-episode arc discovery, multi-reel V8 compile & client delivery pack.

    Strict fail-stop:
    - Requires EITHER ``transcript_path`` OR ``use_omni_asr=True`` (never guesses or skips).
    - Never silently falls back from Gemini Path A to offline discovery.
    - Verifies every deliverable file in every clip's ``ClientDeliveryPack`` before returning.
    """
    t0 = time.monotonic()
    cfg = config if config is not None else V8EpisodeConfig()

    if not source.is_file():
        raise V8EpisodeError(f"Source video not found: {source}")
    if transcript_path is None and not use_omni_asr:
        raise V8EpisodeError(
            "Must specify either transcript_path or use_omni_asr=True (zero silent fallbacks)"
        )
    if transcript_path is not None and not transcript_path.is_file():
        raise V8EpisodeError(f"Transcript file not found: {transcript_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / ".work"
    media_id = _safe_media_id(source.stem)

    # 1. Acquire aligned episode words + Stage 0 WAV.
    resolved_transcript_path: Path | None = transcript_path
    resolved_wav_path: Path | None = audio_wav_path
    if transcript_path is not None:
        words = load_transcript_words(transcript_path)
    elif asr_runner is not None:
        raw_words, resolved_transcript_path = asr_runner(source, work_dir)
        words = tuple(raw_words)
        if not words:
            raise V8EpisodeError("ASR runner returned zero words")
    else:
        words, resolved_transcript_path, stage0_wav = _run_stage1_omni_asr(source, work_dir, cfg)
        if resolved_wav_path is None:
            resolved_wav_path = stage0_wav

    all_sentences = segment_sentences(words)
    if not all_sentences:
        raise V8EpisodeError("Transcript segmented into zero sentences")
    discovery_sentences = (
        all_sentences if sentence_ranges is not None else _subsegment_long_utterances(all_sentences)
    )

    # 2. Select top viral arcs (override | V10.2 semantic-multicut | legacy Path A / offline).
    use_semantic_multicut = sentence_ranges is None and (
        cfg.story_mode == "semantic-multicut"
        or (
            cfg.story_mode == "auto"
            and cfg.director in ("gemini", "local-omni")
            and gemini_discoverer is None
        )
    )
    if use_semantic_multicut:
        if cfg.director == "gemini":
            story_backend: Literal["gemini", "local-omni"] = "gemini"
        elif cfg.director == "local-omni":
            story_backend = "local-omni"
        else:
            raise V8EpisodeError(
                "story_mode='semantic-multicut' requires --director gemini or --director local-omni"
            )
        if resolved_wav_path is None:
            ffmpeg_bin = cfg.ffmpeg or find_ffmpeg()
            if ffmpeg_bin is not None:
                work_dir.mkdir(parents=True, exist_ok=True)
                resolved_wav_path = extract_audio(source, work_dir / "audio.wav", ffmpeg=ffmpeg_bin)
        ffmpeg_bin = cfg.ffmpeg or find_ffmpeg()
        src_dur_ms = probe_duration_ms(source, ffmpeg_bin) if ffmpeg_bin is not None else None
        plan_count = cfg.max_clips + 2 if cfg.overgenerate_candidates else cfg.max_clips
        try:
            recipes = plan_episode_multicut_stories(
                words,
                backend=story_backend,
                max_stories=plan_count,
                min_duration_ms=cfg.min_duration_ms,
                max_duration_ms=cfg.max_duration_ms,
                audio_wav=resolved_wav_path,
                model_id=cfg.director_model,
                base_url=cfg.omni_url,
            )
        except StoryEditorError as exc:
            raise V8EpisodeError(f"V11 semantic multi-cut planning failed: {exc}") from exc

        compile_cfg = _build_compile_config(cfg)
        compiler_fn = clip_compiler if clip_compiler is not None else compile_v8_clip
        sem_items: list[V8EpisodeClipItem] = []
        quarantined_items: list[dict[str, Any]] = []
        total_arcs = len(recipes)
        for cand_idx, raw_recipe in enumerate(recipes, start=1):
            if len(sem_items) >= cfg.max_clips:
                break
            rank = len(sem_items) + 1
            clip_t0 = time.monotonic()
            if on_progress is not None:
                start_pct = 35 + int(((cand_idx - 1) / max(1, total_arcs)) * 55)
                on_progress(f"v8_clip_{rank}_of_{cfg.max_clips}", "started", start_pct)
            clip_id = f"{media_id}-r{rank:02d}-mc"
            try:
                refined_recipe = refine_story_pruning(
                    words,
                    raw_recipe,
                    backend=story_backend,
                    model_id=cfg.director_model,
                    base_url=cfg.omni_url,
                )
                verified_recipe, verify_res = verify_story_meaning_preservation(
                    words,
                    refined_recipe,
                    backend=story_backend,
                    model_id=cfg.director_model if story_backend == "local-omni" else None,
                    base_url=cfg.omni_url,
                )
                compiled = compile_story_to_assembly_spans(
                    words,
                    verified_recipe,
                    audio_wav=resolved_wav_path,
                    source_duration_ms=src_dur_ms,
                )
                clip_in_ms = min(sp.source_in_ms for sp in compiled.assembly_spans)
                clip_out_ms = max(sp.source_out_ms for sp in compiled.assembly_spans)
                co_tag = (
                    f" cold_open={compiled.cold_open_end_ms}ms"
                    if compiled.cold_open_end_ms is not None
                    else ""
                )
                reason = (
                    f"v11-semantic-multicut beats={len(verified_recipe.keep_spans)} "
                    f"spans={len(compiled.assembly_spans)} drops={compiled.dropped_word_count} "
                    f"restored={len(verify_res.restored_drop_indices)} "
                    f"cues={len(verified_recipe.visual_cues)}{co_tag}"
                )
                compile_res = compiler_fn(
                    source_mp4=source,
                    clip_id=clip_id,
                    clip_in_ms=clip_in_ms,
                    clip_out_ms=clip_out_ms,
                    words=compiled.remapped_words,
                    out_dir=out_dir,
                    config=compile_cfg,
                    semantic_assembly_spans=compiled.assembly_spans,
                    semantic_words=compiled.remapped_words,
                    semantic_cut_times_ms=compiled.semantic_cut_times_ms,
                    semantic_visual_cues=verified_recipe.visual_cues,
                    semantic_word_idx_to_ms=compiled.word_idx_to_output_ms,
                    semantic_hook_title_ckb=verified_recipe.hook_title_ckb,
                )
                pack = write_client_delivery_pack(
                    compile_res,
                    source_mp4=source,
                    clip_in_ms=clip_in_ms,
                    clip_out_ms=clip_out_ms,
                    fps=cfg.fps,
                    media_id=media_id,
                    hook_title_ckb=compile_res.script.hook_title_ckb,
                    subtitle_languages=cfg.subtitle_languages,
                    dub_languages=cfg.dub_languages,
                    translation_model=cfg.translation_model,
                    post_cta=(
                        cfg.end_card_title_ckb,
                        cfg.end_card_subtitle_ckb,
                        cfg.end_card_handle,
                    ),
                    retained_intervals_ms=compile_res.retained_intervals_ms,
                    keep_overlay=cfg.keep_overlay,
                    ffmpeg=cfg.ffmpeg,
                    cover_extractor=cover_extractor,
                )
                verify_client_pack_complete(pack)
            except (StoryEditorError, V8CompileError, DeliveryPackError) as exc:
                if not cfg.overgenerate_candidates:
                    raise V8EpisodeError(
                        f"V10.2 semantic compile failed for {raw_recipe.story_id}: {exc}"
                    ) from exc
                q_dir = out_dir / "quarantine"
                q_dir.mkdir(parents=True, exist_ok=True)
                for partial in (
                    out_dir / f"{clip_id}.v8.mp4",
                    out_dir / f"{clip_id}.v8.overlay.mov",
                ):
                    if partial.is_file():
                        partial.unlink()
                q_record = {
                    "candidate_index": cand_idx,
                    "story_id": raw_recipe.story_id,
                    "clip_id": clip_id,
                    "hook_title_ckb": raw_recipe.hook_title_ckb,
                    "error": str(exc),
                }
                write_text_atomic(
                    q_dir / f"cand-{cand_idx:02d}-{raw_recipe.story_id}.quarantine.json",
                    json.dumps(q_record, ensure_ascii=False, indent=2) + "\n",
                )
                quarantined_items.append(q_record)
                continue

            if on_progress is not None:
                done_pct = 35 + int((len(sem_items) + 1) / max(1, cfg.max_clips) * 55)
                on_progress(f"v8_clip_{rank}_of_{cfg.max_clips}", "completed", done_pct)

            sem_items.append(
                V8EpisodeClipItem(
                    rank=rank,
                    clip_id=clip_id,
                    sentence_indices=tuple(range(len(compiled.assembly_spans))),
                    clip_in_ms=clip_in_ms,
                    clip_out_ms=clip_out_ms,
                    discovery_score=round(float(verified_recipe.viral_score), 4),
                    discovery_reason=reason,
                    compile_result=compile_res,
                    delivery_pack=pack,
                    wall_time_s=round(time.monotonic() - clip_t0, 3),
                )
            )

        if not sem_items:
            summary = "; ".join(f"{q['story_id']}: {q['error']}" for q in quarantined_items)
            raise V8EpisodeError(
                f"All {len(recipes)} semantic multi-cut candidates were quarantined: {summary}"
            )

        total_wall_s = round(time.monotonic() - t0, 3)
        all_grills_passed = bool(sem_items) and all(item.grill_passed is True for item in sem_items)
        review_html_path = write_client_review_html(
            [item.delivery_pack for item in sem_items],
            out_dir / "client-review.html",
            episode_title=f"HawEdit V11 — {source.stem}",
            source_name=source.name,
            director_backend=cfg.director,
            total_wall_s=total_wall_s,
            style_preset=cfg.style_preset,
        )
        episode_json_path = out_dir / "episode.v8.json"
        result = V8EpisodeResult(
            media_id=media_id,
            source_mp4=source,
            out_dir=out_dir,
            transcript_path=resolved_transcript_path,
            director=cfg.director,
            clips=tuple(sem_items),
            episode_json_path=episode_json_path,
            review_html_path=review_html_path,
            total_wall_s=total_wall_s,
            all_grills_passed=all_grills_passed,
            quarantined=tuple(quarantined_items),
        )
        payload = result.to_dict()
        payload["config"] = cfg.to_dict()
        write_text_atomic(
            episode_json_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        return result

    use_reserves = (
        sentence_ranges is None and cfg.director == "offline" and cfg.overgenerate_candidates
    )
    selected_arcs: tuple[tuple[tuple[int, ...], float, str], ...]
    if sentence_ranges is not None:
        if not sentence_ranges:
            raise V8EpisodeError("sentence_ranges override cannot be empty")
        validated_arcs: list[tuple[tuple[int, ...], float, str]] = []
        for idx_group in sentence_ranges:
            ordered = tuple(sorted(dict.fromkeys(int(i) for i in idx_group)))
            if not ordered:
                raise V8EpisodeError("Empty range inside sentence_ranges")
            for idx in ordered:
                if not (0 <= idx < len(all_sentences)):
                    raise V8EpisodeError(
                        f"Sentence index {idx} out of range (0..{len(all_sentences) - 1})"
                    )
            validated_arcs.append(
                (ordered, 1.0, f"explicit sentence range s{ordered[0]}..s{ordered[-1]}")
            )
        selected_arcs = tuple(validated_arcs)
    elif cfg.director == "gemini":
        selected_arcs = _discover_arcs_gemini_path_a(
            media_id=media_id,
            words=words,
            sentences=discovery_sentences,
            audio_wav_path=resolved_wav_path,
            cfg=cfg,
            gemini_discoverer=gemini_discoverer,
        )
    else:
        if resolved_wav_path is None:
            ffmpeg_bin = cfg.ffmpeg or find_ffmpeg()
            if ffmpeg_bin is None:
                raise V8EpisodeError(
                    "No ffmpeg binary available to extract Stage 0 WAV for offline arc discovery"
                )
            work_dir.mkdir(parents=True, exist_ok=True)
            resolved_wav_path = extract_audio(source, work_dir / "audio.wav", ffmpeg=ffmpeg_bin)
        effective_max_dur_ms = (
            max(cfg.max_duration_ms, 95_000) if cfg.condense else cfg.max_duration_ms
        )
        selected_arcs = discover_viral_arcs_offline(
            discovery_sentences,
            resolved_wav_path,
            max_clips=cfg.max_clips * 2 if use_reserves else cfg.max_clips,
            min_duration_ms=cfg.min_duration_ms,
            max_duration_ms=effective_max_dur_ms,
            min_separation_ms=cfg.min_separation_ms,
        )

    # 3. Compile every selected arc & publish its verified ClientDeliveryPack.
    compile_cfg = _build_compile_config(cfg)
    compiler_fn = clip_compiler if clip_compiler is not None else compile_v8_clip
    items: list[V8EpisodeClipItem] = []

    rejected: list[dict[str, Any]] = []
    total_arcs = min(cfg.max_clips, len(selected_arcs)) if use_reserves else len(selected_arcs)
    for candidate_index, (sent_indices, score, reason) in enumerate(selected_arcs, start=1):
        if use_reserves and len(items) >= cfg.max_clips:
            break
        rank = len(items) + 1
        clip_t0 = time.monotonic()
        if on_progress is not None:
            start_pct = 35 + int(((rank - 1) / max(1, total_arcs)) * 55)
            on_progress(f"v8_clip_{rank}_of_{total_arcs}", "started", start_pct)
        selected_sentences = tuple(discovery_sentences[idx] for idx in sent_indices)
        span_words = tuple(w for s in selected_sentences for w in s.words)
        clip_in_ms = max(0, span_words[0].start_ms - 120)
        clip_out_ms = span_words[-1].end_ms + 180
        clip_words = tuple(
            Word(
                w=w.w,
                start_ms=max(0, w.start_ms - clip_in_ms),
                end_ms=max(1, w.end_ms - clip_in_ms),
                conf=w.conf,
            )
            for w in span_words
        )
        clip_id = f"{media_id}-r{rank:02d}-s{sent_indices[0]}-{sent_indices[-1]}"

        try:
            compile_res = compiler_fn(
                source_mp4=source,
                clip_id=clip_id,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                words=clip_words,
                out_dir=out_dir,
                config=compile_cfg,
                source_sentences=selected_sentences,
            )
        except ReelQualityError as exc:
            if not use_reserves:
                raise
            rejected.append(
                {
                    "candidate_index": candidate_index,
                    "clip_id": clip_id,
                    "clip_in_ms": clip_in_ms,
                    "clip_out_ms": clip_out_ms,
                    "error": str(exc),
                }
            )
            continue
        try:
            pack = write_client_delivery_pack(
                compile_res,
                source_mp4=source,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                fps=cfg.fps,
                media_id=media_id,
                hook_title_ckb=compile_res.script.hook_title_ckb,
                post_cta=(cfg.end_card_title_ckb, cfg.end_card_subtitle_ckb, cfg.end_card_handle),
                subtitle_languages=cfg.subtitle_languages,
                dub_languages=cfg.dub_languages,
                translation_model=cfg.translation_model,
                retained_intervals_ms=compile_res.retained_intervals_ms,
                keep_overlay=cfg.keep_overlay,
                ffmpeg=cfg.ffmpeg,
                cover_extractor=cover_extractor,
            )
            verify_client_pack_complete(pack)
        except DeliveryPackError as exc:
            raise V8EpisodeError(f"Delivery pack failed for {clip_id}: {exc}") from exc

        if on_progress is not None:
            done_pct = 35 + int((rank / max(1, total_arcs)) * 55)
            on_progress(f"v8_clip_{rank}_of_{total_arcs}", "completed", done_pct)

        items.append(
            V8EpisodeClipItem(
                rank=rank,
                clip_id=clip_id,
                sentence_indices=sent_indices,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                discovery_score=score,
                discovery_reason=reason,
                compile_result=compile_res,
                delivery_pack=pack,
                wall_time_s=round(time.monotonic() - clip_t0, 3),
            )
        )

    if not items:
        raise V8EpisodeError(f"No accepted clips. Quality results: {rejected!r}")
    total_wall_s = round(time.monotonic() - t0, 3)
    all_grills_passed = bool(items) and all(item.grill_passed is True for item in items)

    # 4. Generate client-review.html & episode.v8.json atomically.
    review_html_path = write_client_review_html(
        [item.delivery_pack for item in items],
        out_dir / "client-review.html",
        episode_title=f"HawEdit V9 — {source.stem}",
        source_name=source.name,
        director_backend=cfg.director,
        total_wall_s=total_wall_s,
        style_preset=cfg.style_preset,
    )

    episode_json_path = out_dir / "episode.v8.json"
    result = V8EpisodeResult(
        media_id=media_id,
        source_mp4=source,
        out_dir=out_dir,
        transcript_path=resolved_transcript_path,
        director=cfg.director,
        clips=tuple(items),
        episode_json_path=episode_json_path,
        review_html_path=review_html_path,
        total_wall_s=total_wall_s,
        all_grills_passed=all_grills_passed,
        quarantined=tuple(rejected),
    )
    payload = result.to_dict()
    payload["config"] = cfg.to_dict()
    write_text_atomic(
        episode_json_path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    return result
