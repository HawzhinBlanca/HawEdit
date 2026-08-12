"""Phase 3's mutating capability: propose a boundary revision, commit on approval, re-render.

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

**Three functions, two writes.** `propose_boundary_revision` builds a candidate `Boundary` from
the proposed span and the run's real anchors, and asks the same `assert_boundary_invariant`
`pipeline.py` itself calls at the render gate — not a reimplementation of Kurdish invariant #2,
the actual function. It never touches disk. `commit_boundary_revision` refuses unless three
things are all true: the proposal passed validation, the caller names who is approving
(`Governance.confirmed_by`'s pattern in `gemini.py` — an unattributed approval is not one), and
`confirm(...)` — the approval channel, a real terminal prompt by default — returns an
unambiguous yes; only then does it write the approval record. `render_boundary_revision` is the
second and only other write, deliberately a separate call — see below for why.

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

**Render is a separate call from commit, deliberately.** `render_boundary_revision` touches
`work_dir / "revisions" / "<id>.{mp4,ass,srt,edl}"` and nothing else does. It is not folded into
`commit_boundary_revision` because a render can fail for reasons that have nothing to do with
whether the revision was legal or approved (no ffmpeg, a missing RTL-capable font, disk full),
and collapsing "the human approved this" into the same call as "the encode succeeded" would make
a legitimate approval look like a failure, or worse, silently drop the recorded approval if the
encode happened to fail. The CLI runs both in sequence (skippable with `--no-render`) and
reports each outcome separately.

**Re-rendering reuses `PipelineRun.selected_sentences` (D-A7), not a re-derived transcript.**
`durable_workflow.py`'s step now persists the exact `Sentence` objects §5's original boundary
was built from — not the episode's full segmentation, not raw words, the specific subset
`build_ass`/`build_srt` were originally timed against. A revision does not change *which*
sentences were selected, only how much soft padding surrounds them, so the same sentences,
re-timed to the revised span's `clip_in_ms`, are the correct captions for the revised clip. Runs
from before this field existed have `selected_sentences == ()`; `render_boundary_revision`
refuses those explicitly rather than rendering silent, empty captions.

**The clip's editorial/output/QC blocks are reused from the original — reused, not re-derived.**
`Clip.assert_renderable` (called inside `render_clip`) requires an editorial block (Stage 4's
judgment) and an output block (title/description/hashtags/crop target); a boundary revision
changes neither of those, only the cut points, so `Clip.from_dict(report["clip"])` plus
`dataclasses.replace` for the new `in_ms`/`out_ms`/`boundary` is correct rather than a
convenience. QC is the one field this module supplies fresh — `Qc(auto_pass=False,
human_reviewed=True)` — because the interactive approval `commit_boundary_revision` already
required *is* the human review for this specific change; reusing the original clip's QC record
would attribute this decision to whoever reviewed a different span.

**Still a real, named simplification: revisions always render with a static centre crop.**
Reproducing face-tracked reframing over a boundary that may now cover different footage would
mean re-running `reframe.py`'s tracker against the source for the new span — real additional
scope this slice does not take on. `focus_points=()` unconditionally. A revision of a
face-tracked original therefore renders centred, not tracked; this is visible in the revision
record it writes, not hidden in one that claims otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from hawedit.boundary import Boundary, BoundaryInvariantViolated, assert_boundary_invariant
from hawedit.captions import CaptionStyle, build_ass
from hawedit.cli import program_name, use_utf8_streams
from hawedit.clip import Clip, Qc
from hawedit.delivery import DeliveryError, build_edl, build_srt
from hawedit.ingest import IngestError
from hawedit.pipeline import FONTS_DIR, _proxy_dimensions, _write_atomic
from hawedit.render import RenderError, frame_rate, render_clip
from hawedit.sentences import Sentence, UndeliverableOrder
from hawedit.transcripts import Word

__all__ = [
    "BoundaryRevisionProposal",
    "RevisionRejected",
    "commit_boundary_revision",
    "propose_boundary_revision",
    "render_boundary_revision",
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
    """Write an approved revision record. Does not render — see `render_boundary_revision`.

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


