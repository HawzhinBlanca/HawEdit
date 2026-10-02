"""Actual runtime-only Linux authority replay; no pytest or dependency installation."""

from __future__ import annotations

import json
import platform
from dataclasses import replace
from pathlib import Path

import hawedit.editorial_acceptance as editorial
from hawedit.visual_scorecard import (
    CompetitorComparison,
    DatasetSplit,
    EvaluationProposalRecord,
    ProvenanceRecord,
    UnsupportedLeadershipClaimError,
    compute_visual_scorecard,
)
from hawedit.wsl_setup import package_digest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    assert Path(editorial.__file__).resolve().is_relative_to(root / "src")
    expected = json.loads(
        (root / "specs/evidence-based-studio/T8-authority-source-manifest.json").read_text(
            encoding="utf-8-sig"
        )
    )
    digest = package_digest()
    assert digest == expected["source_package_sha256"]
    card = editorial.compute_acceptance_scorecard(
        total_proposed_clips=200,
        refusal_count=200,
        accepted_count=0,
        episodes_evaluated=20,
        episodes_with_no_clips=20,
    )
    scoped = editorial.evaluate_scoped_acceptance(
        commit_sha="not-a-sha",
        scorecard=card,
        gate_verified=True,
        human_review_verified=True,
        ci_verified=True,
    )
    assert scoped.acceptance_status == "refused_unverified_evidence"
    sustained = editorial.evaluate_sustained_acceptance(
        scoped_report=scoped,
        fresh_holdout_scorecard=card,
        fresh_holdout_verified=True,
        use_window_days=30,
        kurdish_editor_signoff=True,
        owner_signoff=True,
        rating_claim="10/10",
    )
    assert not sustained.is_sustained and sustained.rating_claim is None
    refusals = 0
    for assertion in (scoped.assert_accepted, sustained.assert_sustained):
        try:
            assertion()
        except editorial.EditorialAcceptanceError:
            refusals += 1
    assert refusals == 2
    try:
        replace(scoped, acceptance_status="accepted", evidence_intact=True)
    except editorial.EditorialAcceptanceError:
        pass
    else:
        raise AssertionError("Manual construction authorized acceptance")
    episodes = frozenset(f"episode-{i}" for i in range(20))
    visual = compute_visual_scorecard(
        provenance=ProvenanceRecord("not-a-sha", "not-a-date", "synthetic", "synthetic"),
        split=DatasetSplit("synthetic", episodes),
        proposals=[
            EvaluationProposalRecord(
                clip_id=f"clip-{i}",
                episode_id=f"episode-{i // 10}",
                status="accepted" if i % 10 < 8 else "rejected",
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
    assert not visual.is_release_eligible
    for claim in ("10/10", "10 out of 10"):
        try:
            visual.evaluate_leadership_claim(claim)
        except UnsupportedLeadershipClaimError:
            pass
        else:
            raise AssertionError("Claim authorized superiority")
    print(
        json.dumps(
            {
                "status": "unaccepted-linux-engineering-observations",
                "grouped_observations_passed": 5,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "source_package_sha256": digest,
                "import_path": editorial.__file__,
                "canonical_linux_gate_passed": False,
                "independent_human_study": False,
            }
        )
    )


if __name__ == "__main__":
    main()
