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

## `cancel_run` / `resume_run` (D-A20/D-A21)

**The prerequisite D-A19 shipped without: a discoverable run ID.** `commit_start_pipeline`
called `run_durable(argv)` with no explicit `run_id`, so DBOS assigned a random UUID nothing
outside that one process call ever saw again — cancelling a run from a second process (a human
who started `hawedit-workflow start` in one terminal and wants to stop it from another) had no
ID to cancel *by*. `dbos_run_id_for(work_dir)` closes that: a pure function of `work_dir`, not a
persisted file, so `commit_start_pipeline`, `propose_cancel_run` and `propose_resume_run` all
derive the same ID independently and agree without a discovery round-trip. This also makes
`start_pipeline` idempotent in the sense the architecture record requires ("every mutating tool
must have... an idempotency key", line 199) for the first time — previously the only guard
against a duplicate submission was `propose_start_pipeline`'s `report.json`-exists check, which
does not cover the window before a run has produced one.

**Every claim below was measured against the installed `dbos==2.29.0` source, not read off a
docstring** — the same bar `durable_workflow.py` already holds itself to, extended here because
DBOS's cancel/resume semantics are exactly the kind of thing worth getting wrong quietly:

1. `DBOS.cancel_workflow(run_id)` marks the workflow `CANCELLED` in the system database and
   fails any `get_result()` awaiting it (`DBOSAwaitedWorkflowCancelledError`) — but does **not**
   stop code already executing inside a running step. `_run_pipeline_step` is one coarse step
   (`durable_workflow.py`); if a run is genuinely mid-flight in another process, cancelling it
   stops DBOS from ever recording that process's outcome as `SUCCESS`, not the process itself.
   Measured directly: a slow step cancelled mid-execution keeps running to completion, and its
   *step-level* output is still checkpointed even though the *workflow* stays `CANCELLED`.
2. `DBOS.resume_workflow(run_id)` is real, and is a **third**, genuinely distinct action from
   the two D-A19 already named (crash auto-recovery of a `PENDING` workflow at `DBOS.launch()`,
   and re-calling `run_durable` under a completed `run_id` to fetch a cached result) — D-A19's
   claim that no such third action exists was wrong, reached without checking `DBOS.dbos`'s
   actual API surface for `cancel_workflow`/`resume_workflow`/`get_workflow_status` first.
   `resume_workflow` resets a non-terminal workflow to `ENQUEUED` and a background queue thread
   (started by `DBOS.launch()`, confirmed live in `dbos/_dbos.py::_launch`) picks it up and
   re-executes it. If the step's output was already checkpointed (case 1 above — the run
   finished despite being cancelled), DBOS returns that cached output and finalizes `SUCCESS`
   without re-running `_build_and_run` at all; if it was not (the process actually died before
   finishing), it re-enters `_run_pipeline_step(argv)` from scratch, safe for the same reason
   crash recovery already is — the pipeline's own digest caches reuse whatever completed.
3. Reusing a `run_id` that is already `CANCELLED` to start a *new* logical run under it does not
   silently execute — `DBOS.cancel_workflow`/`run_pipeline_workflow` raises
   `DBOSAwaitedWorkflowCancelledError` immediately, the underlying step body never runs a second
   time. `commit_start_pipeline` does not catch this and translate it: it propagates exactly as
   `_build_and_run`'s own exceptions already do (see that function's docstring), and the honest
   recovery from it is `resume_run`, not a second `start_pipeline` into the same `work_dir`.

**Cancelling never cascades to children.** `DBOS.cancel_workflow(run_id, cancel_children=...)`
takes a flag for exactly this, hardcoded `False` here rather than exposed as a parameter:
`run_pipeline_workflow` is the only `@DBOS.workflow()` in this codebase (grepped, not assumed),
so there are no children to cascade to, and a parameter with one legal value is not a parameter.

