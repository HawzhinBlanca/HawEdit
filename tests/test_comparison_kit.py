"""Unit tests for the blind pairwise comparison kit (Task T5.1, H7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hawedit.comparison_kit import (
    ComparisonKitError,
    PairCandidate,
    PairRating,
    RaterSubmission,
    analyze_study,
    export_to_qc_records,
    format_kurdish_form_markdown,
    generate_kurdish_rating_form,
    prepare_blind_study,
    validate_ratings,
    wilson_score_interval,
)


def test_wilson_score_interval_properties_and_known_values() -> None:
    """Task T5.1: Wilson score interval computes exact 95% confidence bounds."""
    # N=100, 50% success
    low, high = wilson_score_interval(0.5, 100)
    assert 0.40 <= low <= 0.41
    assert 0.59 <= high <= 0.60
    assert abs((low + high) / 2.0 - 0.5) < 0.01

    # Perfect win rate (N=20)
    low_1, high_1 = wilson_score_interval(1.0, 20)
    assert low_1 > 0.83
    assert high_1 == 1.0

    # Zero win rate (N=20)
    low_0, high_0 = wilson_score_interval(0.0, 20)
    assert low_0 == 0.0
    assert high_0 < 0.17

    # Bounds validation
    with pytest.raises(ComparisonKitError, match="Sample size"):
        wilson_score_interval(0.5, 0)
    with pytest.raises(ComparisonKitError, match="p_hat"):
        wilson_score_interval(-0.1, 10)
    with pytest.raises(ComparisonKitError, match="p_hat"):
        wilson_score_interval(1.1, 10)


def test_prepare_blind_study_randomises_and_seals_keys(tmp_path: Path) -> None:
    """Task T5.1: Seeded blinding produces deterministic pairs and sealed unblinding key."""
    candidates = [
        PairCandidate(
            pair_id=f"pair_{i:02d}",
            system_path=tmp_path / f"sys_{i}.mp4",
            human_path=tmp_path / f"human_{i}.mp4",
            topic_ckb=f"بابەتی ژمارە {i}",
            duration_s=45.0,
        )
        for i in range(1, 6)
    ]

    out_dir = tmp_path / "study_output"
    study = prepare_blind_study(candidates, out_dir, seed=1234, copy_media=False)

    assert study.study_id == "study_seed_1234"
    assert len(study.items) == 5
    assert set(study.unblinding_map.keys()) == {f"pair_{i:02d}" for i in range(1, 6)}

    for item in study.items:
        assert item.blinded_path_a.is_file()
        assert item.blinded_path_b.is_file()
        assert len(item.sha256_a) == 64
        assert len(item.sha256_b) == 64
        map_entry = study.unblinding_map[item.pair_id]
        assert set(map_entry.keys()) == {"A", "B"}
        assert set(map_entry.values()) == {"system", "human"}

    # Determinism: same seed produces same unblinding map
    study_repeat = prepare_blind_study(
        candidates, tmp_path / "study_repeat", seed=1234, copy_media=False
    )
    assert study_repeat.unblinding_map == study.unblinding_map

    # Different seed produces different unblinding map
    study_diff = prepare_blind_study(
        candidates, tmp_path / "study_diff", seed=9999, copy_media=False
    )
    assert study_diff.unblinding_map != study.unblinding_map


def test_kurdish_rating_form_structure_and_markdown_formatting(tmp_path: Path) -> None:
    """Task T5.1: Rating template emits Kurdish Sorani (ckb) rubrics and instructions."""
    candidates = [
        PairCandidate(
            pair_id="pair_01",
            system_path=tmp_path / "sys.mp4",
            human_path=tmp_path / "hum.mp4",
            topic_ckb="گرنگی میدیای کوردی",
            duration_s=35.0,
        )
    ]
    study = prepare_blind_study(candidates, tmp_path / "form_out", seed=42, copy_media=False)
    form_json = generate_kurdish_rating_form(study)

    assert "سەرنجڕاکێشی" in form_json["dimensions"][0]["label_ckb"]
    assert "ڕوونی پەیام" in form_json["dimensions"][1]["label_ckb"]
    assert "بڵاوکردنەوە" in form_json["dimensions"][2]["label_ckb"]
    assert "چەواشەکارانە" in form_json["dimensions"][3]["label_ckb"]

    md = format_kurdish_form_markdown(study)
    assert "# فۆڕمی هەڵسەنگاندنی کوالێتی ڤیدیۆ" in md
    assert "pair_01" in md
    assert "گرنگی میدیای کوردی" in md


def test_validate_ratings_schema_and_boundaries() -> None:
    """Task T5.1: Review validation rejects malformed scores or mismatched pairs."""
    expected = {"pair_01", "pair_02"}
    valid_payload = {
        "reviewer_name": "دیلان ئەحمەد",
        "submitted_at_iso": "2026-09-04T12:00:00Z",
        "ratings": [
            {
                "pair_id": "pair_01",
                "hook_score": 4,
                "clarity_score": 5,
                "shareability_score": 4,
                "misleading_flag": False,
                "preferred_option": "A",
                "notes": "دەستکارییەکی زۆر جوانە",
            },
            {
                "pair_id": "pair_02",
                "hook_score": 3,
                "clarity_score": 4,
                "shareability_score": 3,
                "misleading_flag": False,
                "preferred_option": "B",
            },
        ],
    }

    sub = validate_ratings(valid_payload, expected)
    assert sub.reviewer_name == "دیلان ئەحمەد"
    assert len(sub.ratings) == 2

    first_rating: dict[str, Any] = dict(valid_payload["ratings"][0])  # type: ignore[arg-type]
    second_rating: dict[str, Any] = dict(valid_payload["ratings"][1])  # type: ignore[arg-type]

    # Score out of bounds (6 > 5)
    bad_score = {
        **valid_payload,
        "ratings": [{**first_rating, "hook_score": 6}, second_rating],
    }
    with pytest.raises(ComparisonKitError, match="hook_score"):
        validate_ratings(bad_score, expected)

    # Missing pair
    missing_pair = {
        **valid_payload,
        "ratings": [first_rating],
    }
    with pytest.raises(ComparisonKitError, match="missing ratings"):
        validate_ratings(missing_pair, expected)

    # Invalid preferred_option
    bad_opt = {
        **valid_payload,
        "ratings": [{**first_rating, "preferred_option": "C"}, second_rating],
    }
    with pytest.raises(ComparisonKitError, match="preferred_option"):
        validate_ratings(bad_opt, expected)


def test_analyze_study_better_than_a_team_criterion() -> None:
    """Task T5.1: 'Better than a team' requires Wilson CI lower bound > 50%."""
    unblinding = {
        "pair_01": {"A": "system", "B": "human"},
        "pair_02": {"A": "system", "B": "human"},
        "pair_03": {"A": "human", "B": "system"},
        "pair_04": {"A": "system", "B": "human"},
        "pair_05": {"A": "human", "B": "system"},
    }

    # Scenario 1: Dominant system performance across 20 raters (95% win rate)
    # 20 raters rating 5 pairs each = 100 total comparisons
    # System wins 90, human wins 10
    dominant_ratings = []
    for i in range(100):
        pid = f"pair_{(i % 5) + 1:02d}"
        sys_is_a = unblinding[pid]["A"] == "system"
        pref = "A" if (sys_is_a and i < 90) or (not sys_is_a and i >= 90) else "B"
        dominant_ratings.append(
            PairRating(
                pair_id=pid,
                hook_score=5 if pref == ("A" if sys_is_a else "B") else 2,
                clarity_score=5,
                shareability_score=4,
                misleading_flag=False,
                preferred_option=pref,
            )
        )

    sub_dominant = [
        RaterSubmission(
            reviewer_name=f"reviewer_{k}",
            submitted_at_iso="2026-09-04T12:00:00Z",
            ratings=tuple(dominant_ratings[k * 5 : (k + 1) * 5]),
        )
        for k in range(20)
    ]

    metrics_win = analyze_study(sub_dominant, unblinding)
    assert metrics_win.total_comparisons == 100
    assert metrics_win.system_wins == 90
    assert metrics_win.system_win_rate == 0.90
    assert metrics_win.ci_lower > 0.50  # Lower bound ~0.82 > 0.50
    assert metrics_win.better_than_a_team is True

    # Scenario 2: Marginal majority (55% win rate, N=20 raters rating 1 pair = 20 comparisons)
    # 11 wins, 9 losses -> win_rate = 0.55
    marginal_ratings = [
        PairRating(
            pair_id="pair_01",
            hook_score=3,
            clarity_score=3,
            shareability_score=3,
            misleading_flag=False,
            preferred_option="A" if i < 11 else "B",
        )
        for i in range(20)
    ]
    sub_marginal = [
        RaterSubmission(
            reviewer_name=f"rev_{i}",
            submitted_at_iso="2026-09-04T12:00:00Z",
            ratings=(marginal_ratings[i],),
        )
        for i in range(20)
    ]
    metrics_marginal = analyze_study(sub_marginal, {"pair_01": {"A": "system", "B": "human"}})
    assert metrics_marginal.system_win_rate == 0.55
    # Wilson CI lower bound is ~0.34 < 0.50
    assert metrics_marginal.ci_lower < 0.50
    assert metrics_marginal.better_than_a_team is False  # Cannot claim "Better than a team"


def test_export_to_qc_records_integration(tmp_path: Path) -> None:
    """Task T5.1: Review export creates valid QcRecord objects (Task T1.3)."""
    candidates = [
        PairCandidate(
            pair_id="pair_01",
            system_path=tmp_path / "s.mp4",
            human_path=tmp_path / "h.mp4",
            topic_ckb="تێست",
            duration_s=30.0,
        )
    ]
    study = prepare_blind_study(candidates, tmp_path / "qc_study", seed=42, copy_media=False)

    sub = RaterSubmission(
        reviewer_name="هێمن موکریانی",
        submitted_at_iso="2026-09-04T14:30:00Z",
        ratings=(
            PairRating(
                pair_id="pair_01",
                hook_score=5,
                clarity_score=4,
                shareability_score=5,
                misleading_flag=False,
                preferred_option="A",
                notes="بەهێزە",
            ),
        ),
    )

    records = export_to_qc_records(sub, study)
    assert len(records) == 1
    qc = records[0]
    assert qc.reviewer == "هێمن موکریانی"
    assert qc.reviewed_at == "2026-09-04T14:30:00Z"
    assert qc.mp4_sha256 == study.items[0].sha256_a
    assert qc.verdict == "pass"
    assert "Hook: 5/5" in qc.notes
    assert qc.to_dict()["reviewer"] == "هێمن موکریانی"
