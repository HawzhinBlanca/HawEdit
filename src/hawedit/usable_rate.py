"""Usable-rate scoreboard CSV and Phase F3 tally CLI (A7, D-352)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.comparison_kit import wilson_score_interval

__all__ = [
    "CSV_COLUMNS",
    "DEFAULT_CSV_PATH",
    "USABLE_RATE_BASELINE",
    "USABLE_RATE_TARGET",
    "VALID_VERDICTS",
    "UsableRateSummary",
    "VerdictRow",
    "canonicalize_verdict",
    "format_summary_markdown",
    "load_verdict_rows",
    "main",
    "record_verdict",
    "summarize_usable_rate",
]

USABLE_RATE_BASELINE: Final[float] = 0.62
USABLE_RATE_TARGET: Final[float] = 0.80
VALID_VERDICTS: Final[tuple[str, ...]] = ("publishable", "needs_fix", "unusable")
CSV_COLUMNS: Final[tuple[str, ...]] = (
    "episode",
    "reel",
    "verdict",
    "reason",
    "reel_sha256",
    "commit",
    "recorded_at",
)
DEFAULT_CSV_PATH: Final[Path] = Path("evidence") / "usable-rate.csv"

_VERDICT_ALIASES: Final[dict[str, str]] = {
    "publishable": "publishable",
    "needs_fix": "needs_fix",
    "needs-fix": "needs_fix",
    "needs a fix": "needs_fix",
    "unusable": "unusable",
}


@dataclass(frozen=True, slots=True)
class VerdictRow:
    """Single reel verdict recorded in ``evidence/usable-rate.csv``."""

    episode: str
    reel: str
    verdict: str
    reason: str
    reel_sha256: str
    commit: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class UsableRateSummary:
    """Aggregated usable-rate summary and baseline/target deltas."""

    total: int
    publishable: int
    needs_fix: int
    unusable: int
    usable_rate: float
    wilson_ci_95: tuple[float, float]
    baseline: float
    target: float
    delta_vs_baseline: float
    delta_vs_target: float
    by_episode: dict[str, dict[str, int]]


def canonicalize_verdict(verdict: str) -> str:
    """Normalize a human review verdict into ``VALID_VERDICTS`` or fail stop."""
    normalized = " ".join(verdict.strip().lower().split())
    canonical = _VERDICT_ALIASES.get(normalized)
    if canonical is None:
        raise ValueError(f"Invalid verdict {verdict!r}; expected one of {VALID_VERDICTS}")
    return canonical


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_commit(commit: str | None) -> str:
    if commit is not None:
        cleaned = commit.strip()
        if not cleaned:
            raise ValueError("commit must not be blank when explicitly provided")
        return cleaned
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    head = proc.stdout.strip()
    return head if proc.returncode == 0 and head else "unknown"


def _resolve_reel_sha256(reel: str, reel_path: Path | None) -> str:
    if reel_path is not None:
        if not reel_path.is_file():
            raise FileNotFoundError(f"Explicit --reel-path does not exist: {reel_path}")
        return _sha256_file(reel_path)
    candidate = Path(reel)
    if candidate.is_file():
        return _sha256_file(candidate)
    return "n/a"


def _parse_existing_csv(csv_path: Path) -> list[VerdictRow]:
    if not csv_path.exists():
        return []
    raw_text = csv_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return []
    header = [col.strip() for col in rows[0]]
    required_prefix = list(CSV_COLUMNS[:4])
    if header[:4] != required_prefix:
        raise ValueError(f"Unexpected CSV header {header!r}; expected prefix {required_prefix!r}")
    parsed: list[VerdictRow] = []
    for line_no, raw_row in enumerate(rows[1:], start=2):
        if not raw_row or all(not cell.strip() for cell in raw_row):
            continue
        if len(raw_row) < 4:
            raise ValueError(f"Malformed CSV row at line {line_no}: expected >= 4 columns")
        padded = list(raw_row) + [""] * max(0, len(CSV_COLUMNS) - len(raw_row))
        episode = padded[0].strip()
        reel = padded[1].strip()
        verdict = canonicalize_verdict(padded[2])
        reason = padded[3].strip()
        if not episode or not reel:
            raise ValueError(f"Blank episode or reel at CSV line {line_no}")
        if verdict != "publishable" and not reason:
            raise ValueError(f"Missing reason for non-publishable row at CSV line {line_no}")
        parsed.append(
            VerdictRow(
                episode=episode,
                reel=reel,
                verdict=verdict,
                reason=reason,
                reel_sha256=padded[4].strip() or "n/a",
                commit=padded[5].strip() or "unknown",
                recorded_at=padded[6].strip() or "",
            )
        )
    return parsed


def load_verdict_rows(csv_path: Path) -> list[VerdictRow]:
    """Load and validate verdict rows from an existing CSV scoreboard."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Usable-rate CSV not found: {csv_path}")
    return _parse_existing_csv(csv_path)


