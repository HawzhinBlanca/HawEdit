"""An agent that can compose a developer report. It cannot file one.

Separate from both `agent.py` (read-only, promises no tool changes anything) and
`editor_agent.py` (proposes editorial revisions only): this agent's promise is narrower still
and about a different subject entirely — not the media, but the *application*.
`export_developer_report` is the architecture record's own tool name for this (line 199),
scoped explicitly outside editorial work: "A separate coding agent or developer can fix it
outside the production editor identity" (line 212). Nothing here fixes anything; it only
composes a structured report a human or a separate developer identity can act on.

`export_developer_report_tool` calls `build_developer_report`, which never touches disk —
`write_developer_report` is the only write in `developer_report.py`, and it is not registered
as a tool on this or any agent. `mutating_tool_names()` (`policy.py`) stays `()`.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from hawedit.agent import Deps
from hawedit.developer_report import DeveloperReport, build_developer_report

__all__ = ["build_diagnostics_agent"]


def build_diagnostics_agent(model: Model | KnownModelName | str, deps: Deps) -> Agent[Deps, str]:
    """Construct the developer-report-composing agent."""
    diagnostics = Agent(
        model,
        deps_type=Deps,
        output_type=str,
        system_prompt=(
            "You help file structured developer reports for HawEdit application defects — "
            "bugs in the pipeline itself, not editorial disagreements about a clip. Every "
            "report needs a summary, at least one reproduction step, the expected and actual "
            "behavior, and the smallest component you suspect. Write in English, about the "
            "system's behavior — never quote Kurdish transcript text verbatim; cite the "
            "media_id or workflow_id instead. You cannot file a report yourself: composing it "
            "is as far as you go, and a human decides whether it gets written down."
        ),
    )

    @diagnostics.tool
    def export_developer_report_tool(
        ctx: RunContext[Deps],
        /,
        summary: str,
        reproduction_steps: tuple[str, ...],
        expected_behavior: str,
        actual_behavior: str,
        suspected_component: str,
        workflow_id: str = "",
        artifact_ids: tuple[str, ...] = (),
    ) -> DeveloperReport:
        """Compose a structured developer report. Read-only — this does not file it."""
        return build_developer_report(
            summary=summary,
            reproduction_steps=reproduction_steps,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            suspected_component=suspected_component,
            workflow_id=workflow_id or None,
            artifact_ids=artifact_ids,
        )

    return diagnostics
