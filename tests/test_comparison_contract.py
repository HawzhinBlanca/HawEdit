"""Descriptive paired evidence must never fabricate fidelity or inference authority."""

from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from hawedit import comparison_kit as kit

TIME = "2026-10-03T09:30:00+03:00"
MAP = {"p": {"A": "system", "B": "human"}}


def legacy() -> kit.PairRating:
    return kit.PairRating("p", 5, 4, 3, True, "A")


def payload() -> dict[str, Any]:
    return {"reviewer_name": "reviewer", "submitted_at_iso": TIME, "ratings": [legacy().to_dict()]}


def paired(pair_id: str = "p", preference: str = "A") -> kit.PairRating:
    option = kit.OptionRating
    return kit.PairRating.from_options(
        pair_id,
        option(5, 2, 4, True, seconds_watched=12.5, correction_seconds=0.0),
        option(2, 4, 1, False),
        preference,
        "observations, not approval",
    )


def test_comparison_paired_differences_are_order_invariant() -> None:
    mapping = {**MAP, "q": {"A": "human", "B": "system"}, "r": MAP["p"]}
    observations = [paired(), paired("q", "B"), paired("r", "tie")]
    expected = None
    for order in itertools.permutations(observations):
        metrics = kit.analyze_study([kit.RaterSubmission("rater", TIME, order)], mapping)
        assert metrics.hook_mean_diff == 1.0
        assert metrics.clarity_mean_diff == pytest.approx(-2 / 3, abs=0.0005)
        assert metrics.shareability_mean_diff == 1.0
        assert (metrics.system_wins, metrics.human_wins, metrics.ties) == (2, 0, 1)
        if expected is not None:
            assert metrics == expected
        expected = metrics


@pytest.mark.parametrize("preference", ["A", "B", "tie"])
def test_comparison_paired_flags_follow_option_not_preference(preference: str) -> None:
    sub = kit.RaterSubmission("rater", TIME, (paired(preference=preference),))
    direct = kit.analyze_study([sub], MAP)
    reverse = kit.analyze_study([sub], {"p": {"A": "human", "B": "system"}})
    assert (direct.misleading_rate_system, direct.misleading_rate_human) == (1.0, 0.0)
    assert (reverse.misleading_rate_system, reverse.misleading_rate_human) == (0.0, 1.0)


def test_comparison_paired_submission_roundtrip() -> None:
    original = kit.RaterSubmission("self-declared reviewer", TIME, (paired(),))
    encoded = json.loads(json.dumps(original.to_dict()))
    assert encoded["schema"] == 2
    assert kit.validate_ratings(encoded, {"p"}) == original
    assert encoded["ratings"][0]["option_a"]["seconds_watched"] == 12.5
    assert encoded["ratings"][0]["option_b"]["seconds_watched"] is None
    assert encoded["ratings"][0]["option_a"]["correction_seconds"] == 0.0
    assert "hook_score" not in encoded["ratings"][0]


def test_comparison_legacy_differences_are_unknown() -> None:
    sub = kit.validate_ratings(payload(), {"p"})
    assert kit.validate_ratings(sub.to_dict(), {"p"}) == sub
    metrics = kit.analyze_study([sub], MAP)
    assert metrics.system_wins == 1
    assert metrics.hook_mean_diff is None
    assert metrics.clarity_mean_diff is None
    assert metrics.shareability_mean_diff is None
    assert metrics.misleading_rate_system is None
    assert metrics.misleading_rate_human is None


