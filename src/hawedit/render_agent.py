"""An agent that can propose rendering an already-approved revision. It cannot render one.

A fifth agent, not a tool bolted onto `editor_agent.py` — the same reasoning D-A17 gave for
`diagnostics_agent.py`. `editor_agent.py` carries a stronger, tested guarantee than this
codebase's other agents: `tests/test_prompt_injection.py::
test_the_editor_agents_parameters_are_integers_or_closed_enums` pins every one of its
parameters to an integer or a closed enum, specifically so an injected instruction has no
open string field to smuggle content through. `revision_id` cannot honestly be a closed enum —
naming a revision *is* the input, the same "propose_start_pipeline cannot follow that pattern"
tradeoff `workflow_agent.py` already accepted for `source`/`transcript` (D-A19). Adding it to
`editor_agent.py` would either weaken that module's own tested invariant for every future
reader or make the invariant's own test wrong about what it checks; this module keeps
`editor_agent.py`'s guarantee intact by not touching it at all.

`propose_render_tool` calls `propose_render`, which never touches `ffmpeg` or writes anything —
`commit_render` is the only write in `proposals.py`'s render section, and it is not registered
as a tool on this or any agent, the same "propose, never commit" split every mutating
capability in this codebase has kept since D-A6. `mutating_tool_names()` (`policy.py`) stays
`()`.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from hawedit.agent import Deps
from hawedit.proposals import RenderProposal, propose_render

__all__ = ["build_render_agent"]


def build_render_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the render-proposing agent, scoped to `deps.work_dir`."""
    render = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You can check whether an already-approved revision in this run is ready to "
            "render — the revision must exist, be approved and not yet rendered, still pass "
            "the boundary invariant if it revises a boundary, and ffmpeg must be available. "
            "You cannot render anything yourself: only a human running `hawedit-revise "
            "--render-only` directly, with their name attached, can do that. Report the "
            "validation result plainly; do not claim a revision was rendered unless a human "
            "has told you they ran that command."
        ),
    )

    @render.tool
    def propose_render_tool(ctx: RunContext[Deps], revision_id: str) -> RenderProposal:
        """Check whether `revision_id` is ready to render. Read-only — this does not render
        anything and never touches ffmpeg."""
        return propose_render(ctx.deps.work_dir, revision_id)

    return render
