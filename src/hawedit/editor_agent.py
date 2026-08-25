"""An agent that can propose boundary or caption revisions. It cannot approve or commit either.

Separate from `agent.py`'s read-only `build_agent`: that agent's own system prompt promises "no
tool for that, and none will be added to this conversation" about mutation, and adding a
proposal tool to it would make that promise false. This is a different agent, with a different,
narrower promise: it can check whether a change would be legal, and nothing it does writes
anything without a human running `proposals.commit_boundary_revision`/`commit_caption_revision`
directly.

Also separate from `proposals.py` itself, for the reason `durable_workflow.py` was split from
`durable.py` (D-A3): this module needs `pydantic_ai`, which lives behind the `agentic` extra;
`proposals.py`'s propose/commit functions need none of it, and `hawedit-revise --help` should
not require an extra it does not use.

**`caption_style` is typed `Literal["line", "word_highlight"]`, not `str` (D-A12).**
`tests/test_prompt_injection.py`'s control test pins every parameter on this agent to a schema
with no free-form string field an injected instruction could use to smuggle content through the
tool boundary — a plain `str` here would open exactly that field. A `Literal` renders as
`{"type": "string", "enum": [...]}` (checked against the real schema before relying on it), so
pydantic_ai rejects anything outside the two real `CaptionStyle` values before this module's
code ever runs — closed, not free-form, even though the JSON type is still "string".
"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from hawedit.agent import Deps
from hawedit.proposals import (
    BoundaryRevisionProposal,
    CaptionRevisionProposal,
    propose_boundary_revision,
    propose_caption_revision,
)

__all__ = ["build_editor_agent"]


def build_editor_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the revision-proposing agent, scoped to `deps.work_dir`."""
    editor = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You are an editorial assistant for one HawEdit repurposing run. You can propose a "
            "revised boundary (a new start/end span, checked against Kurdish invariant #2 — "
            "the clip may not start or end mid-sentence) or a revised caption style (`line` or "
            "`word_highlight`, checked against Kurdish invariant #4 — captions must actually "
            "fall inside the clip). You cannot approve or apply either revision yourself: only "
            "a human running `hawedit-revise` directly, with their name attached, can commit "
            "one. Report the validation result plainly; do not claim a proposal is applied "
            "unless a human has told you they ran that command."
        ),
    )

    @editor.tool
    def propose_boundary_revision_tool(
        ctx: RunContext[Deps], final_in_ms: int, final_out_ms: int
    ) -> BoundaryRevisionProposal:
        """Propose a new final_in_ms/final_out_ms for this run's boundary and check whether it
        is legal. Read-only — this does not apply the change."""
        return propose_boundary_revision(ctx.deps.work_dir, final_in_ms, final_out_ms)

    @editor.tool
    def propose_caption_revision_tool(
        ctx: RunContext[Deps], caption_style: Literal["line", "word_highlight"]
    ) -> CaptionRevisionProposal:
        """Propose a new caption style for this run's clip and check whether it is legal.
        Read-only — this does not apply the change."""
        return propose_caption_revision(ctx.deps.work_dir, caption_style)

    return editor
