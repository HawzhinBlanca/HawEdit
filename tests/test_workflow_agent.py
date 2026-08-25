"""The workflow agent: it can propose starting a run, and structurally it cannot start one.

Same two checks `test_editor_agent.py` holds `editor_agent.py` to.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")
dbos = pytest.importorskip("dbos")

from hawedit.agent import Deps  # noqa: E402
from hawedit.durable_workflow import configure_dbos  # noqa: E402
from hawedit.workflow_agent import build_workflow_agent  # noqa: E402
from hawedit.workflow_control import (  # noqa: E402
    CancelRunProposal,
    ResumeRunProposal,
    StartPipelineProposal,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_AGENT_SRC = ROOT / "src" / "hawedit" / "workflow_agent.py"
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


@pytest.fixture(scope="module", autouse=True)
def _dbos_instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """`propose_cancel_run_tool`/`propose_resume_run_tool` call `configure_dbos()` — an isolated
    system database, same as `test_workflow_control.py`'s own fixture, so this file never
    touches the real default `.dbos/hawedit.sqlite`."""
    db_path = tmp_path_factory.mktemp("dbos") / "test.sqlite"
    configure_dbos(system_database_url=f"sqlite:///{db_path}")
    yield
    dbos.DBOS.destroy()


def test_workflow_agent_module_never_calls_commit(tmp_path: Path) -> None:
    """None of `commit_start_pipeline`/`commit_cancel_run`/`commit_resume_run` may appear as a
    name or attribute reference anywhere in this module's source."""
    tree = ast.parse(WORKFLOW_AGENT_SRC.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for commit_fn in ("commit_start_pipeline", "commit_cancel_run", "commit_resume_run"):
        assert commit_fn not in names


def test_the_workflow_agent_has_exactly_three_tools(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert tool_names == {
        "propose_start_pipeline_tool",
        "propose_cancel_run_tool",
        "propose_resume_run_tool",
    }


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


# --- propose_cancel_run_tool / propose_resume_run_tool ------------------------------------------


def test_cancel_tool_direct_call_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.workflow_control import propose_cancel_run

    proposal = propose_cancel_run(tmp_path)
    assert isinstance(proposal, CancelRunProposal)
    assert proposal.valid is False


def test_resume_tool_direct_call_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.workflow_control import propose_resume_run

    proposal = propose_resume_run(tmp_path)
    assert isinstance(proposal, ResumeRunProposal)
    assert proposal.valid is False


def test_cancel_tool_reports_no_workflow_for_a_fresh_work_dir(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync(
        "check whether the run here can be cancelled", deps=Deps(work_dir=tmp_path)
    )
    assert "run_id" in result.output
    assert "current_status" in result.output


def test_resume_tool_reports_no_workflow_for_a_fresh_work_dir(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_workflow_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync(
        "check whether the run here can be resumed", deps=Deps(work_dir=tmp_path)
    )
    assert "run_id" in result.output
    assert "current_status" in result.output