**Same propose/commit split, same decision-delta recording, extended rather than duplicated.**
`propose_cancel_run`/`propose_resume_run` are the one place in this codebase where "propose"
legitimately needs `dbos` (deferred-imported, same as `commit_start_pipeline`) — determining
"is there anything to cancel/resume" is inherently a question DBOS's system database answers,
unlike `propose_start_pipeline`'s pure filesystem checks. Both still never *write*: querying
`DBOS.get_workflow_status` is a read, the same guarantee every other `propose_*` in this
codebase holds, just extended to cover a read that happens to cross the `dbos` boundary rather
than only the filesystem. `commit_cancel_run`/`commit_resume_run` record a `DecisionDelta` with
`kind="cancel_run"`/`"resume_run"` on every outcome, same as `commit_start_pipeline`; neither is
registered as a tool on any agent (`workflow_agent.py` registers only the two `propose_*_tool`
functions), so `mutating_tool_names()` (`policy.py`) stays `()`.
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
    "CancelRunProposal",
    "ResumeRunProposal",
    "StartPipelineProposal",
    "WorkflowRejected",
    "commit_cancel_run",
    "commit_resume_run",
    "commit_start_pipeline",
    "dbos_run_id_for",
    "main",
    "propose_cancel_run",
    "propose_resume_run",
    "propose_start_pipeline",
]


class WorkflowRejected(ValueError):
    """Raised by `commit_start_pipeline`, `commit_cancel_run` and `commit_resume_run` when the
    gate refuses: an invalid proposal, an unattributed approver, or an explicit decline — the
    same three refusals `RevisionRejected` names for content revisions, kept as a distinct type
    since starting, cancelling or resuming a run is not a revision of anything."""


def dbos_run_id_for(work_dir: Path) -> str:
    """The DBOS workflow ID a durable run at `work_dir` runs under.

    A pure function of `work_dir` — never persisted, never agent-suppliable — so
    `commit_start_pipeline`, `propose_cancel_run` and `propose_resume_run` always agree on the
    same ID without a discovery file or a race between writing one and reading it back.
    `work_dir` is resolved first so a relative and an absolute path to the same directory yield
    the same ID; the `hawedit-run:` prefix keeps it readable in DBOS's own system database
    rather than a bare path indistinguishable from any other string DBOS might see there.
    """
    return f"hawedit-run:{work_dir.resolve()}"


def _delta_media_id_for(work_dir: Path) -> str:
    """The `media_id` `commit_cancel_run`/`commit_resume_run` record a `DecisionDelta` under.

    `work_dir.name` is truthy even when it is only whitespace (`"   "` is a non-empty string),
    but `DecisionDelta.__post_init__` requires `media_id.strip()` to be non-blank — checking
    truthiness on the *stripped* value here means a work_dir like `.../work/   ` falls back to
    `str(work_dir)` instead of reaching `record_decision_delta` with a value that would then
    raise an unhandled `ValueError` in a constructor two calls away, rather than this module's
    own `WorkflowRejected`. A pure function so the fix is tested directly, without needing a
    real directory with a whitespace-only name to exist on disk (Windows does not reliably
    create one via `Path.mkdir` — the OS itself normalizes a trailing-space path component away,
    a real platform difference this function's own test discovered and works around).
    """
    return work_dir.name if work_dir.name.strip() else str(work_dir)


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
    return run_durable(argv, run_id=dbos_run_id_for(work_dir))


# --- cancel_run (D-A20) -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CancelRunProposal:
    """Whether the durable run at `work_dir` can be cancelled, and its DBOS status right now."""

    work_dir: str
    run_id: str
    valid: bool
    current_status: str | None
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_dir": self.work_dir,
            "run_id": self.run_id,
            "valid": self.valid,
            "current_status": self.current_status,
            "violation": self.violation,
        }


