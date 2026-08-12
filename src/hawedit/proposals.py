"""Phase 3's first mutating capability: propose a boundary revision, commit only on approval.

`AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` Phase 3: "Add typed proposal tools for
boundaries... Run deterministic validators before displaying an approval request. Commit only
an explicitly approved change set." One proposal type, boundary revisions, chosen over
captions/render variants for the same reason D-A5 chose it as Phase 2's read-only span: it is
the smallest slice with a real deterministic validator already in this codebase —
`boundary.py`'s Kurdish invariant #2 — rather than one this module would have to invent.

**What "revising a boundary" means, precisely.** A `Boundary` has two hard anchors (from forced
alignment — where the selected sentences actually start and end) and a soft final span that may
only extend *outward* from them (§3 Stage 5, `boundary.py`'s own docstring). Revising a boundary
means proposing a different final span; it does not mean moving the anchors, which would be a
different operation — choosing different sentences — outside this module's scope. A proposal
that would move an anchor is not expressible here: `propose_boundary_revision` takes only
`final_in_ms`/`final_out_ms` and reads the run's own `anchor_in_ms`/`anchor_out_ms` unchanged
from its `report.json`.

**Two functions, one writes.** `propose_boundary_revision` builds a candidate `Boundary` from
the proposed span and the run's real anchors, and asks the same `assert_boundary_invariant`
`pipeline.py` itself calls at the render gate — not a reimplementation of Kurdish invariant #2,
the actual function. It never touches disk. `commit_boundary_revision` is the only thing in this
module that writes, and it refuses unless three things are all true: the proposal passed
validation, the caller names who is approving (`Governance.confirmed_by`'s pattern in
`gemini.py` — an unattributed approval is not one), and `confirm(...)` — the approval channel,
a real terminal prompt by default — returns an unambiguous yes.

**The model can propose; it cannot approve or commit.** `editor_agent.py`'s `build_editor_agent`
registers only `propose_boundary_revision` as a tool. There is no `commit_boundary_revision_tool`
on any agent in this codebase: committing a change happens only through a human directly calling
`commit_boundary_revision` (or the `hawedit-revise` CLI, which does exactly that) with a real
approval channel in the loop. This is deliberately more conservative than the architecture
record's full tool list, which includes a `commit_approved_edit` *tool* the agent could call
after some upstream `request_human_approval` step — that shape needs a real, out-of-band way to
prove a human (not the model, deciding on the model's own behalf) actually approved, which this
branch does not have yet. Until it does, the approval gate is a real terminal prompt a human
runs directly, not a tool call a model makes.

**Why the agent constructor lives in a separate module.** `build_editor_agent` needs
`pydantic_ai`, which lives behind the `agentic` extra — the same reason `durable_workflow.py`
was split from `durable.py` (D-A3): `propose_boundary_revision` and `commit_boundary_revision`
need none of it, and `hawedit-revise --help` (or a `commit_boundary_revision` call from a plain
script) should not require an extra it does not use. `editor_agent.py` imports `pydantic_ai` at
its own top level; this module does not.

**Does not re-render.** A committed revision is a written, attributed record of an approved
change — `work_dir / "revisions" / "<revision_id>.json"` — not yet a new MP4. Re-rendering with
a shifted boundary needs the selected sentences' word-level timing to rebuild captions
(`captions.py`'s `build_ass` takes `Sequence[Sentence]`, and `report.json` currently persists
only a sentence *count*, not the sentences themselves), which this repo does not persist per
run today. Named here rather than built halfway: a revision tool that silently produced a
caption-broken re-render would be a worse outcome than one that honestly stops at "approved,
pending render." See PROGRESS.md for the follow-on this leaves.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.boundary import Boundary, BoundaryInvariantViolated, assert_boundary_invariant
from hawedit.cli import program_name, use_utf8_streams
from hawedit.pipeline import _write_atomic

__all__ = [
    "BoundaryRevisionProposal",
    "RevisionRejected",
    "commit_boundary_revision",
    "propose_boundary_revision",
]


class RevisionRejected(ValueError):
    """Raised by `commit_boundary_revision` when the proposal is invalid, unattributed, or the
    approver declined. Never raised by `propose_boundary_revision`, which only ever returns a
    result — proposing an invalid revision is a fact worth reporting, not an error."""


@dataclass(frozen=True, slots=True)
class BoundaryRevisionProposal:
    """A proposed new final span for one run's boundary, and whether it is legal.

    `valid`/`violation` come from the real `assert_boundary_invariant`, not a re-derived check —
    a second implementation of Kurdish invariant #2 here could drift from the one the render
    gate actually enforces, and a proposal this module calls valid must mean the render gate
    would also accept it.
    """

    media_id: str
    original: Boundary
    proposed_final_in_ms: int
    proposed_final_out_ms: int
    valid: bool
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "original": self.original.to_dict(),
            "proposed_final_in_ms": self.proposed_final_in_ms,
            "proposed_final_out_ms": self.proposed_final_out_ms,
            "valid": self.valid,
            "violation": self.violation,
        }


def _load_boundary(work_dir: Path) -> tuple[str, Boundary]:
    """The run's `media_id` and its real `Boundary`, read from `report.json`.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
        ValueError: the run has no boundary yet — §3 Stage 5 was skipped or never reached, so
            there is nothing here for a revision to be relative to.
    """
    path = work_dir / "report.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no report.json under {work_dir} — durable_workflow.py writes this once a run "
            f"completes or stops; has one run here yet?"
        )
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    boundary = report.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("skipped"):
        reason = boundary.get("reason") if isinstance(boundary, dict) else None
        raise ValueError(
            f"the run at {work_dir} has no boundary to revise"
            + (f" — {reason}" if reason else " (§3 Stage 5 was never reached).")
        )
    return str(report["media_id"]), Boundary.from_dict(boundary)


def propose_boundary_revision(
    work_dir: Path, final_in_ms: int, final_out_ms: int
) -> BoundaryRevisionProposal:
    """Validate a proposed new final span against the run's real anchors. Never writes.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
        ValueError: the run has no boundary to revise.
    """
    media_id, original = _load_boundary(work_dir)
    candidate = Boundary(
        anchor_in_ms=original.anchor_in_ms,
        anchor_out_ms=original.anchor_out_ms,
        final_in_ms=final_in_ms,
        final_out_ms=final_out_ms,
        in_extended_by="proposed_revision",
        out_extended_by="proposed_revision",
        sentence_complete=original.sentence_complete,
    )
    try:
        assert_boundary_invariant(candidate)
        valid, violation = True, None
    except BoundaryInvariantViolated as exc:
        valid, violation = False, str(exc)
    return BoundaryRevisionProposal(
        media_id=media_id,
        original=original,
        proposed_final_in_ms=final_in_ms,
        proposed_final_out_ms=final_out_ms,
        valid=valid,
        violation=violation,
    )


def _interactive_confirm(prompt: str) -> bool:
    """The default approval channel: a real terminal prompt.

    Anything other than a bare, case-insensitive "y" is a refusal — an empty line, a typo, and
    Ctrl-D (which raises `EOFError`, treated as "no" rather than crashing an approval prompt)
    all decline. Approval must be unambiguous; a channel that defaults to yes on noise is not one.
    """
    try:
        answer = input(f"{prompt} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def commit_boundary_revision(
    work_dir: Path,
    proposal: BoundaryRevisionProposal,
    revision_id: str,
    approved_by: str,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> Path:
    """Write an approved revision record. The only function in this module that writes.

    Args:
        revision_id: names the output file (`work_dir/revisions/{revision_id}.json`) and is the
            caller's to choose — explicit rather than a timestamp or random id generated here,
            so a caller can pick a stable name and a test can assert on it without relying on
            wall-clock time. Two commits under the same id and directory overwrite; that is the
            caller's idempotency key to manage, the same way `durable_workflow.py`'s `run_id` is.
        approved_by: who is approving. Required and must be non-blank — `gemini.py`'s
            `Governance.confirmed_by` is the same rule for the same reason: an unattributed
            approval is not a recorded one.
        confirm: the approval channel. Defaults to a real terminal prompt; tests substitute a
            function that returns a fixed answer, exactly the way `gemini.py`'s `GeminiJudge`
            takes an injectable `sleep`.

    Raises:
        RevisionRejected: the proposal failed validation, `approved_by` is blank, or `confirm`
            returned a refusal.
    """
    if not proposal.valid:
        raise RevisionRejected(
            f"proposal for {proposal.media_id!r} fails Kurdish invariant #2: {proposal.violation}"
        )
    if not approved_by.strip():
        raise RevisionRejected(
            "a revision needs a named approver; an unattributed approval is not one "
            "(same rule as gemini.py's Governance.confirmed_by)."
        )
    prompt = (
        f"{proposal.media_id}: boundary {proposal.original.final_in_ms}.."
        f"{proposal.original.final_out_ms} ms -> {proposal.proposed_final_in_ms}.."
        f"{proposal.proposed_final_out_ms} ms. Apply?"
    )
    if not confirm(prompt):
        raise RevisionRejected(f"{approved_by!r} declined the proposed revision")

    record = {
        **proposal.to_dict(),
        "revision_id": revision_id,
        "approved_by": approved_by,
        "status": "approved_pending_render",
    }
    revisions_dir = work_dir / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    path = revisions_dir / f"{revision_id}.json"
    _write_atomic(path, json.dumps(record, ensure_ascii=False, indent=2))
    return path


def main(argv: list[str] | None = None) -> int:
    """`hawedit-revise <work_dir> --final-in-ms N --final-out-ms N --revision-id ID
    --approved-by NAME`.

    Proposes, prints the validation result, and — only if valid — asks on the real terminal
    before committing. No flag skips that prompt: this entry point's whole purpose is being the
    human gate, so unlike every other flag in this module's functions, there is deliberately
    nothing here to automate it away. A caller that wants a scripted approval channel calls
    `commit_boundary_revision` directly with its own `confirm`.

    Exit codes: 0 committed, 1 declined or invalid, 2 bad arguments or no report to revise.
    """
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.proposals"),
        description="Propose a boundary revision for a completed HawEdit run, and commit it "
        "only on explicit approval.",
    )
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--final-in-ms", type=int, required=True)
    parser.add_argument("--final-out-ms", type=int, required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args(argv)

    try:
        proposal = propose_boundary_revision(args.work_dir, args.final_in_ms, args.final_out_ms)
    except (FileNotFoundError, ValueError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    print(
        f"{proposal.media_id}: {proposal.original.final_in_ms}..{proposal.original.final_out_ms} "
        f"ms -> {proposal.proposed_final_in_ms}..{proposal.proposed_final_out_ms} ms"
    )
    if not proposal.valid:
        print(f"✗ invalid — {proposal.violation}", file=sys.stderr)
        return 1

    try:
        path = commit_boundary_revision(args.work_dir, proposal, args.revision_id, args.approved_by)
    except RevisionRejected as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    print(f"committed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
