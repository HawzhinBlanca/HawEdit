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

**A second proposal type, added later (D-A12): captions.** Same propose/commit/render shape,
reusing every shared helper (`_write_atomic`, `_sentence_from_dict`, `_interactive_confirm`,
`RevisionRejected`) rather than a parallel copy. See the module's caption-revision section
below for what "revising a caption" means and does not mean, and why the deterministic
validator is `assert_captions_within_clip` rather than an invented safe-region check.
`revisions/<id>.json` records now carry `"kind"` (`"boundary"` or `"caption"`) so the two
render functions refuse a record that is not theirs instead of failing on a missing key; a
record written before this field existed is still treated as a boundary revision, matching
what every such record on disk actually is.

**Phase 4's decision-delta ledger, added later (D-A13).** Both `commit_*_revision` functions
now record every outcome — approved, declined, or refused before a human ever saw it — to
`work_dir/decisions.jsonl` via `learning.record_decision_delta`, closing a real gap: a decline
previously wrote nothing to disk at all. Both take a `reason_code: ReasonCode`, required
unconditionally the same way `approved_by` is, because the architecture record is explicit that
a decision is not automatically a preference. `replay_decision_deltas` re-runs every recorded
*approved* decision's own propose function against the run's current `report.json` and flags
any today's real validator no longer accepts — the "offline evaluation" step, scoped to what
this branch can honestly claim without a live model or a benchmark corpus (`BLOCKED.md` #1,
#3). See `learning.py`'s module docstring for the ledger's own design.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from hawedit.atomic_fs import write_text_atomic
from hawedit.boundary import Boundary, BoundaryInvariantViolated, assert_boundary_invariant
from hawedit.captions import (
    CaptionsOutsideClip,
    CaptionStyle,
    assert_captions_within_clip,
    build_ass,
    find_ffmpeg,
)
from hawedit.cli import program_name, use_utf8_streams
from hawedit.clip import Clip, Qc
from hawedit.delivery import DeliveryError, build_edl, build_srt
from hawedit.ingest import IngestError
from hawedit.learning import (
    DecisionOutcome,
    ReasonCode,
    ReplayFinding,
    read_decision_deltas,
    record_decision_delta,
)
from hawedit.pipeline import FONTS_DIR, _proxy_dimensions
from hawedit.render import RenderError, frame_rate, render_clip
from hawedit.sentences import Sentence, UndeliverableOrder
from hawedit.transcripts import Word, validate_media_id

__all__ = [
    "ArtifactInspection",
    "BoundaryRevisionProposal",
    "CaptionRevisionProposal",
    "ReasonCode",
    "RenderProposal",
    "ReplayFinding",
    "RevisionRejected",
    "VersionComparison",
    "commit_boundary_revision",
    "commit_caption_revision",
    "commit_render",
    "compare_versions",
    "inspect_artifact",
    "propose_boundary_revision",
    "propose_caption_revision",
    "propose_render",
    "render_boundary_revision",
    "render_caption_revision",
    "replay_decision_deltas",
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


def _is_safe_identifier(value: str) -> bool:
    """Whether `value` can be interpolated into a filename without escaping the run directory.

    Reuses `validate_media_id` — the sanitiser audit finding #9 added for exactly this shape —
    rather than a second implementation that could drift from it. `revision_id` and
    `artifact_id` are interpolated into `work_dir/revisions/<id>.{json,ass,mp4,srt,edl}` at
    fourteen sites, six of them writes; a parent reference or path separator there reads or
    writes outside the run entirely.

    Measured before this existed: `inspect_artifact(work_dir, "../../outside")` returned
    `found=True` with the `status` and `approved_by` of a JSON file outside the work directory,
    and that function is reachable from `explorer_agent`'s tool with a model-supplied string —
    so a prompt-injected transcript could ask a "read-only" agent to probe the host. That
    falsified `agent.py`'s own claim that "there is no flag, config, or prompt phrasing that
    changes what directory a given agent instance can read". D-A27.
    """
    try:
        validate_media_id(value)
    except ValueError:
        return False
    return True


def _assert_safe_identifier(value: str, label: str) -> None:
    """Refuse an identifier that would escape `work_dir/revisions/`. For the write paths, where
    reporting "not found" would be wrong: nothing was looked up, the name was rejected."""
    if not _is_safe_identifier(value):
        raise ValueError(
            f"{label} {value!r} is not a safe filename component. It is interpolated into "
            f"work_dir/revisions/, so a path separator or parent reference there would read or "
            f"write outside the run entirely (audit finding #9's shape, D-A27)."
        )


def _load_report(work_dir: Path) -> dict[str, Any]:
    """The run's `report.json`, read raw. Same shape and same error message as `agent.py`'s own
    `_load_report` — deliberately not imported from there: `agent.py` will import read-only
    functions from this module for tool registration (`inspect_artifact`, `compare_versions`),
    and importing back the other way would make the two modules circular.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
    """
    path = work_dir / "report.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no report.json under {work_dir} — durable_workflow.py writes this once a run "
            f"completes or stops; has one run here yet?"
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


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
    reason_code: ReasonCode,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> Path:
    """Write an approved revision record. Does not render — see `render_boundary_revision`.

    Every outcome — approved, declined, or refused before a human ever saw it — is recorded to
    `work_dir/decisions.jsonl` via `learning.record_decision_delta` (D-A13). This is the one
    function-level side effect that happens regardless of which branch below is taken, which is
    why it is not folded into any single return/raise below.

    Args:
        revision_id: names the output file (`work_dir/revisions/{revision_id}.json`) and is the
            caller's to choose — explicit rather than a timestamp or random id generated here,
            so a caller can pick a stable name and a test can assert on it without relying on
            wall-clock time. Two commits under the same id and directory overwrite; that is the
            caller's idempotency key to manage, the same way `durable_workflow.py`'s `run_id` is.
        approved_by: who is approving. Required and must be non-blank — `gemini.py`'s
            `Governance.confirmed_by` is the same rule for the same reason: an unattributed
            approval is not a recorded one.
        reason_code: why the human is making this decision — required unconditionally, the same
            way `approved_by` is, because §Phase 4 is explicit that a decision is not
            automatically a preference. Recorded only when the decision actually reaches a human
            (approved or declined); a proposal refused before that point (invalid, or
            unattributed) is recorded with no reason code — nobody made a reasoned decision, so
            the value supplied here is not used for that record.

    Raises:
        RevisionRejected: the proposal failed validation, `approved_by` is blank, or `confirm`
            returned a refusal.
        ValueError: `reason_code` is present/absent the wrong way round for this outcome —
            raised by `DecisionDelta.__post_init__` inside `record_decision_delta`.
    """
    _assert_safe_identifier(revision_id, "revision_id")
    if not proposal.valid:
        record_decision_delta(
            work_dir,
            proposal.media_id,
            "boundary",
            DecisionOutcome.REFUSED_INVALID,
            proposal.to_dict(),
        )
        raise RevisionRejected(
            f"proposal for {proposal.media_id!r} fails Kurdish invariant #2: {proposal.violation}"
        )
    if not approved_by.strip():
        record_decision_delta(
            work_dir,
            proposal.media_id,
            "boundary",
            DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal.to_dict(),
        )
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
        record_decision_delta(
            work_dir,
            proposal.media_id,
            "boundary",
            DecisionOutcome.DECLINED,
            proposal.to_dict(),
            reason_code=reason_code,
            approved_by=approved_by,
        )
        raise RevisionRejected(f"{approved_by!r} declined the proposed revision")

    record_decision_delta(
        work_dir,
        proposal.media_id,
        "boundary",
        DecisionOutcome.APPROVED,
        proposal.to_dict(),
        reason_code=reason_code,
        approved_by=approved_by,
    )
    record = {
        **proposal.to_dict(),
        "kind": "boundary",
        "revision_id": revision_id,
        "approved_by": approved_by,
        "status": "approved_pending_render",
    }
    revisions_dir = work_dir / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    path = revisions_dir / f"{revision_id}.json"
    write_text_atomic(path, json.dumps(record, ensure_ascii=False, indent=2))
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
    _assert_safe_identifier(revision_id, "revision_id")
    revision_path = work_dir / "revisions" / f"{revision_id}.json"
    if not revision_path.is_file():
        raise FileNotFoundError(f"no revision record at {revision_path}")
    revision: dict[str, Any] = json.loads(revision_path.read_text(encoding="utf-8"))
    # `None` covers a record written before D-A12 added `"kind"` — old boundary revisions have
    # no such field and remain renderable here, which a caption revision never predates.
    if revision.get("kind") not in (None, "boundary"):
        raise ValueError(
            f"revision {revision_id!r} has kind {revision.get('kind')!r}, not a boundary "
            f"revision — render_caption_revision handles caption revisions."
        )
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

    write_text_atomic(
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
        write_text_atomic(revision_path, json.dumps(revision, ensure_ascii=False, indent=2))
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
        write_text_atomic(srt_path, srt)
        write_text_atomic(edl_path, edl)
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

    write_text_atomic(revision_path, json.dumps(revision, ensure_ascii=False, indent=2))
    return revision


# --- Caption revisions (D-A12) --------------------------------------------------------------
#
# The second proposal type `AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` names directly beside
# boundaries (`propose_caption_revision`, line 193). Same shape as the boundary triad above —
# propose validates and never writes, commit requires a named human and an explicit yes,
# render is its own call — deliberately, not a second implementation copied by hand: the
# functions below are shorter than the boundary ones precisely because they reuse
# `_write_atomic`, `_sentence_from_dict`, `_interactive_confirm` and `RevisionRejected` rather
# than repeating them.
#
# **What "revising a caption" means here, precisely.** Not the caption *text* — §4.3's own
# docstring is explicit that caption text is "the raw surface forms... a viewer must see what
# was said," so an agent proposing different words would violate the same invariant boundary
# revisions cannot touch anchors. What is genuinely revisable is `Output.caption_style`
# (`CaptionStyle.LINE` vs `WORD_HIGHLIGHT`) — real, both already implemented in `build_ass`,
# not aspirational. The architecture record's deterministic gate "captions fit validated safe
# regions" (line 225) has no §-numbered spatial-margin check anywhere in `BLUEPRINT.md` to
# reuse or divergence from — inventing a pixel-safe-region validator would be product judgment
# this frozen spec does not back. What *is* real and already gates every render is Kurdish
# invariant #4's `assert_captions_within_clip` (`captions.py`) — reused here exactly the way
# `propose_boundary_revision` reuses `assert_boundary_invariant`, not reimplemented.


@dataclass(frozen=True, slots=True)
class CaptionRevisionProposal:
    """A proposed new `caption_style` for one run's clip, and whether it is legal.

    `valid`/`violation` come from the real `assert_captions_within_clip`, run against the
    candidate style's own rebuilt caption file — the same gate `render_clip` applies at the
    burn, not a second implementation of Kurdish invariant #4.
    """

    media_id: str
    original_caption_style: str
    proposed_caption_style: str
    valid: bool
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "original_caption_style": self.original_caption_style,
            "proposed_caption_style": self.proposed_caption_style,
            "valid": self.valid,
            "violation": self.violation,
        }


def _load_clip_and_sentences(work_dir: Path) -> tuple[str, Clip, tuple[Sentence, ...]]:
    """The run's `media_id`, its real `Clip`, and the sentences its captions were built from.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
        ValueError: the run has no clip yet, or predates `selected_sentences` (D-A7) and so has
            nothing a caption proposal could validate against.
    """
    path = work_dir / "report.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no report.json under {work_dir} — durable_workflow.py writes this once a run "
            f"completes or stops; has one run here yet?"
        )
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    clip_data = report.get("clip")
    if not clip_data:
        raise ValueError(f"the run at {work_dir} has no clip to propose a caption revision for")
    clip = Clip.from_dict(clip_data)
    selected_data = report.get("selected_sentences") or []
    if not selected_data:
        raise ValueError(
            f"the run at {work_dir} has no persisted selected sentences, so a caption proposal "
            f"cannot be validated against real captions. This run predates D-A7 — re-run the "
            f"pipeline over the same source to produce a report that carries them."
        )
    return str(report["media_id"]), clip, tuple(_sentence_from_dict(s) for s in selected_data)


def propose_caption_revision(work_dir: Path, caption_style: str) -> CaptionRevisionProposal:
    """Validate a proposed `caption_style` by rebuilding real captions and running Kurdish
    invariant #4 against them. Never writes.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
        ValueError: the run has no clip, or predates `selected_sentences` (D-A7).
    """
    media_id, clip, selected = _load_clip_and_sentences(work_dir)
    original_style = clip.output.caption_style if clip.output is not None else ""
    try:
        style = CaptionStyle(caption_style)
    except ValueError:
        return CaptionRevisionProposal(
            media_id=media_id,
            original_caption_style=original_style,
            proposed_caption_style=caption_style,
            valid=False,
            violation=(
                f"{caption_style!r} is not a recognized caption style; choose one of "
                f"{[member.value for member in CaptionStyle]}"
            ),
        )
    clip_duration_ms = clip.out_ms - clip.in_ms
    ass_text = build_ass(
        selected, style=style, clip_in_ms=clip.in_ms, clip_duration_ms=clip_duration_ms
    )
    try:
        assert_captions_within_clip(ass_text, clip_duration_ms)
        valid, violation = True, None
    except CaptionsOutsideClip as exc:
        valid, violation = False, str(exc)
    return CaptionRevisionProposal(
        media_id=media_id,
        original_caption_style=original_style,
        proposed_caption_style=style.value,
        valid=valid,
        violation=violation,
    )


def commit_caption_revision(
    work_dir: Path,
    proposal: CaptionRevisionProposal,
    revision_id: str,
    approved_by: str,
    reason_code: ReasonCode,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> Path:
    """Write an approved caption-revision record. Does not render — see
    `render_caption_revision`. Same three refusals as `commit_boundary_revision`: an invalid
    proposal, an unattributed approver, or an explicit decline — and the same decision-delta
    recording on every outcome (D-A13); see that function's docstring for `reason_code`.

    Raises:
        RevisionRejected: the proposal failed validation, `approved_by` is blank, or `confirm`
            returned a refusal.
        ValueError: `reason_code` is present/absent the wrong way round for this outcome —
            raised by `DecisionDelta.__post_init__` inside `record_decision_delta`.
    """
    _assert_safe_identifier(revision_id, "revision_id")
    if not proposal.valid:
        record_decision_delta(
            work_dir,
            proposal.media_id,
            "caption",
            DecisionOutcome.REFUSED_INVALID,
            proposal.to_dict(),
        )
        raise RevisionRejected(
            f"caption proposal for {proposal.media_id!r} fails Kurdish invariant #4: "
            f"{proposal.violation}"
        )
    if not approved_by.strip():
        record_decision_delta(
            work_dir,
            proposal.media_id,
            "caption",
            DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal.to_dict(),
        )
        raise RevisionRejected(
            "a revision needs a named approver; an unattributed approval is not one "
            "(same rule as gemini.py's Governance.confirmed_by)."
        )
    prompt = (
        f"{proposal.media_id}: caption style {proposal.original_caption_style!r} -> "
        f"{proposal.proposed_caption_style!r}. Apply?"
    )
    if not confirm(prompt):
        record_decision_delta(
            work_dir,
            proposal.media_id,
            "caption",
            DecisionOutcome.DECLINED,
            proposal.to_dict(),
            reason_code=reason_code,
            approved_by=approved_by,
        )
        raise RevisionRejected(f"{approved_by!r} declined the proposed caption revision")

    record_decision_delta(
        work_dir,
        proposal.media_id,
        "caption",
        DecisionOutcome.APPROVED,
        proposal.to_dict(),
        reason_code=reason_code,
        approved_by=approved_by,
    )
    record = {
        **proposal.to_dict(),
        "kind": "caption",
        "revision_id": revision_id,
        "approved_by": approved_by,
        "status": "approved_pending_render",
    }
    revisions_dir = work_dir / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    path = revisions_dir / f"{revision_id}.json"
    write_text_atomic(path, json.dumps(record, ensure_ascii=False, indent=2))
    return path


def render_caption_revision(
    work_dir: Path, revision_id: str, ffmpeg: Path | None = None
) -> dict[str, Any]:
    """Render an approved-but-not-yet-rendered caption revision into a real deliverable set.

    Same shape as `render_boundary_revision`: rebuilds captions from `report.json`'s persisted
    `selected_sentences` (unchanged span, new style), reuses the original clip's boundary and
    editorial blocks (a caption revision changes neither), supplies a fresh QC record for the
    same reason — the approval `commit_caption_revision` already required *is* the human review
    for this change — and renders through the same `render_clip` every other output uses.

    Raises:
        FileNotFoundError: no such revision record, or no `report.json`.
        ValueError: the revision is not a caption revision, its status is not
            `"approved_pending_render"`, the run has no clip or output block, or the run
            predates `selected_sentences` (D-A7).
        RenderError: rendering failed. The revision record is updated to `"render_failed"`
            before this propagates.
        IngestError: the source could not be probed for its frame dimensions.
    """
    _assert_safe_identifier(revision_id, "revision_id")
    revision_path = work_dir / "revisions" / f"{revision_id}.json"
    if not revision_path.is_file():
        raise FileNotFoundError(f"no revision record at {revision_path}")
    revision: dict[str, Any] = json.loads(revision_path.read_text(encoding="utf-8"))
    if revision.get("kind") != "caption":
        raise ValueError(
            f"revision {revision_id!r} has kind {revision.get('kind')!r}, not a caption "
            f"revision — render_boundary_revision handles boundary revisions."
        )
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
    if original_clip.output is None:
        raise ValueError(f"the run at {work_dir} has no output block to revise a caption on")

    selected_data = report.get("selected_sentences") or []
    if not selected_data:
        raise ValueError(
            f"the run at {work_dir} has no persisted selected sentences, so its captions "
            f"cannot be rebuilt. This run predates D-A7 — re-run the pipeline over the same "
            f"source to produce a report that carries them."
        )
    selected = tuple(_sentence_from_dict(s) for s in selected_data)

    style = CaptionStyle(revision["proposed_caption_style"])
    revised_clip = replace(
        original_clip,
        clip_id=f"{original_clip.clip_id}-{revision_id}",
        output=replace(original_clip.output, caption_style=style.value),
        qc=Qc(auto_pass=False, flags=(), human_reviewed=True),
    )

    revisions_dir = work_dir / "revisions"
    ass_path = revisions_dir / f"{revision_id}.ass"
    render_path = revisions_dir / f"{revision_id}.mp4"
    srt_path = revisions_dir / f"{revision_id}.srt"
    edl_path = revisions_dir / f"{revision_id}.edl"
    clip_duration_ms = revised_clip.out_ms - revised_clip.in_ms

    write_text_atomic(
        ass_path,
        build_ass(
            selected, style=style, clip_in_ms=revised_clip.in_ms, clip_duration_ms=clip_duration_ms
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
        write_text_atomic(revision_path, json.dumps(revision, ensure_ascii=False, indent=2))
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
        write_text_atomic(srt_path, srt)
        write_text_atomic(edl_path, edl)
        revision["srt_path"] = str(srt_path)
        revision["edl_path"] = str(edl_path)
        revision["status"] = "rendered"
    except (DeliveryError, UndeliverableOrder) as exc:
        revision["status"] = "rendered_without_delivery_sidecars"
        revision["delivery_error"] = str(exc)

    write_text_atomic(revision_path, json.dumps(revision, ensure_ascii=False, indent=2))
    return revision


# --- Offline replay (D-A13) -------------------------------------------------------------------
#
# The architecture record's "offline evaluation" step, scoped to what this branch can honestly
# claim without a live model or a benchmark corpus: not an evaluation against held-out data
# (`BLOCKED.md` #1, no labelled Sorani set) or a live judge call (`BLOCKED.md` #3, Gemini
# billing), but a regression check on the codebase's own deterministic gates — did today's code
# change what an already-approved edit is allowed to do?


# --- inspect_artifact / compare_versions (D-A22) ------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArtifactInspection:
    """One addressable artifact's effective span/style/status, read-only.

    `artifact_id` is either the literal string `"original"` (the run's own clip, as produced —
    never revised) or a `revision_id` naming `work_dir/revisions/{revision_id}.json`. There is
    no third kind: every addressable thing this codebase can point at is one or the other.

    `found=False` with every other field `None` reports an `artifact_id` that resolves to
    nothing — never an exception. `propose_cancel_run`/`propose_resume_run`/`propose_render`
    already hold this contract for a caller-supplied identifier that turns out not to exist;
    `artifact_id` is exactly as agent-suppliable as `run_id`/`revision_id` are there, and an
    agent tool that raises on an ordinary "not found" cannot be recovered from mid-conversation
    the way a reported value can (`tests/test_prompt_injection.py`'s `TestModel`-driven suite
    caught this directly: it probes every tool with a placeholder string, and a first version of
    this function raised on it).
    """

    artifact_id: str
    found: bool
    kind: str | None
    in_ms: int | None
    out_ms: int | None
    caption_style: str | None
    status: str | None
    approved_by: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "found": self.found,
            "kind": self.kind,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "caption_style": self.caption_style,
            "status": self.status,
            "approved_by": self.approved_by,
        }


def _not_found_artifact(artifact_id: str) -> ArtifactInspection:
    return ArtifactInspection(
        artifact_id=artifact_id,
        found=False,
        kind=None,
        in_ms=None,
        out_ms=None,
        caption_style=None,
        status=None,
        approved_by=None,
    )


def inspect_artifact(work_dir: Path, artifact_id: str) -> ArtifactInspection:
    """Resolve one addressable artifact to its effective span/style/status.

    For a revision, this mirrors the reconstruction `render_boundary_revision`/
    `render_caption_revision` perform — the original clip with only the one field that kind of
    revision changes replaced — minus the actual encode. A boundary revision's `caption_style`
    is therefore the *original* clip's (unchanged); a caption revision's `in_ms`/`out_ms` are
    likewise the original's. This is deliberately the same read every render function already
    trusts, not a second derivation that could disagree with what would actually be rendered.

    A run that has not reached §3 Stage 5 yet has no clip at all — an ordinary, common state
    (`run_quality_checks`, D-A18, already treats it as a reportable value, not an exception, for
    the same reason) — so this reports `found=False` for every `artifact_id` rather than
    raising, the same as an `artifact_id` that names nothing real.

    Raises:
        FileNotFoundError: no `report.json` under `work_dir` — `work_dir` is never
            agent-suppliable (`Deps.work_dir` is fixed at construction), so this is a genuine
            caller/setup error, the same case every other report-reading tool in this codebase
            already raises for.
    """
    report = _load_report(work_dir)
    clip_data = report.get("clip")
    if not clip_data:
        return _not_found_artifact(artifact_id)
    original = Clip.from_dict(clip_data)
    original_style = original.output.caption_style if original.output else None

    if artifact_id == "original":
        # `StageSkipped.to_dict()` is *also* a dict (`{"skipped": true, "stage": "render", ...}`)
        # and `pipeline.py` sets `clip` before the render stage, so a run whose render failed or
        # was gated has a populated clip and a skipped-shaped `render` with no file on disk.
        # `isinstance(..., dict)` alone would call that "rendered". `agent.py`'s own
        # `inspect_run` already guards the same trap with `"path" in render`, and
        # `_load_boundary` below with `boundary.get("skipped")` — found by an adversarial review
        # pass, not by a test, because this file's fixtures used `"render": None`, a shape the
        # real pipeline never writes once a clip exists.
        render = report.get("render")
        rendered = isinstance(render, dict) and not render.get("skipped")
        return ArtifactInspection(
            artifact_id="original",
            found=True,
            kind="original",
            in_ms=original.in_ms,
            out_ms=original.out_ms,
            caption_style=original_style,
            status="rendered" if rendered else "not_rendered",
            approved_by=None,
        )

    # Refused before the path is built, not after: an identifier carrying a separator or a
    # parent reference is not "an artifact that does not exist", it is one that must never be
    # looked up. Reported as not-found rather than raised, so the contract this function holds
    # for every other unresolvable id is unchanged - and so a probe learns nothing either way.
    if not _is_safe_identifier(artifact_id):
        return _not_found_artifact(artifact_id)
    path = work_dir / "revisions" / f"{artifact_id}.json"
    if not path.is_file():
        return _not_found_artifact(artifact_id)
    revision: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    # A record written before D-A12 added "kind" has none and is always a boundary revision —
    # the same backward-compatible default `render_boundary_revision` already relies on. An
    # explicitly *unknown* kind is a different case: falling through to the caption branch would
    # read `proposed_caption_style` off a record that has no such key, raising `KeyError` and
    # breaking this module's own "an identifier that resolves to something is never an
    # exception" contract. `propose_render` guards the identical spot; `replay_decision_deltas`
    # records this exact defect being found once already, for `start_pipeline` deltas.
    kind = revision.get("kind") or "boundary"
    if kind == "boundary":
        in_ms = int(revision["proposed_final_in_ms"])
        out_ms = int(revision["proposed_final_out_ms"])
        caption_style = original_style
    elif kind == "caption":
        in_ms = original.in_ms
        out_ms = original.out_ms
        caption_style = str(revision["proposed_caption_style"])
    else:
        return _not_found_artifact(artifact_id)
    return ArtifactInspection(
        artifact_id=artifact_id,
        found=True,
        kind=kind,
        in_ms=in_ms,
        out_ms=out_ms,
        caption_style=caption_style,
        status=str(revision.get("status", "unknown")),
        approved_by=revision.get("approved_by"),
    )


@dataclass(frozen=True, slots=True)
class VersionComparison:
    """Two artifacts, resolved side by side, and whether each dimension actually differs.

    `span_changed`/`caption_style_changed` are only meaningful when `both_found` is true — an
    artifact that was not found compares as "unchanged" against anything rather than raising,
    the same `found`-not-an-exception contract `ArtifactInspection` holds; check `both_found`
    (or `a.found`/`b.found` directly) before trusting either flag.
    """

    a: ArtifactInspection
    b: ArtifactInspection
    both_found: bool
    span_changed: bool
    caption_style_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "a": self.a.to_dict(),
            "b": self.b.to_dict(),
            "both_found": self.both_found,
            "span_changed": self.span_changed,
            "caption_style_changed": self.caption_style_changed,
        }


def compare_versions(work_dir: Path, artifact_id_a: str, artifact_id_b: str) -> VersionComparison:
    """Resolve two artifacts and report what actually differs between them.

    Built on `inspect_artifact` rather than a parallel lookup, so a comparison can never
    disagree with what inspecting either artifact alone would report.

    Raises:
        FileNotFoundError: no `report.json` under `work_dir` — see `inspect_artifact`. Neither
            a missing clip nor an `artifact_id` failing to resolve raises; `both_found` reports
            that instead.
    """
    a = inspect_artifact(work_dir, artifact_id_a)
    b = inspect_artifact(work_dir, artifact_id_b)
    both_found = a.found and b.found
    return VersionComparison(
        a=a,
        b=b,
        both_found=both_found,
        span_changed=both_found and (a.in_ms, a.out_ms) != (b.in_ms, b.out_ms),
        caption_style_changed=both_found and a.caption_style != b.caption_style,
    )


# --- request_render, as propose_render/commit_render (D-A25) ------------------------------------


@dataclass(frozen=True, slots=True)
class RenderProposal:
    """Whether `revision_id` under `work_dir` is ready to render, and why not if it is not.

    Every check here mirrors a real precondition `render_boundary_revision`/
    `render_caption_revision` themselves enforce (same status string, same clip/
    selected_sentences/output-block requirements, same `assert_boundary_invariant` re-check for
    a boundary revision) plus one neither of those functions can check for free: whether ffmpeg
    is even findable, the same `find_ffmpeg() is None` gate `tests/`'s own `needs_ffmpeg` marker
    uses. `propose_render` never calls either render function and never touches `ffmpeg` itself
    — it can be wrong only in the direction of "looked renderable, then genuinely failed to
    render" (a source probe error, an ffmpeg crash), never in reporting something unrenderable
    as ready.
    """

    work_dir: str
    revision_id: str
    kind: str | None
    valid: bool
    violation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_dir": self.work_dir,
            "revision_id": self.revision_id,
            "kind": self.kind,
            "valid": self.valid,
            "violation": self.violation,
        }


def propose_render(work_dir: Path, revision_id: str) -> RenderProposal:
    """Check whether `revision_id` is ready to render. Never touches `ffmpeg` or writes
    anything — the same "propose never mutates" guarantee every other proposal in this codebase
    holds."""
    if not _is_safe_identifier(revision_id):
        return RenderProposal(
            str(work_dir),
            revision_id,
            None,
            False,
            "revision_id is not a safe filename component — it would be interpolated into "
            "work_dir/revisions/ (D-A27).",
        )
    revision_path = work_dir / "revisions" / f"{revision_id}.json"
    if not revision_path.is_file():
        return RenderProposal(
            str(work_dir), revision_id, None, False, f"no revision record at {revision_path}"
        )
    revision: dict[str, Any] = json.loads(revision_path.read_text(encoding="utf-8"))
    # Only an *absent* `kind` defaults to boundary (a pre-D-A12 record). A present-but-falsy one
    # (`""`, `null`) must not: `render_boundary_revision` refuses anything whose `kind` is not
    # literally `None` or `"boundary"`, so `or "boundary"` here would call `""` renderable and
    # then `commit_render` would record an APPROVED delta before the render raised a bare
    # `ValueError` — a ledger entry for a render that never happened. Only reachable via a
    # hand-edited record, which is exactly the case this function claims to cover.
    raw_kind = revision.get("kind")
    kind = "boundary" if raw_kind is None else raw_kind
    if kind not in ("boundary", "caption"):
        return RenderProposal(
            str(work_dir), revision_id, str(kind), False, f"unknown revision kind {kind!r}"
        )
    if revision.get("status") != "approved_pending_render":
        return RenderProposal(
            str(work_dir),
            revision_id,
            kind,
            False,
            f"revision has status {revision.get('status')!r}, not 'approved_pending_render' — "
            f"only an approved, not-yet-rendered revision can be rendered.",
        )
    report_path = work_dir / "report.json"
    if not report_path.is_file():
        return RenderProposal(
            str(work_dir), revision_id, kind, False, f"no report.json under {work_dir}"
        )
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    clip_data = report.get("clip")
    if not clip_data:
        return RenderProposal(
            str(work_dir), revision_id, kind, False, "the run has no clip to revise"
        )
    if not (report.get("selected_sentences") or []):
        return RenderProposal(
            str(work_dir),
            revision_id,
            kind,
            False,
            "the run has no persisted selected sentences (predates D-A7) — captions cannot be "
            "rebuilt for this span.",
        )
    original_clip = Clip.from_dict(clip_data)
    if kind == "caption" and original_clip.output is None:
        return RenderProposal(
            str(work_dir),
            revision_id,
            kind,
            False,
            "the run has no output block to revise a caption on",
        )
    if kind == "boundary":
        try:
            new_boundary = Boundary(
                anchor_in_ms=original_clip.boundary.anchor_in_ms,
                anchor_out_ms=original_clip.boundary.anchor_out_ms,
                final_in_ms=int(revision["proposed_final_in_ms"]),
                final_out_ms=int(revision["proposed_final_out_ms"]),
                in_extended_by="approved_revision",
                out_extended_by="approved_revision",
                sentence_complete=original_clip.boundary.sentence_complete,
            )
            assert_boundary_invariant(new_boundary)
        except BoundaryInvariantViolated as exc:
            return RenderProposal(
                str(work_dir),
                revision_id,
                kind,
                False,
                f"revised boundary is no longer legal: {exc}",
            )
    if find_ffmpeg() is None:
        return RenderProposal(
            str(work_dir),
            revision_id,
            kind,
            False,
            "no ffmpeg available on this machine (set HAWEDIT_FFMPEG)",
        )
    return RenderProposal(str(work_dir), revision_id, kind, True, None)


def commit_render(
    work_dir: Path,
    proposal: RenderProposal,
    approved_by: str,
    reason_code: ReasonCode,
    confirm: Callable[[str], bool] = _interactive_confirm,
) -> dict[str, Any]:
    """Render `proposal`'s revision. The only write in this section.

    Dispatches to `render_boundary_revision`/`render_caption_revision` by `proposal.kind` —
    neither is reimplemented here. `revision_id` is the recorded `DecisionDelta.media_id`: a
    render decision is about one specific revision, not the run's own media, and `revision_id`
    is always non-blank (`commit_boundary_revision`/`commit_caption_revision` already require it
    to name the revision file).

    Raises:
        RevisionRejected: the proposal is invalid, `approved_by` is blank, or `confirm` returns
            a refusal.
    """
    if not proposal.valid:
        record_decision_delta(
            work_dir,
            proposal.revision_id,
            "render",
            DecisionOutcome.REFUSED_INVALID,
            proposal.to_dict(),
        )
        raise RevisionRejected(f"cannot render {proposal.revision_id!r}: {proposal.violation}")
    if not approved_by.strip():
        record_decision_delta(
            work_dir,
            proposal.revision_id,
            "render",
            DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal.to_dict(),
        )
        raise RevisionRejected(
            "rendering needs a named approver; an unattributed approval is not one."
        )
    prompt = f"render revision {proposal.revision_id!r} ({proposal.kind}) in {work_dir}?"
    if not confirm(prompt):
        record_decision_delta(
            work_dir,
            proposal.revision_id,
            "render",
            DecisionOutcome.DECLINED,
            proposal.to_dict(),
            reason_code=reason_code,
            approved_by=approved_by,
        )
        raise RevisionRejected(f"{approved_by!r} declined rendering")

    record_decision_delta(
        work_dir,
        proposal.revision_id,
        "render",
        DecisionOutcome.APPROVED,
        proposal.to_dict(),
        reason_code=reason_code,
        approved_by=approved_by,
    )
    if proposal.kind == "boundary":
        return render_boundary_revision(work_dir, proposal.revision_id)
    return render_caption_revision(work_dir, proposal.revision_id)


def replay_decision_deltas(work_dir: Path) -> tuple[ReplayFinding, ...]:
    """Re-propose every recorded *approved* decision under `work_dir` and flag any today's real
    validator no longer accepts.

    Deliberately re-runs `propose_boundary_revision`/`propose_caption_revision` themselves
    against the run's current `report.json`, rather than hand-rebuilding a `Boundary` or
    re-deriving caption validity from the recorded proposal dict — the same validator the
    original commit checked, invoked the same way, so a finding here means the codebase's
    behaviour changed, not that this function's own re-implementation drifted from it.

    Only `APPROVED` deltas are replayed — a `DECLINED` or `REFUSED_*` decision was never
    applied, so there is no committed state for a validator regression to silently break.

    Only `"boundary"`/`"caption"` deltas are replayed at all. `"start_pipeline"`/`"cancel_run"`/
    `"resume_run"` (`workflow_control.py`, D-A19/D-A20/D-A21) are workflow-lifecycle decisions
    and `"render"` (D-A25) is an encode of an already-approved revision — none is a content
    revision, and there is no deterministic content validator to re-run any of them against the
    way `propose_boundary_revision`/`propose_caption_revision` re-check a span or a style.
    Before this branch was added, any kind other than `"boundary"` fell into the `"caption"`
    branch by default and read `delta.proposal["proposed_caption_style"]`, which does not exist
    on a `start_pipeline` delta's proposal dict — a real `KeyError` on any `work_dir` whose
    ledger held an approved `start_pipeline` decision, found while widening `DecisionDelta.kind`
    further for D-A20/D-A21 and fixed here rather than left for the next kind to trip over too.

    Raises:
        FileNotFoundError: no `decisions.jsonl` under `work_dir`, or (surfaced from the
            underlying propose call) no `report.json` — the run's own state that a replayed
            decision needs is gone, and replay cannot honestly proceed without it.
    """
    deltas = read_decision_deltas(work_dir / "decisions.jsonl")
    findings: list[ReplayFinding] = []
    for delta in deltas:
        if delta.outcome is not DecisionOutcome.APPROVED:
            continue
        valid: bool
        violation: str | None
        if delta.kind == "boundary":
            boundary_now = propose_boundary_revision(
                work_dir,
                delta.proposal["proposed_final_in_ms"],
                delta.proposal["proposed_final_out_ms"],
            )
            valid, violation = boundary_now.valid, boundary_now.violation
        elif delta.kind == "caption":
            caption_now = propose_caption_revision(
                work_dir, delta.proposal["proposed_caption_style"]
            )
            valid, violation = caption_now.valid, caption_now.violation
        else:
            continue
        if not valid:
            findings.append(
                ReplayFinding(
                    sequence=delta.sequence,
                    media_id=delta.media_id,
                    kind=delta.kind,
                    violation=violation or "",
                )
            )
    return tuple(findings)


def _main_boundary(args: argparse.Namespace) -> int:
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
        path = commit_boundary_revision(
            args.work_dir,
            proposal,
            args.revision_id,
            args.approved_by,
            ReasonCode(args.reason_code),
        )
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


def _main_caption(args: argparse.Namespace) -> int:
    try:
        proposal = propose_caption_revision(args.work_dir, args.caption_style)
    except (FileNotFoundError, ValueError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    print(
        f"{proposal.media_id}: caption style {proposal.original_caption_style!r} -> "
        f"{proposal.proposed_caption_style!r}"
    )
    if not proposal.valid:
        print(f"✗ invalid — {proposal.violation}", file=sys.stderr)
        return 1

    try:
        path = commit_caption_revision(
            args.work_dir,
            proposal,
            args.revision_id,
            args.approved_by,
            ReasonCode(args.reason_code),
        )
    except RevisionRejected as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print(f"committed: {path}")

    if args.no_render:
        return 0

    try:
        record = render_caption_revision(args.work_dir, args.revision_id)
    except (FileNotFoundError, ValueError, RenderError, IngestError) as exc:
        print(f"✗ render failed — {exc}", file=sys.stderr)
        return 1

    print(f"{record['status']}: {record.get('render_path')}")
    if record["status"] == "rendered_without_delivery_sidecars":
        print(f"✗ delivery sidecars: {record.get('delivery_error')}", file=sys.stderr)
    return 0


def _main_render(args: argparse.Namespace) -> int:
    proposal = propose_render(args.work_dir, args.revision_id)
    print(f"{proposal.revision_id}: {'valid' if proposal.valid else 'invalid'}")
    if not proposal.valid:
        print(f"✗ invalid — {proposal.violation}", file=sys.stderr)
        return 1

    try:
        record = commit_render(
            args.work_dir,
            proposal,
            args.approved_by,
            ReasonCode(args.reason_code),
        )
    except RevisionRejected as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, RenderError, IngestError) as exc:
        print(f"✗ render failed — {exc}", file=sys.stderr)
        return 1

    print(f"{record['status']}: {record.get('render_path')}")
    if record["status"] == "rendered_without_delivery_sidecars":
        print(f"✗ delivery sidecars: {record.get('delivery_error')}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """`hawedit-revise <work_dir> --revision-id ID --approved-by NAME --reason-code CODE`, plus
    exactly one of `--final-in-ms N --final-out-ms N` (a boundary revision) or `--caption-style
    STYLE` (a caption revision — `line` or `word_highlight`). `--reason-code` is one of
    `preference`/`undo`/`experiment`/`accident`/`policy_forced` (D-A13) — required unconditionally,
    the same way `--approved-by` is, even though it is only ever recorded if the proposal is
    valid enough to reach a human decision at all.

    Proposes, prints the validation result, and — only if valid — asks on the real terminal
    before committing. No flag skips that prompt: this entry point's whole purpose is being the
    human gate, so unlike every other flag in this module's functions, there is deliberately
    nothing here to automate it away. A caller that wants a scripted approval channel calls
    `commit_boundary_revision`/`commit_caption_revision` directly with its own `confirm`.

    Renders immediately after a successful commit unless `--no-render` is given — approval and
    render are still two separate function calls underneath, so a render failure is reported as
    its own outcome rather than unwinding the approval that already happened. `--no-render`
    leaves the revision at `"approved_pending_render"` for a later render call — useful on a
    machine without ffmpeg, or to batch approvals separately from encoding.

    Exit codes: 0 committed (and rendered, unless `--no-render`); 1 declined, invalid, or
    render failed; 2 bad arguments or no report to revise.
    """
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.proposals"),
        description="Propose a boundary or caption revision for a completed HawEdit run, and "
        "commit it only on explicit approval.",
    )
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--final-in-ms", type=int)
    parser.add_argument("--final-out-ms", type=int)
    parser.add_argument("--caption-style", choices=[member.value for member in CaptionStyle])
    parser.add_argument(
        "--render-only",
        action="store_true",
        help=(
            "render an already-committed, not-yet-rendered revision (D-A25) instead of "
            "proposing a new one — for the --no-render case, or a retry after render_failed"
        ),
    )
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument(
        "--reason-code",
        required=True,
        choices=[member.value for member in ReasonCode],
        help="why this decision is being made — required, never assumed (D-A13)",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="commit the approval without rendering; leaves status=approved_pending_render",
    )
    args = parser.parse_args(argv)

    boundary_given = args.final_in_ms is not None or args.final_out_ms is not None
    if args.render_only:
        if boundary_given or args.caption_style is not None:
            parser.error("--render-only cannot be combined with a new proposal")
        if args.no_render:
            parser.error("--render-only and --no-render are contradictory")
        return _main_render(args)
    if boundary_given and args.caption_style is not None:
        parser.error("--final-in-ms/--final-out-ms and --caption-style are mutually exclusive")
    if boundary_given and (args.final_in_ms is None or args.final_out_ms is None):
        parser.error("--final-in-ms and --final-out-ms must both be given")
    if not boundary_given and args.caption_style is None:
        parser.error("give either --final-in-ms/--final-out-ms or --caption-style")

    if args.caption_style is not None:
        return _main_caption(args)
    return _main_boundary(args)


if __name__ == "__main__":
    raise SystemExit(main())