def _sentence_from_dict(data: dict[str, Any]) -> Sentence:
    """The inverse of `dataclasses.asdict(sentence)` — `pipeline.py`'s own serialization for
    `PipelineRun.selected_sentences`, matching `RawTranscript.from_json`'s `Word(**w)` pattern
    for the same nested-dataclass shape."""
    return Sentence(words=tuple(Word(**w) for w in data["words"]), complete=data["complete"])


def render_boundary_revision(
    work_dir: Path, revision_id: str, ffmpeg: Path | None = None
) -> dict[str, Any]:
    """Render an approved-but-not-yet-rendered revision into a real deliverable set.

    Rebuilds captions from `report.json`'s persisted `selected_sentences`, timed to the revised
    span, reuses the original clip's editorial/output blocks (a boundary revision changes
    neither), supplies a fresh QC record (the approval `commit_boundary_revision` already
    required *is* the human review for this span), and renders through the same `render_clip`
    the original pipeline run uses — Kurdish invariant #4's caption-burn guard applies exactly
    as it does to any other render, not a parallel path that could skip it.

    Updates the revision record's `status` in place: `"rendered"` on full success (MP4, ASS,
    SRT and EDL all written), `"rendered_without_delivery_sidecars"` if the render succeeded but
    the EDL could not be built (`build_edl` refuses a non-integer NTSC frame rate rather than
    writing timecode that drifts — the same refusal `pipeline.py`'s own delivery step makes),
    or `"render_failed"` if rendering itself failed — in which case no partial MP4/ASS are left
    behind. Returns the updated record.

    Raises:
        FileNotFoundError: no such revision record, or no `report.json`.
        ValueError: the revision's status is not `"approved_pending_render"` (already rendered,
            or was never approved), the run has no clip, or the run predates `selected_sentences`
            being persisted (D-A7) and so cannot be re-rendered from `report.json` alone.
        RenderError: rendering failed — no ffmpeg, no usable encoder, or the encode itself
            failed. The revision record is updated to `"render_failed"` before this propagates.
        IngestError: the source could not be probed for its frame dimensions.
    """
    revision_path = work_dir / "revisions" / f"{revision_id}.json"
    if not revision_path.is_file():
        raise FileNotFoundError(f"no revision record at {revision_path}")
    revision: dict[str, Any] = json.loads(revision_path.read_text(encoding="utf-8"))
    if revision.get("status") != "approved_pending_render":
        raise ValueError(
            f"revision {revision_id!r} has status {revision.get('status')!r}, not "
            f"'approved_pending_render' — only an approved, not-yet-rendered revision can be "
            f"rendered."
        )

    report_path = work_dir / "report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"no report.json under {work_dir}")
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))

    source = Path(report["source"])
    clip_data = report.get("clip")
    if not clip_data:
        raise ValueError(f"the run at {work_dir} has no clip to revise")
    original_clip = Clip.from_dict(clip_data)

    selected_data = report.get("selected_sentences") or []
    if not selected_data:
        raise ValueError(
            f"the run at {work_dir} has no persisted selected sentences, so its captions "
            f"cannot be rebuilt for a revised span. This run predates D-A7 — re-run the "
            f"pipeline over the same source to produce a report that carries them."
        )
    selected = tuple(_sentence_from_dict(s) for s in selected_data)

    new_boundary = Boundary(
        anchor_in_ms=original_clip.boundary.anchor_in_ms,
        anchor_out_ms=original_clip.boundary.anchor_out_ms,
        final_in_ms=revision["proposed_final_in_ms"],
        final_out_ms=revision["proposed_final_out_ms"],
        in_extended_by="approved_revision",
        out_extended_by="approved_revision",
        sentence_complete=original_clip.boundary.sentence_complete,
    )
    # Belt and braces: `commit_boundary_revision` already refused an invalid proposal, and the
    # revision record on disk could in principle have been hand-edited since. The render gate
    # gets its own check rather than trusting a status string.
    assert_boundary_invariant(new_boundary)

    revised_clip = replace(
        original_clip,
        clip_id=f"{original_clip.clip_id}-{revision_id}",
        in_ms=new_boundary.final_in_ms,
        out_ms=new_boundary.final_out_ms,
        boundary=new_boundary,
        qc=Qc(auto_pass=False, flags=(), human_reviewed=True),
    )

    revisions_dir = work_dir / "revisions"
    ass_path = revisions_dir / f"{revision_id}.ass"
    render_path = revisions_dir / f"{revision_id}.mp4"
    srt_path = revisions_dir / f"{revision_id}.srt"
    edl_path = revisions_dir / f"{revision_id}.edl"
    clip_duration_ms = revised_clip.out_ms - revised_clip.in_ms

    _write_atomic(
        ass_path,
        build_ass(
            selected,
            style=CaptionStyle.WORD_HIGHLIGHT,
            clip_in_ms=revised_clip.in_ms,
            clip_duration_ms=clip_duration_ms,
        ),
    )
    width, height = _proxy_dimensions(source, ffmpeg)
    try:
        render_clip(
            revised_clip,
            source,
            ass_path,
            FONTS_DIR,
            render_path,
            source_width=width,
            source_height=height,
            ffmpeg=ffmpeg,
        )
    except (IngestError, RenderError, ValueError) as exc:
        ass_path.unlink(missing_ok=True)
        render_path.unlink(missing_ok=True)
        revision["status"] = "render_failed"
        revision["render_error"] = str(exc)
        _write_atomic(revision_path, json.dumps(revision, ensure_ascii=False, indent=2))
        raise

    revision["ass_path"] = str(ass_path)
    revision["render_path"] = str(render_path)

    try:
        srt = build_srt(selected, clip_in_ms=revised_clip.in_ms, clip_duration_ms=clip_duration_ms)
        edl = build_edl(
            clip_in_ms=revised_clip.in_ms,
            clip_out_ms=revised_clip.out_ms,
            fps=frame_rate(source, ffmpeg),
            title=f"{report['media_id']} {revised_clip.clip_id}",
        )
        _write_atomic(srt_path, srt)
        _write_atomic(edl_path, edl)
        revision["srt_path"] = str(srt_path)
        revision["edl_path"] = str(edl_path)
        revision["status"] = "rendered"
    except (DeliveryError, UndeliverableOrder) as exc:
        # The MP4/ASS above are real successes and stay — only the two sidecars are missing, and
        # the status says exactly that rather than either silently dropping them from the
        # record or discarding a render that worked. Same D-072 reasoning `pipeline.py`'s own
        # delivery step follows: an NTSC source refuses drop-frame timecode rather than faking it.
        revision["status"] = "rendered_without_delivery_sidecars"
        revision["delivery_error"] = str(exc)

    _write_atomic(revision_path, json.dumps(revision, ensure_ascii=False, indent=2))
    return revision


