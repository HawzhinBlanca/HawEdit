"""`start_pipeline`, the first of the architecture record's workflow-lifecycle tools (line 187).

Same propose/commit shape as every mutating capability in this codebase since D-A6:
`propose_start_pipeline` validates and never touches `dbos` or the filesystem beyond reading;
`commit_start_pipeline` is the only function that actually starts a durable run, and it is not
a tool any agent registers (`workflow_agent.py`).

**Scoped to a small, safe slice of `pipeline.py`'s CLI, not the whole 25-flag surface.**
`build_parser()` (`pipeline.py`) accepts `--omni-asr`, `--gemini`, `--visual`, `--confidential`,
`--zero-data-retention`, `--qc-pass`, device selection, and more — an agent proposing to start a
run should not be tuning compliance flags (`--confidential`/`--zero-data-retention`) or
bypassing the human QC gate (`--qc-pass`) by itself. This module exposes exactly three
parameters: `source` (the file to process), `media_id` (optional label), and `transcript` (an
optional pre-existing transcript, since live ASR/Gemini calls are blocked in this environment
anyway — `BLOCKED.md` #1/#3). Everything else runs at `pipeline.py`'s own defaults, the same
degraded-but-honest run `_build_and_run` already produces for any caller who supplies neither
`--omni-asr` nor `--gemini`: `StageSkipped`, not a crash, matching every other stage's own
graceful-absence handling this codebase has followed since Phase 0.

**`work_dir` is bound the same way it is everywhere else in this codebase — never a
caller-suppliable path for the agent side.** `propose_start_pipeline`/`commit_start_pipeline`
both take `work_dir` as an explicit argument the *human or application wiring* supplies (mirroring
every `propose_*`/`commit_*` pair since D-A6); `workflow_agent.py`'s tool closes over
`Deps.work_dir` exactly like every other agent tool in this codebase, so an agent instance can
propose starting a run only into the one directory it was constructed with.

**A run must not silently overwrite a completed one.** `propose_start_pipeline` refuses if
`work_dir/report.json` already exists — the same "a revision is additive, never destructive"
principle `proposals.py` already holds for boundary/caption revisions, applied to the run that
would produce the first `report.json` in the first place.

**Recorded as a decision delta, same as every other commit.** `commit_start_pipeline` records a
`DecisionDelta` (`learning.py`) with `kind="start_pipeline"` on every outcome — approved,
declined, or refused before a human ever saw the proposal — for the same reason D-A13 recorded
boundary/caption commits: starting a real, compute-consuming run is exactly the kind of decision
worth a permanent, reasoned record.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.cli import program_name, use_utf8_streams
from hawedit.learning import DecisionOutcome, ReasonCode, record_decision_delta
from hawedit.proposals import _interactive_confirm

__all__ = [
    "StartPipelineProposal",
    "WorkflowRejected",
    "commit_start_pipeline",
    "main",
    "propose_start_pipeline",
]


class WorkflowRejected(ValueError):
    """Raised by `commit_start_pipeline` (and `commit_cancel_run`, to follow) when the gate
    refuses: an invalid proposal, an unattributed approver, or an explicit decline — the same
    three refusals `RevisionRejected` names for content revisions, kept as a distinct type
    since starting or cancelling a run is not a revision of anything."""


@dataclass(frozen=True, slots=True)
class StartPipelineProposal:
    """A proposed pipeline run, and whether it is safe to start."""

    source: str
    media_id: str | None
    transcript: str | None
    valid: bool
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "media_id": self.media_id,
            "transcript": self.transcript,
            "valid": self.valid,
            "violation": self.violation,
        }


def propose_start_pipeline(
    work_dir: Path,
    source: Path,
    media_id: str | None = None,
    transcript: Path | None = None,
) -> StartPipelineProposal:
    """Validate that starting a durable pipeline run into `work_dir` is well-formed.

    Never touches `dbos`, never starts anything — the same "propose never writes" guarantee
    `propose_boundary_revision` holds.
    """
    if not source.is_file():
        return StartPipelineProposal(
            source=str(source),
            media_id=media_id,
            transcript=str(transcript) if transcript else None,
            valid=False,
            violation=f"no file at {source} — nothing to process",
        )
    if transcript is not None and not transcript.is_file():
        return StartPipelineProposal(
            source=str(source),
            media_id=media_id,
            transcript=str(transcript),
            valid=False,
            violation=f"no transcript file at {transcript}",
        )
    if (work_dir / "report.json").is_file():
        return StartPipelineProposal(
            source=str(source),
            media_id=media_id,
            transcript=str(transcript) if transcript else None,
            valid=False,
            violation=(
                f"{work_dir} already has a completed run (report.json exists) — starting "
                f"again would overwrite it silently. Remove it deliberately, or choose a "
                f"different work_dir."
            ),
        )
    return StartPipelineProposal(
        source=str(source),
        media_id=media_id,
        transcript=str(transcript) if transcript else None,
        valid=True,
        violation=None,
    )


def commit_start_pipeline(
    work_dir: Path,
    proposal: StartPipelineProposal,
    approved_by: str,
    reason_code: ReasonCode,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> dict[str, Any]:
    """Start the durable pipeline run `proposal` describes. The only write in this module.

    Args:
        approved_by: who is approving. Required and non-blank — every commit function in this
            codebase applies the same rule.
        reason_code: why the human is starting this run — required unconditionally, matching
            `commit_boundary_revision`'s own rule (D-A13).

    Raises:
        WorkflowRejected: the proposal is invalid, `approved_by` is blank, or `confirm` returns
            a refusal.
    """
    delta_media_id = proposal.media_id or Path(proposal.source).stem
    if not proposal.valid:
        record_decision_delta(
            work_dir,
            delta_media_id,
            "start_pipeline",
            DecisionOutcome.REFUSED_INVALID,
            proposal.to_dict(),
        )
        raise WorkflowRejected(f"proposal for {proposal.source!r} is invalid: {proposal.violation}")
    if not approved_by.strip():
        record_decision_delta(
            work_dir,
            delta_media_id,
            "start_pipeline",
            DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal.to_dict(),
        )
        raise WorkflowRejected(
            "starting a run needs a named approver; an unattributed approval is not one."
        )
    prompt = f"start a pipeline run on {proposal.source!r} into {work_dir}?"
    if not confirm(prompt):
        record_decision_delta(
            work_dir,
            delta_media_id,
            "start_pipeline",
            DecisionOutcome.DECLINED,
            proposal.to_dict(),
            reason_code=reason_code,
            approved_by=approved_by,
        )
        raise WorkflowRejected(f"{approved_by!r} declined starting the run")

    record_decision_delta(
        work_dir,
        delta_media_id,
        "start_pipeline",
        DecisionOutcome.APPROVED,
        proposal.to_dict(),
        reason_code=reason_code,
        approved_by=approved_by,
    )

    from hawedit.durable_workflow import run_durable  # deferred: needs dbos (D-A2/D-A3)

    argv = [proposal.source, "--work-dir", str(work_dir)]
    if proposal.media_id:
        argv += ["--media-id", proposal.media_id]
    if proposal.transcript:
        argv += ["--transcript", proposal.transcript]
    return run_durable(argv)


def main(argv: list[str] | None = None) -> int:
    """`hawedit-workflow start <source> --work-dir DIR --approved-by NAME --reason-code CODE
    [--media-id ID] [--transcript PATH]`.

    A single subcommand today (`start`); the parser is split into subcommands rather than
    `hawedit-revise`'s flag-dispatch shape because a future `cancel` subcommand needs an
    entirely different positional argument (a run reference, not a source file), not another
    flag on the same command.

    Proposes, prints the validation result, and — only if valid — asks on the real terminal
    before committing. No flag skips that prompt, the same discipline `hawedit-revise` holds.

    Exit codes: 0 committed; 1 declined or invalid; 2 bad arguments or no source to process.
    """
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.workflow_control"),
        description="Propose and, on explicit approval, start a HawEdit pipeline run.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="propose and start a new pipeline run")
    start.add_argument("source", type=Path)
    start.add_argument("--work-dir", type=Path, required=True)
    start.add_argument("--media-id")
    start.add_argument("--transcript", type=Path)
    start.add_argument("--approved-by", required=True)
    start.add_argument(
        "--reason-code",
        required=True,
        choices=[member.value for member in ReasonCode],
        help="why this decision is being made — required unconditionally, like --approved-by",
    )
    args = parser.parse_args(argv)

    proposal = propose_start_pipeline(
        args.work_dir, args.source, media_id=args.media_id, transcript=args.transcript
    )
    print(f"{proposal.source}: {'valid' if proposal.valid else 'invalid'}")
    if not proposal.valid:
        print(f"✗ invalid — {proposal.violation}", file=sys.stderr)
        return 1

    try:
        result = commit_start_pipeline(
            args.work_dir,
            proposal,
            args.approved_by,
            ReasonCode(args.reason_code),
        )
    except WorkflowRejected as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print(f"started: media_id={result.get('media_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