def propose_cancel_run(work_dir: Path) -> CancelRunProposal:
    """Check whether the run at `work_dir` has a cancellable DBOS workflow.

    A read, never a write: asks `DBOS.get_workflow_status`, the same "propose never mutates"
    guarantee every other proposal in this codebase holds — this one just needs `dbos`
    (deferred-imported) to answer it, since "is there a run in flight" is a question only DBOS's
    system database can answer, not the filesystem.
    """
    run_id = dbos_run_id_for(work_dir)
    from dbos import DBOS

    from hawedit.durable_workflow import configure_dbos  # deferred: needs dbos (D-A2/D-A3)

    configure_dbos()
    status = DBOS.get_workflow_status(run_id)
    if status is None:
        return CancelRunProposal(
            work_dir=str(work_dir),
            run_id=run_id,
            valid=False,
            current_status=None,
            violation=(
                f"no DBOS workflow found for {work_dir} — either no run was ever started "
                f"durably here, or DBOS's system database does not know this run_id."
            ),
        )
    if status.status in ("SUCCESS", "ERROR"):
        return CancelRunProposal(
            work_dir=str(work_dir),
            run_id=run_id,
            valid=False,
            current_status=status.status,
            violation=f"run already finished ({status.status}) — nothing to cancel.",
        )
    if status.status == "CANCELLED":
        return CancelRunProposal(
            work_dir=str(work_dir),
            run_id=run_id,
            valid=False,
            current_status=status.status,
            violation="run is already cancelled.",
        )
    return CancelRunProposal(
        work_dir=str(work_dir),
        run_id=run_id,
        valid=True,
        current_status=status.status,
        violation=None,
    )


def commit_cancel_run(
    work_dir: Path,
    proposal: CancelRunProposal,
    approved_by: str,
    reason_code: ReasonCode,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> dict[str, Any]:
    """Cancel the DBOS workflow `proposal` names. The only write in this section.

    Marks the workflow `CANCELLED` in DBOS's system database and fails any caller awaiting its
    result — it does **not** stop code already executing inside a running step (measured; see
    the module docstring). `cancel_children` is hardcoded `False`: `run_pipeline_workflow` is
    this codebase's only `@DBOS.workflow()`, so there are no children to cascade to.

    Raises:
        WorkflowRejected: the proposal is invalid, `approved_by` is blank, or `confirm` returns
            a refusal.
    """
    delta_media_id = _delta_media_id_for(work_dir)
    if not proposal.valid:
        record_decision_delta(
            work_dir,
            delta_media_id,
            "cancel_run",
            DecisionOutcome.REFUSED_INVALID,
            proposal.to_dict(),
        )
        raise WorkflowRejected(f"cannot cancel the run at {work_dir}: {proposal.violation}")
    if not approved_by.strip():
        record_decision_delta(
            work_dir,
            delta_media_id,
            "cancel_run",
            DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal.to_dict(),
        )
        raise WorkflowRejected(
            "cancelling a run needs a named approver; an unattributed approval is not one."
        )
    prompt = (
        f"cancel the run at {work_dir} (DBOS workflow {proposal.run_id!r}, currently "
        f"{proposal.current_status})? This does not stop work already in progress in another "
        f"process — it only stops DBOS from recording that process's result as successful."
    )
    if not confirm(prompt):
        record_decision_delta(
            work_dir,
            delta_media_id,
            "cancel_run",
            DecisionOutcome.DECLINED,
            proposal.to_dict(),
            reason_code=reason_code,
            approved_by=approved_by,
        )
        raise WorkflowRejected(f"{approved_by!r} declined cancelling the run")

    record_decision_delta(
        work_dir,
        delta_media_id,
        "cancel_run",
        DecisionOutcome.APPROVED,
        proposal.to_dict(),
        reason_code=reason_code,
        approved_by=approved_by,
    )

    from dbos import DBOS

    from hawedit.durable_workflow import configure_dbos  # deferred: needs dbos (D-A2/D-A3)

    configure_dbos()
    DBOS.cancel_workflow(proposal.run_id, cancel_children=False)
    after = DBOS.get_workflow_status(proposal.run_id)
    return {
        "run_id": proposal.run_id,
        "previous_status": proposal.current_status,
        "status": after.status if after else None,
    }


# --- resume_run (D-A21) --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResumeRunProposal:
    """Whether the run at `work_dir` has a resumable DBOS workflow, and its status right now."""

    work_dir: str
    run_id: str
    valid: bool
    current_status: str | None
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_dir": self.work_dir,
            "run_id": self.run_id,
            "valid": self.valid,
            "current_status": self.current_status,
            "violation": self.violation,
        }


