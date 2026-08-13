"""The workflow agent: it can propose starting a run, and structurally it cannot start one.

Same two checks `test_editor_agent.py` holds `editor_agent.py` to.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")

from hawedit.agent import Deps
from hawedit.workflow_agent import build_workflow_agent
from hawedit.workflow_control import StartPipelineProposal

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_AGENT_SRC = ROOT / "src" / "hawedit" / "workflow_agent.py"
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def test_workflow_agent_module_never_calls_commit(tmp_path: Path) -> None:
    """`commit_start_pipeline` must not appear as a name or attribute reference anywhere in
    this module's source."""
    tree = ast.parse(WORKFLOW_AGENT_SRC.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "commit_start_pipeline" not in names


def test_the_workflow_agent_has_exactly_one_tool(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert tool_names == {"propose_start_pipeline_tool"}


def test_the_agent_run_writes_nothing_to_the_work_dir(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    agent.run_sync("propose starting a run", deps=Deps(work_dir=tmp_path))
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before, "proposing a run must not write anything to work_dir"


def test_the_tool_reports_an_invalid_proposal_rather_than_silently_fixing_it(
    tmp_path: Path,
) -> None:
    """TestModel's default string argument is `"a"`, which is not a real file — the agent must
    surface that as an invalid result."""
    from pydantic_ai.models.test import TestModel

    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose starting a run", deps=Deps(work_dir=tmp_path))
    assert '"valid":false' in result.output.replace(" ", "")


def test_the_tool_reports_a_valid_proposal_for_a_real_source(tmp_path: Path) -> None:
    """The control case: a real, existing source must be reported valid, not just the default
    failure case above."""
    from hawedit.workflow_control import propose_start_pipeline

    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    assert proposal.valid is True


def test_the_tool_returns_the_typed_dataclass_not_a_bare_string(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose starting a run", deps=Deps(work_dir=tmp_path))
    assert "source" in result.output
    assert "violation" in result.output


def test_direct_call_still_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.workflow_control import propose_start_pipeline

    proposal = propose_start_pipeline(tmp_path, FIXTURE)
    assert isinstance(proposal, StartPipelineProposal)
