"""An agent that can inspect one specific artifact, compare two, list or preview candidates.

Separate from `agent.py`'s read-only `build_agent`, and for a specific, tested reason rather
than a stylistic one: `tests/test_prompt_injection.py::
test_injected_paths_cannot_move_the_agent_outside_its_work_dir` pins every tool `build_agent`
registers to zero parameters at all — the strongest of this codebase's parameter guarantees.
`inspect_artifact`, `compare_versions`, `list_candidates` and `preview_candidate` all
inherently need at least one caller-supplied identifier or filter (which artifact, which two,
how many, which candidate) — there is no honest zero-parameter version of any of them. Adding
them to `build_agent` would either break that agent's own tested invariant or make the
invariant's test wrong about what it checks; this module holds a different, weaker guarantee
instead of loosening that one.

**The guarantee this module actually holds**: every parameter is an integer, a closed enum, or
a free-form identifier a caller must supply to name what they mean — `artifact_id`,
`artifact_id_a`/`artifact_id_b`, `candidate_id`. The last category is the same accepted
tradeoff `workflow_agent.py` named for `source`/`transcript` (D-A19) and `render_agent.py`
named for `revision_id`: naming a thing *is* the input, so it cannot be a closed enum. The
honest boundary this leaves is narrow — each identifier is only ever used to look up a record
already inside `work_dir` (`revisions/<id>.json`, or a `candidate_id` matched against
`report.json`'s own list), never to construct a path outside it, and a lookup that fails
reports `found=False` rather than raising or otherwise revealing anything about the host.

**None of these four ever raises for a caller-supplied identifier that resolves to nothing.**
`propose_cancel_run`/`propose_resume_run`/`propose_render` already hold this contract for a
`run_id`/`revision_id` that does not exist; `inspect_artifact`/`preview_candidate` extend it to
`artifact_id`/`candidate_id`, and `compare_versions` to `both_found`. An agent tool that raises
on an ordinary "not found" ends the tool call with an exception a model cannot recover from
mid-conversation the way a reported value can — `tests/test_prompt_injection.py`'s
`TestModel`-driven suite (which probes every tool with a placeholder string) is what caught the
first version of this getting it wrong.

Every function this module calls is a plain read: `inspect_artifact`/`compare_versions` live in
`proposals.py` (they need the same revision-record format the render functions read);
`list_candidates`/`preview_candidate` live in `agent.py` (they need only `report.json`). None of
the four writes anything, and none is folded into `agent.py`'s own toolset.
"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from hawedit.agent import CandidateList, CandidatePreview, Deps, list_candidates, preview_candidate
from hawedit.proposals import (
    ArtifactInspection,
    VersionComparison,
    compare_versions,
    inspect_artifact,
)

__all__ = ["build_explorer_agent"]


def build_explorer_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the artifact/candidate-exploring agent, scoped to `deps.work_dir`."""
    explorer = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You are a read-only exploration assistant for one HawEdit repurposing run. You "
            'can inspect one specific artifact in detail — `"original"` for the run\'s own '
            "clip, or a revision_id for a boundary/caption revision — compare two artifacts "
            "side by side, list §3 Stage 3's surviving candidates (optionally filtered to one "
            "discovery path and capped at a limit), and preview one candidate's actual "
            "transcript text. An identifier that names nothing real is reported back to you as "
            "not found, not an error. You cannot change anything — there is no tool for that, "
            "and none will be added to this conversation."
        ),
    )

    @explorer.tool
    def inspect_artifact_tool(ctx: RunContext[Deps], /, artifact_id: str) -> ArtifactInspection:
        """Inspect one artifact in detail: `"original"` for the run's own clip, or a
        revision_id for a specific boundary/caption revision. Read-only."""
        return inspect_artifact(ctx.deps.work_dir, artifact_id)

    @explorer.tool
    def compare_versions_tool(
        ctx: RunContext[Deps], /, artifact_id_a: str, artifact_id_b: str
    ) -> VersionComparison:
        """Compare two artifacts side by side — `"original"` or a revision_id for either — and
        report what actually differs between them. Read-only."""
        return compare_versions(ctx.deps.work_dir, artifact_id_a, artifact_id_b)

    @explorer.tool
    def list_candidates_tool(
        ctx: RunContext[Deps],
        /,
        limit: int = 10,
        discovery_path: Literal["", "verbal", "visual", "both"] = "",
    ) -> CandidateList:
        """List §3 Stage 3's surviving candidates, capped at `limit`, optionally filtered to
        one discovery path (`"verbal"`, `"visual"`, or `"both"`). Lighter than
        compare_candidates — no rejections, no cross-path ranking. Read-only."""
        return list_candidates(
            ctx.deps.work_dir, limit=limit, discovery_path=discovery_path or None
        )

    @explorer.tool
    def preview_candidate_tool(ctx: RunContext[Deps], /, candidate_id: str) -> CandidatePreview:
        """Preview one candidate: its span, score, and the actual transcript text it covers.
        Read-only."""
        return preview_candidate(ctx.deps.work_dir, candidate_id)

    return explorer
