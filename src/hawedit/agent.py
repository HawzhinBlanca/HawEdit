"""Phase 2: a read-only creative-director agent over one run's on-disk state.

`AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` Phase 2: "Add Pydantic AI with inspection,
explanation and candidate-comparison tools... Make all proposals non-mutating." Three tools,
one per category, and nothing here writes anything:

- `inspect_run` — what stage the run reached and whether it produced a deliverable.
- `explain_run_state` — *why* it stopped where it did, quoting the actual `StageSkipped` reason
  rather than paraphrasing one. A model is not a trusted source for why a pipeline stopped; the
  pipeline already said why, and this tool's job is to surface that sentence, not improve on it.
- `compare_candidates` — every candidate §3 Stage 3 found and every one it rejected, with the
  path that found it and the reason it lost. Deliberately does not guess which candidate became
  the final clip: `Clip` (D-A5's own reading of `clip.py`) carries no `candidate_id`, matching a
  clip back to its source candidate by span would be a heuristic that can be wrong on a boundary
  that VAD or TimeLens moved, and a wrong inference here is worse than an honest gap — `clip.py`
  is already in the returned document (via `inspect_run`) for a reader who wants to check.

**`work_dir` is bound at construction, never a tool argument.** The architecture record's own
security section: "Media storage uses scoped object references rather than filesystem paths
where possible" and "the model sees only an allowlisted tool registry." A tool that accepted an
arbitrary path string from the model would let a prompt-injected transcript ask the "read-only"
agent to read anything the OS user running it can read — outside the project, outside the work
directory entirely. `Deps.work_dir` is fixed by whoever constructs the agent (a human, or the
application wiring it into a request), and every tool closes over `ctx.deps.work_dir` rather
than accepting a path parameter. There is no flag, config, or prompt phrasing that changes what
directory a given agent instance can read.

**Reads `report.json` and `events.jsonl`, both written by `durable_workflow.py`.** Neither is
this project's eventual Postgres Artifact Ledger — see that module's docstring for why a flat
file is the right amount of ledger for one reader replaying one run. If neither file exists yet
(no durable run has completed here), every tool raises `FileNotFoundError` naming the path it
looked for rather than returning an empty-but-valid report a reader could mistake for "this run
did nothing."

**Model-portable by construction.** `build_agent` takes any `pydantic_ai.models.Model` — a real
provider, or `pydantic_ai.models.test.TestModel` for a test that never calls out to a network.
This module does not choose a model. `AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md`'s "benchmarked
model router" needs the editorial bench's own evidence to justify a choice (`judge.py`'s
`decide_judge` is the existing example of that discipline for Stage 4); inventing a default here
without that evidence would be exactly the kind of unverified claim this branch has spent Phase 1
avoiding. Deferred, not forgotten — see PROGRESS.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

__all__ = [
    "AppManifest",
    "CandidateComparison",
    "CandidateRecord",
    "Deps",
    "RejectionRecord",
    "RunExplanation",
    "RunInspection",
    "app_manifest",
    "build_agent",
    "compare_candidates",
    "explain_run_state",
    "inspect_run",
]

# §3's stage order, for "which stage stopped this run" — the first name in this tuple that
# appears in the report's `skipped` list is the answer. Read off `pipeline.py`'s own `# --- §3
# Stage N ---` comment sequence rather than invented, so a reordering of the pipeline is a diff
# to this constant, not a silent divergence. `tests/test_agent.py` pins it against the same
# report `events.py`'s stage names produce.
_STAGE_ORDER: Final = (
    "ingest",
    "transcript",
    "sentences",
    "index",
    "discovery",
    "visual_index",
    "editorial",
    "boundary",
    "render",
    "delivery",
)


@dataclass(frozen=True, slots=True)
class Deps:
    """What one agent instance is scoped to. Immutable, and the only source of `work_dir`."""

    work_dir: Path


class AppManifest(BaseModel):
    """Versioned facts about this build — what the architecture record calls the agent's
    startup context, kept to what can be read off the running interpreter rather than asserted.
    """

    hawedit_version: str
    read_only: bool = True
    tool_names: tuple[str, ...] = ("inspect_run", "explain_run_state", "compare_candidates")


class RunInspection(BaseModel):
    media_id: str
    complete: bool
    skipped_stages: tuple[str, ...]
    candidate_count: int
    rejected_count: int
    clip_id: str | None
    render_path: str | None
    delivery_complete: bool


class RunExplanation(BaseModel):
    media_id: str
    complete: bool
    stopped_at_stage: str | None
    reason: str | None
    blocked_by: tuple[str, ...]


class CandidateRecord(BaseModel):
    candidate_id: str
    in_ms: int
    out_ms: int
    discovery_path: str
    verbal_score: float | None
    visual_score: float | None


class RejectionRecord(BaseModel):
    in_ms: int
    out_ms: int
    discovery_path: str
    reject_reason: str


class CandidateComparison(BaseModel):
    media_id: str
    candidates: tuple[CandidateRecord, ...]
    rejected: tuple[RejectionRecord, ...]
    final_clip_span_ms: tuple[int, int] | None


def app_manifest() -> AppManifest:
    """The manifest an agent loop would show a model at startup. Nothing here is asserted:
    `hawedit_version` comes from the installed package, not a hand-maintained string that could
    drift the way `PROGRESS.md`'s own history shows plain lists do (D-127, D-129, D-141).
    """
    try:
        version = metadata.version("hawedit")
    except metadata.PackageNotFoundError:
        # Editable install without a built wheel — real during development, and "unknown" is
        # honest about it rather than a guessed version string nothing produced.
        version = "unknown"
    return AppManifest(hawedit_version=version)


def _load_report(work_dir: Path) -> dict[str, Any]:
    path = work_dir / "report.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no report.json under {work_dir} — durable_workflow.py writes this once a run "
            f"completes or stops; has one run here yet?"
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def inspect_run(work_dir: Path) -> RunInspection:
    """What the run at `work_dir` reached, read off its `report.json`.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
    """
    report = _load_report(work_dir)
    render = report.get("render")
    delivery = report.get("delivery")
    clip = report.get("clip")
    return RunInspection(
        media_id=report["media_id"],
        complete=report["complete"],
        skipped_stages=tuple(report["skipped"]),
        candidate_count=len(report["candidates"]),
        rejected_count=len(report["rejected"]),
        clip_id=clip["clip_id"] if clip else None,
        render_path=render.get("path") if isinstance(render, dict) and "path" in render else None,
        delivery_complete=isinstance(delivery, dict) and "srt_path" in delivery,
    )


def explain_run_state(work_dir: Path) -> RunExplanation:
    """Why the run at `work_dir` stopped where it did, quoting its own recorded reason.

    Walks `_STAGE_ORDER` and reports the *first* stage the run skipped — that is the one that
    actually stopped it, since every later `StageSkipped` in `pipeline.py` is a downstream
    consequence ("boundary did not run because complete selected sentences was not available")
    rather than an independent cause. Reads the reason from the report's own per-stage record,
    never from a hand-written explanation.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
    """
    report = _load_report(work_dir)
    skipped = set(report["skipped"])
    for stage in _STAGE_ORDER:
        if stage in skipped:
            record = report.get(stage)
            reason = record.get("reason") if isinstance(record, dict) else None
            blocked_by = tuple(record.get("blocked_by", ())) if isinstance(record, dict) else ()
            return RunExplanation(
                media_id=report["media_id"],
                complete=report["complete"],
                stopped_at_stage=stage,
                reason=reason,
                blocked_by=blocked_by,
            )
    return RunExplanation(
        media_id=report["media_id"],
        complete=report["complete"],
        stopped_at_stage=None,
        reason=None,
        blocked_by=(),
    )


def compare_candidates(work_dir: Path) -> CandidateComparison:
    """Every §3 Stage 3 candidate and rejection for the run at `work_dir`, side by side.

    Does not guess which candidate became the final clip — see the module docstring for why a
    span-matching heuristic here would be worse than the honest gap. `final_clip_span_ms` is
    reported alongside so a reader (human or the calling model) can compare it against the
    listed candidates themselves.

    Raises:
        FileNotFoundError: no run has completed under `work_dir` yet.
    """
    report = _load_report(work_dir)
    clip = report.get("clip")
    return CandidateComparison(
        media_id=report["media_id"],
        candidates=tuple(
            CandidateRecord(
                candidate_id=c["candidate_id"],
                in_ms=c["in_ms"],
                out_ms=c["out_ms"],
                discovery_path=c["discovery_path"],
                verbal_score=c["verbal_score"],
                visual_score=c["visual_score"],
            )
            for c in report["candidates"]
        ),
        rejected=tuple(
            RejectionRecord(
                in_ms=r["in_ms"],
                out_ms=r["out_ms"],
                discovery_path=r["discovery_path"],
                reject_reason=r["reject_reason"],
            )
            for r in report["rejected"]
        ),
        final_clip_span_ms=(clip["in_ms"], clip["out_ms"]) if clip else None,
    )


def build_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the read-only creative-director agent, scoped to `deps.work_dir`.

    `model` is anything `pydantic_ai.Agent` accepts, including `pydantic_ai.models.test.
    TestModel()` — this module makes no model choice of its own (module docstring). `deps` is
    fixed at construction, not per-call: a fresh `Agent` per run/request is the cost of never
    letting a running conversation's `work_dir` be reassigned mid-session.
    """
    creative_director = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You are a read-only creative-director assistant for one HawEdit repurposing run. "
            "You can inspect what the run produced, explain why it stopped where it did, and "
            "compare the candidates §3 Stage 3 found against the ones it rejected. You cannot "
            "change anything — there is no tool for that, and none will be added to this "
            "conversation."
        ),
    )

    @creative_director.tool
    def inspect_run_tool(ctx: RunContext[Deps]) -> RunInspection:
        """Report what this run reached: completion, which stages were skipped, whether a
        clip was produced and rendered."""
        return inspect_run(ctx.deps.work_dir)

    @creative_director.tool
    def explain_run_state_tool(ctx: RunContext[Deps]) -> RunExplanation:
        """Explain why this run stopped where it did, quoting its own recorded reason."""
        return explain_run_state(ctx.deps.work_dir)

    @creative_director.tool
    def compare_candidates_tool(ctx: RunContext[Deps]) -> CandidateComparison:
        """List every candidate §3 Stage 3 found and every one it rejected, with reasons."""
        return compare_candidates(ctx.deps.work_dir)

    return creative_director
