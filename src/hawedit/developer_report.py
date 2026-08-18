"""`export_developer_report` — the one tool the architecture record scopes outside editorial
work entirely: "If the agent finds an application defect, it creates a structured developer
report with reproduction steps, workflow/artifact IDs, sanitized logs, expected versus actual
behavior and the smallest suspected component. A separate coding agent or developer can fix it
outside the production editor identity" (line 212).

**Compose, don't file — the same split every mutating capability in this codebase already
uses.** `build_developer_report` is pure: it validates and returns a `DeveloperReport`, and
touches no disk. `write_developer_report` is the only write in this module, and it is not a
tool any agent registers — mirroring `propose_boundary_revision`/`commit_boundary_revision`
(D-A6) exactly, and for the same reason `test_nothing_reachable_from_an_agent_mutates_anything`
(D-A10) is the strongest statement this branch makes: the set of mutating capabilities reachable
from any agent is empty, not merely small. A developer report is diagnostic, not an editorial
change, but it is still a write, and this codebase does not carve out exceptions to "the model
can propose; it cannot commit" for a capability just because the write feels low-risk.

**"Sanitized logs" is a checked constraint, not a naming convention.** This project's own
domain risk is exactly what D-A16 closed for telemetry: real Kurdish transcript content
leaking somewhere it should not. A developer report about *the application* has no legitimate
reason to quote Kurdish speech verbatim — `captions.py`'s own `KURDISH_REQUIRED_GLYPHS` (letters
that do not appear in English prose) is reused here as the check: any free-text field
containing one of them is refused, on the theory that a defect report is written in English
about the system's behavior, and Kurdish-script content appearing in one is far more likely to
be an accidentally pasted transcript excerpt than a legitimate quoted string.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.captions import KURDISH_REQUIRED_GLYPHS

__all__ = [
    "DeveloperReport",
    "SanitizationError",
    "build_developer_report",
    "read_developer_reports",
    "write_developer_report",
]


class SanitizationError(ValueError):
    """Raised when a developer report field carries content it should not — today, Kurdish
    script where only English prose about the application belongs."""


def _assert_sanitized(field_name: str, text: str) -> None:
    hit = KURDISH_REQUIRED_GLYPHS & set(text)
    if hit:
        raise SanitizationError(
            f"{field_name} contains Kurdish-script character(s) {sorted(hit)} — a developer "
            f"report is prose about the application's behavior, not a place for verbatim "
            f"transcript content. If this is a genuine defect about Kurdish text handling, "
            f"describe the symptom in English and cite the media_id/workflow_id instead of "
            f"pasting the text itself."
        )


@dataclass(frozen=True, slots=True)
class DeveloperReport:
    """One structured bug report, scoped exactly to the architecture record's own list."""

    summary: str
    reproduction_steps: tuple[str, ...]
    expected_behavior: str
    actual_behavior: str
    suspected_component: str
    workflow_id: str | None = None
    artifact_ids: tuple[str, ...] = ()
    sequence: int = 1

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("a developer report needs a summary")
        if not self.reproduction_steps:
            raise ValueError("a developer report needs at least one reproduction step")
        if any(not step.strip() for step in self.reproduction_steps):
            raise ValueError("a developer report's reproduction steps must not be blank")
        if not self.expected_behavior.strip():
            raise ValueError("a developer report needs the expected behavior")
        if not self.actual_behavior.strip():
            raise ValueError("a developer report needs the actual behavior")
        if not self.suspected_component.strip():
            raise ValueError(
                "a developer report needs the smallest suspected component — 'somewhere in "
                "the pipeline' is not a component"
            )
        if self.sequence < 1:
            raise ValueError(f"developer report sequence starts at 1, not {self.sequence}")

        _assert_sanitized("summary", self.summary)
        for index, step in enumerate(self.reproduction_steps):
            _assert_sanitized(f"reproduction_steps[{index}]", step)
        _assert_sanitized("expected_behavior", self.expected_behavior)
        _assert_sanitized("actual_behavior", self.actual_behavior)
        _assert_sanitized("suspected_component", self.suspected_component)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "reproduction_steps": list(self.reproduction_steps),
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "suspected_component": self.suspected_component,
            "workflow_id": self.workflow_id,
            "artifact_ids": list(self.artifact_ids),
            "sequence": self.sequence,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DeveloperReport:
        return DeveloperReport(
            summary=str(data["summary"]),
            reproduction_steps=tuple(data["reproduction_steps"]),
            expected_behavior=str(data["expected_behavior"]),
            actual_behavior=str(data["actual_behavior"]),
            suspected_component=str(data["suspected_component"]),
            workflow_id=data.get("workflow_id"),
            artifact_ids=tuple(data.get("artifact_ids", ())),
            sequence=int(data.get("sequence", 1)),
        )


def build_developer_report(
    summary: str,
    reproduction_steps: Sequence[str],
    expected_behavior: str,
    actual_behavior: str,
    suspected_component: str,
    workflow_id: str | None = None,
    artifact_ids: Sequence[str] = (),
) -> DeveloperReport:
    """Compose and validate a developer report. Never writes — see `write_developer_report`.

    Raises:
        ValueError: a required field is missing or blank.
        SanitizationError: a free-text field contains Kurdish-script content.
    """
    return DeveloperReport(
        summary=summary,
        reproduction_steps=tuple(reproduction_steps),
        expected_behavior=expected_behavior,
        actual_behavior=actual_behavior,
        suspected_component=suspected_component,
        workflow_id=workflow_id,
        artifact_ids=tuple(artifact_ids),
    )


def write_developer_report(work_dir: Path, report: DeveloperReport) -> Path:
    """Append one developer report to `work_dir/developer_reports.jsonl`.

    The only write in this module, and not something any agent tool calls — a human or a
    separate developer-facing script decides a composed report is worth filing, the same way
    `commit_boundary_revision` is the only write in `proposals.py` and is never a tool either.
    """
    path = work_dir / "developer_reports.jsonl"
    existing = read_developer_reports(path.parent) if path.is_file() else ()
    numbered = DeveloperReport.from_dict({**report.to_dict(), "sequence": len(existing) + 1})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(numbered.to_dict(), ensure_ascii=False) + "\n")
        handle.flush()
    return path


def read_developer_reports(work_dir: Path) -> tuple[DeveloperReport, ...]:
    """Read one run's developer reports back, tolerating a line a crash left half-written.

    Raises:
        FileNotFoundError: no developer report was ever filed under `work_dir`.
    """
    reports: list[DeveloperReport] = []
    with (work_dir / "developer_reports.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                reports.append(DeveloperReport.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                break
    return tuple(reports)
