"""An agent that can propose starting a pipeline run. It cannot start one.

Separate from `agent.py` (read-only), `editor_agent.py` (proposes content revisions) and
`diagnostics_agent.py` (composes defect reports): this agent's concern is workflow lifecycle —
whether to run the pipeline at all — which is neither a read, a content edit, nor a bug report.
`start_pipeline` is the architecture record's own tool name for this (line 187).

**A real defect this tool's own name found in the Policy Gate, fixed at the source rather than
worked around.** `policy.py`'s `_FORBIDDEN_NAME_FRAGMENTS` had a bare `"pip"` fragment meant to
catch a tool shelling out to the package installer; `propose_start_pipeline_tool` — the natural
name, matching the Python function it wraps — matched it, since "pipeline" contains "pip". The
comment beside that list calls a false positive "a five-second rename," but this codebase's own
central domain word is not a rare collision worth renaming around every time a workflow tool
gets added — `cancel_or_pause_run`, `resume_run` and anything else pipeline-shaped would hit it
again. Fixed by narrowing the fragment to `"pip_"` (`policy.py`, same trailing-underscore
precision `"commit_"` already uses) rather than renaming this tool away from the architecture
record's own vocabulary — `test_a_real_pip_shaped_tool_name_is_still_refused` and
`test_pipeline_in_a_tool_name_is_not_a_blocked_capability` (`test_policy.py`) pin both halves.

`propose_start_pipeline_tool` calls `propose_start_pipeline`, which never touches `dbos` or
starts anything — `commit_start_pipeline` is the only write in `workflow_control.py`, and it is
not registered as a tool on this or any agent, the same "propose, never commit" split every
mutating capability in this codebase has kept since D-A6. `mutating_tool_names()` (`policy.py`)
stays `()`.

**A real, named tradeoff: `source`/`transcript` are free-form strings, not a closed schema.**
Every other agent tool in this codebase either takes no parameters at all (`agent.py`'s
read-only four) or a closed enum (`caption_style`, D-A12) — deliberately, so an injected
instruction has no open string field to smuggle a path through. `start_pipeline` cannot follow
that pattern: its entire purpose is naming a file to process, so the path *is* the input. The
honest boundary this leaves is a narrow one: `propose_start_pipeline` only ever calls
`Path.is_file()` against `source`/`transcript` — an existence check, not a read — so an injected
instruction could at most learn whether an attacker-chosen path exists on the host, never its
contents, and only by observing which `violation` message comes back. Nothing runs from a
proposal alone: `commit_start_pipeline` shows the real path in its confirmation prompt, and a
human deciding whether "start a pipeline run on a path under someone's home directory that ends
in id_rsa" sounds right is the actual boundary this capability relies on, not the tool schema.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from hawedit.agent import Deps
from hawedit.workflow_control import StartPipelineProposal, propose_start_pipeline

__all__ = ["build_workflow_agent"]


def build_workflow_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the workflow-proposing agent, scoped to `deps.work_dir`."""
    workflow = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You can propose starting a HawEdit pipeline run on a source file and check "
            "whether it is safe to start — the source must exist, and the run directory must "
            "not already hold a completed run you would silently overwrite. You cannot start a "
            "run yourself: only a human running the commit step directly, with their name and "
            "a stated reason attached, can do that. Report the validation result plainly; do "
            "not claim a run started unless a human has told you they committed it."
        ),
    )

    @workflow.tool
    def propose_start_pipeline_tool(
        ctx: RunContext[Deps],
        /,
        source: str,
        media_id: str = "",
        transcript: str = "",
    ) -> StartPipelineProposal:
        """Propose starting a pipeline run on `source` into this run's work_dir, and check
        whether it is safe. Read-only — this does not start anything."""
        return propose_start_pipeline(
            ctx.deps.work_dir,
            Path(source),
            media_id=media_id or None,
            transcript=Path(transcript) if transcript else None,
        )

    return workflow
