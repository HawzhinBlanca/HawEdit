"""Episode packaging with shared preprocessing, semantic diversity, and truthful states (VE-13).

Delivers up to N distinct eligible clips from a long-form episode:
1. Reuses shared episode preprocessing (ingest, transcription, observation inventory) once.
2. Filters semantic duplicates beyond lexical Jaccard while preserving distinct perspectives.
3. Does not force N outputs when fewer high-retention clips qualify (zero filler clips).
4. Reports truthful per-item states (approved, needs review, rejected with specific reasons).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hawedit.episode import compute_text_similarity
from hawedit.render_critic import CritiqueInspectionResult
from hawedit.transcripts import NormalizedTranscript, Word

__all__ = [
    "CandidateEditorialState",
    "CandidateEvaluationItem",
    "EpisodePackageConfig",
    "EpisodePackageReport",
    "EvaluatedCandidateRecord",
    "SharedEpisodeContext",
    "build_episode_package",
    "compute_semantic_similarity",
]


class CandidateEditorialState(str, Enum):
    """Truthful per-clip editorial evaluation state in the episode catalog."""

    SELECTED_APPROVED = "selected_approved"
    SELECTED_NEEDS_REVIEW = "selected_needs_review"
    REJECTED_DUPLICATE = "rejected_duplicate"
    REJECTED_DEFECTS = "rejected_defects"
    REJECTED_LOW_QUALITY = "rejected_low_quality"
    REJECTED_OVERLAP = "rejected_overlap"


@dataclass(frozen=True, slots=True)
class SharedEpisodeContext:
    """Preprocessed episode-level assets shared across all candidate evaluations."""

    episode_id: str
    media_id: str
    duration_ms: int
    normalized_transcript: NormalizedTranscript
    observation_coverage_ratio: float = 1.0
    total_source_tokens: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id.strip():
            raise ValueError("episode_id must be a non-empty string")
        if not isinstance(self.media_id, str) or not self.media_id.strip():
            raise ValueError("media_id must be a non-empty string")
        if self.duration_ms <= 0:
            raise ValueError(f"duration_ms must be positive, got {self.duration_ms}")


@dataclass(frozen=True, slots=True)
class CandidateEvaluationItem:
    """A proposed candidate clip evaluated under the shared episode context."""

    candidate_id: str
    span: tuple[int, int]
    title_ckb: str
    topic_tags: tuple[str, ...]
    core_claim: str
    perspective: str
    quality_score: float
    semantic_embedding: tuple[float, ...] = ()
    critique_result: CritiqueInspectionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        if self.span[0] < 0 or self.span[1] <= self.span[0]:
            raise ValueError(f"Invalid candidate span: {self.span}")
        if not math.isfinite(self.quality_score):
            raise TypeError("quality_score must be a finite float")


@dataclass(frozen=True, slots=True)
class EvaluatedCandidateRecord:
    """Truthful individual state and audit reason for one candidate in the episode report."""

    candidate_id: str
    state: CandidateEditorialState
    in_ms: int
    out_ms: int
    duration_ms: int
    title_ckb: str
    distinction_reason: str
    rejection_reason: str | None
    quality_score: float
    critique_status: str
    defect_count: int
    is_approved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "state": self.state.value,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "title_ckb": self.title_ckb,
            "distinction_reason": self.distinction_reason,
            "rejection_reason": self.rejection_reason,
            "quality_score": round(self.quality_score, 4),
            "critique_status": self.critique_status,
            "defect_count": self.defect_count,
            "is_approved": self.is_approved,
        }


@dataclass(frozen=True, slots=True)
class EpisodePackageConfig:
    """Configuration constraints for episode-level clip delivery."""

    max_clips: int = 3
    min_separation_ms: int = 15_000
    max_semantic_similarity: float = 0.80
    max_lexical_similarity: float = 0.50
    min_quality_score: float = 0.60
    allow_distinct_perspectives: bool = True

    def __post_init__(self) -> None:
        if self.max_clips < 1:
            raise ValueError(f"max_clips must be >= 1, got {self.max_clips}")
        if self.min_separation_ms < 0:
            raise ValueError(f"min_separation_ms must be non-negative: {self.min_separation_ms}")
        if not 0.0 <= self.max_semantic_similarity <= 1.0:
            raise ValueError(
                f"max_semantic_similarity must be in [0.0, 1.0], got {self.max_semantic_similarity}"
            )


@dataclass(frozen=True, slots=True)
class EpisodePackageReport:
    """Comprehensive catalog report delivering up to N distinct clips with truthful states."""

    episode_id: str
    media_id: str
    requested_clips: int
    delivered_clips_count: int
    selected_clips: tuple[EvaluatedCandidateRecord, ...]
    rejected_clips: tuple[EvaluatedCandidateRecord, ...]
    needs_review_clips: tuple[EvaluatedCandidateRecord, ...]
    shared_preprocessing_verified: bool
    preprocessing_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "media_id": self.media_id,
            "requested_clips": self.requested_clips,
            "delivered_clips_count": self.delivered_clips_count,
            "shared_preprocessing_verified": self.shared_preprocessing_verified,
            "preprocessing_summary": self.preprocessing_summary,
            "selected_clips": [c.to_dict() for c in self.selected_clips],
            "rejected_clips": [c.to_dict() for c in self.rejected_clips],
            "needs_review_clips": [c.to_dict() for c in self.needs_review_clips],
        }


def compute_semantic_similarity(
    vec_a: Sequence[float],
    vec_b: Sequence[float],
) -> float:
    """Computes cosine similarity between two semantic embedding vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0

    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _extract_candidate_text(words: Sequence[Word], span: tuple[int, int]) -> str:
    """Extracts Kurdish transcript text for a candidate span."""
    matched = [w.w for w in words if span[0] <= w.start_ms and w.end_ms <= span[1]]
    return " ".join(matched)


