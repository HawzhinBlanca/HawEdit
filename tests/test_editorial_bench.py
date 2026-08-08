from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hawedit.corpus import Dialect
from hawedit.editorial_bench import (
    EditorialComparison,
    EditorialRegressionSet,
    Preference,
)
from hawedit.judge import JUDGE_SHADOW, KURDISH_EDITORIAL_JUDGE, JudgeVerdict


def verdict(model: str) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id="c1",
        hook_score=0.8,
        self_contained=True,
        payoff_at_ms=1_500,
        meaning_fidelity=0.9,
        misleading_edit_risk=0.02,
        cultural_landing=0.8,
        narrative_role="payoff",
        title_ckb="ڕۆژنامەوانی کوردی",
        description_ckb="بابەتێکی گرنگی کوردی",
        hashtags_ckb=("#کوردی",),
        judge=model,
        clip_in_ms=1_000,
        clip_out_ms=2_000,
    )


def comparison(index: int, media: Path, preference: Preference) -> EditorialComparison:
    dialect = tuple(Dialect)[index % len(Dialect)]
    return EditorialComparison(
        item_id=f"item-{index:02d}",
        media_path=media.name,
        dialect=dialect,
        incumbent=verdict(KURDISH_EDITORIAL_JUDGE),
        shadow=verdict(JUDGE_SHADOW),
        preference=preference,
        reviewers=("reviewer-a", "reviewer-b"),
    )


def test_real_balanced_set_produces_the_existing_promotion_decision(tmp_path: Path) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"real source placeholder")
    items = tuple(
        comparison(i, media, Preference.SHADOW if i < 16 else Preference.INCUMBENT)
        for i in range(20)
    )
    report = EditorialRegressionSet("client-sorani", "client-owner", False, items).evaluate(
        tmp_path
    )
    assert report.total_items == 20
    assert report.decision.switch
    assert set(report.items_by_dialect) == set(Dialect)


def test_interim_or_tiny_sets_cannot_claim_real_editorial_evidence(tmp_path: Path) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"x")
    items = tuple(comparison(i, media, Preference.TIE) for i in range(20))
    with pytest.raises(ValueError, match="interim"):
        EditorialRegressionSet("synthetic", "test author", True, items).evaluate(tmp_path)
    with pytest.raises(ValueError, match="promotion floor"):
        EditorialRegressionSet("tiny", "client", False, items[:5]).evaluate(tmp_path)


def test_judges_must_have_scored_the_exact_same_footage(tmp_path: Path) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"x")
    with pytest.raises(ValueError, match="different candidates/spans"):
        EditorialComparison(
            item_id="mismatch",
            media_path=media.name,
            dialect=Dialect.HEWLER,
            incumbent=verdict(KURDISH_EDITORIAL_JUDGE),
            shadow=replace(verdict(JUDGE_SHADOW), clip_out_ms=2_100),
            preference=Preference.INCUMBENT,
            reviewers=("a", "b"),
        )


def test_missing_media_or_single_reviewer_is_refused(tmp_path: Path) -> None:
    media = tmp_path / "source.mp4"
    with pytest.raises(ValueError, match="two named"):
        replace(comparison(0, media, Preference.TIE), reviewers=("one",))
    items = tuple(comparison(i, media, Preference.TIE) for i in range(20))
    with pytest.raises(FileNotFoundError, match="item"):
        EditorialRegressionSet("real", "client", False, items).evaluate(tmp_path)
