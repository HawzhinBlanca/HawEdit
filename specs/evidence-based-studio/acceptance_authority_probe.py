"""Replay the actual flag-only counterexample without overwriting its defect evidence."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

from hawedit.editorial_acceptance import (
    EditorialAcceptanceError,
    compute_acceptance_scorecard,
    evaluate_scoped_acceptance,
    evaluate_sustained_acceptance,
)
from hawedit.wsl_setup import package_digest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    destination = Path(__file__).with_name("T8-authority-native-replay.json")
    if destination.exists():
        raise RuntimeError("Refusing to overwrite an actual authority replay")
    observations = []
    for accepted, commit in ((0, "not-a-sha"), (200, "372a16645d7a8558bc6cedcff34a9fbfa13f712f")):
        card = compute_acceptance_scorecard(
            total_proposed_clips=200, refusal_count=200 - accepted, accepted_count=accepted,
            episodes_evaluated=20, episodes_with_no_clips=20 if accepted == 0 else 0,
        )
        scoped = evaluate_scoped_acceptance(
            commit_sha=commit, scorecard=card,
            gate_verified=True, human_review_verified=True, ci_verified=True,
        )
        sustained = evaluate_sustained_acceptance(
            scoped_report=scoped, fresh_holdout_scorecard=card,
            fresh_holdout_verified=True, use_window_days=30,
            kurdish_editor_signoff=True, owner_signoff=True, rating_claim="10/10",
        )
        assert scoped.acceptance_status == "refused_unverified_evidence"
        assert not scoped.evidence_intact and not sustained.is_sustained
        assert sustained.rating_claim is None
        for assertion in (scoped.assert_accepted, sustained.assert_sustained):
            try:
                assertion()
            except EditorialAcceptanceError as exc:
                assert "not authorization" in str(exc)
            else:
                raise AssertionError("Descriptive report authorized acceptance")
        observations.append({"scoped": scoped.to_dict(), "sustained": sustained.to_dict()})
    record = {
        "status": "synthetic-unaccepted-engineering-replay",
        "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_package_sha256": package_digest(), "python": platform.python_version(),
        "independent_human_evidence_supplied": False, "observations": observations,
    }
    destination.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Two actual aggregate/flag-only replay cases refused; no accepted human study or release")


if __name__ == "__main__":
    main()
