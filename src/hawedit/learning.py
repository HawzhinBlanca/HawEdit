"""Phase 4's decision-delta ledger: every commit outcome, human-reasoned, replayable.

`AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md`'s "safe learning loop" (lines 265-294): "Store
structured deltas such as moved boundary, rejected candidate, caption correction, reason codes
and final approval. Do not treat every user action as a preference: undo operations,
experiments, accidental changes and policy-forced changes need distinct labels."

**What this closes: a decline currently writes nothing.** `commit_boundary_revision`/
`commit_caption_revision` (`proposals.py`) raise `RevisionRejected` for an invalid proposal, an
unattributed approver, or an explicit decline — and in all three cases nothing reaches disk (the
only write in either function is the `_write_atomic` call after `confirm()` returns true). An
approval and a decline are both facts worth a permanent record: Phase 4's "final approval" needs
the approvals, and offline replay needs the declines just as much, since a validator that would
now accept what a human once rejected is exactly the regression worth catching.

**`reason_code` is required on every decision a human actually made, never inferred.** The
record is explicit that a click is not automatically a preference. `commit_boundary_revision`/
`commit_caption_revision` take a `reason_code: ReasonCode` parameter — the human committing (or
declining) states why, the same way `approved_by` already requires a name rather than assuming
one. A proposal that never reaches a human — invalid, or an unattributed approval attempt —
carries no reason code at all: nobody made a reasoned decision, so nothing here invents one.
`DecisionDelta.__post_init__` enforces this both ways.

**Same append-only JSONL shape as `events.py`'s ledger, a deliberately separate file.**
`RunEvent`'s schema is purpose-built for pipeline stage transitions — a 3-state enum with a
skip/reason coupling baked into validation — and cannot carry a decision delta without breaking
that invariant. This is a sibling ledger (`work_dir/decisions.jsonl`), open-append,
flush-per-line, tolerant of a torn last line — the same properties `JsonlEventSink`/
`read_events` exist for, and for the same reason: a crash must not lose an already-recorded
decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DecisionDelta",
    "DecisionOutcome",
    "JsonlDecisionSink",
    "ReasonCode",
    "ReplayFinding",
    "read_decision_deltas",
    "record_decision_delta",
]


class ReasonCode(Enum):
    """Why a human made this decision — required, never inferred.

    The record's own words: "undo operations, experiments, accidental changes and
    policy-forced changes need distinct labels" from a genuine preference.
    """

    PREFERENCE = "preference"
    UNDO = "undo"
    EXPERIMENT = "experiment"
    ACCIDENT = "accident"
    POLICY_FORCED = "policy_forced"


class DecisionOutcome(Enum):
    """What happened to a proposal.

    The two `REFUSED_*` values never reached a human — `commit_*_revision` refuses before the
    approval prompt is even shown — so no `ReasonCode` applies to a decision nobody made.
    """

    APPROVED = "approved"
    DECLINED = "declined"
    REFUSED_INVALID = "refused_invalid"
    REFUSED_UNATTRIBUTED = "refused_unattributed"


_HUMAN_REACHED: Final[frozenset[DecisionOutcome]] = frozenset(
    {DecisionOutcome.APPROVED, DecisionOutcome.DECLINED}
)


@dataclass(frozen=True, slots=True)
class DecisionDelta:
    """One recorded outcome of one proposal, structured rather than a free-text log line."""

    media_id: str
    kind: str
    outcome: DecisionOutcome
    proposal: dict[str, Any]
    sequence: int
    reason_code: ReasonCode | None = None
    approved_by: str | None = None

    def __post_init__(self) -> None:
        if not self.media_id.strip():
            raise ValueError("a decision delta belongs to a run; media_id is empty")
        if self.kind not in ("boundary", "caption", "start_pipeline", "cancel_run", "resume_run"):
            raise ValueError(
                f"unknown decision kind {self.kind!r} — expected boundary/caption/"
                f"start_pipeline/cancel_run/resume_run"
            )
        if self.sequence < 1:
            raise ValueError(f"decision sequence starts at 1, not {self.sequence}")
        human_reached = self.outcome in _HUMAN_REACHED
        if human_reached and self.reason_code is None:
            raise ValueError(
                f"a {self.outcome.value} decision carries no reason_code — a human made this "
                f"decision and must state why, not have it assumed a preference."
            )
        if not human_reached and self.reason_code is not None:
            raise ValueError(
                f"a {self.outcome.value} decision never reached a human, so it cannot carry a "
                f"reason_code ({self.reason_code.value})."
            )
        if human_reached and not (self.approved_by or "").strip():
            raise ValueError(f"a {self.outcome.value} decision carries no approved_by")
        if not human_reached and self.approved_by is not None:
            raise ValueError(
                f"a {self.outcome.value} decision never reached a human, so it cannot carry "
                f"approved_by ({self.approved_by!r})."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "kind": self.kind,
            "outcome": self.outcome.value,
            "proposal": self.proposal,
            "sequence": self.sequence,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "approved_by": self.approved_by,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DecisionDelta:
        reason = data.get("reason_code")
        return DecisionDelta(
            media_id=str(data["media_id"]),
            kind=str(data["kind"]),
            outcome=DecisionOutcome(str(data["outcome"])),
            proposal=dict(data["proposal"]),
            sequence=int(data["sequence"]),
            reason_code=ReasonCode(str(reason)) if reason is not None else None,
            approved_by=data.get("approved_by"),
        )


@dataclass(frozen=True, slots=True)
class ReplayFinding:
    """One recorded, approved decision whose proposal today's real validator no longer accepts.

    Only `APPROVED` deltas are worth replaying — a `DECLINED` or `REFUSED_*` decision was never
    applied, so there is no committed state for a validator regression to silently break.
    """

    sequence: int
    media_id: str
    kind: str
    violation: str


class JsonlDecisionSink:
    """Appends every `DecisionDelta` to one file, flushed immediately — same shape as
    `events.py`'s `JsonlEventSink`, for the same reason: a crash must not lose an
    already-recorded decision."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a", encoding="utf-8")

    def __call__(self, delta: DecisionDelta) -> None:
        self._handle.write(json.dumps(delta.to_dict(), ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def read_decision_deltas(path: Path) -> tuple[DecisionDelta, ...]:
    """Read one run's decision ledger back, tolerating a line a crash left half-written.

    Raises:
        FileNotFoundError: no decision was ever recorded at `path`.
    """
    deltas: list[DecisionDelta] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                deltas.append(DecisionDelta.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                # A torn last line, the same tolerance `events.py`'s read_events applies: every
                # earlier line already parsed and is kept.
                break
    return tuple(deltas)


def record_decision_delta(
    work_dir: Path,
    media_id: str,
    kind: str,
    outcome: DecisionOutcome,
    proposal: dict[str, Any],
    reason_code: ReasonCode | None = None,
    approved_by: str | None = None,
) -> DecisionDelta:
    """Append one decision to `work_dir/decisions.jsonl`, assigning the next sequence number.

    Reads the existing ledger once per call to determine that number — cheap at the scale this
    ledger actually reaches (decisions per run, not events per second), and avoids threading a
    counter across calls that, unlike `RunEventLog`, do not share a process lifetime: each
    `commit_*_revision` call is its own independent invocation.
    """
    path = work_dir / "decisions.jsonl"
    existing = read_decision_deltas(path) if path.is_file() else ()
    delta = DecisionDelta(
        media_id=media_id,
        kind=kind,
        outcome=outcome,
        proposal=proposal,
        sequence=len(existing) + 1,
        reason_code=reason_code,
        approved_by=approved_by,
    )
    sink = JsonlDecisionSink(path)
    try:
        sink(delta)
    finally:
        sink.close()
    return delta
