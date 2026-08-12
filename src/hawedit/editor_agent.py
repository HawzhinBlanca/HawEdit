"""An agent that can propose boundary revisions. It cannot approve or commit one.

Separate from `agent.py`'s read-only `build_agent`: that agent's own system prompt promises "no
tool for that, and none will be added to this conversation" about mutation, and adding a
proposal tool to it would make that promise false. This is a different agent, with a different,
narrower promise: it can check whether a change would be legal, and nothing it does writes
anything without a human running `proposals.commit_boundary_revision` directly.

Also separate from `proposals.py` itself, for the reason `durable_workflow.py` was split from
`durable.py` (D-A3): this module needs `pydantic_ai`, which lives behind the `agentic` extra;
`proposals.py`'s `propose_boundary_revision`/`commit_boundary_revision` need none of it, and
`hawedit-revise --help` should not require an extra it does not use.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from hawedit.agent import Deps
from hawedit.proposals import BoundaryRevisionProposal, propose_boundary_revision

__all__ = ["build_editor_agent"]


def build_editor_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the boundary-revision-proposing agent, scoped to `deps.work_dir`."""
    editor = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You are an editorial assistant for one HawEdit repurposing run. You can propose a "
            "revised boundary (a new start/end span) and see whether it is legal under Kurdish "
            "invariant #2 — the clip may not start or end mid-sentence. You cannot approve or "
            "apply a revision yourself: only a human running `hawedit-revise` directly, with "
            "their name attached, can commit one. Report the validation result plainly; do not "
            "claim a proposal is applied unless a human has told you they ran that command."
        ),
    )

    @editor.tool
    def propose_boundary_revision_tool(
        ctx: RunContext[Deps], final_in_ms: int, final_out_ms: int
    ) -> BoundaryRevisionProposal:
        """Propose a new final_in_ms/final_out_ms for this run's boundary and check whether it
        is legal. Read-only — this does not apply the change."""
        return propose_boundary_revision(ctx.deps.work_dir, final_in_ms, final_out_ms)

    return editor