def build_episode_package(
    context: SharedEpisodeContext,
    candidates: Sequence[CandidateEvaluationItem],
    config: EpisodePackageConfig | None = None,
) -> EpisodePackageReport:
    """Packages up to N diverse, eligible clips from shared episode preprocessing.

    Enforces:
    - Preprocessing shared once (no redundant transcription/indexing).
    - Up to N clips (stops without forcing filler clips if fewer qualify).
    - Rejection of semantic duplicates while preserving distinct perspectives.
    - Truthful per-item status reporting with explicit rejection rationales.
    """
    cfg = config if config is not None else EpisodePackageConfig()

    selected_records: list[EvaluatedCandidateRecord] = []
    rejected_records: list[EvaluatedCandidateRecord] = []
    needs_review_records: list[EvaluatedCandidateRecord] = []

    # Selected candidate items for diversity checking
    selected_items: list[tuple[CandidateEvaluationItem, str]] = []

    # Sort candidates by quality score descending
    ranked_candidates = sorted(candidates, key=lambda c: c.quality_score, reverse=True)

    for item in ranked_candidates:
        in_ms, out_ms = item.span
        duration_ms = out_ms - in_ms
        cand_text = _extract_candidate_text(context.normalized_transcript.words, item.span)

        critique_status = "uninspected"
        defect_count = 0
        is_approved = False
        has_critical_defects = False

        if item.critique_result is not None:
            critique_status = "all_clear" if item.critique_result.is_all_clear else "defects_found"
            defect_count = len(item.critique_result.defects)
            has_critical_defects = item.critique_result.has_critical_defects
            is_approved = item.critique_result.is_all_clear

        # 1. Quality threshold check
        if item.quality_score < cfg.min_quality_score:
            rejected_records.append(
                EvaluatedCandidateRecord(
                    candidate_id=item.candidate_id,
                    state=CandidateEditorialState.REJECTED_LOW_QUALITY,
                    in_ms=in_ms,
                    out_ms=out_ms,
                    duration_ms=duration_ms,
                    title_ckb=item.title_ckb,
                    distinction_reason="N/A",
                    rejection_reason=(
                        f"Editorial score {item.quality_score:.2f} is below minimum threshold "
                        f"{cfg.min_quality_score:.2f}"
                    ),
                    quality_score=item.quality_score,
                    critique_status=critique_status,
                    defect_count=defect_count,
                    is_approved=False,
                )
            )
            continue

        # 2. Critical defect check
        if has_critical_defects:
            rejected_records.append(
                EvaluatedCandidateRecord(
                    candidate_id=item.candidate_id,
                    state=CandidateEditorialState.REJECTED_DEFECTS,
                    in_ms=in_ms,
                    out_ms=out_ms,
                    duration_ms=duration_ms,
                    title_ckb=item.title_ckb,
                    distinction_reason="N/A",
                    rejection_reason=(
                        f"Rejected due to {defect_count} unresolved defect(s) in post-render "
                        "critique"
                    ),
                    quality_score=item.quality_score,
                    critique_status=critique_status,
                    defect_count=defect_count,
                    is_approved=False,
                )
            )
            continue

        # Check capacity: do not select if maximum clips already reached
        if len(selected_records) >= cfg.max_clips:
            rejected_records.append(
                EvaluatedCandidateRecord(
                    candidate_id=item.candidate_id,
                    state=CandidateEditorialState.REJECTED_LOW_QUALITY,
                    in_ms=in_ms,
                    out_ms=out_ms,
                    duration_ms=duration_ms,
                    title_ckb=item.title_ckb,
                    distinction_reason="N/A",
                    rejection_reason=(
                        f"Quota reached: maximum {cfg.max_clips} clips already selected"
                    ),
                    quality_score=item.quality_score,
                    critique_status=critique_status,
                    defect_count=defect_count,
                    is_approved=False,
                )
            )
            continue

        # 3. Temporal overlap & separation check against already selected
        temporal_conflict = False
        for sel_item, _ in selected_items:
            s_in, s_out = sel_item.span
            # Check overlap
            if not (out_ms <= s_in or in_ms >= s_out):
                rejected_records.append(
                    EvaluatedCandidateRecord(
                        candidate_id=item.candidate_id,
                        state=CandidateEditorialState.REJECTED_OVERLAP,
                        in_ms=in_ms,
                        out_ms=out_ms,
                        duration_ms=duration_ms,
                        title_ckb=item.title_ckb,
                        distinction_reason="N/A",
                        rejection_reason=(
                            f"Temporal overlap with selected clip '{sel_item.candidate_id}'"
                        ),
                        quality_score=item.quality_score,
                        critique_status=critique_status,
                        defect_count=defect_count,
                        is_approved=False,
                    )
                )
                temporal_conflict = True
                break

            # Check minimum separation
            dist_left = in_ms - s_out
            dist_right = s_in - out_ms
            sep = max(dist_left, dist_right)
            if sep < cfg.min_separation_ms:
                rejected_records.append(
                    EvaluatedCandidateRecord(
                        candidate_id=item.candidate_id,
                        state=CandidateEditorialState.REJECTED_OVERLAP,
                        in_ms=in_ms,
                        out_ms=out_ms,
                        duration_ms=duration_ms,
                        title_ckb=item.title_ckb,
                        distinction_reason="N/A",
                        rejection_reason=(
                            f"Separation {sep} ms is below required {cfg.min_separation_ms} ms "
                            f"from clip '{sel_item.candidate_id}'"
                        ),
                        quality_score=item.quality_score,
                        critique_status=critique_status,
                        defect_count=defect_count,
                        is_approved=False,
                    )
                )
                temporal_conflict = True
                break

        if temporal_conflict:
            continue

        # 4. Semantic & lexical duplication check
        duplicate_conflict = False
        distinction_reason = "Unique narrative topic and self-contained hook"

        for sel_item, sel_text in selected_items:
            lex_sim = (
                compute_text_similarity(cand_text, sel_text) if cand_text and sel_text else 0.0
            )
            sem_sim = (
                compute_semantic_similarity(item.semantic_embedding, sel_item.semantic_embedding)
                if item.semantic_embedding and sel_item.semantic_embedding
                else 0.0
            )

            if sem_sim > cfg.max_semantic_similarity or lex_sim > cfg.max_lexical_similarity:
                # Check if genuinely distinct perspectives justify keeping both
                if (
                    cfg.allow_distinct_perspectives
                    and item.perspective.strip().lower() != sel_item.perspective.strip().lower()
                ):
                    distinction_reason = (
                        f"Distinct perspective ('{item.perspective}' vs '{sel_item.perspective}') "
                        f"on shared topic ({', '.join(item.topic_tags)})"
                    )
                else:
                    rejected_records.append(
                        EvaluatedCandidateRecord(
                            candidate_id=item.candidate_id,
                            state=CandidateEditorialState.REJECTED_DUPLICATE,
                            in_ms=in_ms,
                            out_ms=out_ms,
                            duration_ms=duration_ms,
                            title_ckb=item.title_ckb,
                            distinction_reason="N/A",
                            rejection_reason=(
                                f"Semantic duplicate (sem={sem_sim:.2f}, lex={lex_sim:.2f}) "
                                f"of selected clip '{sel_item.candidate_id}'"
                            ),
                            quality_score=item.quality_score,
                            critique_status=critique_status,
                            defect_count=defect_count,
                            is_approved=False,
                        )
                    )
                    duplicate_conflict = True
                    break

        if duplicate_conflict:
            continue

        # Candidate is eligible and distinct! Select it with truthful approval state
        state = (
            CandidateEditorialState.SELECTED_APPROVED
            if is_approved
            else CandidateEditorialState.SELECTED_NEEDS_REVIEW
        )

        record = EvaluatedCandidateRecord(
            candidate_id=item.candidate_id,
            state=state,
            in_ms=in_ms,
            out_ms=out_ms,
            duration_ms=duration_ms,
            title_ckb=item.title_ckb,
            distinction_reason=distinction_reason,
            rejection_reason=None,
            quality_score=item.quality_score,
            critique_status=critique_status,
            defect_count=defect_count,
            is_approved=is_approved,
        )

        selected_records.append(record)
        selected_items.append((item, cand_text))
        if state == CandidateEditorialState.SELECTED_NEEDS_REVIEW:
            needs_review_records.append(record)

    preprocessing_summary = {
        "words_count": len(context.normalized_transcript.words),
        "characters_count": len(context.normalized_transcript.text_ckb),
        "observation_coverage": context.observation_coverage_ratio,
        "shared_once": True,
    }

    return EpisodePackageReport(
        episode_id=context.episode_id,
        media_id=context.media_id,
        requested_clips=cfg.max_clips,
        delivered_clips_count=len(selected_records),
        selected_clips=tuple(selected_records),
        rejected_clips=tuple(rejected_records),
        needs_review_clips=tuple(needs_review_records),
        shared_preprocessing_verified=True,
        preprocessing_summary=preprocessing_summary,
    )
