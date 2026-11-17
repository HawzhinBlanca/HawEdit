"""Descriptive counts and caller assertions cannot authorize release acceptance."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from hawedit.editorial_acceptance import (
    AcceptanceScorecard,
    EditorialAcceptanceError,
    ScopedAcceptanceReport,
    SustainedAcceptanceReport,
    compute_acceptance_scorecard,
    evaluate_scoped_acceptance,
    evaluate_sustained_acceptance,
)
from hawedit.visual_scorecard import (
    CompetitorComparison,
    DatasetSplit,
    EvaluationProposalRecord,
    ProvenanceRecord,
    UnsupportedLeadershipClaimError,
    VisualScorecard,
    compute_visual_scorecard,
)


def _card(accepted: int = 200) -> AcceptanceScorecard:
    return compute_acceptance_scorecard(
        total_proposed_clips=200,
        refusal_count=200 - accepted,
        accepted_count=accepted,
        episodes_evaluated=20,
        episodes_with_no_clips=20 if accepted == 0 else 0,
    )


def _scoped(**overrides: Any) -> ScopedAcceptanceReport:
    values: dict[str, Any] = {
        "commit_sha": "372a16645d7a8558bc6cedcff34a9fbfa13f712f",
        "scorecard": _card(),
        "gate_verified": True,
        "human_review_verified": True,
        "ci_verified": True,
    }
    values.update(overrides)
    return evaluate_scoped_acceptance(**values)


def _sustained(**overrides: Any) -> SustainedAcceptanceReport:
    values: dict[str, Any] = {
        "scoped_report": _scoped(),
        "fresh_holdout_scorecard": _card(),
        "fresh_holdout_verified": True,
        "use_window_days": 30,
        "kurdish_editor_signoff": True,
        "owner_signoff": True,
        "rating_claim": "10/10",
    }
    values.update(overrides)
    return evaluate_sustained_acceptance(**values)


@pytest.mark.parametrize("accepted", [0, 160, 190, 200])
def test_scoped_claims_cannot_authorize_acceptance(accepted: int) -> None:
    report = _scoped(scorecard=_card(accepted))
    assert report.acceptance_status == "refused_unverified_evidence"
    assert report.is_sample_sufficient is True
    assert report.evidence_intact is False
    assert report.gate_verified is False
    assert report.human_review_verified is False
    assert report.ci_verified is False
    assert any("caller assertions" in reason for reason in report.deficiencies)
    assert report.to_dict()["reported_checks"] == {
        "gate_verified": True,
        "human_review_verified": True,
        "ci_verified": True,
    }
    with pytest.raises(EditorialAcceptanceError, match="not authorization"):
        report.assert_accepted()


@pytest.mark.parametrize("accepted", [0, 160, 190, 200])
@pytest.mark.parametrize("days", [30, 300])
def test_sustained_claims_cannot_authorize_rating(accepted: int, days: int) -> None:
    report = _sustained(fresh_holdout_scorecard=_card(accepted), use_window_days=days)
    assert report.sustained_status == "refused_unverified_evidence"
    assert report.is_sustained is False
    assert report.fresh_holdout_verified is False
    assert report.kurdish_editor_signoff is False
    assert report.owner_signoff is False
    assert report.rating_claim is None
    assert report.to_dict()["requested_rating_claim"] == "10/10"
    assert report.to_dict()["reported_checks"] == {
        "fresh_holdout_verified": True,
        "kurdish_editor_signoff": True,
        "owner_signoff": True,
    }
    with pytest.raises(EditorialAcceptanceError, match="not authorization"):
        report.assert_sustained()


@pytest.mark.parametrize("field", ["gate_verified", "human_review_verified", "ci_verified"])
@pytest.mark.parametrize("value", [1, "true", None])
def test_scoped_claim_input_validation(field: str, value: object) -> None:
    with pytest.raises(EditorialAcceptanceError, match="boolean"):
        _scoped(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "fresh_holdout_verified",
        "kurdish_editor_signoff",
        "owner_signoff",
        "automatic_rating_claimed",
    ],
)
@pytest.mark.parametrize("value", [1, "true", None])
def test_sustained_claim_input_validation(field: str, value: object) -> None:
    with pytest.raises(EditorialAcceptanceError, match="boolean"):
        _sustained(**{field: value})


@pytest.mark.parametrize("value", [-1, True, 30.0, "30"])
def test_use_window_claim_requires_nonnegative_integer(value: object) -> None:
    with pytest.raises(EditorialAcceptanceError, match="use_window_days"):
        _sustained(use_window_days=value)


@pytest.mark.parametrize("value", [None, 123, [], "", "abcdef0", "g" * 40])
def test_invalid_commit_claim_is_not_verified(value: object) -> None:
    report = _scoped(commit_sha=value)
    assert report.acceptance_status == "refused_unverified_evidence"
    assert any("invalid committed commit SHA" in reason for reason in report.deficiencies)
    assert report.evidence_intact is False


@pytest.mark.parametrize("value", [0, 199, True, 200.0, "200"])
def test_acceptance_floor_cannot_be_lowered(value: object) -> None:
    with pytest.raises(EditorialAcceptanceError, match="min_sample_size"):
        _scoped(min_sample_size=value)
    with pytest.raises(EditorialAcceptanceError, match="min_sample_size"):
        _sustained(min_sample_size=value)


@pytest.mark.parametrize("value", [0, 29, True, 30.0, "30"])
def test_sustained_use_floor_cannot_be_lowered(value: object) -> None:
    with pytest.raises(EditorialAcceptanceError, match="min_use_window_days"):
        _sustained(min_use_window_days=value)


def test_report_construction_cannot_forge_authority() -> None:
    scoped = _scoped()
    sustained = _sustained()
    for fields in (
        {"acceptance_status": "accepted"},
        {"evidence_intact": True},
        {"gate_verified": True},
        {"human_review_verified": True},
        {"ci_verified": True},
    ):
        with pytest.raises(EditorialAcceptanceError, match="descriptive"):
            replace(scoped, **fields)
    for fields in (
        {"sustained_status": "sustained"},
        {"is_sustained": True},
        {"rating_claim": "10/10"},
        {"fresh_holdout_verified": True},
        {"owner_signoff": True},
        {"kurdish_editor_signoff": True},
    ):
        with pytest.raises(EditorialAcceptanceError, match="descriptive"):
            replace(sustained, **fields)


def test_report_assertions_do_not_trust_status_fields() -> None:
    # Python objects are not an authentication boundary, even when frozen.
    scoped = _scoped()
    object.__setattr__(scoped, "acceptance_status", "accepted")
    object.__setattr__(scoped, "evidence_intact", True)
    with pytest.raises(EditorialAcceptanceError, match="not authorization"):
        scoped.assert_accepted()
    sustained = _sustained()
    object.__setattr__(sustained, "is_sustained", True)
    object.__setattr__(sustained, "sustained_status", "sustained")
    with pytest.raises(EditorialAcceptanceError, match="not authorization"):
        sustained.assert_sustained()


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_proposed_clips", True),
        ("accepted_count", -1),
        ("refusal_count", 1),
        ("first_pass_publishable_rate", 0.5),
        ("refusal_rate", float("nan")),
        ("margin_of_error", float("inf")),
        ("episodes_evaluated", 0),
        ("episodes_with_no_clips", 21),
        ("episodes_with_no_clips", 20),
    ],
)
def test_scorecard_direct_construction_validates_counts(field: str, value: Any) -> None:
    with pytest.raises(EditorialAcceptanceError):
        replace(_card(), **{field: value})


def test_aggregate_uncertainty_is_reference_only() -> None:
    card = _card(160)
    assert card.first_pass_publishable_rate == 0.8
    assert 0 < card.margin_of_error < 1
    assert card.to_dict()["margin_of_error_method"] == "unclustered-wald-reference-only"
    assert card.to_dict()["evidence_status"] == "descriptive-unverified"


def _visual() -> VisualScorecard:
    episodes = frozenset(f"episode-{i}" for i in range(20))
    return compute_visual_scorecard(
        provenance=ProvenanceRecord(
            commit_sha="not-a-sha",
            timestamp="not-a-date",
            hardware_info="synthetic",
            verifier_version="synthetic",
        ),
        split=DatasetSplit("synthetic", episodes),
        proposals=[
            EvaluationProposalRecord(
                clip_id=f"clip-{i}",
                episode_id=f"episode-{i // 10}",
                status="accepted" if i < 160 else "rejected",
                preserved_visual_ratio=0.2,
            )
            for i in range(200)
        ],
        competitor_comparisons={
            "editor": CompetitorComparison("editor", 0, 200, 0, 200, 1.0, 0.9, 1.0)
        },
        signoff_owner="unsigned owner",
        signoff_editor="unsigned editor",
    )


@pytest.mark.parametrize(
    "claim", ["10/10", "market leader", "superior", "#1", "9.5/10", "10 out of 10", "best", ""]
)
def test_visual_descriptions_are_not_release_authority(claim: str) -> None:
    report = _visual()
    assert report.is_release_eligible is False
    assert report.to_dict()["is_release_eligible"] is False
    with pytest.raises(UnsupportedLeadershipClaimError, match="unverified descriptive"):
        report.evaluate_leadership_claim(claim)


def test_visual_report_labels_unverified_inference() -> None:
    report = _visual()
    assert report.first_pass_rate == 0.8
    assert report.average_visual_relevance == pytest.approx(0.2)
    assert report.to_dict()["evidence_status"] == "descriptive-unverified"
    assert report.to_dict()["inference_status"] == "diagnostic-not-preregistered"
