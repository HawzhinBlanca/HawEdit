"""Tests for A7 usable-rate scoreboard CSV and CLI (`hawedit.usable_rate`)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_usable_rate_initializes_header_and_appends_row(tmp_path: Path) -> None:
    from hawedit.usable_rate import CSV_COLUMNS, load_verdict_rows, record_verdict

    csv_path = tmp_path / "nested" / "usable-rate.csv"
    row = record_verdict(
        csv_path,
        episode="zar-ai-lamo",
        reel="clip_01.mp4",
        verdict="publishable",
        reason="",
        commit="deadbeef",
    )
    assert csv_path.is_file()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = list(csv.reader(handle))
    assert reader[0] == list(CSV_COLUMNS)
    assert len(reader) == 2
    assert row.episode == "zar-ai-lamo"
    assert row.reel == "clip_01.mp4"
    assert row.verdict == "publishable"
    assert row.commit == "deadbeef"
    assert load_verdict_rows(csv_path) == [row]


def test_usable_rate_rejects_mismatched_csv_header(tmp_path: Path) -> None:
    from hawedit.usable_rate import record_verdict

    csv_path = tmp_path / "bad.csv"
    original = "wrong,columns,here\n1,2,3\n"
    csv_path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="header"):
        record_verdict(
            csv_path,
            episode="ep1",
            reel="clip_01.mp4",
            verdict="publishable",
            commit="abc123",
        )
    assert csv_path.read_text(encoding="utf-8") == original


def test_usable_rate_canonicalizes_and_validates_verdict() -> None:
    from hawedit.usable_rate import canonicalize_verdict

    assert canonicalize_verdict("publishable") == "publishable"
    assert canonicalize_verdict("  Publishable ") == "publishable"
    assert canonicalize_verdict("needs_fix") == "needs_fix"
    assert canonicalize_verdict("needs-fix") == "needs_fix"
    assert canonicalize_verdict("needs a fix") == "needs_fix"
    assert canonicalize_verdict("UNUSABLE") == "unusable"

    with pytest.raises(ValueError, match="verdict"):
        canonicalize_verdict("almost_ok")


def test_usable_rate_rejects_unknown_verdict_without_writing(tmp_path: Path) -> None:
    from hawedit.usable_rate import record_verdict

    csv_path = tmp_path / "usable-rate.csv"
    record_verdict(
        csv_path,
        episode="ep1",
        reel="clip_01.mp4",
        verdict="publishable",
        commit="abc123",
    )
    before = csv_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="verdict"):
        record_verdict(
            csv_path,
            episode="ep1",
            reel="clip_02.mp4",
            verdict="ok-ish",
            reason="blurry",
            commit="abc123",
        )
    assert csv_path.read_text(encoding="utf-8") == before


def test_usable_rate_requires_reason_for_non_publishable(tmp_path: Path) -> None:
    from hawedit.usable_rate import record_verdict

    csv_path = tmp_path / "usable-rate.csv"
    for bad_verdict in ("needs_fix", "unusable"):
        with pytest.raises(ValueError, match="reason"):
            record_verdict(
                csv_path,
                episode="ep1",
                reel="clip_01.mp4",
                verdict=bad_verdict,
                reason="   ",
                commit="abc123",
            )
    assert not csv_path.exists()

    with pytest.raises(ValueError, match="episode"):
        record_verdict(
            csv_path,
            episode="  ",
            reel="clip_01.mp4",
            verdict="publishable",
            commit="abc123",
        )


def test_usable_rate_records_sha256_and_commit_provenance(tmp_path: Path) -> None:
    from hawedit.usable_rate import record_verdict

    reel_file = tmp_path / "reel_01.mp4"
    payload = b"synthetic-mp4-bytes-for-sha"
    reel_file.write_bytes(payload)
    expected_sha = hashlib.sha256(payload).hexdigest()

    csv_path = tmp_path / "usable-rate.csv"
    row_file = record_verdict(
        csv_path,
        episode="ep1",
        reel=str(reel_file),
        verdict="publishable",
        commit="c0mm1t1",
    )
    assert row_file.reel_sha256 == expected_sha
    assert row_file.commit == "c0mm1t1"
    assert row_file.recorded_at

    row_logical = record_verdict(
        csv_path,
        episode="ep1",
        reel="logical_clip_02",
        verdict="needs a fix",
        reason="caption overlap at 12.4s",
        commit="c0mm1t2",
    )
    assert row_logical.reel_sha256 == "n/a"
    assert row_logical.verdict == "needs_fix"


def test_usable_rate_guards_duplicate_reel_unless_replace(tmp_path: Path) -> None:
    from hawedit.usable_rate import load_verdict_rows, record_verdict

    csv_path = tmp_path / "usable-rate.csv"
    record_verdict(
        csv_path,
        episode="ep1",
        reel="clip_01.mp4",
        verdict="needs_fix",
        reason="cut inside word",
        commit="abc111",
    )

    with pytest.raises(ValueError, match="Duplicate"):
        record_verdict(
            csv_path,
            episode="ep1",
            reel="clip_01.mp4",
            verdict="publishable",
            commit="abc222",
        )

    updated = record_verdict(
        csv_path,
        episode="ep1",
        reel="clip_01.mp4",
        verdict="publishable",
        reason="re-rendered clean cut",
        commit="abc222",
        replace=True,
    )
    rows = load_verdict_rows(csv_path)
    assert rows == [updated]
    assert rows[0].verdict == "publishable"
    assert rows[0].commit == "abc222"


def test_usable_rate_summary_computes_rate_and_baseline_delta(tmp_path: Path) -> None:
    from hawedit.usable_rate import (
        USABLE_RATE_BASELINE,
        USABLE_RATE_TARGET,
        record_verdict,
        summarize_usable_rate,
    )

    assert pytest.approx(0.62) == USABLE_RATE_BASELINE
    assert pytest.approx(0.80) == USABLE_RATE_TARGET

    csv_path = tmp_path / "usable-rate.csv"
    for idx in range(4):
        record_verdict(
            csv_path,
            episode="ep_a",
            reel=f"a_{idx}.mp4",
            verdict="publishable",
            commit="abc123",
        )
    record_verdict(
        csv_path,
        episode="ep_b",
        reel="b_0.mp4",
        verdict="needs_fix",
        reason="weak hook",
        commit="abc123",
    )

    summary = summarize_usable_rate(csv_path)
    assert summary.total == 5
    assert summary.publishable == 4
    assert summary.needs_fix == 1
    assert summary.unusable == 0
    assert summary.usable_rate == pytest.approx(0.8)
    assert summary.delta_vs_baseline == pytest.approx(0.18)
    assert summary.delta_vs_target == pytest.approx(0.0)
    assert 0.0 < summary.wilson_ci_95[0] < 0.8 < summary.wilson_ci_95[1] <= 1.0
    assert summary.by_episode["ep_a"]["publishable"] == 4
    assert summary.by_episode["ep_b"]["needs_fix"] == 1


def test_usable_rate_summary_handles_empty_sheet(tmp_path: Path) -> None:
    from hawedit.usable_rate import CSV_COLUMNS, summarize_usable_rate

    csv_path = tmp_path / "empty.csv"
    csv_path.write_text(",".join(CSV_COLUMNS) + "\n", encoding="utf-8")

    summary = summarize_usable_rate(csv_path)
    assert summary.total == 0
    assert summary.usable_rate == 0.0
    assert summary.wilson_ci_95 == (0.0, 0.0)


def test_usable_rate_cli_add_and_summary_utf8_roundtrip(tmp_path: Path) -> None:
    csv_path = tmp_path / "usable-rate.csv"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    add_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "hawedit.usable_rate",
            "add",
            "--csv",
            str(csv_path),
            "--episode",
            "zar-ai-lamo",
            "--reel",
            "clip_01.mp4",
            "--verdict",
            "needs_fix",
            "--reason",
            "ژێرنووسی کوردی پچڕاوە",
            "--commit",
            "deadbeef",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert add_proc.returncode == 0, add_proc.stderr

    summary_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "hawedit.usable_rate",
            "summary",
            "--csv",
            str(csv_path),
            "--json",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert summary_proc.returncode == 0, summary_proc.stderr
    payload = json.loads(summary_proc.stdout)
    assert payload["total"] == 1
    assert payload["needs_fix"] == 1
    assert payload["usable_rate"] == 0.0


def test_usable_rate_evidence_csv_does_not_trip_claims_gate() -> None:
    csv_path = ROOT / "evidence" / "usable-rate.csv"
    assert csv_path.is_file()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header[:4] == ["episode", "reel", "verdict", "reason"]
