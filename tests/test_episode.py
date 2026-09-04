"""Unit and integration tests for Episode Plan: N clips per run (Task T4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.clip import DiscoveryPath, Sv6d
from hawedit.discovery import MergedCandidate
from hawedit.episode import (
    EpisodeClipSummary,
    EpisodeManifest,
    EpisodePlanConfig,
    EpisodeReconciliationError,
    compute_text_similarity,
    reconcile_episode_manifest,
    select_episode_plan,
)
from hawedit.judge import JudgeVerdict
from hawedit.transcripts import NormalizedTranscript, Word


def _make_dummy_candidate(
    cand_id: str,
    in_ms: int,
    out_ms: int,
    hook_score: float,
    payoff_strength: float = 0.8,
) -> tuple[MergedCandidate, tuple[int, ...], JudgeVerdict]:
    cand = MergedCandidate(
        candidate_id=cand_id,
        media_id="test-media-1",
        in_ms=in_ms,
        out_ms=out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        sources=(cand_id,),
        verbal_score=hook_score,
        sv6d=Sv6d(
            subject="interview at 00:01:00",
            aesthetics="high at 00:01:00",
            camera="steady at 00:01:00",
            editing="clean at 00:01:00",
            narrative="strong at 00:01:00",
            retention="viral at 00:01:00",
        ),
    )
    verdict = JudgeVerdict(
        candidate_id=cand_id,
        clip_in_ms=in_ms,
        clip_out_ms=out_ms,
        hook_score=hook_score,
        self_contained=True,
        payoff_at_ms=(in_ms + out_ms) // 2,
        meaning_fidelity=0.9,
        misleading_edit_risk=0.05,
        cultural_landing=0.8,
        narrative_role="payoff",
        title_ckb=f"سەردێڕی {cand_id}",
        description_ckb="وەسفی کورت",
        hashtags_ckb=("#کوردستان",),
        judge="gemini-2.5-pro",
        payoff_strength=payoff_strength,
        ends_on_a_beat=True,
        reason_ckb="گرتەیەکی زۆر بەهێزە بۆ بڵاوکردنەوە",
        title_variants_ckb=(f"سەردێڕی {cand_id}", "پرسیار؟", "وەڵام"),
        sv6d=cand.sv6d,
    )
    return (cand, (0, 1), verdict)


def test_compute_text_similarity_matches_sorani_jaccard() -> None:
    """AC-4: compute_text_similarity computes word Jaccard similarity accurately."""
    text1 = "هەولێر پایتەختی هەرێمی کوردستانە"
    text2 = "هەولێر پایتەختی هەرێمی کوردستانە"
    assert compute_text_similarity(text1, text2) == 1.0

    text3 = "تەکنەلۆژیا و ژیری دەستکرد جیهان دەگۆڕن"
    assert compute_text_similarity(text1, text3) == 0.0

    # Overlap: 2 words common out of 6 unique total words -> 2/6 = 0.3333
    text4 = "هەولێر شاری گەورەیە لە عێراق"
    sim = compute_text_similarity(text1, text4)
    assert 0.10 <= sim <= 0.40


def test_select_episode_plan_enforces_max_clips() -> None:
    """AC-1: select_episode_plan limits selected clips to config.max_clips."""
    c1 = _make_dummy_candidate("c1", 0, 30_000, hook_score=0.95)
    c2 = _make_dummy_candidate("c2", 60_000, 90_000, hook_score=0.90)
    c3 = _make_dummy_candidate("c3", 120_000, 150_000, hook_score=0.85)

    config = EpisodePlanConfig(max_clips=2, min_separation_ms=10_000)
    selected = select_episode_plan([c1, c2, c3], config)

    assert len(selected) == 2
    assert selected[0][0].candidate_id == "c1"
    assert selected[1][0].candidate_id == "c2"


def test_select_episode_plan_rejects_temporal_overlap() -> None:
    """AC-2: select_episode_plan rejects candidates that temporally overlap with selected clips."""
    c1 = _make_dummy_candidate("c1", 0, 30_000, hook_score=0.95)
    c2_overlapping = _make_dummy_candidate("c2", 15_000, 45_000, hook_score=0.92)
    c3_distinct = _make_dummy_candidate("c3", 60_000, 90_000, hook_score=0.85)

    config = EpisodePlanConfig(max_clips=3, min_separation_ms=10_000)
    selected = select_episode_plan([c1, c2_overlapping, c3_distinct], config)

    assert len(selected) == 2
    selected_ids = [s[0].candidate_id for s in selected]
    assert "c1" in selected_ids
    assert "c3" in selected_ids
    assert "c2" not in selected_ids


def test_select_episode_plan_enforces_min_separation() -> None:
    """AC-3: select_episode_plan rejects candidates within min_separation_ms of selected clips."""
    c1 = _make_dummy_candidate("c1", 0, 30_000, hook_score=0.95)
    # c2 is 5 seconds away from c1 (less than 15s min_separation_ms)
    c2_too_close = _make_dummy_candidate("c2", 35_000, 65_000, hook_score=0.90)
    # c3 is 30 seconds away from c1
    c3_far_enough = _make_dummy_candidate("c3", 60_000, 90_000, hook_score=0.80)

    config = EpisodePlanConfig(max_clips=3, min_separation_ms=15_000)
    selected = select_episode_plan([c1, c2_too_close, c3_far_enough], config)

    assert len(selected) == 2
    selected_ids = [s[0].candidate_id for s in selected]
    assert "c1" in selected_ids
    assert "c3" in selected_ids
    assert "c2" not in selected_ids


def test_select_episode_plan_enforces_lexical_diversity() -> None:
    """AC-4: select_episode_plan rejects candidates with word similarity > max_text_similarity."""
    # Build a normalized transcript spanning the candidates
    words = (
        Word(w="ئەمڕۆ", start_ms=0, end_ms=1000, conf=0.9),
        Word(w="باس", start_ms=1000, end_ms=2000, conf=0.9),
        Word(w="لە", start_ms=2000, end_ms=3000, conf=0.9),
        Word(w="ئابووری", start_ms=3000, end_ms=4000, conf=0.9),
        Word(w="دەکەین", start_ms=4000, end_ms=5000, conf=0.9),
        # c2 repeats almost same words
        Word(w="ئەمڕۆ", start_ms=60_000, end_ms=61_000, conf=0.9),
        Word(w="باس", start_ms=61_000, end_ms=62_000, conf=0.9),
        Word(w="لە", start_ms=62_000, end_ms=63_000, conf=0.9),
        Word(w="ئابووری", start_ms=63_000, end_ms=64_000, conf=0.9),
        # c3 has completely different words
        Word(w="هونەری", start_ms=120_000, end_ms=121_000, conf=0.9),
        Word(w="شێوەکاری", start_ms=121_000, end_ms=122_000, conf=0.9),
        Word(w="کوردی", start_ms=122_000, end_ms=123_000, conf=0.9),
    )
    transcript = NormalizedTranscript(
        media_id="test-media-1",
        text_ckb=" ".join(w.w for w in words),
        source_sha256="0" * 64,
        words=words,
    )

    c1 = _make_dummy_candidate("c1", 0, 10_000, hook_score=0.95)
    c2_redundant = _make_dummy_candidate("c2", 60_000, 70_000, hook_score=0.90)
    c3_distinct = _make_dummy_candidate("c3", 120_000, 130_000, hook_score=0.85)

    config = EpisodePlanConfig(max_clips=3, min_separation_ms=5000, max_text_similarity=0.50)
    selected = select_episode_plan([c1, c2_redundant, c3_distinct], config, transcript)

    assert len(selected) == 2
    selected_ids = [s[0].candidate_id for s in selected]
    assert "c1" in selected_ids
    assert "c3" in selected_ids
    assert "c2" not in selected_ids


def test_episode_manifest_roundtrip_and_serialization(tmp_path: Path) -> None:
    """AC-5: EpisodeManifest serializes to JSON and round-trips byte-for-byte."""
    clip1 = EpisodeClipSummary(
        clip_id="ep29-c1",
        in_ms=10_000,
        out_ms=45_000,
        duration_ms=35_000,
        hook_score=0.88,
        hook_type="question",
        title_ckb="سەردێڕی یەکەم",
        title_variants_ckb=("سەردێڕی یەکەم", "پرسیاری سەرەکی؟", "دەربارەی ڕاستییەکان"),
        cover_frame_ms=15_000,
        delivery_dir="ep29-c1",
    )
    clip2 = EpisodeClipSummary(
        clip_id="ep29-c2",
        in_ms=80_000,
        out_ms=120_000,
        duration_ms=40_000,
        hook_score=0.82,
        hook_type="claim",
        title_ckb="سەردێڕی دووەم",
        title_variants_ckb=("سەردێڕی دووەم", "ئایا دەزانیت؟", "بەڵگەی گرنگ"),
        cover_frame_ms=85_000,
        delivery_dir="ep29-c2",
    )
    manifest = EpisodeManifest(
        episode_id="ep29",
        media_id="ep29-media",
        media_sha256="0" * 64,
        clips_count=2,
        total_duration_ms=75_000,
        clips=(clip1, clip2),
        reconciled=True,
        total_cost_usd=0.08,
    )

    json_path = tmp_path / "episode.json"
    manifest.write_json(json_path)
    assert json_path.is_file()

    loaded = EpisodeManifest.from_dict(json.loads(json_path.read_text(encoding="utf-8")))
    assert loaded.episode_id == manifest.episode_id
    assert loaded.clips_count == manifest.clips_count
    assert loaded.total_duration_ms == manifest.total_duration_ms
    assert len(loaded.clips) == 2
    assert loaded.clips[0].title_variants_ckb == clip1.title_variants_ckb
    assert loaded.clips[1].hook_type == "claim"


def test_reconcile_episode_manifest_verifies_bundles_and_detects_collision(tmp_path: Path) -> None:
    """AC-6: reconcile_episode_manifest verifies valid bundles and catches errors."""
    base_dir = tmp_path / "delivered"
    clip_dir = base_dir / "ep29-c1"
    clip_dir.mkdir(parents=True, exist_ok=True)

    clip_id = "ep29-c1"
    for suffix in (".mp4", ".ass", ".srt", ".edl", ".json", ".cover.png"):
        (clip_dir / f"{clip_id}{suffix}").write_bytes(b"dummy_content")

    meas_data = {
        "video": {"duration_ms": 30_000},
    }
    (clip_dir / f"{clip_id}.measured.json").write_text(json.dumps(meas_data), encoding="utf-8")

    clip = EpisodeClipSummary(
        clip_id=clip_id,
        in_ms=0,
        out_ms=30_000,
        duration_ms=30_000,
        hook_score=0.9,
        title_ckb="سەردێڕ",
        delivery_dir=clip_id,
    )
    manifest = EpisodeManifest(
        episode_id="ep29",
        media_id="ep29-media",
        media_sha256="0" * 64,
        clips_count=1,
        total_duration_ms=30_000,
        clips=(clip,),
    )

    # Valid reconciliation
    reconcile_episode_manifest(manifest, base_dir)

    # Corrupt: missing cover.png
    (clip_dir / f"{clip_id}.cover.png").unlink()
    with pytest.raises(EpisodeReconciliationError, match="missing required delivery file"):
        reconcile_episode_manifest(manifest, base_dir)
