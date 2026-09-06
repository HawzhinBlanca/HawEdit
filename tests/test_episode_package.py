"""Tests for episode packaging with shared preprocessing and truthful states (VE-13)."""

from __future__ import annotations

import pytest

from hawedit.episode_package import (
    CandidateEditorialState,
    CandidateEvaluationItem,
    EpisodePackageConfig,
    EpisodePackageReport,
    SharedEpisodeContext,
    build_episode_package,
    compute_semantic_similarity,
)
from hawedit.render_critic import (
    CritiqueInspectionResult,
    DefectKind,
    DefectSeverity,
    PermittedRepair,
    RenderDefect,
)
from hawedit.transcripts import NormalizedTranscript, Word


def test_episode_visual_delivery_shares_preprocessing_and_reports_each_state() -> None:
    """VE-13: Delivers up to N distinct clips sharing preprocessing and reporting truthful states.

    WHEN an episode requests N clips, THE system SHALL share preprocessing and return up to N
    distinct eligible, independently checked candidates with truthful per-item states.
    """
    words = (
        Word("ئەمڕۆ", 0, 1000, 0.99),
        Word("باسی", 1000, 2000, 0.99),
        Word("بازاڕ", 2000, 3000, 0.98),
        Word("دەکەین", 3000, 4000, 0.99),
        Word("کە", 4000, 4500, 0.99),
        Word("چۆن", 4500, 5000, 0.99),
        Word("داهات", 5000, 6000, 0.98),
        Word("زیاد", 6000, 7000, 0.99),
        Word("دەکات", 7000, 8000, 0.99),
    )
    norm_transcript = NormalizedTranscript(
        media_id="podcast_ep01",
        text_ckb=" ".join(w.w for w in words),
        source_sha256="abc123sha",
        words=words,
    )

    # 1. Preprocessing is shared once across the entire episode
    shared_context = SharedEpisodeContext(
        episode_id="ep_kurdish_talk_01",
        media_id="podcast_ep01",
        duration_ms=600000,  # 10-minute podcast
        normalized_transcript=norm_transcript,
        observation_coverage_ratio=1.0,
        total_source_tokens=25000,
    )

    # Candidate 1: High quality (0.92), all-clear critique -> Should be SELECTED_APPROVED
    critique_clean_1 = CritiqueInspectionResult(
        inspection_id="crit_01",
        render_path="work/renders/cand_01.mp4",
        duration_ms=35000,
        coverage_ratio=1.0,
        windows=(),
        defects=(),
        is_all_clear=True,
        all_clear_refused=False,
    )
    cand_1 = CandidateEvaluationItem(
        candidate_id="cand_01",
        span=(10000, 45000),
        title_ckb="کارتێکەری ئابووری بازاڕ",
        topic_tags=("ئابووری", "بازاڕ"),
        core_claim="گەشەی بازاڕ دەبێتە هۆی بەرزبوونەوەی داهات",
        perspective="economic_impact",
        quality_score=0.92,
        semantic_embedding=(0.8, 0.6, 0.1, 0.0),
        critique_result=critique_clean_1,
    )

    # Candidate 2: High quality (0.88), shares topic but has distinct perspective
    # -> Should be SELECTED_APPROVED with distinction reason noted!
    critique_clean_2 = CritiqueInspectionResult(
        inspection_id="crit_02",
        render_path="work/renders/cand_02.mp4",
        duration_ms=40000,
        coverage_ratio=1.0,
        windows=(),
        defects=(),
        is_all_clear=True,
        all_clear_refused=False,
    )
    cand_2 = CandidateEvaluationItem(
        candidate_id="cand_02",
        span=(80000, 120000),
        title_ckb="مێژووی سەرهەڵدانی بازاڕ",
        topic_tags=("ئابووری", "بازاڕ"),
        core_claim="سەرەتای دروستبوونی بازاڕی نوێ لە کوردستان",
        perspective="historical_background",  # Distinct perspective!
        quality_score=0.88,
        semantic_embedding=(0.78, 0.59, 0.12, 0.02),  # Similar topic vector
        critique_result=critique_clean_2,
    )

    # Candidate 3: High quality (0.86), but duplicate perspective & high semantic
    # overlap with cand_1
    # -> Should be REJECTED_DUPLICATE (no duplicate weak fillers!)
    cand_3_dup = CandidateEvaluationItem(
        candidate_id="cand_03_dup",
        span=(150000, 190000),
        title_ckb="داهات و بازاڕی ئابووری",
        topic_tags=("ئابووری", "بازاڕ"),
        core_claim="داهات چۆن لە بازاڕ گەشە دەکات",
        perspective="economic_impact",  # Duplicate perspective!
        quality_score=0.86,
        semantic_embedding=(0.81, 0.59, 0.09, 0.01),  # Cosine similarity > 0.99
        critique_result=critique_clean_1,
    )

    # Candidate 4: Good quality (0.84), but has unresolved critical defect in critique
    # -> Should be REJECTED_DEFECTS
    critique_damaged = CritiqueInspectionResult(
        inspection_id="crit_04",
        render_path="work/renders/cand_04.mp4",
        duration_ms=30000,
        coverage_ratio=1.0,
        windows=(),
        defects=(
            RenderDefect(
                defect_id="def_crit_04",
                timestamp_ms=5000,
                end_timestamp_ms=10000,
                severity=DefectSeverity.CRITICAL,
                defect_kind=DefectKind.LOST_DEMONSTRATION_OR_CHART,
                observation="Chart cropped out",
                source_reference="chart_04",
                permitted_repair=PermittedRepair.ADJUST_CROP,
            ),
        ),
        is_all_clear=False,
        all_clear_refused=True,
    )
    cand_4_defective = CandidateEvaluationItem(
        candidate_id="cand_04_defective",
        span=(220000, 250000),
        title_ckb="نموونەی نەخشەی داهات",
        topic_tags=("داهات",),
        core_claim="شیکردنەوەی گرافیکی داهات",
        perspective="technical_analysis",
        quality_score=0.84,
        semantic_embedding=(0.2, 0.3, 0.8, 0.4),
        critique_result=critique_damaged,
    )

    # Candidate 5: Low quality score (0.42) below minimum threshold
    # -> Should be REJECTED_LOW_QUALITY
    cand_5_low = CandidateEvaluationItem(
        candidate_id="cand_05_low",
        span=(300000, 330000),
        title_ckb="وتەی ئاسایی",
        topic_tags=("گشتی",),
        core_claim="قسەی سەرەتایی بێ هۆک",
        perspective="general_talk",
        quality_score=0.42,  # Below 0.60
        semantic_embedding=(0.1, 0.1, 0.1, 0.1),
    )

    # Candidate 6: Overlaps temporally with Candidate 1
    # -> Should be REJECTED_OVERLAP
    cand_6_overlap = CandidateEvaluationItem(
        candidate_id="cand_06_overlap",
        span=(30000, 60000),  # Overlaps cand_1 (10000..45000)
        title_ckb="کۆتایی باسی بازاڕ",
        topic_tags=("بازاڕ",),
        core_claim="تەواوکەری وتەکە",
        perspective="extension",
        quality_score=0.89,
        semantic_embedding=(0.1, 0.9, 0.1, 0.1),
    )

    candidates = (cand_1, cand_2, cand_3_dup, cand_4_defective, cand_5_low, cand_6_overlap)

    # Build episode package requesting max 3 clips
    report: EpisodePackageReport = build_episode_package(
        context=shared_context,
        candidates=candidates,
        config=EpisodePackageConfig(
            max_clips=3,
            min_separation_ms=15000,
            max_semantic_similarity=0.80,
            min_quality_score=0.60,
            allow_distinct_perspectives=True,
        ),
    )

    # Verification 1: Shared preprocessing was used once
    assert report.shared_preprocessing_verified is True
    assert report.preprocessing_summary["words_count"] == len(words)
    assert report.preprocessing_summary["shared_once"] is True

    # Verification 2: Up to N clips returned — strictly DOES NOT FORCE 3 CLIPS!
    # Only 2 genuinely distinct, eligible clips qualified
    assert report.requested_clips == 3
    assert report.delivered_clips_count == 2
    assert len(report.selected_clips) == 2

    # Verification 3: Truthful per-item status for selected clips
    selected_ids = [c.candidate_id for c in report.selected_clips]
    assert selected_ids == ["cand_01", "cand_02"]
    for c in report.selected_clips:
        assert c.state == CandidateEditorialState.SELECTED_APPROVED
        assert c.is_approved is True
        assert c.rejection_reason is None

    # Cand 2 was accepted on shared topic because it provided a distinct perspective!
    c2 = next(c for c in report.selected_clips if c.candidate_id == "cand_02")
    assert "historical_background" in c2.distinction_reason

    # Verification 4: Truthful rejection records with clear reasons
    rejected_dict = {c.candidate_id: c for c in report.rejected_clips}

    # Duplicate rejected
    assert rejected_dict["cand_03_dup"].state == CandidateEditorialState.REJECTED_DUPLICATE
    assert "Semantic duplicate" in str(rejected_dict["cand_03_dup"].rejection_reason)

    # Defective rejected
    assert rejected_dict["cand_04_defective"].state == CandidateEditorialState.REJECTED_DEFECTS
    assert "unresolved defect" in str(rejected_dict["cand_04_defective"].rejection_reason)

    # Low quality rejected
    assert rejected_dict["cand_05_low"].state == CandidateEditorialState.REJECTED_LOW_QUALITY
    assert "below minimum threshold" in str(rejected_dict["cand_05_low"].rejection_reason)

    # Overlapping rejected
    assert rejected_dict["cand_06_overlap"].state == CandidateEditorialState.REJECTED_OVERLAP
    assert "Temporal overlap" in str(rejected_dict["cand_06_overlap"].rejection_reason)


def test_semantic_similarity_computation() -> None:
    """VE-13: compute_semantic_similarity computes cosine similarity with boundary invariants."""
    vec_a = (1.0, 0.0, 0.0)
    vec_b = (1.0, 0.0, 0.0)
    vec_c = (0.0, 1.0, 0.0)

    # Identical vectors -> 1.0
    assert compute_semantic_similarity(vec_a, vec_b) == pytest.approx(1.0)

    # Orthogonal vectors -> 0.0
    assert compute_semantic_similarity(vec_a, vec_c) == pytest.approx(0.0)

    # Empty or mismatched dimensions -> 0.0
    assert compute_semantic_similarity((), ()) == 0.0
    assert compute_semantic_similarity(vec_a, (1.0, 0.0)) == 0.0
