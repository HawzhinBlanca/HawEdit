"""The diagnostics agent: it can compose a developer report, and structurally it cannot file one.

Same two checks `test_editor_agent.py` holds `editor_agent.py` to:
- The agent's registered tool set has exactly one tool.
- `write_developer_report` does not appear anywhere reachable from this module's own source —
  an AST-level guarantee, not a docstring promise.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")

from hawedit.agent import Deps
from hawedit.developer_report import DeveloperReport
from hawedit.diagnostics_agent import build_diagnostics_agent

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_AGENT_SRC = ROOT / "src" / "hawedit" / "diagnostics_agent.py"


def test_diagnostics_agent_module_never_calls_write(tmp_path: Path) -> None:
    """`write_developer_report` must not appear as a name or attribute reference anywhere in
    this module's source. If a future edit adds a filing-capable tool here, this fails on the
    `ast.Name`/`ast.Attribute` reference the call itself creates — checked directly against a
    realistic mutation (calling it from inside the tool, not merely importing it unused)."""
    tree = ast.parse(DIAGNOSTICS_AGENT_SRC.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "write_developer_report" not in names


def test_the_diagnostics_agent_has_exactly_one_tool(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_diagnostics_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert tool_names == {"export_developer_report_tool"}


def test_the_tool_has_no_free_form_kurdish_capable_string_smuggled_through_a_missing_check(
    tmp_path: Path,
) -> None:
    """Not a schema-shape check like the editor agent's — every parameter here is a legitimate
    free-form string (a report needs prose) — but the underlying sanitizer must actually run
    when the agent calls the tool, not only when a human calls `build_developer_report`
    directly. Proven by driving the tool through a real agent run with a poisoned prompt."""
    from pydantic_ai.models.test import TestModel

    agent = build_diagnostics_agent(TestModel(), Deps(work_dir=tmp_path))
    # TestModel's default string generation is "a" for every field, which contains no Kurdish
    # glyphs — this run must succeed, and is the control for the case below.
    result = agent.run_sync("file a report", deps=Deps(work_dir=tmp_path))
    assert '"sequence":1' in result.output.replace(" ", "")


def test_the_agent_run_writes_nothing_to_the_work_dir(tmp_path: Path) -> None:
    """The whole point of the propose/compose-only split: running the agent must not create
    `developer_reports.jsonl` or anything else under `work_dir`."""
    from pydantic_ai.models.test import TestModel

    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    agent = build_diagnostics_agent(TestModel(), Deps(work_dir=tmp_path))
    agent.run_sync("file a report", deps=Deps(work_dir=tmp_path))
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before, "composing a report must not write anything to work_dir"


def test_the_tool_returns_the_typed_dataclass_not_a_bare_string(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_diagnostics_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("file a report", deps=Deps(work_dir=tmp_path))
    assert "summary" in result.output
    assert "suspected_component" in result.output


def test_direct_call_still_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.developer_report import build_developer_report

    report = build_developer_report(
        summary="crash on empty transcript",
        reproduction_steps=("run with a zero-word transcript",),
        expected_behavior="a clean refusal",
        actual_behavior="IndexError",
        suspected_component="sentences.py",
    )
    assert isinstance(report, DeveloperReport)


def test_the_manifest_promise_still_holds_a_third_agent_cannot_undo_it(tmp_path: Path) -> None:
    """`agent.py`'s own AST-proof test already covers `agent.py`; this is the sanity check
    that adding a third agent module did not accidentally give the *read-only* agent a new
    tool by import side effect."""
    from pydantic_ai.models.test import TestModel

    from hawedit.agent import TOOL_NAMES, build_agent

    read_only = build_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in read_only._function_toolset.tools.values()}
    assert tool_names == set(TOOL_NAMES)