def main(argv: list[str] | None = None) -> int:
    """`hawedit-revise <work_dir> --final-in-ms N --final-out-ms N --revision-id ID
    --approved-by NAME`.

    Proposes, prints the validation result, and — only if valid — asks on the real terminal
    before committing. No flag skips that prompt: this entry point's whole purpose is being the
    human gate, so unlike every other flag in this module's functions, there is deliberately
    nothing here to automate it away. A caller that wants a scripted approval channel calls
    `commit_boundary_revision` directly with its own `confirm`.

    Renders immediately after a successful commit unless `--no-render` is given — approval and
    render are still two separate function calls underneath (`commit_boundary_revision`,
    `render_boundary_revision`), so a render failure is reported as its own outcome rather than
    unwinding the approval that already happened. `--no-render` leaves the revision at
    `"approved_pending_render"` for a later `render_boundary_revision` call — useful on a
    machine without ffmpeg, or to batch approvals separately from encoding.

    Exit codes: 0 committed (and rendered, unless `--no-render`); 1 declined, invalid, or
    render failed; 2 bad arguments or no report to revise.
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
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="commit the approval without rendering; leaves status=approved_pending_render",
    )
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

    if args.no_render:
        return 0

    try:
        record = render_boundary_revision(args.work_dir, args.revision_id)
    except (FileNotFoundError, ValueError, RenderError, IngestError) as exc:
        print(f"✗ render failed — {exc}", file=sys.stderr)
        return 1

    print(f"{record['status']}: {record.get('render_path')}")
    if record["status"] == "rendered_without_delivery_sidecars":
        print(f"✗ delivery sidecars: {record.get('delivery_error')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