def test_comparison_duplicate_observations_refused() -> None:
    with pytest.raises(kit.ComparisonKitError, match="Duplicate"):
        kit.RaterSubmission("reviewer", TIME, (legacy(), legacy()))
    original = kit.RaterSubmission("reviewer", TIME, (legacy(),))
    with pytest.raises(kit.ComparisonKitError, match="Duplicate"):
        kit.analyze_study([original] * 200, MAP)
    duplicate = payload()
    duplicate["ratings"].append(legacy().to_dict())
    with pytest.raises(kit.ComparisonKitError, match="Duplicate"):
        kit.validate_ratings(duplicate, {"p"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hook_score", True),
        ("hook_score", 1.5),
        ("clarity_score", 0),
        ("shareability_score", 6),
        ("misleading_flag", "false"),
        ("misleading_flag", 0),
        ("preferred_option", 1),
        ("notes", None),
        ("unknown", "extra"),
    ],
)
def test_comparison_malformed_payloads_are_contextual(field: str, value: Any) -> None:
    bad = payload()
    bad["ratings"][0][field] = value
    with pytest.raises(kit.ComparisonKitError):
        kit.validate_ratings(bad, {"p"})


@pytest.mark.parametrize(
    "field", ["hook_score", "clarity_score", "misleading_flag", "preferred_option"]
)
def test_comparison_missing_fields_refuse_contextually(field: str) -> None:
    bad = payload()
    del bad["ratings"][0][field]
    with pytest.raises(kit.ComparisonKitError, match="fields"):
        kit.validate_ratings(bad, {"p"})


@pytest.mark.parametrize(
    "timestamp", ["yesterday", "2026-02-30T00:00:00Z", "2026-10-03T09:30:00", "2026-10-03"]
)
def test_comparison_timestamp_requires_actual_aware_datetime(timestamp: str) -> None:
    bad = payload()
    bad["submitted_at_iso"] = timestamp
    with pytest.raises(kit.ComparisonKitError, match="submitted_at_iso"):
        kit.validate_ratings(bad, {"p"})
    with pytest.raises(kit.ComparisonKitError, match="submitted_at_iso"):
        kit.RaterSubmission("reviewer", timestamp, (legacy(),))


@pytest.mark.parametrize(
    "mapping",
    [
        {},
        {"p": {"A": "system", "B": "system"}},
        {"p": {"A": "system"}},
        {"p": {"A": "system", "B": "human", "C": "human"}},
        {**MAP, "unrated": {"A": "human", "B": "system"}},
    ],
)
def test_comparison_unblinding_map_is_complete_and_bijective(
    mapping: dict[str, dict[str, str]],
) -> None:
    with pytest.raises(kit.ComparisonKitError, match="map"):
        kit.analyze_study([kit.RaterSubmission("reviewer", TIME, (legacy(),))], mapping)


def test_comparison_repeated_ratings_do_not_authorize_superiority() -> None:
    submissions = [kit.RaterSubmission(f"self-label-{i}", TIME, (legacy(),)) for i in range(200)]
    result = kit.analyze_study(submissions, MAP)
    assert result.total_comparisons == 200
    assert result.system_win_rate == 1.0
    assert result.independent_reference_ci_lower > 0.98
    assert result.nominal_reviewers == 200
    assert result.distinct_pairs == 1
    assert result.ci_lower is None and result.ci_upper is None
    assert result.better_than_a_team is False
    assert result.inference_status == "unavailable-unverified-study"
    assert "independent" in result.independent_reference_method


def test_comparison_wilson_uses_requested_confidence() -> None:
    low90, high90 = kit.wilson_score_interval(0.5, 100, 0.90)
    low95, high95 = kit.wilson_score_interval(0.5, 100, 0.95)
    low99, high99 = kit.wilson_score_interval(0.5, 100, 0.99)
    assert low99 < low95 < low90 < 0.5 < high90 < high95 < high99
    assert low90 == pytest.approx(0.4188478, abs=0.000001)
    assert low99 == pytest.approx(0.37527962504484, abs=0.000001)


