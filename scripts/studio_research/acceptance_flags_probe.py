"""Execute synthetic admission diagnostics, never an acceptance verdict."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

from hawedit.editorial_acceptance import (
    compute_acceptance_scorecard,
    evaluate_scoped_acceptance,
    evaluate_sustained_acceptance,
)
from hawedit.wsl_setup import package_digest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    destination = root / "specs/evidence-based-studio/T8-flags-admission-counterexample.json"
    if destination.exists():
        raise RuntimeError("Refusing to overwrite a diagnostic observation")
    card = compute_acceptance_scorecard(
        total_proposed_clips=200,
        refusal_count=200,
        accepted_count=0,
        episodes_evaluated=20,
        episodes_with_no_clips=20,
    )
    scoped = evaluate_scoped_acceptance(
        commit_sha="not-a-sha",
        scorecard=card,
        gate_verified=True,
        human_review_verified=True,
        ci_verified=True,
    )
    sustained = evaluate_sustained_acceptance(
        scoped_report=scoped,
        fresh_holdout_scorecard=card,
        fresh_holdout_verified=True,
        use_window_days=30,
        kurdish_editor_signoff=True,
        owner_signoff=True,
        rating_claim="10/10",
    )
    result = {
        "status": "synthetic-unaccepted-admission-defect",
        "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_package_sha256": package_digest(),
        "python": platform.python_version(),
        "independent_human_evidence_supplied": False,
        "scoped": scoped.to_dict(),
        "sustained": sustained.to_dict(),
    }
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scoped_status": scoped.acceptance_status,
                "sustained_status": sustained.sustained_status,
                "defect_only": True,
            }
        )
    )


if __name__ == "__main__":
    main()
