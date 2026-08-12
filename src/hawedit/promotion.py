"""Phase 4's remaining bullet: shadow challengers, turned into a versioned, rollback-able state.

`judge.py` already has the evaluation half of this — `ShadowVerdict` (a shadow model's opinion,
structurally unable to ship) and `decide_judge` (§3's "empirical beats newer" rule as a pure
function) — built before this branch and never wired to anything: neither is ever called or
persisted anywhere in `src/`. This module is the missing second half of the architecture
record's loop: "Shadow or canary challenger -> Human promotion gate -> Versioned ... model" —
persistence for the shadow opinion, and a real, human-gated promotion that turns
`decide_judge`'s recommendation into an active, rollback-able version.

**Scoped to the judge model only, the one axis with real backing.** The acceptance gate names
"model, prompt, skill, policy and workflow" version. Of those, only the judge model has a real
comparison mechanism (`decide_judge`) and a real incumbent (`KURDISH_EDITORIAL_JUDGE`) to
promote against; `policy.py`'s `POLICY_VERSION` (D-A10) already covers policy. Building a
generic version registry for prompt/skill/workflow axes that have no comparison logic anywhere
in this codebase would be inventing infrastructure for content that does not exist — the
D-A11/Phase 5 mistake this branch keeps declining to repeat. `PromotionRecord.component` is a
free string so a future axis can reuse the same ledger shape without a rewrite; only `"judge"`
is produced today.

**The first system-wide (cross-run) persistent state in this branch.** Every other ledger —
`events.jsonl`, `revisions/<id>.json`, `decisions.jsonl` — is scoped to one run's `work_dir`,
because the fact it records is about that run. A promotion is different: it changes what judge
*future* runs should use, so it cannot live inside any single run's directory. Stored at
`.hawedit/judge_promotions.jsonl`, relative to the current working directory — the same
precedent `durable_workflow.py`'s `.dbos/hawedit.sqlite` already set for "state that belongs to
the installation, not to one run", and for the same reason: a single Windows box running one
CLI at a time has exactly one meaningful "current working directory" for this to mean.

**Read-only integration today, and that is a named boundary, not an oversight.**
`current_judge()` reports what the ledger says is active. `gemini.py`'s `GeminiJudge` still
defaults every constructor to the module constant `KURDISH_EDITORIAL_JUDGE`, unchanged — wiring
a dynamically promoted judge into the actual render path is a real, separate change to an
already-shipped, tested call site, not something this row silently does as a side effect of
adding a promotion ledger.

**Rollback restores the immediately preceding version, not an arbitrary point in history.** The
acceptance gate's own wording is "a rollback restores *the previous* ... version" — singular.
`rollback_judge` reads the last two ledger entries (or the pinned default, if only one
promotion has ever happened) and writes a new entry restoring the one before the most recent
change. A second rollback therefore toggles back to what the first rollback undid, the same way
a single-level undo does — an intentionally simple model, not a full history stack nothing here
claims to be.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeDecision, ShadowVerdict
from hawedit.proposals import _interactive_confirm

__all__ = [
    "DEFAULT_PROMOTION_LEDGER",
    "PromotionOutcome",
    "PromotionRecord",
    "PromotionRejected",
    "current_judge",
    "promote_judge",
    "read_shadow_verdicts",
    "record_shadow_verdict",
    "rollback_judge",
]

DEFAULT_PROMOTION_LEDGER: Final = Path(".hawedit") / "judge_promotions.jsonl"


class PromotionRejected(ValueError):
    """Raised by `promote_judge`/`rollback_judge` when the gate refuses: a decision that does
    not recommend switching, an unattributed approver, a decline, or nothing to roll back to."""


class PromotionOutcome(Enum):
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True, slots=True)
class PromotionRecord:
    """One entry in the promotion ledger — the active version after this record, and why."""

    component: str
    version: str
    outcome: PromotionOutcome
    approved_by: str
    sequence: int
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("a promotion record names no component")
        if not self.version.strip():
            raise ValueError("a promotion record names no version")
        if not self.approved_by.strip():
            raise ValueError("a promotion record carries no approver")
        if self.sequence < 1:
            raise ValueError(f"promotion sequence starts at 1, not {self.sequence}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "version": self.version,
            "outcome": self.outcome.value,
            "approved_by": self.approved_by,
            "sequence": self.sequence,
            "reasons": list(self.reasons),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> PromotionRecord:
        return PromotionRecord(
            component=str(data["component"]),
            version=str(data["version"]),
            outcome=PromotionOutcome(str(data["outcome"])),
            approved_by=str(data["approved_by"]),
            sequence=int(data["sequence"]),
            reasons=tuple(data.get("reasons", ())),
        )


def _append_json_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()


def _read_promotions(path: Path) -> tuple[PromotionRecord, ...]:
    if not path.is_file():
        return ()
    records: list[PromotionRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                records.append(PromotionRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                # A torn last line — the same tolerance events.py's read_events applies.
                break
    return tuple(records)


def current_judge(ledger_path: Path = DEFAULT_PROMOTION_LEDGER) -> str:
    """The judge model id the ledger says is active: the last promotion's version, or the
    pinned `KURDISH_EDITORIAL_JUDGE` default if no promotion has ever happened.

    Read-only, and reports the ledger's state — not what `gemini.py` actually calls; see this
    module's docstring for why those are deliberately not the same thing yet.
    """
    records = _read_promotions(ledger_path)
    return records[-1].version if records else KURDISH_EDITORIAL_JUDGE


def promote_judge(
    decision: JudgeDecision,
    approved_by: str,
    ledger_path: Path = DEFAULT_PROMOTION_LEDGER,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> Path:
    """Turn `decide_judge`'s recommendation into an active, recorded version.

    Args:
        decision: `decide_judge`'s own output. `promote_judge` does not re-run the comparison —
            it refuses to promote a decision that did not recommend switching, the same way
            `commit_boundary_revision` refuses an invalid proposal rather than re-deriving
            validity.
        approved_by: who is promoting. Required and non-blank, the same rule every commit
            function in this codebase applies to an approval.
        confirm: the approval channel. Defaults to a real terminal prompt.

    Raises:
        PromotionRejected: `decision.switch` is `False`, `approved_by` is blank, or `confirm`
            returns a refusal.
    """
    if not decision.switch or decision.challenger is None:
        raise PromotionRejected(
            f"decide_judge did not recommend switching: {'; '.join(decision.reasons)}"
        )
    if not approved_by.strip():
        raise PromotionRejected(
            "a promotion needs a named approver; an unattributed one is not one."
        )
    prompt = f"promote judge {decision.incumbent!r} -> {decision.challenger!r}?"
    if not confirm(prompt):
        raise PromotionRejected(f"{approved_by!r} declined the promotion")

    records = _read_promotions(ledger_path)
    record = PromotionRecord(
        component="judge",
        version=decision.challenger,
        outcome=PromotionOutcome.PROMOTED,
        approved_by=approved_by,
        sequence=len(records) + 1,
        reasons=decision.reasons,
    )
    _append_json_line(ledger_path, record.to_dict())
    return ledger_path


def rollback_judge(
    approved_by: str,
    ledger_path: Path = DEFAULT_PROMOTION_LEDGER,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> Path:
    """Restore the judge to what it was immediately before the most recent promotion.

    Raises:
        PromotionRejected: no promotion has ever happened (nothing to roll back), `approved_by`
            is blank, or `confirm` returns a refusal.
    """
    records = _read_promotions(ledger_path)
    if not records:
        raise PromotionRejected("no promotion is recorded; there is nothing to roll back to.")
    if not approved_by.strip():
        raise PromotionRejected(
            "a rollback needs a named approver; an unattributed one is not one."
        )
    previous = records[-2].version if len(records) >= 2 else KURDISH_EDITORIAL_JUDGE
    prompt = f"roll back judge {records[-1].version!r} -> {previous!r}?"
    if not confirm(prompt):
        raise PromotionRejected(f"{approved_by!r} declined the rollback")

    record = PromotionRecord(
        component="judge",
        version=previous,
        outcome=PromotionOutcome.ROLLED_BACK,
        approved_by=approved_by,
        sequence=len(records) + 1,
    )
    _append_json_line(ledger_path, record.to_dict())
    return ledger_path


# --- Shadow-verdict persistence, per run --------------------------------------------------
#
# Unlike the promotion ledger above, a shadow verdict is a fact about one run's Stage 4 —
# which judge is being challenged on which candidate — so it belongs beside that run's other
# artifacts, not in the system-wide `.hawedit/` directory.


def record_shadow_verdict(work_dir: Path, shadow: ShadowVerdict) -> Path:
    """Append one shadow opinion to `work_dir/shadow_verdicts.jsonl`.

    A shadow opinion nobody can read back is one `decide_judge`'s incumbent/shadow/tie tally
    cannot be reconstructed from later — this is what makes that tally possible at all.
    """
    path = work_dir / "shadow_verdicts.jsonl"
    _append_json_line(path, shadow.to_dict())
    return path


def read_shadow_verdicts(work_dir: Path) -> tuple[ShadowVerdict, ...]:
    """Read one run's recorded shadow opinions back.

    Raises:
        FileNotFoundError: no shadow verdict was ever recorded under `work_dir`.
    """
    path = work_dir / "shadow_verdicts.jsonl"
    verdicts: list[ShadowVerdict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                verdicts.append(ShadowVerdict.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                break
    return tuple(verdicts)