def _atomic_write_csv(csv_path: Path, rows: Sequence[VerdictRow]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = csv_path.with_name(f".{csv_path.name}.{os.getpid()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        os.replace(tmp_path, csv_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def record_verdict(
    csv_path: Path,
    *,
    episode: str,
    reel: str,
    verdict: str,
    reason: str = "",
    reel_path: Path | None = None,
    commit: str | None = None,
    replace: bool = False,
) -> VerdictRow:
    """Validate and atomically append or replace a reel verdict row."""
    episode_clean = episode.strip()
    reel_clean = reel.strip()
    if not episode_clean:
        raise ValueError("episode must be non-empty")
    if not reel_clean:
        raise ValueError("reel must be non-empty")
    canonical = canonicalize_verdict(verdict)
    reason_clean = reason.strip()
    if canonical != "publishable" and not reason_clean:
        raise ValueError(f"reason is required when verdict is {canonical!r}")

    existing = _parse_existing_csv(csv_path)
    new_row = VerdictRow(
        episode=episode_clean,
        reel=reel_clean,
        verdict=canonical,
        reason=reason_clean,
        reel_sha256=_resolve_reel_sha256(reel_clean, reel_path),
        commit=_resolve_commit(commit),
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    updated: list[VerdictRow] = []
    matched = False
    for row in existing:
        if (row.episode, row.reel) == (episode_clean, reel_clean):
            if not replace:
                raise ValueError(
                    f"Duplicate entry for episode={episode_clean!r}, reel={reel_clean!r}; "
                    "pass replace=True or --replace to update"
                )
            updated.append(new_row)
            matched = True
        else:
            updated.append(row)
    if not matched:
        updated.append(new_row)

    _atomic_write_csv(csv_path, updated)
    return new_row


def summarize_usable_rate(csv_path: Path) -> UsableRateSummary:
    """Compute aggregate and per-episode usable-rate statistics."""
    rows = load_verdict_rows(csv_path)
    counts = {"publishable": 0, "needs_fix": 0, "unusable": 0}
    by_episode: dict[str, dict[str, int]] = {}
    for row in rows:
        counts[row.verdict] += 1
        ep_counts = by_episode.setdefault(
            row.episode,
            {"total": 0, "publishable": 0, "needs_fix": 0, "unusable": 0},
        )
        ep_counts["total"] += 1
        ep_counts[row.verdict] += 1

    total = len(rows)
    if total == 0:
        return UsableRateSummary(
            total=0,
            publishable=0,
            needs_fix=0,
            unusable=0,
            usable_rate=0.0,
            wilson_ci_95=(0.0, 0.0),
            baseline=USABLE_RATE_BASELINE,
            target=USABLE_RATE_TARGET,
            delta_vs_baseline=0.0,
            delta_vs_target=0.0,
            by_episode={},
        )

    rate = counts["publishable"] / total
    ci = wilson_score_interval(rate, total)
    return UsableRateSummary(
        total=total,
        publishable=counts["publishable"],
        needs_fix=counts["needs_fix"],
        unusable=counts["unusable"],
        usable_rate=rate,
        wilson_ci_95=ci,
        baseline=USABLE_RATE_BASELINE,
        target=USABLE_RATE_TARGET,
        delta_vs_baseline=rate - USABLE_RATE_BASELINE,
        delta_vs_target=rate - USABLE_RATE_TARGET,
        by_episode=by_episode,
    )


def format_summary_markdown(summary: UsableRateSummary) -> str:
    """Render a compact Markdown summary table for Phase F3 evidence notes."""
    ci_lo, ci_hi = summary.wilson_ci_95
    lines = [
        "## Usable-Rate Summary",
        "",
        f"- Total reels rated: `{summary.total}`",
        f"- Publishable: `{summary.publishable}` (`{summary.usable_rate * 100:.1f}%`, "
        f"95% Wilson CI `[{ci_lo * 100:.1f}%, {ci_hi * 100:.1f}%]`)",
        f"- Needs fix: `{summary.needs_fix}`",
        f"- Unusable: `{summary.unusable}`",
        f"- Delta vs OpusClip baseline (`{summary.baseline * 100:.0f}%`): "
        f"`{summary.delta_vs_baseline * 100:+.1f} pp`",
        f"- Delta vs HawEdit target (`{summary.target * 100:.0f}%`): "
        f"`{summary.delta_vs_target * 100:+.1f} pp`",
    ]
    if summary.by_episode:
        lines.extend(
            [
                "",
                "| Episode | Total | Publishable | Needs fix | Unusable |",
                "|---|---|---|---|---|",
            ]
        )
        for episode, ep in sorted(summary.by_episode.items()):
            lines.append(
                f"| `{episode}` | {ep['total']} | {ep['publishable']} | "
                f"{ep['needs_fix']} | {ep['unusable']} |"
            )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.usable_rate"),
        description="Record and summarize human reel verdicts in evidence/usable-rate.csv.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_cmd = sub.add_parser("add", help="Append or update a reel verdict row.")
    add_cmd.add_argument("--episode", required=True, help="Episode identifier.")
    add_cmd.add_argument("--reel", required=True, help="Reel filename, path, or clip ID.")
    add_cmd.add_argument("--verdict", required=True, help="publishable | needs_fix | unusable")
    add_cmd.add_argument("--reason", default="", help="Required note for needs_fix / unusable.")
    add_cmd.add_argument("--reel-path", type=Path, default=None, help="Optional MP4 path to hash.")
    add_cmd.add_argument("--commit", default=None, help="Explicit git commit SHA override.")
    add_cmd.add_argument("--replace", action="store_true", help="Replace existing (episode, reel).")
    add_cmd.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="Target CSV path.")
    add_cmd.add_argument("--json", action="store_true", help="Emit JSON output to stdout.")

    sum_cmd = sub.add_parser("summary", help="Compute usable-rate tally and baseline deltas.")
    sum_cmd.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="Source CSV path.")
    sum_cmd.add_argument("--json", action="store_true", help="Emit JSON summary to stdout.")
    sum_cmd.add_argument("--markdown", action="store_true", help="Emit Markdown summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint (`python -m hawedit.usable_rate`)."""
    use_utf8_streams()
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "add":
            row = record_verdict(
                args.csv,
                episode=args.episode,
                reel=args.reel,
                verdict=args.verdict,
                reason=args.reason,
                reel_path=args.reel_path,
                commit=args.commit,
                replace=args.replace,
            )
            if args.json:
                with machine_readable_stdout() as out:
                    out.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
            else:
                print(
                    f"Recorded {row.episode}/{row.reel}: {row.verdict} (sha256={row.reel_sha256})"
                )
            return 0

        summary = summarize_usable_rate(args.csv)
        if args.json:
            with machine_readable_stdout() as out:
                out.write(json.dumps(asdict(summary), ensure_ascii=False) + "\n")
        elif args.markdown:
            print(format_summary_markdown(summary))
        else:
            ci_lo, ci_hi = summary.wilson_ci_95
            print(
                f"usable={summary.publishable}/{summary.total} ({summary.usable_rate * 100:.1f}%, "
                f"CI95 [{ci_lo * 100:.1f}%, {ci_hi * 100:.1f}%]), "
                f"needs_fix={summary.needs_fix}, unusable={summary.unusable}, "
                f"vs_baseline={summary.delta_vs_baseline * 100:+.1f}pp, "
                f"vs_target={summary.delta_vs_target * 100:+.1f}pp"
            )
        return 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
