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


# --- the refusals on the promotion evidence itself, none of which any test held ---------------
#
# Measured by neutralising each refusal in a shadow copy of src/hawedit and running this file:
# the `interim`, promotion-floor, span-match and reviewer guards redden something. The six below
# did not. This module is what decides whether the shadow replaces the pinned judge, so a
# comparison assembled wrongly is a promotion argued from evidence about something else.


def test_a_comparison_must_name_its_item_and_its_media(tmp_path: Path) -> None:
    """An unnamed item cannot be traced back to the footage two reviewers watched."""
    media = tmp_path / "source.mp4"
    with pytest.raises(ValueError, match="needs an item_id and media_path"):
        replace(comparison(0, media, Preference.TIE), item_id="   ")
    with pytest.raises(ValueError, match="needs an item_id and media_path"):
        replace(comparison(0, media, Preference.TIE), media_path="   ")


def test_the_incumbent_verdict_must_come_from_the_pinned_judge(tmp_path: Path) -> None:
    """§3 Stage 4 pins `gemini-2.5-pro` and §7 marks `gemini-3.1-pro` "evaluated, not routed".

    The whole promotion rule is that the shadow must beat the incumbent on the Sorani
    regression set. A comparison whose "incumbent" verdict came from some other model is not
    that comparison, and the resulting decision would be a switch argued from evidence about
    two models nobody pinned.
    """
    media = tmp_path / "source.mp4"
    with pytest.raises(ValueError, match="incumbent verdict came from"):
        replace(comparison(0, media, Preference.TIE), incumbent=verdict(JUDGE_SHADOW))


def test_the_shadow_verdict_must_come_from_the_shadow(tmp_path: Path) -> None:
    """The mirror of the check above, and the direction that flatters the incumbent: comparing
    2.5 Pro against itself ties every item and the shadow never wins."""
    media = tmp_path / "source.mp4"
    with pytest.raises(ValueError, match="shadow verdict came from"):
        replace(comparison(0, media, Preference.TIE), shadow=verdict(KURDISH_EDITORIAL_JUDGE))


def test_a_regression_set_must_record_who_authorized_the_media(tmp_path: Path) -> None:
    """`authorized_by` is the recorded authorization for footage a benchmark redistributes as
    evidence. Blank means it was used without one, and a set that cannot say who authorized it
    is not evidence anyone can act on."""
    media = tmp_path / "source.mp4"
    items = tuple(comparison(i, media, Preference.TIE) for i in range(20))
    for name, author in (("   ", "client"), ("real", "   ")):
        with pytest.raises(ValueError, match="needs a name and a recorded media authorization"):
            EditorialRegressionSet(name, author, False, items)


def test_a_regression_set_refuses_duplicate_item_ids(tmp_path: Path) -> None:
    """Twenty items of which two are the same item is nineteen items and a double-counted vote,
    which moves a promotion decision without changing the reported total."""
    media = tmp_path / "source.mp4"
    items = tuple(comparison(i, media, Preference.TIE) for i in range(20))
    with pytest.raises(ValueError, match="duplicate item ids"):
        EditorialRegressionSet("real", "client", False, (*items, items[0]))


def test_a_set_thin_in_one_dialect_cannot_claim_production_evidence(tmp_path: Path) -> None:
    """The floor is per dialect, not just overall — a set of twenty that is all Hewlêr says
    nothing about how the shadow reads Silêmanî, and §8.2's decision is about Sorani, not about
    one city's Sorani.
    """
    media = tmp_path / "source.mp4"
    media.write_bytes(b"x")
    one_dialect = tuple(
        replace(comparison(i, media, Preference.TIE), dialect=Dialect.HEWLER) for i in range(20)
    )
    with pytest.raises(ValueError, match="fewer than"):
        EditorialRegressionSet("real", "client", False, one_dialect).evaluate(tmp_path)
