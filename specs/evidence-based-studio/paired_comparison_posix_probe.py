"""Actual Linux runtime contract checks, not a gate or a human evaluation."""

from __future__ import annotations

import itertools
import json
import os
import platform
import sys
from pathlib import Path

from hawedit.comparison_kit import (
    ComparisonKitError, OptionRating, PairRating, RaterSubmission,
    analyze_study, validate_ratings, wilson_score_interval,
)
from hawedit.wsl_setup import package_digest


def main() -> None:
    assert os.name == "posix"
    destination = Path(__file__).with_name("T8-paired-posix.json")
    if destination.exists():
        raise RuntimeError("Refusing observation overwrite")
    first = PairRating.from_options("p", OptionRating(5, 2, 4, True), OptionRating(2, 4, 1, False), "tie")
    second = PairRating.from_options("q", OptionRating(2, 4, 1, False), OptionRating(5, 2, 4, True), "B")
    mapping = {"p": {"A": "system", "B": "human"}, "q": {"A": "human", "B": "system"}}
    observations: list[str] = []
    expected = None
    for order in itertools.permutations((first, second)):
        submission = RaterSubmission("self-label", "2026-10-03T00:00:00Z", order)
        assert validate_ratings(json.loads(json.dumps(submission.to_dict())), set(mapping)) == submission
        result = analyze_study([submission], mapping)
        assert (result.hook_mean_diff, result.clarity_mean_diff, result.shareability_mean_diff) == (3, -2, 3)
        assert (result.misleading_rate_system, result.misleading_rate_human) == (1, 0)
        assert result.ci_lower is None and not result.better_than_a_team
        assert expected is None or result == expected
        expected = result
    observations.append("paired roundtrip, flags and order-independent differences")
    try:
        analyze_study([submission, submission], mapping)
    except ComparisonKitError:
        observations.append("actual duplicate refusal")
    else:
        raise AssertionError("duplicate accepted")
    legacy = RaterSubmission("legacy", "2026-10-03T00:00:00Z", (PairRating("p", 5, 5, 5, False, "A"),))
    unknown = analyze_study([legacy], {"p": mapping["p"]})
    assert unknown.hook_mean_diff is None and unknown.misleading_rate_system is None
    observations.append("unknown legacy measurements and unavailable inference")
    assert wilson_score_interval(.5, 100, .99)[0] < wilson_score_interval(.5, 100, .95)[0] < wilson_score_interval(.5, 100, .90)[0]
    observations.append("requested confidence changes actual interval")
    destination.write_text(json.dumps({
        "status": "unaccepted-native-runtime-probe", "python": platform.python_version(),
        "platform": platform.platform(), "executable": sys.executable,
        "source_package_sha256": package_digest(),
        "observations": observations, "passed": True, "gate_passed": False,
        "human_evaluation": False,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{len(observations)} native Linux grouped observations passed")


if __name__ == "__main__":
    main()