@pytest.mark.parametrize(
    ("proportion", "n", "confidence"),
    [
        (0.5, True, 0.95),
        (0.5, 1.5, 0.95),
        (True, 10, 0.95),
        (float("nan"), 10, 0.95),
        (0.5, 10, 0),
        (0.5, 10, 1),
        (0.5, 10, float("nan")),
        (0.5, 10, True),
    ],
)
def test_comparison_wilson_invalid_inputs_refuse(proportion: Any, n: Any, confidence: Any) -> None:
    with pytest.raises(kit.ComparisonKitError):
        kit.wilson_score_interval(proportion, n, confidence)


def test_comparison_preference_cannot_become_qc_approval(tmp_path: Path) -> None:
    study = kit.prepare_blind_study(
        [kit.PairCandidate("p", tmp_path / "s", tmp_path / "h", "topic", 10)],
        tmp_path / "study",
        copy_media=False,
    )
    with pytest.raises(kit.ComparisonKitError, match="preference.*QC"):
        kit.export_to_qc_records(kit.RaterSubmission("label", TIME, (legacy(),)), study)


def test_comparison_form_requires_each_option(tmp_path: Path) -> None:
    study = kit.prepare_blind_study(
        [kit.PairCandidate("p", tmp_path / "s", tmp_path / "h", "topic", 10)],
        tmp_path / "study",
        copy_media=False,
    )
    form = kit.generate_kurdish_rating_form(study)
    assert form["schema"] == 2
    assert all(dimension["scope"] == "per_option" for dimension in form["dimensions"][:4])
    assert form["dimensions"][4]["scope"] == "pair"
    assert form["items"][0]["rating_options"] == ["A", "B"]
    rendered = kit.format_kurdish_form_markdown(study)
    assert "### A" in rendered and "### B" in rendered


def test_comparison_paired_invalid_and_mixed_schemas_refuse() -> None:
    original = kit.RaterSubmission("reviewer", TIME, (paired(),)).to_dict()
    for field, value in [
        ("hook_score", True),
        ("seconds_watched", -1),
        ("correction_seconds", float("inf")),
        ("misleading_flag", "false"),
    ]:
        bad = copy.deepcopy(original)
        bad["ratings"][0]["option_a"][field] = value
        with pytest.raises(kit.ComparisonKitError):
            kit.validate_ratings(bad, {"p"})
    with pytest.raises(kit.ComparisonKitError, match="schema"):
        kit.RaterSubmission(
            "reviewer", TIME, (paired(), kit.PairRating("q", 1, 1, 1, False, "tie"))
        )
    bad = copy.deepcopy(original)
    bad["ratings"][0]["hook_score"] = 5
    with pytest.raises(kit.ComparisonKitError, match="fields"):
        kit.validate_ratings(bad, {"p"})
    for schema in [True, 3, "2"]:
        with pytest.raises(kit.ComparisonKitError, match="schema"):
            kit.validate_ratings({**original, "schema": schema}, {"p"})


def test_comparison_mixed_study_does_not_select_known_measurements() -> None:
    mixed = [
        kit.RaterSubmission("paired", TIME, (paired(),)),
        kit.RaterSubmission("legacy", TIME, (legacy(),)),
    ]
    result = kit.analyze_study(mixed, MAP)
    assert result.total_comparisons == 2
    assert result.paired_comparisons == 1
    assert result.hook_mean_diff is None
    assert result.misleading_rate_system is None
    assert result.better_than_a_team is False
    assert result.to_dict()["ci_lower"] is None


@pytest.mark.parametrize("constructor", ["legacy-score", "partial-options", "overall-and-options"])
def test_comparison_direct_constructors_refuse_invalid_observations(constructor: str) -> None:
    option = kit.OptionRating(5, 5, 5, False)
    with pytest.raises(kit.ComparisonKitError):
        if constructor == "legacy-score":
            kit.PairRating("p", True, 5, 5, False, "A")
        elif constructor == "partial-options":
            kit.PairRating("p", None, None, None, None, "A", option_a=option)
        else:
            kit.PairRating("p", 5, 5, 5, False, "A", option_a=option, option_b=option)