def propose_resume_run(work_dir: Path) -> ResumeRunProposal:
    """Check whether the run at `work_dir` has a DBOS workflow worth resuming.

    Valid only for `CANCELLED` or `MAX_RECOVERY_ATTEMPTS_EXCEEDED` — the two states a human
    resuming something is actually acting on. `PENDING`/`ENQUEUED` are already in flight (DBOS's
    own recovery already owns those); `SUCCESS`/`ERROR` are terminal. A read, same as
    `propose_cancel_run` — see that function for why this is the one place `propose_*`
    legitimately needs `dbos`.
    """
    run_id = dbos_run_id_for(work_dir)
    from dbos import DBOS

    from hawedit.durable_workflow import configure_dbos  # deferred: needs dbos (D-A2/D-A3)

    configure_dbos()
    status = DBOS.get_workflow_status(run_id)
    if status is None:
        return ResumeRunProposal(
            work_dir=str(work_dir),
            run_id=run_id,
            valid=False,
            current_status=None,
            violation=f"no DBOS workflow found for {work_dir} — nothing to resume.",
        )
    if status.status in ("SUCCESS", "ERROR"):
        return ResumeRunProposal(
            work_dir=str(work_dir),
            run_id=run_id,
            valid=False,
            current_status=status.status,
            violation=(
                f"run already finished ({status.status}) — nothing to resume; start a new run "
                f"into a different work_dir instead."
            ),
        )
    if status.status in ("PENDING", "ENQUEUED"):
        return ResumeRunProposal(
            work_dir=str(work_dir),
            run_id=run_id,
            valid=False,
            current_status=status.status,
            violation=f"run is already {status.status.lower()} — nothing to resume.",
        )
    return ResumeRunProposal(
        work_dir=str(work_dir),
        run_id=run_id,
        valid=True,
        current_status=status.status,
        violation=None,
    )


