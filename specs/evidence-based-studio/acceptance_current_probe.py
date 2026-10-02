"""Synthetic diagnostic of the existing scorecard; never human or release evidence."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

from hawedit.visual_scorecard import (
    CompetitorComparison, DatasetSplit, EvaluationProposalRecord, ProvenanceRecord,
    UnsupportedLeadershipClaimError, compute_visual_scorecard,
)
from hawedit.wsl_setup import package_digest


def main() -> None:
    proposals = [
        EvaluationProposalRecord(
            clip_id=f"synthetic-proposal-{index}", episode_id=f"synthetic-episode-{index // 10}",
            status="accepted" if index % 10 < 8 else "rejected", preserved_visual_ratio=0.2,
        )
        for index in range(200)
    ]
    card = compute_visual_scorecard(
        provenance=ProvenanceRecord("not-a-sha", "not-a-date", "synthetic diagnostic", "unverified"),
        split=DatasetSplit("synthetic-not-holdout", frozenset(p.episode_id for p in proposals)),
        proposals=proposals,
        competitor_comparisons={"synthetic-editor": CompetitorComparison(
            "synthetic-editor", wins=60, losses=40, ties=0, total=100,
            win_rate=0.6, ci_lower=0.91, ci_upper=0.95,
        )},
        signoff_owner="unverified-owner-string", signoff_editor="unverified-editor-string",
    )
    reason = None
    try:
        card.evaluate_leadership_claim("10/10")
    except UnsupportedLeadershipClaimError as exc:
        reason = str(exc)
    result = {
        "schema": 1, "status": "synthetic-counterexample-not-evaluation",
        "python": platform.python_version(), "source_package_sha256": package_digest(),
        "unsupported_claim_refused": reason is not None, "refusal_reason": reason,
        "first_pass_rate": card.first_pass_rate, "first_pass_ci_lower": card.first_pass_ci_lower,
        "first_pass_ci_upper": card.first_pass_ci_upper,
        "accounting_property_reports_release_eligible": card.is_release_eligible,
        "synthetic_visual_relevance": card.average_visual_relevance,
        "total_episodes": card.total_episodes, "total_proposed": card.total_proposed,
        "malformed_provenance": card.provenance.commit_sha == "not-a-sha",
        "signatures_or_human_review": False, "provider_calls": 0,
        "limitations": ["diagnostic only", "not a 10/10 verdict", "no real holdout or CI acceptance"],
    }
    destination = Path(sys.argv[1])
    if destination.exists():
        raise RuntimeError("Refusing to overwrite earlier diagnostic evidence")
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
