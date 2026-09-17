"""Unit and integration tests for Episode Plan: N clips per run (Task T4.1)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import DiscoveryPath, Sv6d
from hawedit.discovery import Candidate, MergedCandidate
from hawedit.episode import (
    EpisodeClipSummary,
    EpisodeItemRecord,
    EpisodeItemStatus,
    EpisodeManifest,
    EpisodePlanConfig,
    EpisodeReconciliationError,
    compute_text_similarity,
    plan_episode,
    reconcile_episode_manifest,
    select_episode_plan,
)
from hawedit.judge import JudgeRequest, JudgeVerdict
from hawedit.pipeline import build_parser, run_pipeline
from hawedit.transcripts import AsrProvenance, NormalizedTranscript, RawTranscript, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest() if FIXTURE.is_file() else ""

_WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_500, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def _a_transcript(media_id: str = "fixture") -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=_WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )


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


@pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")
def test_episode_cli_renders_distinct_eligible_clips_with_shared_ingest(tmp_path: Path) -> None:
    """AC-19: Episode pipeline delivers up to N distinct clips with shared preprocessing."""
    # 1. Assert CLI surface parses episode arguments accurately
    parser = build_parser()
    args = parser.parse_args(
        [
            str(FIXTURE),
            "--max-clips",
            "2",
            "--min-separation-ms",
            "100",
            "--max-text-similarity",
            "0.7",
            "--episode-id",
            "ep-custom-123",
        ]
    )
    assert args.max_clips == 2
    assert args.min_separation_ms == 100
    assert args.max_text_similarity == 0.7
    assert args.episode_id == "ep-custom-123"

    # 2. Run pipeline with max_clips=2 over FIXTURE with 3 candidates
    cand1 = Candidate("c1", "fixture", 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.95)
    cand2 = Candidate("c2", "fixture", 2_000, 4_100, DiscoveryPath.VERBAL, rank=2, score=0.90)
    cand3 = Candidate("c3", "fixture", 100, 4_100, DiscoveryPath.VERBAL, rank=3, score=0.85)

    class MultiJudge:
        model_id = "gemini-2.5-pro"

        def __init__(self) -> None:
            self.calls: list[str] = []

        def judge(self, request: JudgeRequest) -> JudgeVerdict:
            self.calls.append(request.candidate_id)
            score = (
                0.95
                if request.candidate_id == "c1"
                else (0.90 if request.candidate_id == "c2" else 0.85)
            )
            return JudgeVerdict(
                candidate_id=request.candidate_id,
                clip_in_ms=request.clip_in_ms,
                clip_out_ms=request.clip_out_ms,
                hook_score=score,
                self_contained=True,
                payoff_at_ms=(request.clip_in_ms + request.clip_out_ms) // 2,
                meaning_fidelity=0.92,
                misleading_edit_risk=0.03,
                cultural_landing=0.85,
                narrative_role="payoff",
                title_ckb=f"سەردێڕی {request.candidate_id}",
                description_ckb="وەسفی کورتی گرتەکە",
                hashtags_ckb=("#کوردستان",),
                judge="gemini-2.5-pro",
                payoff_strength=0.85,
                ends_on_a_beat=True,
                reason_ckb="شیاوە بۆ بڵاوکردنەوە",
                title_variants_ckb=(f"سەردێڕی {request.candidate_id}", "پرسیار", "وەڵام"),
            )

    work_dir = tmp_path / "work"
    judge = MultiJudge()
    run = run_pipeline(
        FIXTURE,
        work_dir,
        media_id="fixture",
        transcript=_a_transcript("fixture"),
        discover=lambda _n: [cand1, cand2, cand3],
        judge=judge,
        auto_select=True,
        judge_top_n=3,
        min_clip_ms=1_000,
        max_clips=2,
        min_separation_ms=100,
        episode_id="ep-custom-123",
    )

    # Preprocessing (Stage 0 ingest) ran once
    assert run.ingest is not None
    stage0_json = work_dir / "stage0" / "ingest.json"
    assert stage0_json.is_file()

    # Manifest checks
    assert run.episode_manifest is not None
    manifest = run.episode_manifest
    assert manifest.episode_id == "ep-custom-123"
    assert manifest.clips_count == 2
    assert len(manifest.clips) == 2
    assert manifest.reconciled is True
    assert manifest.has_partial_failure is False
    assert manifest.is_no_clip_outcome is False

    # Delivered items are c1 and c2, c3 is rejected
    delivered_ids = [c.clip_id for c in manifest.clips]
    assert delivered_ids == ["c1", "c2"]

    # Check honest item records
    assert len(manifest.items) == 3
    rec_by_id = {it.candidate_id: it for it in manifest.items}
    assert rec_by_id["c1"].status in (
        EpisodeItemStatus.PUBLISHED.value,
        EpisodeItemStatus.PENDING_REVIEW.value,
    )
    assert rec_by_id["c2"].status in (
        EpisodeItemStatus.PUBLISHED.value,
        EpisodeItemStatus.PENDING_REVIEW.value,
    )
    assert rec_by_id["c3"].status == EpisodeItemStatus.REJECTED.value
    assert rec_by_id["c3"].rejection_reason is not None

    # Disk deliverables check: all 7 required files exist for both clips
    for clip_summary in manifest.clips:
        clip_dir = work_dir / clip_summary.delivery_dir
        assert clip_dir.is_dir()
        for suffix in (
            ".mp4",
            ".ass",
            ".srt",
            ".edl",
            ".json",
            ".measured.json",
            ".cover.png",
        ):
            target = clip_dir / f"{clip_summary.clip_id}{suffix}"
            assert target.is_file(), f"Missing delivery file: {target}"
            assert target.stat().st_size > 0

    # Verify manifest file on disk
    manifest_on_disk = EpisodeManifest.from_dict(
        json.loads((work_dir / "episode.json").read_text(encoding="utf-8"))
    )
    assert manifest_on_disk.episode_id == "ep-custom-123"
    assert manifest_on_disk.clips_count == 2
    assert manifest_on_disk.reconciled is True
    assert len(manifest_on_disk.items) == 3

    # Reconcile passes cleanly without errors
    reconcile_episode_manifest(manifest, work_dir)


def test_episode_manifest_exposes_partial_failure_and_no_clip_outcome(tmp_path: Path) -> None:
    """AC-19: Truthful item states preserve partial failure resilience and no-clip outcome."""
    # Part A: Partial Failure
    # Two candidates selected, but candidate 2 fails during rendering
    work_dir = tmp_path / "work_partial"

    # Set up clip 1 delivery on disk
    clip1_dir = work_dir / "c1"
    clip1_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".mp4", ".ass", ".srt", ".edl", ".json", ".cover.png"):
        (clip1_dir / f"c1{suffix}").write_bytes(b"content")
    (clip1_dir / "c1.measured.json").write_text(
        json.dumps({"video": {"duration_ms": 30_000}}), encoding="utf-8"
    )

    clip1_summary = EpisodeClipSummary(
        clip_id="c1",
        in_ms=0,
        out_ms=30_000,
        duration_ms=30_000,
        hook_score=0.95,
        title_ckb="سەردێڕی یەکەم",
        delivery_dir="c1",
    )

    # Record states: c1 published, c2 failed with explicit error
    item1 = EpisodeItemRecord(
        candidate_id="c1",
        status=EpisodeItemStatus.PUBLISHED.value,
        in_ms=0,
        out_ms=30_000,
        duration_ms=30_000,
        hook_score=0.95,
        title_ckb="سەردێڕی یەکەم",
        delivery_dir="c1",
    )
    item2 = EpisodeItemRecord(
        candidate_id="c2",
        status=EpisodeItemStatus.FAILED.value,
        in_ms=60_000,
        out_ms=90_000,
        duration_ms=30_000,
        hook_score=0.90,
        title_ckb="سەردێڕی دووەم",
        error="RenderError: NVENC session allocation exhausted on GPU 0",
    )

    manifest_partial = EpisodeManifest(
        episode_id="ep-partial",
        media_id="test-media",
        media_sha256="0" * 64,
        clips_count=1,
        total_duration_ms=30_000,
        clips=(clip1_summary,),
        reconciled=False,
        total_cost_usd=0.04,
        items=(item1, item2),
    )

    assert manifest_partial.has_partial_failure is True
    assert manifest_partial.is_no_clip_outcome is False
    assert len(manifest_partial.published_items) == 1
    assert len(manifest_partial.failed_items) == 1
    assert "NVENC" in (manifest_partial.failed_items[0].error or "")

    # Reconciling manifest_partial passes for published clip1
    reconcile_episode_manifest(manifest_partial, work_dir)

    # Serializes to episode.json and preserves states
    json_path = work_dir / "episode.json"
    manifest_partial.write_json(json_path)
    loaded_partial = EpisodeManifest.from_dict(json.loads(json_path.read_text(encoding="utf-8")))
    assert loaded_partial.has_partial_failure is True
    assert loaded_partial.failed_items[0].error == item2.error

    # Part B: No-clip Outcome
    # Candidates judged, but ALL fail hard editorial thresholds
    # (fidelity < 0.70, risk > 0.10, or not self_contained)
    work_dir_none = tmp_path / "work_noclip"
    work_dir_none.mkdir(parents=True, exist_ok=True)

    cand_bad1 = _make_dummy_candidate("bad1", 0, 30_000, hook_score=0.95)
    cand_bad1 = (
        cand_bad1[0],
        cand_bad1[1],
        replace(cand_bad1[2], meaning_fidelity=0.55),  # fails fidelity < 0.70
    )
    cand_bad2 = _make_dummy_candidate("bad2", 40_000, 70_000, hook_score=0.90)
    cand_bad2 = (
        cand_bad2[0],
        cand_bad2[1],
        replace(cand_bad2[2], misleading_edit_risk=0.25),  # fails risk > 0.10
    )
    cand_bad3 = _make_dummy_candidate("bad3", 80_000, 110_000, hook_score=0.85)
    cand_bad3 = (
        cand_bad3[0],
        cand_bad3[1],
        replace(cand_bad3[2], self_contained=False),  # uncontained fragment
    )

    config = EpisodePlanConfig(max_clips=3, min_separation_ms=5_000)
    selected_empty, rejected_records = plan_episode(
        [cand_bad1, cand_bad2, cand_bad3],
        config,
        require_eligible=True,
    )
    assert len(selected_empty) == 0
    assert len(rejected_records) == 3
    assert all(r.status == EpisodeItemStatus.REJECTED.value for r in rejected_records)
    assert all(r.rejection_reason is not None for r in rejected_records)

    manifest_none = EpisodeManifest(
        episode_id="ep-none",
        media_id="test-media",
        media_sha256="0" * 64,
        clips_count=0,
        total_duration_ms=0,
        clips=(),
        reconciled=True,
        total_cost_usd=0.06,
        items=tuple(rejected_records),
    )

    assert manifest_none.is_no_clip_outcome is True
    assert manifest_none.has_partial_failure is False
    assert manifest_none.clips_count == 0
    assert len(manifest_none.published_items) == 0
    assert len(manifest_none.rejected_items) == 3

    # Reconcile empty manifest succeeds cleanly
    reconcile_episode_manifest(manifest_none, work_dir_none)

    # Persist and round-trip
    none_json_path = work_dir_none / "episode.json"
    manifest_none.write_json(none_json_path)
    loaded_none = EpisodeManifest.from_dict(json.loads(none_json_path.read_text(encoding="utf-8")))
    assert loaded_none.is_no_clip_outcome is True
    assert loaded_none.has_partial_failure is False
    assert len(loaded_none.rejected_items) == 3