def commit_resume_run(
    work_dir: Path,
    proposal: ResumeRunProposal,
    approved_by: str,
    reason_code: ReasonCode,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> dict[str, Any]:
    """Resume the DBOS workflow `proposal` names. The only write in this section.

    Returns exactly what `commit_start_pipeline` returns on success — the run's own
    `PipelineRun.to_dict()` — since a resumed workflow is the same logical run continuing, not a
    new one. If its step output was already checkpointed (the process kept running despite an
    earlier cancel), DBOS returns that cached result without re-running `_build_and_run`;
    otherwise it re-enters `_run_pipeline_step(argv)` from scratch, safe for the same reason
    crash recovery already is.

    Raises:
        WorkflowRejected: the proposal is invalid, `approved_by` is blank, or `confirm` returns
            a refusal.
    """
    delta_media_id = _delta_media_id_for(work_dir)
    if not proposal.valid:
        record_decision_delta(
            work_dir,
            delta_media_id,
            "resume_run",
            DecisionOutcome.REFUSED_INVALID,
            proposal.to_dict(),
        )
        raise WorkflowRejected(f"cannot resume the run at {work_dir}: {proposal.violation}")
    if not approved_by.strip():
        record_decision_delta(
            work_dir,
            delta_media_id,
            "resume_run",
            DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal.to_dict(),
        )
        raise WorkflowRejected(
            "resuming a run needs a named approver; an unattributed approval is not one."
        )
    prompt = (
        f"resume the run at {work_dir} (DBOS workflow {proposal.run_id!r}, currently "
        f"{proposal.current_status})?"
    )
    if not confirm(prompt):
        record_decision_delta(
            work_dir,
            delta_media_id,
            "resume_run",
            DecisionOutcome.DECLINED,
            proposal.to_dict(),
            reason_code=reason_code,
            approved_by=approved_by,
        )
        raise WorkflowRejected(f"{approved_by!r} declined resuming the run")

    record_decision_delta(
        work_dir,
        delta_media_id,
        "resume_run",
        DecisionOutcome.APPROVED,
        proposal.to_dict(),
        reason_code=reason_code,
        approved_by=approved_by,
    )

    from dbos import DBOS

    from hawedit.durable_workflow import configure_dbos  # deferred: needs dbos (D-A2/D-A3)

    configure_dbos()
    handle = DBOS.resume_workflow(proposal.run_id)
    result: dict[str, Any] = handle.get_result()
    return result


def _add_approval_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--work-dir", type=Path, required=True)
    subparser.add_argument("--approved-by", required=True)
    subparser.add_argument(
        "--reason-code",
        required=True,
        choices=[member.value for member in ReasonCode],
        help="why this decision is being made — required unconditionally, like --approved-by",
    )


def main(argv: list[str] | None = None) -> int:
    """`hawedit-workflow {start,cancel,resume} ... --work-dir DIR --approved-by NAME
    --reason-code CODE`.

    Three subcommands. `cancel`/`resume` take no positional argument, unlike `start` — D-A19's
    docstring here anticipated a "run reference" positional for `cancel`; `dbos_run_id_for`
    (D-A20) made that unnecessary, since `--work-dir` alone determines the DBOS workflow ID.

    Proposes, prints the validation result, and — only if valid — asks on the real terminal
    before committing. No flag skips that prompt, the same discipline `hawedit-revise` holds.

    Exit codes: 0 committed; 1 declined or invalid; 2 bad arguments or no source to process.
    """
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.workflow_control"),
        description="Propose and, on explicit approval, start/cancel/resume a HawEdit run.",
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

    cancel = subparsers.add_parser("cancel", help="propose and cancel a run in flight")
    _add_approval_arguments(cancel)

    resume = subparsers.add_parser("resume", help="propose and resume a cancelled/stalled run")
    _add_approval_arguments(resume)

    args = parser.parse_args(argv)

    if args.command == "start":
        proposal = propose_start_pipeline(
            args.work_dir, args.source, media_id=args.media_id, transcript=args.transcript
        )
        print(f"{proposal.source}: {'valid' if proposal.valid else 'invalid'}")
        if not proposal.valid:
            print(f"✗ invalid — {proposal.violation}", file=sys.stderr)
            return 1
        try:
            result = commit_start_pipeline(
                args.work_dir, proposal, args.approved_by, ReasonCode(args.reason_code)
            )
        except WorkflowRejected as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        print(f"started: media_id={result.get('media_id')}")
        return 0

    if args.command == "cancel":
        cancel_proposal = propose_cancel_run(args.work_dir)
        print(f"{cancel_proposal.run_id}: {'valid' if cancel_proposal.valid else 'invalid'}")
        if not cancel_proposal.valid:
            print(f"✗ invalid — {cancel_proposal.violation}", file=sys.stderr)
            return 1
        try:
            cancel_result = commit_cancel_run(
                args.work_dir, cancel_proposal, args.approved_by, ReasonCode(args.reason_code)
            )
        except WorkflowRejected as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        print(f"cancelled: status={cancel_result.get('status')}")
        return 0

    # args.command == "resume"
    resume_proposal = propose_resume_run(args.work_dir)
    print(f"{resume_proposal.run_id}: {'valid' if resume_proposal.valid else 'invalid'}")
    if not resume_proposal.valid:
        print(f"✗ invalid — {resume_proposal.violation}", file=sys.stderr)
        return 1
    try:
        resume_result = commit_resume_run(
            args.work_dir, resume_proposal, args.approved_by, ReasonCode(args.reason_code)
        )
    except WorkflowRejected as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print(f"resumed: media_id={resume_result.get('media_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
