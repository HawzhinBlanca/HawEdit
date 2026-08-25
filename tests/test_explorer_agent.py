"""The explorer and render agents: what they register, and what they structurally cannot do.

Same shape as `test_workflow_agent.py`/`test_editor_agent.py`. Two agents in one file because
they exist for the same reason — each holds a *weaker* parameter guarantee than the agent it was
split from, and the split is the point: `agent.py`'s toolset is zero-parameter and
`editor_agent.py`'s is integer-or-closed-enum, and neither could absorb a tool needing a
free-form identifier without breaking a guarantee its own tests already pin.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")

from hawedit.agent import Deps
from hawedit.explorer_agent import build_explorer_agent
from hawedit.render_agent import build_render_agent

ROOT = Path(__file__).resolve().parents[1]
EXPLORER_SRC = ROOT / "src" / "hawedit" / "explorer_agent.py"
RENDER_SRC = ROOT / "src" / "hawedit" / "render_agent.py"


def _write_minimal_report(work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(
        json.dumps(
            {
                "media_id": "fixture",
                "source": "x.mp4",
                "work_dir": str(work_dir),
                "complete": False,
                "skipped": [],
                "candidates": [],
                "rejected": [],
                "clip": None,
                "render": None,
                "delivery": None,
            }
        ),
        encoding="utf-8",
    )


def _names(src: Path) -> set[str]:
    tree = ast.parse(src.read_text(encoding="utf-8"))
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }


# --- structural: neither module can reach a commit or a render ---------------------------------


def test_explorer_agent_module_never_calls_a_commit_or_render_function() -> None:
    names = _names(EXPLORER_SRC)
    for forbidden in (
        "commit_boundary_revision",
        "commit_caption_revision",
        "commit_render",
        "render_boundary_revision",
        "render_caption_revision",
    ):
        assert forbidden not in names


def test_render_agent_module_never_calls_a_commit_or_render_function() -> None:
    """The one that matters most: this agent is *about* rendering, so the proof that it cannot
    render has to be structural rather than a promise in its prompt."""
    names = _names(RENDER_SRC)
    for forbidden in ("commit_render", "render_boundary_revision", "render_caption_revision"):
        assert forbidden not in names


# --- registration ------------------------------------------------------------------------------


def test_the_explorer_agent_has_exactly_its_four_tools(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_explorer_agent(TestModel(), Deps(work_dir=tmp_path))
    assert {tool.name for tool in agent._function_toolset.tools.values()} == {
        "inspect_artifact_tool",
        "compare_versions_tool",
        "list_candidates_tool",
        "preview_candidate_tool",
    }


def test_the_render_agent_has_exactly_one_tool(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_render_agent(TestModel(), Deps(work_dir=tmp_path))
    assert {tool.name for tool in agent._function_toolset.tools.values()} == {"propose_render_tool"}


# --- the parameter guarantee each of these two actually holds ----------------------------------


def test_every_explorer_parameter_is_an_integer_a_closed_enum_or_a_named_identifier(
    tmp_path: Path,
) -> None:
    """Weaker than `agent.py`'s zero-parameter rule and `editor_agent.py`'s
    integer-or-closed-enum rule — and stated explicitly rather than left as "it takes strings".
    The only free-form strings permitted are the three identifiers naming what to look up; a
    fifth tool growing some other open string field fails here."""
    from pydantic_ai.models.test import TestModel

    allowed_free_form = {"artifact_id", "artifact_id_a", "artifact_id_b", "candidate_id"}
    agent = build_explorer_agent(TestModel(), Deps(work_dir=tmp_path))
    properties: dict[str, dict[str, object]] = {}
    for tool in agent._function_toolset.tools.values():
        properties.update(tool.function_schema.json_schema.get("properties", {}))
    assert properties, "the control case must actually have parameters, or it proves nothing"
    for name, spec in properties.items():
        if spec["type"] == "integer":
            continue
        if spec["type"] == "string" and "enum" in spec:
            continue
        assert name in allowed_free_form, (
            f"{name} is an open string parameter that is not one of this module's named "
            f"lookup identifiers {sorted(allowed_free_form)}: {spec}"
        )


def test_the_render_agents_only_parameter_is_the_revision_identifier(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    agent = build_render_agent(TestModel(), Deps(work_dir=tmp_path))
    properties: dict[str, dict[str, object]] = {}
    for tool in agent._function_toolset.tools.values():
        properties.update(tool.function_schema.json_schema.get("properties", {}))
    assert set(properties) == {"revision_id"}


# --- a real run, driven through TestModel -------------------------------------------------------


def test_the_explorer_agent_writes_nothing_to_the_work_dir(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    _write_minimal_report(tmp_path)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    agent = build_explorer_agent(TestModel(), Deps(work_dir=tmp_path))
    agent.run_sync("look around", deps=Deps(work_dir=tmp_path))
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before


def test_the_render_agent_writes_nothing_to_the_work_dir(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    _write_minimal_report(tmp_path)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    agent = build_render_agent(TestModel(), Deps(work_dir=tmp_path))
    agent.run_sync("can anything be rendered", deps=Deps(work_dir=tmp_path))
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before


def test_a_placeholder_identifier_is_reported_not_raised(tmp_path: Path) -> None:
    """`TestModel` probes every tool with the placeholder string `"a"`. Every tool on both
    agents must survive that — this is the exact failure that caught the first version of these
    tools raising `ValueError`/`FileNotFoundError` on an unresolvable identifier."""
    from pydantic_ai.models.test import TestModel

    _write_minimal_report(tmp_path)
    for builder in (build_explorer_agent, build_render_agent):
        agent = builder(TestModel(), Deps(work_dir=tmp_path))
        result = agent.run_sync("probe every tool", deps=Deps(work_dir=tmp_path))
        assert result.output, f"{builder.__name__} produced no output at all"
