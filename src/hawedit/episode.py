"""Episode planning and multi-clip reconciliation (Task T4.1).

Coordinates multi-clip social reel extraction across long-form episodes (podcasts, interviews),
guaranteeing zero temporal overlap, minimum inter-clip separation, topic diversity,
and independent delivery bundle verification per clip.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.discovery import MergedCandidate
from hawedit.judge import JudgeVerdict
from hawedit.normalize import normalize_sorani
from hawedit.transcripts import NormalizedTranscript

__all__ = [
    "DEFAULT_MAX_TEXT_SIMILARITY",
    "DEFAULT_MIN_SEPARATION_MS",
    "EpisodeClipSummary",
    "EpisodeError",
    "EpisodeManifest",
    "EpisodePlanConfig",
    "EpisodeReconciliationError",
    "compute_text_similarity",
    "reconcile_episode_manifest",
    "select_episode_plan",
]

DEFAULT_MIN_SEPARATION_MS: Final[int] = 15_000
DEFAULT_MAX_TEXT_SIMILARITY: Final[float] = 0.50


class EpisodeError(Exception):
    """Raised when an episode plan operation fails."""


class EpisodeReconciliationError(EpisodeError):
    """Raised when an episode manifest fails reconciliation against delivered bundles."""


def compute_text_similarity(text_a: str, text_b: str) -> float:
    """Compute lexical Jaccard similarity between two Kurdish text excerpts."""
    norm_a = normalize_sorani(text_a)
    norm_b = normalize_sorani(text_b)

    words_a = set(re.findall(r"[\u0600-\u06FF\w]+", norm_a))
    words_b = set(re.findall(r"[\u0600-\u06FF\w]+", norm_b))

    if not words_a or not words_b:
        return 0.0

    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return float(intersection / union) if union > 0 else 0.0


@dataclass(frozen=True)
class EpisodePlanConfig:
    """Configuration constraints for episode-level clip selection."""

    max_clips: int = 3
    min_separation_ms: int = DEFAULT_MIN_SEPARATION_MS
    max_text_similarity: float = DEFAULT_MAX_TEXT_SIMILARITY
    cost_cap_usd: float | None = None

    def __post_init__(self) -> None:
        if self.max_clips < 1:
            raise ValueError(f"max_clips must be >= 1, got {self.max_clips}")
        if self.min_separation_ms < 0:
            raise ValueError(
                f"min_separation_ms must be non-negative, got {self.min_separation_ms}"
            )
        if not (0.0 <= self.max_text_similarity <= 1.0):
            raise ValueError(
                f"max_text_similarity must be in [0.0, 1.0], got {self.max_text_similarity}"
            )
        if self.cost_cap_usd is not None and self.cost_cap_usd <= 0.0:
            raise ValueError(f"cost_cap_usd must be positive, got {self.cost_cap_usd}")


@dataclass(frozen=True)
class EpisodeClipSummary:
    """Summary metadata for one delivered clip inside an episode manifest."""

    clip_id: str
    in_ms: int
    out_ms: int
    duration_ms: int
    hook_score: float
    title_ckb: str
    delivery_dir: str
    hook_type: str | None = None
    title_variants_ckb: tuple[str, ...] = ()
    cover_frame_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "hook_score": round(self.hook_score, 4),
            "hook_type": self.hook_type,
            "title_ckb": self.title_ckb,
            "title_variants_ckb": list(self.title_variants_ckb),
            "cover_frame_ms": self.cover_frame_ms,
            "delivery_dir": self.delivery_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeClipSummary:
        return cls(
            clip_id=str(data["clip_id"]),
            in_ms=int(data["in_ms"]),
            out_ms=int(data["out_ms"]),
            duration_ms=int(data["duration_ms"]),
            hook_score=float(data["hook_score"]),
            hook_type=data.get("hook_type"),
            title_ckb=str(data["title_ckb"]),
            title_variants_ckb=tuple(data.get("title_variants_ckb", ())),
            cover_frame_ms=data.get("cover_frame_ms"),
            delivery_dir=str(data["delivery_dir"]),
        )


@dataclass(frozen=True)
class EpisodeManifest:
    """Consolidated catalog for all delivered clips from an episode run."""

    episode_id: str
    media_id: str
    media_sha256: str
    clips_count: int
    total_duration_ms: int
    clips: tuple[EpisodeClipSummary, ...]
    reconciled: bool = False
    total_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "episode_id": self.episode_id,
            "media_id": self.media_id,
            "media_sha256": self.media_sha256,
            "clips_count": self.clips_count,
            "total_duration_ms": self.total_duration_ms,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "reconciled": self.reconciled,
            "clips": [c.to_dict() for c in self.clips],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeManifest:
        clips = tuple(EpisodeClipSummary.from_dict(c) for c in data.get("clips", []))
        return cls(
            episode_id=str(data["episode_id"]),
            media_id=str(data["media_id"]),
            media_sha256=str(data["media_sha256"]),
            clips_count=int(data["clips_count"]),
            total_duration_ms=int(data["total_duration_ms"]),
            clips=clips,
            reconciled=bool(data.get("reconciled", False)),
            total_cost_usd=float(data.get("total_cost_usd", 0.0)),
        )

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def select_episode_plan(
    judged_items: Sequence[tuple[MergedCandidate, tuple[int, ...], JudgeVerdict]],
    config: EpisodePlanConfig,
    normalized_transcript: NormalizedTranscript | None = None,
) -> list[tuple[MergedCandidate, tuple[int, ...], JudgeVerdict]]:
    """Select up to N diverse, non-overlapping winners satisfying episode constraints.

    Args:
        judged_items: Sequence of (candidate, sentence_indices, verdict).
        config: EpisodePlanConfig parameters.
        normalized_transcript: Optional transcript for lexical diversity checks.

    Returns:
        List of selected (candidate, sentence_indices, verdict) tuples in ranked order.
    """
    if not judged_items:
        return []

    # Rank shippable items by composite editorial quality
    def _rank_key(
        item: tuple[MergedCandidate, tuple[int, ...], JudgeVerdict],
    ) -> tuple[float, float, bool]:
        _cand, _indices, verdict = item
        return (
            verdict.hook_score,
            getattr(verdict, "payoff_strength", 0.0),
            getattr(verdict, "ends_on_a_beat", False),
        )

    ranked = sorted(judged_items, key=_rank_key, reverse=True)

    selected: list[tuple[MergedCandidate, tuple[int, ...], JudgeVerdict]] = []
    selected_texts: list[str] = []

    def _get_text(cand: MergedCandidate) -> str:
        if normalized_transcript is not None:
            words = [
                w.w
                for w in normalized_transcript.words
                if cand.span[0] <= w.start_ms and w.end_ms <= cand.span[1]
            ]
            if words:
                return " ".join(words)
        return cand.candidate_id

    for candidate, sentence_indices, verdict in ranked:
        if len(selected) >= config.max_clips:
            break

        cand_span = candidate.span
        conflict = False

        # Constraint 1: Zero temporal overlap and minimum separation
        for existing_cand, _, _ in selected:
            exist_span = existing_cand.span

            # Overlap check
            overlap = not (cand_span[1] <= exist_span[0] or cand_span[0] >= exist_span[1])
            if overlap:
                conflict = True
                break

            # Minimum separation check
            dist_left = cand_span[0] - exist_span[1]
            dist_right = exist_span[0] - cand_span[1]
            separation = max(dist_left, dist_right)
            if separation < config.min_separation_ms:
                conflict = True
                break

        if conflict:
            continue

        # Constraint 2: Lexical / topic diversity check
        cand_text = _get_text(candidate)
        too_similar = False
        for existing_text in selected_texts:
            similarity = compute_text_similarity(cand_text, existing_text)
            if similarity > config.max_text_similarity:
                too_similar = True
                break

        if too_similar:
            continue

        # All constraints satisfied: add to episode selection
        selected.append((candidate, sentence_indices, verdict))
        selected_texts.append(cand_text)

    return selected


def reconcile_episode_manifest(
    manifest: EpisodeManifest,
    base_dir: Path,
    *,
    fps: float = 25.0,
) -> None:
    """Reconcile all delivered bundles in an episode manifest against ground-truth files.

    Args:
        manifest: EpisodeManifest to reconcile.
        base_dir: Directory containing delivery bundles.
        fps: Target frame rate for tolerance math.

    Raises:
        EpisodeReconciliationError on missing bundle files, duration mismatches,
        or temporal collisions between clips.
    """
    if len(manifest.clips) != manifest.clips_count:
        raise EpisodeReconciliationError(
            f"clips_count mismatch: manifest says {manifest.clips_count} clips, "
            f"holds {len(manifest.clips)}"
        )

    expected_total_duration = sum(c.duration_ms for c in manifest.clips)
    if expected_total_duration != manifest.total_duration_ms:
        raise EpisodeReconciliationError(
            f"total_duration_ms mismatch: manifest says {manifest.total_duration_ms} ms, "
            f"clips sum to {expected_total_duration} ms"
        )

    frame_ms = int(round(1000.0 / fps)) if fps > 0 else 40
    tolerance_ms = frame_ms + int(round(frame_ms / 2))

    # Verify each clip's deliverables on disk
    for clip in manifest.clips:
        clip_dir = base_dir / clip.delivery_dir
        if not clip_dir.is_dir():
            raise EpisodeReconciliationError(
                f"delivery directory not found for clip {clip.clip_id}: {clip_dir}"
            )

        required_suffixes = [
            ".mp4",
            ".ass",
            ".srt",
            ".edl",
            ".json",
            ".measured.json",
            ".cover.png",
        ]
        for suffix in required_suffixes:
            target = clip_dir / f"{clip.clip_id}{suffix}"
            if suffix == ".cover.png" and not target.is_file():
                alt_cover = clip_dir / "cover.png"
                if alt_cover.is_file():
                    target = alt_cover
            if not target.is_file() or target.stat().st_size == 0:
                raise EpisodeReconciliationError(
                    f"missing required delivery file for clip {clip.clip_id}: {target}"
                )

        # Verify measured duration if available
        meas_path = clip_dir / f"{clip.clip_id}.measured.json"
        try:
            meas_data = json.loads(meas_path.read_text(encoding="utf-8"))
            measured_dur = int(meas_data["video"]["duration_ms"])
            if abs(measured_dur - clip.duration_ms) > tolerance_ms:
                raise EpisodeReconciliationError(
                    f"measured duration mismatch for clip {clip.clip_id}: "
                    f"expected {clip.duration_ms} ms, measured {measured_dur} ms"
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise EpisodeReconciliationError(
                f"invalid measurement file for clip {clip.clip_id}: {exc}"
            ) from exc

    # Verify zero temporal collisions between delivered clips
    sorted_clips = sorted(manifest.clips, key=lambda c: c.in_ms)
    for i in range(len(sorted_clips) - 1):
        c1 = sorted_clips[i]
        c2 = sorted_clips[i + 1]
        if c1.out_ms > c2.in_ms:
            raise EpisodeReconciliationError(
                f"temporal collision detected in episode: clip {c1.clip_id} "
                f"({c1.in_ms}..{c1.out_ms} ms) overlaps with clip {c2.clip_id} "
                f"({c2.in_ms}..{c2.out_ms} ms)"
            )
